"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Goal Health Monitor: Multi-State Diagnostic Health & Trajectory Analysis.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from goals.models import (
    GoalHealthRecord,
    GoalHealthState,
    GoalLifecycleState,
)
from goals.persistence import GoalRepository
from goals.progress import ProgressMeasurementEngine

logger = logging.getLogger("Omnia.Goals.Health")


class GoalHealthMonitor:
    """
    Evaluates real-time goal health across 9 distinct states based on hard evidence.
    Never assumes HEALTHY without evidence (defaults to UNKNOWN).
    """

    def __init__(
        self,
        repository: Optional[GoalRepository] = None,
        progress_engine: Optional[ProgressMeasurementEngine] = None,
    ):
        self.repo = repository or GoalRepository()
        self.progress_engine = progress_engine or ProgressMeasurementEngine(self.repo)

    def evaluate_goal_health(self, goal_id: str) -> GoalHealthRecord:
        """Evaluates goal health strictly from evidence, metrics, and milestones."""
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        # Check terminal states
        if goal.state == GoalLifecycleState.COMPLETED:
            return self._record_health(goal_id, GoalHealthState.COMPLETED, "Goal successfully verified completed", "STABLE")
        if goal.state == GoalLifecycleState.CANCELLED:
            return self._record_health(goal_id, GoalHealthState.CANCELLED, "Goal was cancelled by operator", "STABLE")

        key_results = self.repo.list_key_results(goal_id)
        milestones = self.repo.list_milestones(goal_id)
        # Fetch latest progress snapshot if already computed, else assess with defaults
        progress = self.repo.get_latest_progress_assessment(goal_id) or self.progress_engine.assess_progress(goal_id)

        risk_factors: List[str] = []
        stale_metric_count = 0
        blocked_count = 0

        # If no key results are configured, state is UNKNOWN / NEEDS_REVIEW
        if not key_results:
            return self._record_health(
                goal_id,
                GoalHealthState.UNKNOWN,
                "No Key Results defined. Insufficient evidence to determine health.",
                "STABLE",
                risk_factors=["Unmeasured objective"],
            )

        # Check milestone statuses
        missed_milestones = [m for m in milestones if m.status == "MISSED"]
        if missed_milestones:
            risk_factors.append(f"{len(missed_milestones)} missed milestones detected.")

        # Check activity vs outcome variance (Busywork detection)
        if progress.activity_to_outcome_variance > 0.40 and progress.reported_task_progress > 0.50:
            risk_factors.append(
                f"Severe activity-to-outcome divergence: reported task progress ({progress.reported_task_progress:.1%}) drastically outpaces verified outcome ({progress.verified_outcome_progress:.1%})."
            )

        # Check schedule or budget slippage
        if progress.schedule_variance_days > 14:
            risk_factors.append(f"Schedule delayed by {progress.schedule_variance_days:.1f} days.")
        if progress.budget_variance_ratio > 0.25:
            risk_factors.append(f"Budget overrun of {progress.budget_variance_ratio:.1%}.")

        # Classify Health State
        if len(missed_milestones) >= 2 or progress.schedule_variance_days >= 21 or progress.budget_variance_ratio > 0.40:
            state = GoalHealthState.OFF_TRACK
            reason = "Significant schedule or budget variance with operational execution delays."
            trajectory = "DECLINING"
        elif risk_factors:
            state = GoalHealthState.AT_RISK
            reason = f"Operational risks detected: {'; '.join(risk_factors[:2])}"
            trajectory = "DECLINING"
        elif progress.verified_outcome_progress >= 1.0:
            state = GoalHealthState.COMPLETED
            reason = "All verified key results have achieved their targets."
            trajectory = "IMPROVING"
        else:
            state = GoalHealthState.HEALTHY
            reason = "All key results and milestones progressing within acceptable variance."
            trajectory = "IMPROVING"

        return self._record_health(
            goal_id,
            state,
            reason,
            trajectory,
            risk_factors=risk_factors,
            stale_metric_count=stale_metric_count,
            blocked_dependency_count=blocked_count,
        )

    def _record_health(
        self,
        goal_id: str,
        state: GoalHealthState,
        reason: str,
        trajectory: str,
        risk_factors: Optional[List[str]] = None,
        stale_metric_count: int = 0,
        blocked_dependency_count: int = 0,
    ) -> GoalHealthRecord:
        record = GoalHealthRecord(
            health_id=f"hlth-{uuid.uuid4().hex[:8]}",
            goal_id=goal_id,
            health_state=state,
            primary_reason=reason,
            progress_trajectory=trajectory,
            risk_factors=risk_factors or [],
            stale_metric_count=stale_metric_count,
            blocked_dependency_count=blocked_dependency_count,
            confidence_score=1.0 if state != GoalHealthState.UNKNOWN else 0.5,
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_health_record(record)
        logger.info(f"Goal '{goal_id}' health assessed as {state.value} ({trajectory}): {reason}")
        return record
