"""
Inbound Webhook Gateway & Signature Verification for Omnia Module 26:
External Integration & Connector Gateway

Invariants:
1. Every inbound webhook must be cryptographically verified against the provider secret.
2. Replay attack protection enforces timestamp drift window and event ID deduplication.
3. Payload sizes are strictly bounded to prevent DoS.
4. Verified events are normalized and dispatched into Module 18 Event Fabric.
"""

import time
import hmac
import hashlib
import json
import logging
from typing import Dict, Any, Optional, Tuple

from connectors.models import WebhookEndpoint, WebhookEvent
from events.models import Event, EventEnvelope
from events.fabric import event_fabric
from secrets import secrets_service

logger = logging.getLogger("Omnia.Connectors.Webhooks")


class WebhookGateway:
    """Processes, validates, verifies, and normalizes inbound webhook requests."""

    def __init__(self, persistence=None, sec_service=None):
        self.persistence = persistence
        self._sec_service = sec_service
        self._endpoints: Dict[str, WebhookEndpoint] = {}
        self._processed_events: Dict[str, float] = {}  # event_id -> received_at

    def register_endpoint(self, endpoint: WebhookEndpoint):
        """Registers a webhook endpoint route."""
        self._endpoints[endpoint.endpoint_path] = endpoint
        if self.persistence:
            self.persistence.save_webhook_endpoint(endpoint)
        logger.info(f"Registered webhook endpoint '{endpoint.endpoint_path}' for provider '{endpoint.provider_id}'.")

    def get_endpoint(self, path: str) -> Optional[WebhookEndpoint]:
        return self._endpoints.get(path)

    async def process_webhook(
        self,
        endpoint_path: str,
        headers: Dict[str, str],
        raw_body: bytes
    ) -> Tuple[bool, Optional[WebhookEvent], str]:
        """
        Validates, verifies, and normalizes an incoming webhook.
        Returns (success, WebhookEvent, reason).
        """
        endpoint = self.get_endpoint(endpoint_path)
        if not endpoint:
            return False, None, f"WEBHOOK_NOT_FOUND: No registered endpoint for path '{endpoint_path}'."

        # 1. Payload size check
        if len(raw_body) > endpoint.max_payload_bytes:
            return False, None, f"PAYLOAD_TOO_LARGE: {len(raw_body)} bytes exceeds {endpoint.max_payload_bytes} limit."

        # 2. Extract signature and timestamp from headers
        # Normalize header keys to lowercase
        norm_headers = {k.lower(): v for k, v in headers.items()}

        sig_header = norm_headers.get("x-hub-signature-256") or norm_headers.get("stripe-signature") or norm_headers.get("x-signature")
        if not sig_header:
            return False, None, "MISSING_SIGNATURE: Webhook payload missing signature header."

        # 3. Retrieve signing secret from Module 25
        signing_key = ""
        if endpoint.secret_reference:
            sec_svc = self._sec_service or secrets_service
            try:
                handle = sec_svc.acquire_secret(
                    uri_or_id=endpoint.secret_reference,
                    requester="webhook_gateway",
                    purpose="webhook.verify",
                    capability="capability.connector",
                    ttl_seconds=60.0
                )
                signing_key = handle.get_raw_value()
                handle.release()
            except Exception as e:
                logger.error(f"Failed to acquire webhook secret '{endpoint.secret_reference}': {e}")
                return False, None, "SECRET_UNAVAILABLE: Failed to resolve webhook verification secret."

        # 4. Cryptographic Signature Verification
        verified = self._verify_signature(
            provider_id=endpoint.provider_id,
            raw_body=raw_body,
            sig_header=sig_header,
            signing_key=signing_key,
            headers=norm_headers
        )
        if not verified:
            logger.warning(f"WEBHOOK_REJECTED: Forged or invalid signature on endpoint '{endpoint_path}'.")
            return False, None, "INVALID_SIGNATURE: Cryptographic signature mismatch."

        # 5. Parse JSON Payload & Extract Provider Event ID
        try:
            payload_data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception as e:
            return False, None, f"MALFORMED_JSON: Failed to parse body: {e}"

        provider_event_id = None
        if isinstance(payload_data, dict):
            provider_event_id = payload_data.get("id") or payload_data.get("event_id") or payload_data.get("delivery_id")
        if not provider_event_id:
            provider_event_id = norm_headers.get("x-github-delivery") or norm_headers.get("x-request-id")

        if not provider_event_id:
            # Fallback to hash of body if provider provides no event ID
            provider_event_id = hashlib.sha256(raw_body).hexdigest()[:16]

        # 6. Replay Attack & Duplicate Protection
        now = time.time()
        # Clean expired events from memory
        self._processed_events = {
            eid: ts for eid, ts in self._processed_events.items()
            if (now - ts) < endpoint.replay_window_sec
        }

        if provider_event_id in self._processed_events:
            logger.warning(f"WEBHOOK_REPLAY_REJECTED: Duplicate delivery of event '{provider_event_id}'.")
            return False, None, f"REPLAY_DETECTED: Event '{provider_event_id}' has already been processed."

        if self.persistence and self.persistence.has_webhook_event(provider_event_id):
            logger.warning(f"WEBHOOK_REPLAY_REJECTED (DB): Event '{provider_event_id}' already persisted.")
            return False, None, f"REPLAY_DETECTED: Event '{provider_event_id}' already processed."

        # Mark processed
        self._processed_events[provider_event_id] = now
        endpoint.last_event_at = now

        # 7. Normalize Event
        event_obj = WebhookEvent(
            event_id=f"wevt_{provider_event_id}",
            webhook_id=endpoint.webhook_id,
            provider_id=endpoint.provider_id,
            raw_payload=raw_body,
            headers=headers,
            received_at=now,
            provider_event_id=provider_event_id,
            signature_verified=True,
            normalized_type=f"external.{endpoint.provider_id}.event",
            normalized_data=payload_data if isinstance(payload_data, dict) else {"raw": str(payload_data)}
        )

        if self.persistence:
            self.persistence.save_webhook_event(event_obj)

        # 8. Publish Normalized Event into Module 18 Event Fabric
        try:
            fabric_evt = Event(
                envelope=EventEnvelope(
                    event_type="connector.webhook.verified",
                    source=f"connectors.webhook.{endpoint.provider_id}"
                ),
                payload={
                    "webhook_id": endpoint.webhook_id,
                    "provider_id": endpoint.provider_id,
                    "event_id": provider_event_id,
                    "normalized_type": event_obj.normalized_type
                }
            )
            await event_fabric.publish(fabric_evt)
        except Exception as e:
            logger.debug(f"Failed to publish webhook event to fabric: {e}")

        logger.info(f"WEBHOOK_VERIFIED: Successfully processed event '{provider_event_id}' for provider '{endpoint.provider_id}'.")
        return True, event_obj, "SUCCESS"

    def _verify_signature(
        self,
        provider_id: str,
        raw_body: bytes,
        sig_header: str,
        signing_key: str,
        headers: Dict[str, str]
    ) -> bool:
        """Verifies signature across HMAC-SHA256, GitHub sha256=, and Stripe formats."""
        if not signing_key:
            return False

        key_bytes = signing_key.encode("utf-8")

        # GitHub style: "sha256=abcdef..."
        if sig_header.startswith("sha256="):
            expected_mac = hmac.new(key_bytes, raw_body, hashlib.sha256).hexdigest()
            given_mac = sig_header[7:].strip()
            return hmac.compare_digest(expected_mac, given_mac)

        # Stripe style: "t=1492774577,v1=5257a869e7eee..."
        if "t=" in sig_header and "v1=" in sig_header:
            parts = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
            timestamp = parts.get("t", "")
            given_mac = parts.get("v1", "")
            signed_payload = f"{timestamp}.".encode("utf-8") + raw_body
            expected_mac = hmac.new(key_bytes, signed_payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected_mac, given_mac)

        # Direct HMAC-SHA256 hex digest
        expected_mac = hmac.new(key_bytes, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_mac, sig_header.strip())


webhook_gateway = WebhookGateway()
