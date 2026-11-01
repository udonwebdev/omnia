"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Test Intelligence & Strategy Synthesis - test_intelligence.py

Constructs risk-weighted verification strategies mapping requirements and acceptance criteria
to target verification categories (Unit, Contract, Database, UI, Fuzz, Performance).
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from qa_verification.models import (
    RequirementType,
    TestCategory,
    TestStrategy,
    VerificationRequirement,
)
from qa_verification.persistence import QAVerificationRepository

logger = logging.getLogger("Omnia.QAVerification.TestIntelligence")


class TestIntelligenceEngine:
    """
    Synthesizes risk-weighted testing plans based on requirement complexity and category.
    """

    def __init__(self, repository: Optional[QAVerificationRepository] = None):
        self.repo = repository or QAVerificationRepository()

    def generate_strategy(
        self,
        project_id: str,
        name: str,
        requirements: List[VerificationRequirement],
        allocated_budget_seconds: float = 600.0,
        strategy_id: Optional[str] = None,
    ) -> TestStrategy:
        categories: set[TestCategory] = {TestCategory.UNIT, TestCategory.INTEGRATION}

        for r in requirements:
            if r.requirement_type == RequirementType.API_CONTRACT:
                categories.add(TestCategory.API_CONTRACT)
            elif r.requirement_type == RequirementType.DATA_INTEGRITY:
                categories.add(TestCategory.DATABASE_INTEGRITY)
            elif r.requirement_type == RequirementType.PERFORMANCE:
                categories.add(TestCategory.PERFORMANCE_LOAD)
            elif r.requirement_type == RequirementType.SECURITY:
                categories.add(TestCategory.SECURITY_AUDIT)
            elif r.requirement_type == RequirementType.UI_UX:
                categories.add(TestCategory.FRONTEND_UI)

        # Include Property/Fuzz testing for complex requirements
        categories.add(TestCategory.PROPERTY_FUZZ)

        sid = strategy_id or f"strat-{uuid.uuid4().hex[:8]}"
        risk_weighting = {c.value: (1.5 if c in (TestCategory.API_CONTRACT, TestCategory.SECURITY_AUDIT) else 1.0) for c in categories}

        strategy = TestStrategy(
            strategy_id=sid,
            project_id=project_id,
            name=name,
            target_categories=sorted(list(categories), key=lambda x: x.value),
            risk_weighting=risk_weighting,
            allocated_budget_seconds=allocated_budget_seconds,
        )
        self.repo.save_test_strategy(strategy)
        logger.info(f"Synthesized test strategy '{sid}' ({name}) with {len(categories)} target categories.")
        return strategy
