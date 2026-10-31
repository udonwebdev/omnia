"""
OMNIA Module 37: Decision Monitoring & Reassessment Scheduler
Tracks post-decision operational outcomes, measures variance against expectations,
detects invalidated assumptions, and triggers structured reassessments.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    DecisionOutcomeMonitoring,
    DecisionLifecycleState,
)
from strategy.persistence import StrategyRepository

logger = logging.getLogger("Omnia.Strategy.Monitoring")


class DecisionMonitoringService:
    """Tracks implementation of human decisions and triggers reassessments when drift occurs."""

    def __init__(self, repo: StrategyRepository):
        self.repo = repo

    def record_outcome(
        self,
        case_id: str,
        selected_option_id: str,
        actual_cost: Optional[float] = None,
        expected_cost: Optional[float] = None,
        assumptions_status: Optional[Dict[str, bool]] = None,  # assumption_str -> is_valid
        critical_drift_detected: bool = False,
    ) -> DecisionOutcomeMonitoring:
        """
        Records operational reality against decision expectations:
        Triggers reassessment if cost variance > 30% or critical assumptions fail.
        """
        case = self.repo.get_case(case_id)
        if not case:
            raise ValueError(f"Decision case '{case_id}' not found")

        # Compute cost variance
        variance_pct = 0.0
        if actual_cost is not None and expected_cost is not None and expected_cost > 0:
            variance_pct = round(((actual_cost - expected_cost) / expected_cost) * 100.0, 1)

        invalidated = []
        if assumptions_status:
            invalidated = [assump for assump, valid in assumptions_status.items() if not valid]

        assumptions_still_valid = len(invalidated) == 0

        # Trigger reassessment if threshold exceeded
        reassessment_needed = (abs(variance_pct) >= 30.0) or (not assumptions_still_valid) or critical_drift_detected
        reason = None
        if reassessment_needed:
            reasons = []
            if abs(variance_pct) >= 30.0:
                reasons.append(f"Cost variance {variance_pct}% exceeds +/-30% threshold")
            if not assumptions_still_valid:
                reasons.append(f"Invalidated assumptions: {invalidated}")
            if critical_drift_detected:
                reasons.append("External operational environment experienced critical drift")
            reason = "; ".join(reasons)

            # Transition case to REOPENED state
            case.state = DecisionLifecycleState.REOPENED
            case.version += 1
            case.updated_at = time.time()
            self.repo.save_case(case)
            logger.warning(f"Reassessment triggered for case '{case_id}': {reason}")

        monitoring = DecisionOutcomeMonitoring(
            monitoring_id=f"mon-{uuid.uuid4().hex[:8]}",
            case_id=case_id,
            selected_option_id=selected_option_id,
            actual_cost=actual_cost,
            expected_vs_actual_variance_pct=variance_pct,
            assumptions_still_valid=assumptions_still_valid,
            invalidated_assumptions=invalidated,
            reassessment_triggered=reassessment_needed,
            reassessment_reason=reason,
        )
        self.repo.save_outcome_monitoring(monitoring)
        return monitoring
