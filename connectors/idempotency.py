"""
Idempotency Engine for Omnia Module 26:
External Integration & Connector Gateway

Prevents duplicate external side effects (e.g., duplicate payments, message resends, resource creation).
Maintains idempotency records across distributed executions.
"""

import time
import json
import hashlib
import logging
from typing import Optional, Tuple, Any, Dict

from connectors.models import IdempotencyRecord, IdempotencyStatus, ConnectorResponse, VerificationStatus

logger = logging.getLogger("Omnia.Connectors.Idempotency")


class IdempotencyManager:
    """Coordinates deterministic operation keys and cached responses."""

    def __init__(self, persistence=None):
        self.persistence = persistence
        self._in_memory_records: Dict[str, IdempotencyRecord] = {}

    @staticmethod
    def compute_request_hash(operation_id: str, parameters: Dict[str, Any], body: Any) -> str:
        """Computes deterministic SHA-256 fingerprint of request parameters and body."""
        serialized = json.dumps({
            "op": operation_id,
            "params": sorted(parameters.items()) if parameters else [],
            "body": body if isinstance(body, (str, int, float, bool, type(None))) else str(body)
        }, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def check_or_reserve(
        self,
        idempotency_key: str,
        operation_id: str,
        instance_id: str,
        request_hash: str,
        task_id: Optional[str] = None,
        ttl_sec: float = 86400.0
    ) -> Tuple[bool, Optional[ConnectorResponse], str]:
        """
        Checks if an idempotency key exists:
        - If COMPLETED: returns (False, cached_response, "ALREADY_COMPLETED")
        - If IN_FLIGHT: returns (False, None, "IN_FLIGHT_CONFLICT")
        - If new: reserves slot with IN_FLIGHT status, returns (True, None, "RESERVED")
        """
        now = time.time()

        # Check DB first if persistence available, otherwise memory
        rec = None
        if self.persistence:
            rec = self.persistence.get_idempotency_record(idempotency_key)
        else:
            rec = self._in_memory_records.get(idempotency_key)

        if rec:
            # Check expiration
            if now >= rec.expires_at:
                logger.info(f"Idempotency record '{idempotency_key}' expired. Permitting new reservation.")
            else:
                if rec.status == IdempotencyStatus.COMPLETED and rec.response_payload:
                    try:
                        data = json.loads(rec.response_payload)
                        cached_resp = ConnectorResponse(
                            request_id=data.get("request_id", ""),
                            operation_id=operation_id,
                            status_code=data.get("status_code", 200),
                            headers=data.get("headers", {}),
                            body=data.get("body"),
                            verification_status=VerificationStatus(data.get("verification_status", "VERIFIED")),
                            cached_idempotent=True
                        )
                        return False, cached_resp, "ALREADY_COMPLETED"
                    except Exception as e:
                        logger.error(f"Failed to deserialize cached idempotency response: {e}")

                elif rec.status == IdempotencyStatus.IN_FLIGHT:
                    return False, None, "IN_FLIGHT_CONFLICT"

        # Reserve new slot
        new_record = IdempotencyRecord(
            idempotency_key=idempotency_key,
            operation_id=operation_id,
            instance_id=instance_id,
            task_id=task_id,
            status=IdempotencyStatus.IN_FLIGHT,
            request_hash=request_hash,
            created_at=now,
            expires_at=now + ttl_sec
        )

        if self.persistence:
            self.persistence.save_idempotency_record(new_record)
        self._in_memory_records[idempotency_key] = new_record

        return True, None, "RESERVED"

    def record_completion(
        self,
        idempotency_key: str,
        response: ConnectorResponse,
        status: IdempotencyStatus = IdempotencyStatus.COMPLETED
    ):
        """Saves execution outcome and payload against idempotency token."""
        rec = self._in_memory_records.get(idempotency_key)
        now = time.time()

        payload_json = json.dumps({
            "request_id": response.request_id,
            "status_code": response.status_code,
            "headers": response.headers,
            "body": response.body,
            "verification_status": response.verification_status.value
        })

        if rec:
            rec.status = status
            rec.response_payload = payload_json

        if self.persistence:
            updated_rec = IdempotencyRecord(
                idempotency_key=idempotency_key,
                operation_id=response.operation_id,
                instance_id="",
                task_id=None,
                status=status,
                request_hash=rec.request_hash if rec else "",
                response_payload=payload_json,
                created_at=rec.created_at if rec else now,
                expires_at=rec.expires_at if rec else now + 86400.0
            )
            self.persistence.save_idempotency_record(updated_rec)
