"""
forensics/service.py
Central orchestrator facade for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional

from forensics.models import (
    ForensicCase, CaseStatus, EvidenceArtifact, ArtifactType,
    ChainOfCustodyRecord, CustodyOperation, TimelineEvent,
    EvidenceCorrelation, ForensicHypothesis, ForensicReport,
    LegalHold
)
from forensics.persistence import ForensicsRepository
from forensics.vault import EvidenceVault
from forensics.custody_manager import CustodyManager
from forensics.acquisition import EvidenceAcquisitionEngine
from forensics.artifact_parsers import SafeArtifactParser
from forensics.timeline import TimelineReconstructionEngine
from forensics.correlation import EvidenceCorrelationEngine
from forensics.hypothesis_engine import HypothesisEngine
from forensics.report_generator import ForensicReportGenerator

logger = logging.getLogger("omnia.forensics.service")


class DigitalForensicsOrchestrator:
    """
    Unified entrypoint for Autonomous Digital Forensics, Evidence Preservation,
    and Incident Investigation Intelligence.
    """

    def __init__(self, db_path: str = "omnia.db", vault_dir: str = "artifacts/forensics_vault"):
        self.repo = ForensicsRepository(db_path=db_path)
        self.vault = EvidenceVault(storage_dir=vault_dir)
        self.custody_mgr = CustodyManager(repo=self.repo, vault=self.vault)
        self.acq_engine = EvidenceAcquisitionEngine(
            repo=self.repo, vault=self.vault, custody_mgr=self.custody_mgr
        )
        self.parser = SafeArtifactParser()
        self.timeline_engine = TimelineReconstructionEngine(
            repo=self.repo, vault=self.vault, parser=self.parser
        )
        self.correl_engine = EvidenceCorrelationEngine(repo=self.repo)
        self.hypothesis_engine = HypothesisEngine(repo=self.repo)
        self.report_generator = ForensicReportGenerator(
            repo=self.repo, custody_mgr=self.custody_mgr
        )

    # --- Case Lifecycle ---
    def open_investigation_case(
        self,
        title: str,
        description: str,
        incident_id: Optional[str] = None,
        scope_definition: Optional[Dict[str, Any]] = None,
        lead_investigator: str = "omnia_forensic_agent"
    ) -> ForensicCase:
        """Initialize and scope a formal digital forensics case."""
        case_id = f"case_{uuid.uuid4().hex[:10]}"
        case = ForensicCase(
            case_id=case_id,
            title=title,
            description=description,
            incident_id=incident_id,
            scope_definition=scope_definition or {"allowed_sources": ["all"]},
            status=CaseStatus.OPEN,
            lead_investigator=lead_investigator,
            created_at=time.time(),
            updated_at=time.time()
        )
        return self.repo.create_case(case)

    def get_case(self, case_id: str) -> Optional[ForensicCase]:
        return self.repo.get_case(case_id)

    def list_cases(self, status: Optional[CaseStatus] = None) -> List[ForensicCase]:
        return self.repo.list_cases(status=status)

    def close_investigation_case(self, case_id: str) -> bool:
        return self.repo.update_case_status(
            case_id=case_id,
            status=CaseStatus.CLOSED,
            updated_at=time.time(),
            closed_at=time.time()
        )

    # --- Evidence Acquisition & Preservation ---
    def acquire_artifact(
        self,
        case_id: str,
        source_type: ArtifactType,
        source_identifier: str,
        artifact_name: str,
        raw_data: bytes,
        classification: str = "CONFIDENTIAL",
        metadata: Optional[Dict[str, Any]] = None,
        approval_token: Optional[str] = None,
        operator: str = "omnia_forensic_agent"
    ) -> EvidenceArtifact:
        """Acquires and cryptographically preserves an artifact."""
        return self.acq_engine.acquire_artifact(
            case_id=case_id,
            source_type=source_type,
            source_identifier=source_identifier,
            artifact_name=artifact_name,
            raw_data=raw_data,
            classification=classification,
            metadata=metadata,
            approval_token=approval_token,
            operator=operator
        )

    # --- Custody & Tamper Verification ---
    def verify_artifact_custody(self, case_id: str, artifact_id: str) -> Dict[str, Any]:
        """Validates the unbroken cryptographic chain-of-custody for an artifact."""
        return self.custody_mgr.verify_custody_chain(case_id=case_id, artifact_id=artifact_id)

    # --- Timeline & Correlation ---
    def reconstruct_case_timeline(self, case_id: str) -> List[TimelineEvent]:
        """Parses case artifacts, constructs events, and returns ordered sequence."""
        self.timeline_engine.process_case_artifacts(case_id)
        return self.timeline_engine.get_chronological_timeline(case_id)

    def correlate_evidence(self, case_id: str) -> List[EvidenceCorrelation]:
        """Runs cross-source correlation across case artifacts."""
        return self.correl_engine.correlate_case_evidence(case_id)

    # --- Hypothesis Engine ---
    def create_hypothesis(
        self,
        case_id: str,
        title: str,
        theory_description: str,
        competing_with_id: Optional[str] = None
    ) -> ForensicHypothesis:
        return self.hypothesis_engine.create_hypothesis(
            case_id=case_id,
            title=title,
            theory_description=theory_description,
            competing_with_id=competing_with_id
        )

    def evaluate_hypothesis(
        self,
        hypothesis_id: str,
        supporting_evidence: Optional[List[str]] = None,
        contradictory_evidence: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        if supporting_evidence:
            for s in supporting_evidence:
                self.hypothesis_engine.add_supporting_evidence(hypothesis_id, s)
        if contradictory_evidence:
            for c in contradictory_evidence:
                self.hypothesis_engine.add_contradictory_evidence(hypothesis_id, c)

        h = self.repo.get_hypothesis(hypothesis_id)
        if not h:
            return {"error": "Hypothesis not found"}
        return {
            "hypothesis_id": h.hypothesis_id,
            "status": h.status.value,
            "support_score": h.support_score,
            "refutation_score": h.refutation_score,
            "rationale": h.verdict_rationale
        }

    # --- Reporting ---
    def generate_report(self, case_id: str, investigator: str = "omnia_forensic_agent") -> ForensicReport:
        return self.report_generator.generate_report(case_id=case_id, investigator=investigator)

    # --- Legal Hold ---
    def apply_legal_hold(
        self,
        case_id: str,
        hold_reason: str,
        applied_by: str,
        approval_token: str
    ) -> LegalHold:
        """Places a case under legal hold with Module 20 human approval."""
        if not approval_token:
            raise PermissionError("Legal hold requires a verified Module 20 human approval token.")
        hold = LegalHold(
            hold_id=f"hold_{uuid.uuid4().hex[:10]}",
            case_id=case_id,
            hold_reason=hold_reason,
            applied_by=applied_by,
            approval_token=approval_token,
            is_active=True,
            applied_at=time.time()
        )
        self.repo.record_legal_hold(hold)
        self.repo.update_case_legal_hold(case_id=case_id, active=True, updated_at=time.time())
        return hold


# Global singleton instance
forensics_service = DigitalForensicsOrchestrator()
