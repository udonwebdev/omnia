import time
import uuid
import logging
from typing import Dict, Optional, Tuple, List

from coordination.models import (
    OwnershipClaim,
    OwnershipState,
    DistributedLock,
    LockState
)

logger = logging.getLogger("Omnia.Coordination.Ownership")

class OwnershipCoordinator:
    """Manages distributed ownership claims over tasks, missions, and distributed locks."""

    def __init__(self, local_node_id: str):
        self.local_node_id = local_node_id
        self._claims: Dict[str, OwnershipClaim] = {}   # (subject_type, subject_id) -> claim
        self._locks: Dict[str, DistributedLock] = {}    # resource_id -> lock

    def claim_ownership(
        self,
        subject_type: str,
        subject_id: str,
        owner_node_id: str,
        epoch: int,
        lease_sec: float = 30.0
    ) -> Tuple[bool, Optional[OwnershipClaim], str]:
        """Claims exclusive distributed ownership over a task or mission.
        Invariant: If another node already owns the subject with an active lease, claim is rejected.
        """
        key = f"{subject_type}:{subject_id}"
        now = time.time()
        existing = self._claims.get(key)

        if existing and existing.state == OwnershipState.ACTIVE and not existing.is_expired(now):
            if existing.owner_node_id != owner_node_id:
                logger.warning(f"Ownership conflict: {owner_node_id} attempted to claim {key} already owned by {existing.owner_node_id}.")
                return False, existing, f"CLAIM_CONFLICT: Already owned by node '{existing.owner_node_id}'."
            else:
                # Owner renewing active claim
                existing.expires_at = now + lease_sec
                return True, existing, "Ownership lease renewed."

        # Issue new claim
        fencing_token = f"claim_{epoch}_{uuid.uuid4().hex[:6]}"
        claim = OwnershipClaim(
            claim_id=f"own_{uuid.uuid4().hex[:8]}",
            subject_type=subject_type,
            subject_id=subject_id,
            owner_node_id=owner_node_id,
            epoch=epoch,
            issued_at=now,
            expires_at=now + lease_sec,
            fencing_token=fencing_token,
            state=OwnershipState.ACTIVE
        )
        self._claims[key] = claim
        logger.info(f"Ownership claimed: Node '{owner_node_id}' owns {key} (Epoch {epoch}, Token {fencing_token}).")
        return True, claim, "Ownership claim granted."

    def release_ownership(self, subject_type: str, subject_id: str, owner_node_id: str) -> bool:
        """Releases active ownership claim."""
        key = f"{subject_type}:{subject_id}"
        claim = self._claims.get(key)
        if claim and claim.owner_node_id == owner_node_id and claim.state == OwnershipState.ACTIVE:
            claim.state = OwnershipState.RELEASED
            del self._claims[key]
            logger.info(f"Ownership released: {key} by {owner_node_id}.")
            return True
        return False

    def get_owner(self, subject_type: str, subject_id: str) -> Optional[str]:
        """Returns the current active owner node ID, or None if unclaimed/expired."""
        key = f"{subject_type}:{subject_id}"
        claim = self._claims.get(key)
        now = time.time()
        if claim and claim.state == OwnershipState.ACTIVE and not claim.is_expired(now):
            return claim.owner_node_id
        return None

    def acquire_distributed_lock(
        self,
        resource_id: str,
        owner_node_id: str,
        epoch: int,
        lease_sec: float = 15.0
    ) -> Tuple[bool, Optional[DistributedLock], str]:
        """Acquires a lease-bound distributed lock with fencing token."""
        now = time.time()
        existing = self._locks.get(resource_id)

        if existing and existing.state == LockState.ACQUIRED and not existing.is_expired(now):
            if existing.owner_node_id != owner_node_id:
                return False, existing, f"LOCK_BUSY: Resource '{resource_id}' locked by '{existing.owner_node_id}'."
            else:
                existing.expires_at = now + lease_sec
                return True, existing, "Lock lease renewed."

        fencing_token = f"lock_{epoch}_{uuid.uuid4().hex[:6]}"
        lock = DistributedLock(
            lock_id=f"dlock_{uuid.uuid4().hex[:8]}",
            resource_id=resource_id,
            owner_node_id=owner_node_id,
            epoch=epoch,
            fencing_token=fencing_token,
            created_at=now,
            expires_at=now + lease_sec,
            state=LockState.ACQUIRED
        )
        self._locks[resource_id] = lock
        logger.info(f"Distributed lock acquired: Node '{owner_node_id}' locked '{resource_id}' (Token {fencing_token}).")
        return True, lock, "Distributed lock acquired."

    def release_distributed_lock(self, resource_id: str, owner_node_id: str) -> bool:
        """Releases distributed lock."""
        lock = self._locks.get(resource_id)
        if lock and lock.owner_node_id == owner_node_id and lock.state == LockState.ACQUIRED:
            lock.state = LockState.RELEASED
            del self._locks[resource_id]
            logger.info(f"Distributed lock released: '{resource_id}' by '{owner_node_id}'.")
            return True
        return False

    def get_claim(self, subject_type: str, subject_id: str) -> Optional[OwnershipClaim]:
        """Returns claim object for subject."""
        key = f"{subject_type}:{subject_id}"
        return self._claims.get(key)

    def get_lock(self, resource_id: str) -> Optional[DistributedLock]:
        """Returns lock object for resource."""
        return self._locks.get(resource_id)

    def scan_and_reap_expired_claims(self) -> List[OwnershipClaim]:
        """Reaps expired claims and returns them for failover reconciliation."""
        now = time.time()
        expired = []
        for key, claim in list(self._claims.items()):
            if claim.state == OwnershipState.ACTIVE and claim.is_expired(now):
                claim.state = OwnershipState.EXPIRED
                expired.append(claim)
                del self._claims[key]
                logger.warning(f"Ownership claim expired for {key} (Owner: {claim.owner_node_id}). Reclaimed.")
        return expired

    def reap_expired_claims(self) -> List[OwnershipClaim]:
        return self.scan_and_reap_expired_claims()

    def reap_expired_locks(self) -> List[DistributedLock]:
        """Reaps expired locks."""
        now = time.time()
        expired = []
        for res_id, lock in list(self._locks.items()):
            if lock.state == LockState.ACQUIRED and lock.is_expired(now):
                lock.state = LockState.EXPIRED
                expired.append(lock)
                del self._locks[res_id]
                logger.warning(f"Distributed lock expired for {res_id} (Owner: {lock.owner_node_id}). Reclaimed.")
        return expired

    def get_active_claims(self) -> List[OwnershipClaim]:
        now = time.time()
        return [c for c in self._claims.values() if c.state == OwnershipState.ACTIVE and not c.is_expired(now)]

    def get_active_locks(self) -> List[DistributedLock]:
        now = time.time()
        return [l for l in self._locks.values() if l.state == LockState.ACQUIRED and not l.is_expired(now)]
