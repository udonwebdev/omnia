import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from replication.models import StateDelta, StateRecord, DeltaOperation

logger = logging.getLogger("Omnia.Replication.Deltas")

class DeltaManager:
    """Manages incremental delta generation, out-of-order buffering, gap detection, and idempotent application."""

    def __init__(self):
        # Buffered out-of-order deltas: (namespace_id, entity_id) -> list of StateDelta
        self._buffer: Dict[str, List[StateDelta]] = {}
        # Applied delta deduplication cache: delta_id -> timestamp
        self._applied_deltas: Set[str] = set()

    def create_delta(
        self,
        namespace_id: str,
        entity_id: str,
        source_node: str,
        source_epoch: int,
        base_revision: int,
        target_revision: int,
        operation: DeltaOperation,
        payload: Dict[str, Any],
        causal_metadata: Optional[Dict[str, Any]] = None
    ) -> StateDelta:
        """Constructs an incremental state delta with deterministic integrity hash."""
        return StateDelta(
            namespace_id=namespace_id,
            entity_id=entity_id,
            source_node=source_node,
            source_epoch=source_epoch,
            base_revision=base_revision,
            target_revision=target_revision,
            operation=operation,
            payload=payload,
            causal_metadata=causal_metadata or {}
        )

    def apply_delta_to_record(
        self,
        current_record: Optional[StateRecord],
        delta: StateDelta
    ) -> Tuple[bool, Optional[StateRecord], str]:
        """Applies a delta to a state record idempotently.
        
        Detects:
        - Duplicate delivery (returns existing state cleanly without error)
        - Version gaps (base_revision != current revision)
        - Stale deltas
        """
        # 1. Idempotency Check: Already applied?
        if delta.delta_id in self._applied_deltas:
            logger.info(f"Duplicate delta '{delta.delta_id}' received; acknowledged idempotently.")
            return True, current_record, "IDEMPOTENT_DUPLICATE_APPLIED"

        current_rev = current_record.revision if current_record else 0

        # 2. Check for duplicate/obsolete target revision
        if current_record and delta.target_revision <= current_rev and delta.source_epoch == current_record.owner_epoch:
            logger.info(f"Obsolete delta '{delta.delta_id}' (Target: {delta.target_revision} <= Current: {current_rev}); ignoring.")
            self._applied_deltas.add(delta.delta_id)
            return True, current_record, "IDEMPOTENT_OBSOLETE_APPLIED"

        # 3. Gap Detection: delta.base_revision MUST match current revision
        if delta.base_revision > current_rev:
            gap_size = delta.base_revision - current_rev
            logger.warning(f"VERSION_GAP detected for {delta.namespace_id}:{delta.entity_id}. Current: {current_rev}, Base required: {delta.base_revision} (Gap: {gap_size}). Buffering.")
            self._buffer_delta(delta)
            return False, current_record, f"VERSION_GAP: Missing revisions {current_rev + 1} to {delta.base_revision}"

        # 4. Apply transition based on operation
        new_payload = dict(current_record.payload) if current_record else {}
        if delta.operation in {DeltaOperation.CREATE, DeltaOperation.REPLACE}:
            new_payload = dict(delta.payload)
        elif delta.operation in {DeltaOperation.UPDATE, DeltaOperation.PATCH}:
            new_payload.update(delta.payload)
        elif delta.operation == DeltaOperation.DELETE:
            new_payload = {"__deleted__": True}

        new_record = StateRecord(
            state_id=current_record.state_id if current_record else f"st_{delta.entity_id}",
            namespace_id=delta.namespace_id,
            entity_type=current_record.entity_type if current_record else "ENTITY",
            entity_id=delta.entity_id,
            owner_node=delta.source_node,
            owner_epoch=delta.source_epoch,
            revision=delta.target_revision,
            payload=new_payload,
            created_at=current_record.created_at if current_record else delta.created_at,
            updated_at=delta.created_at
        )

        self._applied_deltas.add(delta.delta_id)
        logger.info(f"Delta '{delta.delta_id}' applied to {delta.namespace_id}:{delta.entity_id} -> Rev {delta.target_revision}.")
        return True, new_record, "DELTA_APPLIED"

    def _buffer_delta(self, delta: StateDelta):
        key = f"{delta.namespace_id}:{delta.entity_id}"
        if key not in self._buffer:
            self._buffer[key] = []
        # Prevent unbounded buffer growth
        if len(self._buffer[key]) < 200:
            if not any(d.delta_id == delta.delta_id for d in self._buffer[key]):
                self._buffer[key].append(delta)
                self._buffer[key].sort(key=lambda d: d.target_revision)

    def get_buffered_deltas(self, namespace_id: str, entity_id: str) -> List[StateDelta]:
        key = f"{namespace_id}:{entity_id}"
        return self._buffer.get(key, [])

    def clear_buffered_deltas(self, namespace_id: str, entity_id: str):
        key = f"{namespace_id}:{entity_id}"
        if key in self._buffer:
            del self._buffer[key]

delta_manager = DeltaManager()
