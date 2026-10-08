import logging
from typing import Dict, List, Optional, Tuple, Any
from replication.models import StateRecord, Snapshot, ConflictType, ConflictResolutionStrategy
from replication.integrity import integrity_verifier
from replication.conflicts import conflict_resolver
from coordination import coordination_service

logger = logging.getLogger("Omnia.Replication.Reconciliation")

class StateReconciliationEngine:
    """Detects silent state divergence across peers and computes safe convergence paths."""

    def __init__(self, coord_service=None):
        self.coordination = coord_service or coordination_service

    def detect_divergence(
        self,
        namespace_id: str,
        local_records: List[StateRecord],
        remote_records: List[StateRecord]
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Compares local vs remote state partition hierarchically:
        1. Compare namespace-level root hash
        2. If divergent, pinpoint mismatched entity IDs
        """
        local_hash = integrity_verifier.compute_namespace_hash(local_records)
        remote_hash = integrity_verifier.compute_namespace_hash(remote_records)

        if local_hash == remote_hash:
            return False, [], {"status": "CONVERGED", "hash": local_hash}

        divergent_entities = []
        local_map = {r.entity_id: r for r in local_records}
        remote_map = {r.entity_id: r for r in remote_records}

        all_keys = set(local_map.keys()).union(set(remote_map.keys()))
        for key in all_keys:
            l_rec = local_map.get(key)
            r_rec = remote_map.get(key)
            if not l_rec or not r_rec or l_rec.integrity_hash != r_rec.integrity_hash:
                divergent_entities.append(key)

        logger.warning(f"State divergence detected in namespace '{namespace_id}'. {len(divergent_entities)} entities out of sync.")
        return True, divergent_entities, {
            "status": "DIVERGED",
            "local_hash": local_hash,
            "remote_hash": remote_hash,
            "divergent_count": len(divergent_entities)
        }

    def reconcile_divergent_entity(
        self,
        namespace_id: str,
        local_record: Optional[StateRecord],
        remote_record: Optional[StateRecord],
        current_epoch: int
    ) -> Tuple[str, Optional[StateRecord]]:
        """Deterministically decides which record is authoritative:
        
        1. Epoch Wins: The record carrying the newer epoch is authoritative.
        2. Owner Wins: If same epoch, check Module 22 ownership.
        3. Revision Wins: If same owner and epoch, higher revision wins.
        4. If concurrent unowned divergence occurs, record conflict and escalate.
        """
        if not local_record and remote_record:
            # New entity from remote
            if remote_record.owner_epoch >= current_epoch:
                return "ACCEPT_REMOTE", remote_record
            else:
                return "REJECT_STALE_REMOTE", None

        if local_record and not remote_record:
            return "KEEP_LOCAL", local_record

        # Both exist and differ:
        l_epoch = local_record.owner_epoch
        r_epoch = remote_record.owner_epoch

        # Rule 1: Epoch Wins
        if r_epoch > l_epoch:
            logger.info(f"Reconciling {namespace_id}:{local_record.entity_id}: Remote epoch {r_epoch} > Local epoch {l_epoch}. Remote wins.")
            return "ACCEPT_REMOTE", remote_record
        elif l_epoch > r_epoch:
            logger.info(f"Reconciling {namespace_id}:{local_record.entity_id}: Local epoch {l_epoch} > Remote epoch {r_epoch}. Local wins.")
            return "KEEP_LOCAL", local_record

        # Rule 2: Same Epoch -> Check Owner
        owner = self.coordination.get_task_owner(local_record.entity_id) if namespace_id == "tasks" else None
        if owner:
            if remote_record.owner_node == owner:
                return "ACCEPT_REMOTE", remote_record
            elif local_record.owner_node == owner:
                return "KEEP_LOCAL", local_record

        # Rule 3: Revision Wins
        if remote_record.revision > local_record.revision:
            return "ACCEPT_REMOTE", remote_record
        elif local_record.revision > remote_record.revision:
            return "KEEP_LOCAL", local_record

        # Unresolvable concurrent conflict -> escalate
        conflict_resolver.record_conflict(
            namespace_id=namespace_id,
            entity_id=local_record.entity_id,
            local_record=local_record,
            remote_delta_or_record=remote_record,
            conflict_type=ConflictType.CONCURRENT_MODIFICATION,
            strategy=ConflictResolutionStrategy.MANUAL_REVIEW
        )
        return "ESCALATE_CONFLICT", local_record

reconciliation_engine = StateReconciliationEngine()
