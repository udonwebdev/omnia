import hashlib
import json
import logging
from typing import Dict, List, Any
from replication.models import StateRecord, Snapshot

logger = logging.getLogger("Omnia.Replication.Integrity")

class StateIntegrityVerifier:
    """Computes and verifies cryptographic hashes for state records, snapshots, and namespaces."""

    @staticmethod
    def compute_record_hash(record: StateRecord) -> str:
        return record.compute_hash()

    @staticmethod
    def verify_record_integrity(record: StateRecord) -> bool:
        expected = record.compute_hash()
        return expected == record.integrity_hash

    @staticmethod
    def compute_namespace_hash(records: List[StateRecord]) -> str:
        """Computes a deterministic Merkel-like tree root hash for all records in a namespace."""
        sorted_records = sorted(records, key=lambda r: (r.entity_type, r.entity_id))
        hashes = [r.integrity_hash for r in sorted_records]
        raw = "|".join(hashes)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_snapshot_hash(snapshot: Snapshot) -> bool:
        expected = snapshot.compute_hash()
        return expected == snapshot.content_hash

integrity_verifier = StateIntegrityVerifier()
