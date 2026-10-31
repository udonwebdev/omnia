"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Progress Measurement Engine & Performance Variance Analyzer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from goals.models import (
    GoalProgressAssessment,
)
from goals.outcomes import OutcomeDefinitionEngine
from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Progress")


class ProgressMeasurementEngine:
    """
    Evaluates both reported task/milestone progress and verified outcome achievement.
    Identifies 'busywork variance' where 90% of tasks report completion but 0% of verified outcomes have moved.
    """

    def __init__(
        self,
        repository: Optional[GoalRepository] = None,
        outcomes_engine: Optional[OutcomeDefinitionEngine] = None,
    ):
        self.repo = repository or GoalRepository()
        self.engine = outcomes_engine or OutcomeDefinitionEngine(self.repo)

    def assess_progress(
        self,
        goal_id: str,
        schedule_variance_days: float = 0.0,
        budget_variance_ratio: float = 0.0,
    ) -> GoalProgressAssessment:
        """
        Calculates:
        1. Reported Task Progress: ratio of completed milestones & initiatives.
        2. Verified Outcome Progress: average normalized progress across verified key results.
        3. Activity-to-Outcome Variance: (reported - verified). High values expose deceptive busywork.
        """
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        # Task/Milestone Progress
        milestones = self.repo.list_milestones(goal_id)
        if milestones:
            completed_ms = sum(1 for ms in milestones if ms.status == "ACHIEVED")
            task_progress = completed_ms / len(milestones)
        else:
            task_progress = 0.0

        # Verified Key Results Progress
        key_results = self.repo.list_key_results(goal_id)
        if key_results:
            total_verified_progress = sum(
                self.engine.calculate_progress_ratio(kr, kr.current_verified_value)
                for kr in key_results
            )
            verified_progress = total_verified_progress / len(key_results)
        else:
            verified_progress = 0.0

        variance = task_progress - verified_progress

        assessment = GoalProgressAssessment(
            assessment_id=f"prog-{uuid.uuid4().hex[:8]}",
            goal_id=goal_id,
            reported_task_progress=round(task_progress, 4),
            verified_outcome_progress=round(verified_progress, 4),
            activity_to_outcome_variance=round(variance, 4),
            schedule_variance_days=schedule_variance_days,
            budget_variance_ratio=budget_variance_ratio,
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_progress_assessment(assessment)
        logger.info(
            f"Assessed goal '{goal_id}': Reported={task_progress:.2%}, Verified={verified_progress:.2%}, Variance={variance:.2%}"
        )
        return assessment
