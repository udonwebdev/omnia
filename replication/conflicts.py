import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from replication.models import (
    Conflict,
    ConflictType,
    ConflictResolutionStrategy,
    StateRecord,
    StateDelta
)

logger = logging.getLogger("Omnia.Replication.Conflicts")

class ConflictResolver:
    """Manages explicit conflict detection, evidence logging, and deterministic resolution."""

    def __init__(self):
        self._conflicts: Dict[str, Conflict] = {}

    def record_conflict(
        self,
        namespace_id: str,
        entity_id: str,
        local_record: Optional[StateRecord],
        remote_delta_or_record: Any,
        conflict_type: ConflictType,
        strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.EPOCH_WINS
    ) -> Conflict:
        """Records an explicit replication conflict with complete diagnostic evidence."""
        c = Conflict(
            namespace_id=namespace_id,
            entity_id=entity_id,
            local_version={
                "revision": local_record.revision if local_record else 0,
                "epoch": local_record.owner_epoch if local_record else 0,
                "owner": local_record.owner_node if local_record else "NONE",
                "hash": local_record.integrity_hash if local_record else ""
            },
            remote_version={
                "revision": getattr(remote_delta_or_record, "target_revision", getattr(remote_delta_or_record, "revision", 0)),
                "epoch": getattr(remote_delta_or_record, "source_epoch", getattr(remote_delta_or_record, "owner_epoch", 0)),
                "owner": getattr(remote_delta_or_record, "source_node", getattr(remote_delta_or_record, "owner_node", "UNKNOWN")),
                "hash": getattr(remote_delta_or_record, "integrity_hash", "")
            },
            conflict_type=conflict_type,
            resolution_strategy=strategy,
            resolution_status="PENDING",
            evidence={
                "detected_at": time.time(),
                "local_payload": local_record.payload if local_record else {},
                "remote_payload": getattr(remote_delta_or_record, "payload", {})
            }
        )
        self._conflicts[c.conflict_id] = c
        logger.warning(f"CONFLICT RECORDED: [{conflict_type.value}] for {namespace_id}:{entity_id} (Conflict ID: {c.conflict_id}).")
        return c

    def resolve_conflict(
        self,
        conflict_id: str,
        resolution_strategy: ConflictResolutionStrategy,
        resolution_note: str = ""
    ) -> Optional[Conflict]:
        """Resolves conflict deterministically according to declared strategy."""
        c = self._conflicts.get(conflict_id)
        if not c:
            return None

        c.resolution_strategy = resolution_strategy
        if resolution_strategy == ConflictResolutionStrategy.MANUAL_REVIEW:
            c.resolution_status = "ESCALATED"
        else:
            c.resolution_status = "RESOLVED"
            c.resolved_at = time.time()

        c.evidence["resolution_note"] = resolution_note
        logger.info(f"Conflict '{conflict_id}' resolved using strategy '{resolution_strategy.value}': {c.resolution_status}")
        return c

    def get_conflict(self, conflict_id: str) -> Optional[Conflict]:
        return self._conflicts.get(conflict_id)

    def list_conflicts(self, status: Optional[str] = None) -> List[Conflict]:
        if status:
            return [c for c in self._conflicts.values() if c.resolution_status == status]
        return list(self._conflicts.values())

conflict_resolver = ConflictResolver()
