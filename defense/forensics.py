"""
OMNIA Module 35: Forensic Evidence Manager & Tamper-Evident Custody
Preserves immutable forensic evidence records with SHA-256 integrity digests,
redacts sensitive credentials, and logs chain-of-custody metadata.
"""

import time
import uuid
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
from defense.models import ForensicEvidenceRecord
from defense.telemetry import SecurityEventNormalizer

logger = logging.getLogger("Omnia.Defense.Forensics")


class ForensicEvidenceManager:
    """Collects and verifies immutable forensic evidence records for security incidents."""

    def __init__(self, normalizer: Optional[SecurityEventNormalizer] = None):
        self.normalizer = normalizer or SecurityEventNormalizer()
        self._evidence_records: Dict[str, ForensicEvidenceRecord] = {}

    def preserve_evidence(
        self,
        incident_id: str,
        artifact_type: str,
        source_identifier: str,
        raw_payload: Any,
        collector_identity: str = "Omnia.ForensicEngine",
        data_classification: str = "CONFIDENTIAL",
    ) -> ForensicEvidenceRecord:
        """Sanitizes raw payload, computes SHA-256 integrity digest, and records chain-of-custody."""
        evidence_id = f"evid-{uuid.uuid4().hex[:10]}"
        now = time.time()

        # Scrub credentials from payload before archiving
        sanitized = self.normalizer.sanitize_payload(raw_payload)
        serialized = json.dumps(sanitized, sort_keys=True)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        record = ForensicEvidenceRecord(
            evidence_id=evidence_id,
            incident_id=incident_id,
            artifact_type=artifact_type,
            source_identifier=source_identifier,
            collector_identity=collector_identity,
            integrity_digest=digest,
            raw_payload_redacted=serialized,
            collected_at=now,
            data_classification=data_classification,
            chain_of_custody=[{
                "timestamp": now,
                "actor": collector_identity,
                "action": "EVIDENCE_PRESERVED",
                "digest": digest,
            }],
        )
        self._evidence_records[evidence_id] = record
        return record

    def verify_evidence_integrity(self, evidence_id: str) -> bool:
        """Verifies that the stored redacted payload matches its cryptographic digest."""
        record = self._evidence_records.get(evidence_id)
        if not record:
            return False
        computed = hashlib.sha256(record.raw_payload_redacted.encode("utf-8")).hexdigest()
        return computed == record.integrity_digest
