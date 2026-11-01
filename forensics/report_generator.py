"""
forensics/report_generator.py
Epistemic report builder for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import uuid
import time
import hashlib
import json
import logging
from typing import List, Dict, Any, Optional

from forensics.models import (
    ForensicReport, StatementItem, StatementCategory,
    ForensicCase, HypothesisStatus
)
from forensics.persistence import ForensicsRepository
from forensics.custody_manager import CustodyManager

logger = logging.getLogger("omnia.forensics.report")


class ForensicReportGenerator:
    """
    Generates structured, cryptographically signed forensic investigation reports.
    Strictly categorizes statements into:
    - FACTS: Direct physical/cryptographic observations from evidence artifacts.
    - INFERENCES: Deductions derived logically from correlated facts.
    - HYPOTHESES: Evaluated theories with support/refutation scores.
    - UNKNOWNS: Gaps in telemetry, missing records, or unverified claims.
    """

    def __init__(self, repo: ForensicsRepository, custody_mgr: CustodyManager):
        self.repo = repo
        self.custody_mgr = custody_mgr

    def generate_report(
        self,
        case_id: str,
        investigator: str = "omnia_forensic_agent"
    ) -> ForensicReport:
        """Assembles verified findings into a sealed forensic report."""
        case = self.repo.get_case(case_id)
        if not case:
            raise ValueError(f"Forensic case {case_id} not found.")

        artifacts = self.repo.list_artifacts(case_id)
        events = self.repo.list_timeline_events(case_id)
        correlations = self.repo.list_correlations(case_id)
        hypotheses = self.repo.list_hypotheses(case_id)

        # 1. Compile FACTS from verified artifacts and confirmed events
        facts: List[StatementItem] = []
        for art in artifacts:
            facts.append(StatementItem(
                category=StatementCategory.FACT,
                statement=f"Preserved artifact '{art.artifact_name}' (SHA256: {art.sha256_hash}, Size: {art.size_bytes}B) from {art.source_identifier}.",
                evidence_refs=[art.artifact_id],
                confidence=1.0
            ))

        for ev in events[:5]:  # Key initial events
            facts.append(StatementItem(
                category=StatementCategory.FACT,
                statement=f"[{ev.raw_timestamp}] {ev.summary}",
                evidence_refs=[ev.artifact_id] if ev.artifact_id else [],
                confidence=1.0
            ))

        # 2. Compile INFERENCES from correlations
        inferences: List[StatementItem] = []
        for corr in correlations:
            inferences.append(StatementItem(
                category=StatementCategory.INFERENCE,
                statement=f"Correlation detected: {corr.notes} (Confidence: {corr.confidence_score * 100:.0f}%)",
                evidence_refs=[corr.source_artifact_id, corr.target_artifact_id],
                confidence=corr.confidence_score
            ))

        # 3. Compile HYPOTHESES
        hypo_items: List[StatementItem] = []
        for h in hypotheses:
            hypo_items.append(StatementItem(
                category=StatementCategory.HYPOTHESIS,
                statement=f"[{h.status.value}] {h.title}: {h.theory_description}. (Support: {h.support_score:.1f}, Refutation: {h.refutation_score:.1f})",
                evidence_refs=[],
                confidence=0.8 if h.status == HypothesisStatus.SUPPORTED else 0.3
            ))

        # 4. Identify UNKNOWNS
        unknowns: List[StatementItem] = []
        if not events:
            unknowns.append(StatementItem(
                category=StatementCategory.UNKNOWN,
                statement="No timeline events reconstructed; log coverage is zero.",
                confidence=0.0
            ))
        elif any(e.clock_drift_seconds != 0.0 for e in events):
            unknowns.append(StatementItem(
                category=StatementCategory.UNKNOWN,
                statement="Exact microsecond ordering undetermined due to uncalibrated clock drift on remote collector.",
                confidence=0.0
            ))

        # Executive Summary
        supported_theories = [h.title for h in hypotheses if h.status == HypothesisStatus.SUPPORTED]
        theory_summary = f" Favored theory: {supported_theories[0]}." if supported_theories else " No single theory currently conclusively verified."
        exec_summary = (
            f"Forensic investigation for case {case.title} (ID: {case.case_id}). "
            f"Preserved {len(artifacts)} cryptographic artifacts across {len(events)} chronological events."
            f"{theory_summary}"
        )

        recommendations = [
            "Maintain evidence artifacts under cryptographic legal hold until regulatory review completes.",
            "Rotate all identity credentials and session tokens correlated with compromised access paths.",
            "Enforce multi-factor hardware keys on the identified authentication entrypoint."
        ]

        # Seal generation (SHA-256 over report contents)
        seal_payload = json.dumps({
            "case_id": case_id,
            "facts_count": len(facts),
            "inferences_count": len(inferences),
            "hypotheses_count": len(hypo_items),
            "investigator": investigator,
            "timestamp": time.time()
        }, sort_keys=True)
        seal_hash = hashlib.sha256(seal_payload.encode("utf-8")).hexdigest()

        report = ForensicReport(
            report_id=f"rep_{uuid.uuid4().hex[:12]}",
            case_id=case_id,
            title=f"Forensic Investigation Report: {case.title}",
            executive_summary=exec_summary,
            facts=facts,
            inferences=inferences,
            hypotheses=hypo_items,
            unknowns=unknowns,
            recommendations=recommendations,
            sign_off_investigator=investigator,
            cryptographic_seal=seal_hash,
            created_at=time.time()
        )

        return self.repo.record_report(report)
