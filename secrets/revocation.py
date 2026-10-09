import time
import logging
from typing import Optional, Tuple
from secrets.models import SecretRecord, SecretStatus
from secrets.persistence import SecretPersistence
from secrets.leases import LeaseManager

logger = logging.getLogger("Omnia.Secrets.Revocation")

class RevocationEngine:
    """Orchestrates immediate credential revocation and emergency compromise handling."""

    def __init__(self, persistence: Optional[SecretPersistence] = None, lease_mgr: Optional[LeaseManager] = None):
        self.persistence = persistence or SecretPersistence()
        self.lease_mgr = lease_mgr or LeaseManager(self.persistence)

    def revoke_credential(self, secret_id: str, reason: str = "Operator revoked") -> Tuple[bool, str]:
        meta = self.persistence.get_secret_metadata(secret_id)
        if not meta:
            return False, f"Secret '{secret_id}' not found."

        now = time.time()
        meta.status = SecretStatus.REVOKED
        meta.updated_at = now
        self.persistence.save_secret_metadata(meta)

        # Update active version
        ver_record = self.persistence.get_secret_version(secret_id, meta.version)
        if ver_record:
            ver_record.status = SecretStatus.REVOKED
            ver_record.retired_at = now
            self.persistence.save_secret_version(ver_record)

        # Invalidate all issued leases
        revoked_leases = self.lease_mgr.revoke_all_leases_for_secret(secret_id)

        msg = f"REVOKED: Secret '{secret_id}' v{meta.version} revoked. ({revoked_leases} leases invalidated). Reason: {reason}"
        logger.warning(msg)
        return True, msg

    def mark_compromised(self, secret_id: str, incident_id: str, details: str = "") -> Tuple[bool, str]:
        """Emergency compromise response: marks COMPROMISED, blocks access, kills leases."""
        meta = self.persistence.get_secret_metadata(secret_id)
        if not meta:
            return False, f"Secret '{secret_id}' not found."

        now = time.time()
        meta.status = SecretStatus.COMPROMISED
        meta.updated_at = now
        self.persistence.save_secret_metadata(meta)

        ver_record = self.persistence.get_secret_version(secret_id, meta.version)
        if ver_record:
            ver_record.status = SecretStatus.COMPROMISED
            ver_record.retired_at = now
            self.persistence.save_secret_version(ver_record)

        # Invalidate all leases immediately
        revoked_leases = self.lease_mgr.revoke_all_leases_for_secret(secret_id)

        msg = f"COMPROMISED_ALERT: Secret '{secret_id}' marked COMPROMISED under incident '{incident_id}'! ({revoked_leases} leases killed)."
        logger.critical(msg)
        return True, msg
