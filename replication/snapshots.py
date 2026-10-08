import time
import logging
from typing import List, Optional, Tuple, Dict, Any
from replication.models import Snapshot, StateRecord
from replication.integrity import integrity_verifier

logger = logging.getLogger("Omnia.Replication.Snapshots")

class SnapshotManager:
    """Manages frozen state partition snapshots with deterministic boundaries and verification."""

    def create_snapshot(
        self,
        namespace_id: str,
        source_node: str,
        source_epoch: int,
        records: List[StateRecord]
    ) -> Snapshot:
        """Freezes an atomic point-in-time snapshot of a namespace."""
        # Max revision in partition
        max_rev = max([r.revision for r in records], default=0)
        # Deep copy records to freeze state
        frozen_records = [
            StateRecord(
                state_id=r.state_id,
                namespace_id=r.namespace_id,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                owner_node=r.owner_node,
                owner_epoch=r.owner_epoch,
                revision=r.revision,
                payload=dict(r.payload),
                schema_version=r.schema_version,
                created_at=r.created_at,
                updated_at=r.updated_at,
                integrity_hash=r.integrity_hash
            )
            for r in records
        ]

        snapshot = Snapshot(
            namespace_id=namespace_id,
            source_node=source_node,
            source_epoch=source_epoch,
            revision=max_rev,
            record_count=len(frozen_records),
            records=frozen_records
        )
        snapshot.content_hash = snapshot.compute_hash()
        logger.info(f"Created snapshot '{snapshot.snapshot_id}' for namespace '{namespace_id}' (Rev: {max_rev}, Records: {len(frozen_records)}).")
        return snapshot

    def validate_snapshot(self, snapshot: Snapshot) -> Tuple[bool, str]:
        """Validates snapshot integrity hash, records, and internal schema consistency."""
        if not snapshot.snapshot_id or not snapshot.namespace_id:
            return False, "SNAPSHOT_INVALID: Missing snapshot metadata."

        if not integrity_verifier.verify_snapshot_hash(snapshot):
            return False, f"CHECKSUM_MISMATCH: Snapshot content hash verification failed."

        for rec in snapshot.records:
            if not integrity_verifier.verify_record_integrity(rec):
                return False, f"CHECKSUM_MISMATCH: State record '{rec.entity_id}' hash invalid inside snapshot."

        return True, "SNAPSHOT_VALID"

snapshot_manager = SnapshotManager()
