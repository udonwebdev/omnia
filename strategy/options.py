"""
OMNIA Module 37: Strategic Options Generator
Compiles plausible alternatives, enforces baseline (status-quo) presence,
and integrates upstream forecast/simulation/research inputs.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    StrategicOptionRecord,
)
from strategy.persistence import StrategyRepository

logger = logging.getLogger("Omnia.Strategy.Options")


class StrategicOptionsGenerator:
    """Manages creation and organization of candidate options for a decision case."""

    def __init__(self, repo: StrategyRepository):
        self.repo = repo

    def register_option(
        self,
        case_id: str,
        title: str,
        description: str,
        is_baseline: bool,
        expected_outcome: str,
        estimated_cost: float,
        implementation_complexity: str = "MEDIUM",
        reversibility_score: float = 0.8,
        time_horizon_days: int = 30,
        dependencies: Optional[List[str]] = None,
        benefits: Optional[List[str]] = None,
        disadvantages: Optional[List[str]] = None,
        critical_assumptions: Optional[List[str]] = None,
        known_limitations: Optional[List[str]] = None,
        origin: str = "HUMAN_PROPOSAL",
    ) -> StrategicOptionRecord:
        """Registers a candidate strategic alternative."""
        if not title or len(title.strip()) < 3:
            raise ValueError("Option title must be at least 3 characters")

        option_id = f"opt-{uuid.uuid4().hex[:8]}"
        option = StrategicOptionRecord(
            option_id=option_id,
            case_id=case_id,
            title=title.strip(),
            description=description.strip(),
            is_baseline=is_baseline,
            expected_outcome=expected_outcome.strip(),
            estimated_cost=estimated_cost,
            implementation_complexity=implementation_complexity,
            reversibility_score=max(0.0, min(1.0, reversibility_score)),
            time_horizon_days=time_horizon_days,
            dependencies=dependencies or [],
            benefits=benefits or [],
            disadvantages=disadvantages or [],
            critical_assumptions=critical_assumptions or [],
            known_limitations=known_limitations or [],
            origin=origin,
        )
        self.repo.save_option(option)
        logger.info(f"Registered option '{option_id}' ({option.title}) for case '{case_id}' [Baseline: {is_baseline}]")
        return option

    def ensure_baseline_option(
        self,
        case_id: str,
        status_quo_description: str = "Maintain current architecture and operating model without intervention",
        status_quo_cost: float = 0.0,
    ) -> StrategicOptionRecord:
        """Ensures that a baseline/status-quo option exists in the decision set."""
        options = self.repo.list_options_for_case(case_id)
        for opt in options:
            if opt.is_baseline:
                return opt

        return self.register_option(
            case_id=case_id,
            title="Status Quo (No Action)",
            description=status_quo_description,
            is_baseline=True,
            expected_outcome="Current performance, risks, and failure modes persist without change",
            estimated_cost=status_quo_cost,
            implementation_complexity="LOW",
            reversibility_score=1.0,
            time_horizon_days=0,
            dependencies=[],
            benefits=["Zero implementation friction", "No immediate capital expenditure"],
            disadvantages=["Unmitigated risk exposure", "Failure to capture emerging optimization benefits"],
            critical_assumptions=["External operational parameters remain stationary"],
            known_limitations=["Subject to compounding technical debt and drift"],
            origin="GENERATED_BASELINE",
        )
