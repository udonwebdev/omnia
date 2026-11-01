"""
forensics/acquisition.py
Evidence acquisition engine for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import uuid
import time
import logging
from typing import Dict, Any, Optional

from forensics.models import (
    ForensicCase, CaseStatus, EvidenceArtifact, ArtifactType,
    CustodyOperation, AcquisitionJob
)
from forensics.persistence import ForensicsRepository
from forensics.vault import EvidenceVault
from forensics.custody_manager import CustodyManager

logger = logging.getLogger("omnia.forensics.acquisition")


class EvidenceAcquisitionEngine:
    """
    Manages controlled, authorized acquisition of forensic artifacts from
    registered sources (endpoints, cloud audit logs, identity providers, network taps).
    Enforces human approval requirements (Module 20) for sensitive sources.
    """

    SENSITIVE_SOURCES = {"MEMORY_DUMP", "PAYROLL_DB", "EXECUTIVE_MAILBOX", "PRODUCTION_KMS"}

    def __init__(
        self,
        repo: ForensicsRepository,
        vault: EvidenceVault,
        custody_mgr: CustodyManager
    ):
        self.repo = repo
        self.vault = vault
        self.custody_mgr = custody_mgr

    def acquire_artifact(
        self,
        case_id: str,
        source_type: ArtifactType,
        source_identifier: str,
        artifact_name: str,
        raw_data: bytes,
        classification: str = "CONFIDENTIAL",
        parser_type: str = "json_structured",
        metadata: Optional[Dict[str, Any]] = None,
        approval_token: Optional[str] = None,
        operator: str = "omnia_forensic_agent"
    ) -> EvidenceArtifact:
        """
        Acquires an artifact payload, stores it immutably in the vault,
        registers the metadata, and records the initial ACQUISITION custody record.
        """
        case = self.repo.get_case(case_id)
        if not case:
            raise ValueError(f"Forensic case {case_id} not found.")

        # Check authorization boundary
        if source_identifier in self.SENSITIVE_SOURCES or classification == "TOP_SECRET":
            if not approval_token:
                raise PermissionError(
                    f"Sensitive source {source_identifier} requires an authorized Module 20 human approval token."
                )

        artifact_id = f"art_{uuid.uuid4().hex[:12]}"

        # Store bytes in vault
        sha256_hash, storage_uri, size_bytes = self.vault.store_artifact_bytes(
            artifact_id=artifact_id,
            data=raw_data
        )

        artifact = EvidenceArtifact(
            artifact_id=artifact_id,
            case_id=case_id,
            source_type=source_type,
            source_identifier=source_identifier,
            artifact_name=artifact_name,
            classification=classification,
            sha256_hash=sha256_hash,
            size_bytes=size_bytes,
            storage_uri=storage_uri,
            parser_type=parser_type,
            metadata=metadata or {},
            acquired_at=time.time(),
            acquired_by=operator,
            integrity_status="VERIFIED"
        )

        # Save to DB
        self.repo.record_artifact(artifact)

        # Log custody event
        self.custody_mgr.record_operation(
            artifact=artifact,
            operation=CustodyOperation.ACQUISITION,
            actor=operator,
            reason=f"Acquired from {source_identifier} ({source_type.value})",
            approval_token=approval_token
        )

        logger.info(f"Successfully acquired forensic artifact {artifact_id} ({artifact_name}) for case {case_id}")
        return artifact
