"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Failure Scenario Generator: Controlled Resilience Scenarios with Strict Safety Guards.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from reliability_engineering.models import (
    FailureScenarioRecord,
)
from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.Scenarios")


class FailureScenarioGenerator:
    """
    Synthesizes actionable resilience scenarios across application, infrastructure,
    distributed system, data, and external dependency failure domains.
    Enforces strict safety preconditions and blocks unsafe production targeting.
    """

    def __init__(self, repository: Optional[ReliabilityRepository] = None):
        self.repo = repository or ReliabilityRepository()

    def generate_scenario(
        self,
        title: str,
        category: str,
        affected_components: List[str],
        expected_behavior: str,
        target_environment: str = "ISOLATED_SANDBOX",
        injection_method: str = "SIMULATION",
        preconditions: Optional[List[str]] = None,
        safety_constraints: Optional[List[str]] = None,
        abort_conditions: Optional[List[str]] = None,
        scenario_id: Optional[str] = None,
    ) -> FailureScenarioRecord:
        """
        Creates a versioned failure scenario.
        Strict Safety Rule: Target environment cannot be PRODUCTION by default.
        """
        env = target_environment.upper()
        if "PROD" in env and "SANDBOX" not in env:
            raise PermissionError("SAFETY_GUARD: Destructive resilience scenarios cannot directly target production.")

        sid = scenario_id or f"scen-{uuid.uuid4().hex[:8]}"
        sc = FailureScenarioRecord(
            scenario_id=sid,
            title=title,
            category=category.upper(),
            target_environment=env,
            affected_components=affected_components,
            preconditions=preconditions or ["Baseline health verified green", "Backup validated"],
            injection_method=injection_method,
            safety_constraints=safety_constraints or ["Max timeout 300s", "Automated rollback enabled"],
            expected_behavior=expected_behavior,
            abort_conditions=abort_conditions or ["Cascading failure detected", "Data loss detected"],
        )
        self.repo.save_scenario(sc)
        logger.info(f"Generated failure scenario '{sid}': {title} [{category}]")
        return sc

    def get_scenario(self, scenario_id: str) -> Optional[FailureScenarioRecord]:
        return self.repo.get_scenario(scenario_id)
