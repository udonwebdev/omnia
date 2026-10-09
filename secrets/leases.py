import uuid
import time
import logging
from typing import Dict, Any, Optional, List
from secrets.models import SecretLease, SecretAccessRequest
from secrets.persistence import SecretPersistence

logger = logging.getLogger("Omnia.Secrets.Leases")

class LeaseManager:
    """Manages short-lived, purpose-bound access leases for credentials."""

    def __init__(self, persistence: Optional[SecretPersistence] = None):
        self.persistence = persistence or SecretPersistence()

    def issue_lease(
        self,
        request: SecretAccessRequest,
        secret_id: str,
        version: int,
        ttl_seconds: float = 300.0
    ) -> SecretLease:
        now = time.time()
        lease_id = f"lease_{uuid.uuid4().hex[:12]}"
        lease = SecretLease(
            lease_id=lease_id,
            secret_id=secret_id,
            version=version,
            requester=request.requester_identity,
            purpose=request.purpose,
            capability=request.capability,
            scope=request.scope,
            node_id=request.node_id,
            issued_at=now,
            expires_at=now + ttl_seconds,
            revoked_at=None,
            status="ACTIVE"
        )
        self.persistence.save_lease(lease)
        logger.info(f"Secret lease issued: '{lease_id}' for '{secret_id}' v{version} (TTL: {ttl_seconds}s).")
        return lease

    def get_lease(self, lease_id: str) -> Optional[SecretLease]:
        return self.persistence.get_lease(lease_id)

    def validate_lease(self, lease_id: str) -> bool:
        lease = self.get_lease(lease_id)
        if not lease:
            return False
        return lease.is_valid

    def revoke_lease(self, lease_id: str) -> bool:
        ok = self.persistence.revoke_lease(lease_id)
        if ok:
            logger.info(f"Secret lease revoked: '{lease_id}'.")
        return ok

    def revoke_all_leases_for_secret(self, secret_id: str) -> int:
        """Revokes all active leases for a secret (e.g. upon rotation, revocation, or compromise)."""
        active_leases = self.persistence.list_active_leases(secret_id=secret_id)
        revoked_count = 0
        for l in active_leases:
            if self.persistence.revoke_lease(l.lease_id):
                revoked_count += 1
        logger.info(f"Revoked {revoked_count} active leases for secret '{secret_id}'.")
        return revoked_count
