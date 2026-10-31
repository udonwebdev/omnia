"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Strategic Outcome Reporting: Portfolio Summaries & Briefing Synthesis Bridging.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from goals.models import GoalLifecycleState
from goals.persistence import GoalRepository
from goals.progress import ProgressMeasurementEngine

logger = logging.getLogger("Omnia.Goals.Reporting")


class StrategicOutcomeReporter:
    """Generates structured outcome performance reports for individual goals and portfolios."""

    def __init__(
        self,
        repository: Optional[GoalRepository] = None,
        progress_engine: Optional[ProgressMeasurementEngine] = None,
    ):
        self.repo = repository or GoalRepository()
        self.progress_engine = progress_engine or ProgressMeasurementEngine(self.repo)

    def generate_goal_report(self, goal_id: str) -> Dict[str, Any]:
        """Compiles a complete strategic report for a single goal."""
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        progress = self.progress_engine.assess_progress(goal_id)
        health = self.repo.get_latest_health_record(goal_id)
        krs = self.repo.list_key_results(goal_id)
        initiatives = self.repo.list_initiatives(goal_id)
        milestones = self.repo.list_milestones(goal_id)
        actions = self.repo.list_corrective_actions(goal_id)

        return {
            "goal_id": goal.goal_id,
            "title": goal.title,
            "purpose": goal.purpose,
            "owner": goal.owner,
            "priority": goal.priority.value,
            "state": goal.state.value,
            "target_date": goal.target_date,
            "health_state": health.health_state.value if health else "UNKNOWN",
            "health_reason": health.primary_reason if health else "No assessment available",
            "reported_task_progress": progress.reported_task_progress,
            "verified_outcome_progress": progress.verified_outcome_progress,
            "activity_to_outcome_variance": progress.activity_to_outcome_variance,
            "key_results": [
                {
                    "key_result_id": kr.key_result_id,
                    "metric_name": kr.metric_name,
                    "unit": kr.unit,
                    "baseline": kr.baseline_value,
                    "target": kr.target_value,
                    "reported": kr.current_reported_value,
                    "verified": kr.current_verified_value,
                    "is_satisfied": kr.is_satisfied,
                }
                for kr in krs
            ],
            "initiatives_count": len(initiatives),
            "milestones_count": len(milestones),
            "active_corrective_actions": len([a for a in actions if a.status == "PROPOSED"]),
        }

    def generate_portfolio_report(self) -> Dict[str, Any]:
        """Compiles high-level strategic portfolio performance across all active goals."""
        active_goals = self.repo.list_goals(state=GoalLifecycleState.ACTIVE)
        draft_goals = self.repo.list_goals(state=GoalLifecycleState.DRAFT)
        completed_goals = self.repo.list_goals(state=GoalLifecycleState.COMPLETED)

        goal_summaries = []
        for g in active_goals:
            health = self.repo.get_latest_health_record(g.goal_id)
            prog = self.repo.get_latest_progress_assessment(g.goal_id)
            goal_summaries.append({
                "goal_id": g.goal_id,
                "title": g.title,
                "priority": g.priority.value,
                "target_date": g.target_date,
                "health": health.health_state.value if health else "UNKNOWN",
                "verified_progress": prog.verified_outcome_progress if prog else 0.0,
            })

        return {
            "total_goals_count": len(active_goals) + len(draft_goals) + len(completed_goals),
            "active_goals_count": len(active_goals),
            "completed_goals_count": len(completed_goals),
            "active_portfolio_goals": goal_summaries,
        }
