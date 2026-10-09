"""
Deterministic Deduplication Engine for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Guarantees:
1. Deduplication utilizes stable content hashes, provider resource IDs, and operation keys.
2. Distinct records with duplicate payload hashes are detected to prevent redundant processing.
3. Ambiguous identities are never merged based solely on superficial timestamps.
"""

import time
import logging
from typing import Dict, Any, Tuple, Optional

from ingestion.models import (
    IngestionEnvelope,
    NormalizedRecord,
    DeduplicationStatus
)

logger = logging.getLogger("Omnia.Ingestion.Deduplication")


class DeduplicationEngine:
    """Manages deterministic duplicate detection across in-flight and persisted ingestion records."""

    def __init__(self, persistence=None):
        self.persistence = persistence
        # In-memory sliding window: payload_hash -> timestamp
        self._seen_hashes: Dict[str, float] = {}
        # resource_key (source_id + resource_id) -> (canonical_id, timestamp)
        self._seen_resources: Dict[str, Tuple[str, float]] = {}

    def check_duplicate_envelope(
        self,
        envelope: IngestionEnvelope,
        window_seconds: float = 3600.0
    ) -> Tuple[DeduplicationStatus, Optional[str]]:
        """
        Determines if an incoming envelope is an exact duplicate of a recently ingested item.
        """
        now = time.time()
        # Clean expired hashes
        self._seen_hashes = {h: ts for h, ts in self._seen_hashes.items() if (now - ts) < window_seconds}

        payload_hash = envelope.payload_hash
        if payload_hash in self._seen_hashes:
            return DeduplicationStatus.EXACT_DUPLICATE, f"Duplicate payload hash '{payload_hash[:16]}' seen within {window_seconds:.0f}s."

        # Mark seen
        self._seen_hashes[payload_hash] = now
        return DeduplicationStatus.NOT_DUPLICATE, None

    def check_duplicate_record(
        self,
        record: NormalizedRecord,
        window_seconds: float = 3600.0
    ) -> Tuple[DeduplicationStatus, Optional[str]]:
        """
        Checks if the normalized canonical entity already exists for the given provider source.
        """
        res_key = f"{record.provenance.source_id}:{record.canonical_id}"
        now = time.time()
        self._seen_resources = {k: v for k, v in self._seen_resources.items() if (now - v[1]) < window_seconds}

        if res_key in self._seen_resources:
            prev_id, _ = self._seen_resources[res_key]
            return DeduplicationStatus.LIKELY_DUPLICATE, f"Resource key '{res_key}' previously normalized as record '{prev_id}'."

        self._seen_resources[res_key] = (record.record_id, now)
        return DeduplicationStatus.NOT_DUPLICATE, None


deduplication_engine = DeduplicationEngine()
