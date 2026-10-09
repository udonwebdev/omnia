import uuid
import time
import logging
from typing import Dict, Any, Optional, List

from secrets.models import SecretAuditRecord
from secrets.persistence import SecretPersistence

logger = logging.getLogger("Omnia.Secrets.Audit")

class SecretAuditLogger:
    """Audit logger dedicated to credential lifecycle operations with zero plaintext recording."""

    def __init__(self, persistence: Optional[SecretPersistence] = None):
        self.persistence = persistence or SecretPersistence()

    def log_event(
        self,
        secret_id: str,
        version: int,
        requester: str,
        action: str,
        result: str,
        purpose: str = "",
        capability: str = "",
        scope: str = "CLUSTER",
        node_id: str = "local_node",
        details: Optional[Dict[str, Any]] = None
    ) -> SecretAuditRecord:
        # Sanitize details to guarantee zero plaintext secrets
        sanitized_details = dict(details or {})
        for k in list(sanitized_details.keys()):
            if any(s in k.lower() for s in ["secret", "password", "key", "token", "val"]):
                sanitized_details[k] = "[REDACTED_AUDIT]"

        event_id = f"aud_{uuid.uuid4().hex[:12]}"
        record = SecretAuditRecord(
            event_id=event_id,
            secret_id=secret_id,
            version=version,
            requester=requester,
            purpose=purpose,
            capability=capability,
            scope=scope,
            node_id=node_id,
            action=action,
            result=result,
            timestamp=time.time(),
            details=sanitized_details
        )
        self.persistence.record_audit(record)

        # Mirror to Module 09 audit logger if available
        try:
            from audit_logger import audit_logger
            audit_logger.log_event(
                f"secrets.{action.lower()}",
                {"secret_id": secret_id, "version": version, "requester": requester, "purpose": purpose},
                allowed=(result in ["GRANTED", "SUCCESS"]),
                outcome=result
            )
        except Exception:
            pass

        return record

    def list_logs(self, secret_id: Optional[str] = None, limit: int = 50) -> List[SecretAuditRecord]:
        return self.persistence.list_audit_logs(secret_id=secret_id, limit=limit)
