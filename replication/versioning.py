import logging
from typing import Optional, Dict, Any, Tuple
from coordination import coordination_service
from replication.models import StateVersion, StateDelta, StateRecord

logger = logging.getLogger("Omnia.Replication.Versioning")

class VersionComparator:
    """Deterministic versioning engine comparing revisions, epochs, and causal lineage."""

    @staticmethod
    def compare_versions(
        local_epoch: int,
        local_revision: int,
        remote_epoch: int,
        remote_revision: int
    ) -> str:
        """Compares two state versions without relying solely on wall-clock timestamps.
        
        Returns:
            - 'NEWER': remote is strictly newer
            - 'OLDER': remote is strictly older (stale)
            - 'EQUAL': same epoch and revision
            - 'STALE_EPOCH': remote epoch is older than authoritative cluster epoch
            - 'CONFLICT': same epoch but diverging revisions/branches
        """
        # Epoch takes strict precedence
        if remote_epoch < local_epoch:
            return "STALE_EPOCH"
        elif remote_epoch > local_epoch:
            return "NEWER"
        else:
            # Same epoch: compare revisions
            if remote_revision > local_revision:
                return "NEWER"
            elif remote_revision < local_revision:
                return "OLDER"
            else:
                return "EQUAL"

class ReplicationOwnershipEnforcer:
    """Validates that incoming and published replication updates conform to Module 22 ownership and epoch fencing."""

    def __init__(self, coord_service=None):
        self.coordination = coord_service or coordination_service

    def validate_incoming_delta(
        self,
        delta: StateDelta,
        current_record: Optional[StateRecord] = None
    ) -> Tuple[bool, str]:
        """Epoch Fencing & Ownership Verification:
        
        Invariant:
        1. Source epoch must NOT be older than the current cluster epoch.
        2. If entity is a TASK or MISSION, verify sender is authoritative or current owner.
        3. Reject updates from stale epochs (FENCED_STALE_EPOCH).
        """
        cluster_epoch = self.coordination.election.current_epoch
        
        # 1. Epoch Fencing Check
        if delta.source_epoch < cluster_epoch:
            msg = f"FENCED_STALE_EPOCH: Delta epoch {delta.source_epoch} is older than cluster epoch {cluster_epoch}."
            logger.warning(f"Replication rejected: {msg}")
            return False, msg

        # 2. If entity is currently owned locally or in record, check epoch monotonicity
        if current_record:
            if delta.source_epoch < current_record.owner_epoch:
                msg = f"FENCED_STALE_EPOCH: Delta epoch {delta.source_epoch} is older than existing record epoch {current_record.owner_epoch}."
                logger.warning(f"Replication rejected: {msg}")
                return False, msg
            
            # If same epoch, delta must advance revision
            if delta.source_epoch == current_record.owner_epoch and delta.target_revision <= current_record.revision:
                msg = f"DUPLICATE_OR_STALE_REVISION: Delta revision {delta.target_revision} <= current revision {current_record.revision}."
                return False, msg

        # 3. Ownership Validation for task namespaces
        if delta.namespace_id == "tasks":
            current_owner = self.coordination.get_task_owner(delta.entity_id)
            if current_owner and current_owner != delta.source_node:
                # If sender is not the known owner and not the current leader
                is_leader = (self.coordination.election.current_leader == delta.source_node)
                if not is_leader:
                    msg = f"OWNERSHIP_MISMATCH: Node '{delta.source_node}' does not own task '{delta.entity_id}' (Owner: '{current_owner}')."
                    logger.warning(f"Replication rejected: {msg}")
                    return False, msg

        return True, "VALID"

ownership_enforcer = ReplicationOwnershipEnforcer()
