"""
OMNIA Module 37: Decision Case Manager
Manages the lifecycle, versions, stakeholder scoping, and constraints of strategic decision cases.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    DecisionCaseRecord,
    DecisionLifecycleState,
)
from strategy.persistence import StrategyRepository

logger = logging.getLogger("Omnia.Strategy.Cases")


class DecisionCaseManager:
    """Orchestrates decision case initialization, lifecycle transitions, and version bumps."""

    def __init__(self, repo: StrategyRepository):
        self.repo = repo

    def create_case(
        self,
        title: str,
        description: str,
        owner_id: str,
        category: str = "INFRASTRUCTURE_ARCHITECTURE",
        deadline_ts: Optional[float] = None,
        context: Optional[Dict[str, Any]] = None,
        desired_outcomes: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        available_resources: Optional[Dict[str, Any]] = None,
        stakeholders: Optional[List[str]] = None,
        risk_tolerance: str = "MEDIUM",
    ) -> DecisionCaseRecord:
        """Initializes a new strategic decision case in DRAFT state."""
        if not title or len(title.strip()) < 5:
            raise ValueError("Decision case title must be at least 5 characters")

        case_id = f"case-{uuid.uuid4().hex[:8]}"
        case = DecisionCaseRecord(
            case_id=case_id,
            title=title.strip(),
            description=description.strip(),
            owner_id=owner_id,
            category=category,
            deadline_ts=deadline_ts,
            context=context or {},
            desired_outcomes=desired_outcomes or [],
            constraints=constraints or [],
            available_resources=available_resources or {},
            stakeholders=stakeholders or [owner_id],
            risk_tolerance=risk_tolerance,
            version=1,
            state=DecisionLifecycleState.DRAFT,
        )
        self.repo.save_case(case)
        logger.info(f"Created decision case '{case_id}': {case.title} [{case.category}]")
        return case

    def transition_state(
        self,
        case_id: str,
        new_state: DecisionLifecycleState,
        operator_id: Optional[str] = None,
    ) -> DecisionCaseRecord:
        """Transitions case state machine with audit verification."""
        case = self.repo.get_case(case_id)
        if not case:
            raise ValueError(f"Decision case '{case_id}' not found")

        prev_state = case.state
        case.state = new_state
        case.updated_at = time.time()
        self.repo.save_case(case)
        logger.info(f"Transitioned case '{case_id}' from {prev_state.value} to {new_state.value} (Operator: {operator_id})")
        return case

    def bump_version(self, case_id: str, reason: str = "Reassessment triggered") -> DecisionCaseRecord:
        """Bumps case version upon material reassessment without rewriting history."""
        case = self.repo.get_case(case_id)
        if not case:
            raise ValueError(f"Decision case '{case_id}' not found")

        case.version += 1
        case.state = DecisionLifecycleState.REOPENED
        case.updated_at = time.time()
        self.repo.save_case(case)
        logger.info(f"Bumped version for case '{case_id}' to v{case.version}. Reason: {reason}")
        return case
