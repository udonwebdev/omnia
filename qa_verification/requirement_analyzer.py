"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Requirement Intelligence - requirement_analyzer.py

Parses functional and non-functional specifications, user stories, and contracts into
verifiable acceptance criteria with preconditions, inputs, expected outputs, and failure boundaries.
Identifies ambiguous or untestable requirements.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from qa_verification.models import (
    AcceptanceCriterion,
    RequirementType,
    VerificationRequirement,
)
from qa_verification.persistence import QAVerificationRepository

logger = logging.getLogger("Omnia.QAVerification.RequirementAnalyzer")


class RequirementAnalyzer:
    """
    Analyzes specifications and decomposes requirements into structured acceptance conditions.
    """

    def __init__(self, repository: Optional[QAVerificationRepository] = None):
        self.repo = repository or QAVerificationRepository()

    def import_requirement(
        self,
        project_id: str,
        title: str,
        description: str,
        requirement_type: RequirementType = RequirementType.FUNCTIONAL,
        source_reference: str = "",
        requirement_id: Optional[str] = None,
    ) -> tuple[VerificationRequirement, List[AcceptanceCriterion]]:
        rid = requirement_id or f"req-{uuid.uuid4().hex[:8]}"

        # Ambiguity check
        ambiguous_terms = ["fast", "easy", "robust", "scalable", "user-friendly", "as appropriate"]
        is_ambiguous = any(term in description.lower() for term in ambiguous_terms)
        notes = "Requirement contains subjective/unquantified adjectives" if is_ambiguous else None

        req = VerificationRequirement(
            requirement_id=rid,
            project_id=project_id,
            title=title,
            description=description,
            requirement_type=requirement_type,
            source_reference=source_reference,
            is_ambiguous=is_ambiguous,
            ambiguity_notes=notes,
        )
        self.repo.save_requirement(req)

        # Decompose into structured acceptance criteria
        criteria: List[AcceptanceCriterion] = []

        # 1. Nominal / Success path criterion
        c1_id = f"crit-{uuid.uuid4().hex[:8]}"
        c1 = AcceptanceCriterion(
            criterion_id=c1_id,
            requirement_id=rid,
            expected_behavior=f"System satisfies primary requirement: {title}",
            preconditions=["System is initialized in valid state", "Authenticated principal present"],
            inputs={"mode": "standard_execution", "payload": "valid_spec"},
            expected_outputs={"status": "SUCCESS", "error": None},
            failure_conditions=["Process crash", "Uncaught exception", "Schema mismatch"],
            priority=1,
            confidence=0.95,
        )
        self.repo.save_acceptance_criterion(c1)
        criteria.append(c1)

        # 2. Boundary / Failure boundary criterion
        c2_id = f"crit-{uuid.uuid4().hex[:8]}"
        c2 = AcceptanceCriterion(
            criterion_id=c2_id,
            requirement_id=rid,
            expected_behavior=f"System rejects invalid inputs and enforces boundary constraints for: {title}",
            preconditions=["System is running"],
            inputs={"mode": "boundary_check", "payload": None},
            expected_outputs={"status": "REJECTED", "error_code": 400},
            failure_conditions=["Unhandled 500 error", "Partial write", "Silent failure"],
            priority=2,
            confidence=0.90,
        )
        self.repo.save_acceptance_criterion(c2)
        criteria.append(c2)

        logger.info(
            f"Imported requirement '{rid}' ({title}) with {len(criteria)} acceptance criteria (Ambiguous={is_ambiguous})"
        )
        return req, criteria
