"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Quality Score & Multi-Dimensional Assessment - quality_score.py

Produces transparent, multi-dimensional quality assessments reflecting functional correctness,
coverage, critical unresolved defects, regressions, and flaky test counts.
Never conceals critical failures inside an averaged single score.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from qa_verification.models import (
    DefectRecord,
    DefectSeverity,
    QualityAssessment,
    QualityTier,
)
from qa_verification.persistence import QAVerificationRepository

logger = logging.getLogger("Omnia.QAVerification.QualityScore")


class QualityScoreEngine:
    """
    Computes transparent multi-dimensional software quality assessments.
    """

    def __init__(self, repository: Optional[QAVerificationRepository] = None):
        self.repo = repository or QAVerificationRepository()

    def evaluate_quality_assessment(
        self,
        project_id: str,
        mission_id: str,
        functional_pass_rate: float,
        coverage_score: float,
        unresolved_defects: List[DefectRecord],
        regressions_count: int = 0,
        flaky_tests_count: int = 0,
        assessment_id: Optional[str] = None,
    ) -> QualityAssessment:
        aid = assessment_id or f"qass-{uuid.uuid4().hex[:8]}"

        has_blocker = any(d.severity in (DefectSeverity.BLOCKER, DefectSeverity.CRITICAL) for d in unresolved_defects)
        defect_count = len(unresolved_defects)

        # Multi-dimensional scoring
        dim_scores = {
            "functional_correctness": round(functional_pass_rate, 2),
            "coverage_integrity": round(coverage_score, 2),
            "stability_index": max(round(1.0 - (flaky_tests_count * 0.1), 2), 0.0),
            "regression_penalty": max(round(1.0 - (regressions_count * 0.2), 2), 0.0),
        }

        # Quality tier assignment
        if has_blocker or regressions_count > 0:
            tier = QualityTier.UNACCEPTABLE
            overall = min(functional_pass_rate, 0.49)
            notes = "Unacceptable: critical blocker or unaddressed regressions detected."
        elif functional_pass_rate >= 0.95 and defect_count == 0 and coverage_score >= 0.80:
            tier = QualityTier.PRODUCTION_READY
            overall = round((functional_pass_rate * 0.5) + (coverage_score * 0.3) + (dim_scores["stability_index"] * 0.2), 2)
            notes = "Production Ready: all acceptance criteria verified without unresolved defects."
        elif functional_pass_rate >= 0.85:
            tier = QualityTier.CONDITIONALLY_QUALIFIED
            overall = round((functional_pass_rate * 0.6) + (coverage_score * 0.4), 2)
            notes = "Conditionally qualified: non-critical warnings or minor test gaps present."
        else:
            tier = QualityTier.DEGRADED
            overall = round(functional_pass_rate * 0.6, 2)
            notes = "Degraded: significant test failures observed."

        assessment = QualityAssessment(
            assessment_id=aid,
            project_id=project_id,
            mission_id=mission_id,
            tier=tier,
            overall_score=overall,
            functional_pass_rate=functional_pass_rate,
            coverage_score=coverage_score,
            unresolved_defects_count=defect_count,
            regressions_count=regressions_count,
            flaky_tests_count=flaky_tests_count,
            dimension_scores=dim_scores,
            summary_notes=notes,
        )
        self.repo.save_quality_assessment(assessment)
        logger.info(
            f"Quality assessment '{aid}' for project '{project_id}': Tier={tier.value}, Overall={overall}"
        )
        return assessment
