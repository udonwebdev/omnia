"""
forensics/custody_manager.py
Append-only chain-of-custody manager for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional

from forensics.models import ChainOfCustodyRecord, CustodyOperation, EvidenceArtifact
from forensics.persistence import ForensicsRepository
from forensics.vault import EvidenceVault

logger = logging.getLogger("omnia.forensics.custody")


class CustodyManager:
    """
    Maintains an unbroken, tamper-evident audit trail for all forensic artifacts.
    Enforces that every touch, read, transfer, or verification is cryptographically
    linked and logged into the append-only ledger.
    """

    def __init__(self, repo: ForensicsRepository, vault: EvidenceVault):
        self.repo = repo
        self.vault = vault

    def record_operation(
        self,
        artifact: EvidenceArtifact,
        operation: CustodyOperation,
        actor: str,
        reason: str,
        approval_token: Optional[str] = None
    ) -> ChainOfCustodyRecord:
        """Log a new custody event, verifying artifact hash at time of logging."""
        is_valid, current_hash = self.vault.verify_integrity(artifact.storage_uri, artifact.sha256_hash)
        if not is_valid:
            logger.critical(f"TAMPER DETECTED: Artifact {artifact.artifact_id} hash mismatch during {operation.value}!")
            self.repo.update_artifact_integrity(artifact.artifact_id, "TAMPER_DETECTED")

        rec = ChainOfCustodyRecord(
            custody_id=f"cust_{uuid.uuid4().hex[:12]}",
            artifact_id=artifact.artifact_id,
            case_id=artifact.case_id,
            operation=operation,
            actor=actor,
            reason=reason,
            sha256_verified=current_hash,
            integrity_ok=is_valid,
            approval_token=approval_token,
            recorded_at=time.time()
        )
        return self.repo.record_custody(rec)

    def verify_custody_chain(self, case_id: str, artifact_id: str) -> Dict[str, Any]:
        """
        Validates the unbroken chain-of-custody for a specific artifact.
        Checks for:
        1. Acquisition record exists.
        2. All hashes across historical transitions match the original registration.
        3. Current file on disk matches the initial hash.
        """
        artifact = self.repo.get_artifact(artifact_id)
        if not artifact:
            return {
                "valid": False,
                "error": f"Artifact {artifact_id} not found."
            }

        records = self.repo.list_custody_records(case_id, artifact_id)
        if not records:
            return {
                "valid": False,
                "error": f"No custody records found for artifact {artifact_id}."
            }

        # Check acquisition entry
        has_acq = any(r.operation == CustodyOperation.ACQUISITION for r in records)
        if not has_acq:
            return {
                "valid": False,
                "error": "Missing initial ACQUISITION record in chain of custody."
            }

        # Check all historical verification records
        tampered_records = [r for r in records if not r.integrity_ok or r.sha256_verified != artifact.sha256_hash]
        if tampered_records:
            return {
                "valid": False,
                "error": f"Found {len(tampered_records)} historical custody entries with hash discrepancies.",
                "tampered_entries": [r.custody_id for r in tampered_records]
            }

        # Check live file on disk
        live_valid, live_hash = self.vault.verify_integrity(artifact.storage_uri, artifact.sha256_hash)
        if not live_valid:
            return {
                "valid": False,
                "error": f"Live artifact payload failed integrity verification. Expected {artifact.sha256_hash}, found {live_hash}."
            }

        return {
            "valid": True,
            "artifact_id": artifact_id,
            "case_id": case_id,
            "events_logged": len(records),
            "original_sha256": artifact.sha256_hash,
            "live_sha256": live_hash,
            "integrity_status": "VERIFIED_UNBROKEN"
        }
