"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Security Telemetry Normalizer - normalizer.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from secops.models import EventCategory, EventResult, SecurityEvent, SecuritySeverity
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.Normalizer")


class SecurityEventNormalizer:
    """
    Normalizes heterogeneous raw security events into the unified OMNIA security event model.
    Enforces payload integrity hashing, validation, and safe quarantine of malformed telemetry.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def normalize_event(
        self,
        source_id: str,
        provider: str,
        raw_payload: Dict[str, Any],
        environment: str = "PRODUCTION",
    ) -> SecurityEvent:
        # Calculate raw payload hash for cryptographic non-repudiation
        raw_bytes = json.dumps(raw_payload, sort_keys=True).encode("utf-8")
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()

        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Extract timestamp with fallback to current ingestion timestamp
        raw_ts = raw_payload.get("timestamp") or raw_payload.get("event_time") or now_iso

        # Extract Category and Action
        event_type = str(raw_payload.get("event_type", "UNKNOWN_EVENT"))
        category_str = str(raw_payload.get("category", "WORKLOAD")).upper()
        try:
            category = EventCategory(category_str)
        except ValueError:
            category = EventCategory.WORKLOAD

        action = str(raw_payload.get("action", "EXECUTE"))
        result_str = str(raw_payload.get("result", "SUCCESS")).upper()
        try:
            result = EventResult(result_str)
        except ValueError:
            result = EventResult.SUCCESS

        severity_str = str(raw_payload.get("severity", "INFO")).upper()
        try:
            severity = SecuritySeverity(severity_str)
        except ValueError:
            severity = SecuritySeverity.INFO

        # Entity attribution
        actor_id = raw_payload.get("actor") or raw_payload.get("user") or raw_payload.get("principal")
        target_id = raw_payload.get("target") or raw_payload.get("resource")
        asset_id = raw_payload.get("asset_id") or raw_payload.get("host") or raw_payload.get("service")

        # Network endpoints
        src_ip = raw_payload.get("src_ip") or raw_payload.get("source_address")
        dst_ip = raw_payload.get("dst_ip") or raw_payload.get("destination_address")

        confidence = float(raw_payload.get("confidence", 1.0))
        metadata = raw_payload.get("metadata", {})

        # Validation & Quarantine Check
        is_quarantined = False
        quarantine_reason = None
        if not event_type or event_type == "UNKNOWN_EVENT":
            is_quarantined = True
            quarantine_reason = "Missing or unclassifiable event_type"

        event = SecurityEvent(
            event_id=event_id,
            source_id=source_id,
            provider=provider,
            event_type=event_type,
            event_category=category,
            event_timestamp=raw_ts,
            ingestion_timestamp=now_iso,
            environment=environment,
            asset_id=asset_id,
            actor_id=actor_id,
            target_id=target_id,
            source_address=src_ip,
            destination_address=dst_ip,
            action=action,
            result=result,
            severity=severity,
            confidence=confidence,
            metadata=metadata,
            correlation_ids=[],
            raw_payload_hash=raw_hash,
            quarantine_reason=quarantine_reason,
            is_quarantined=is_quarantined,
        )

        self.repo.save_event(event)
        return event
