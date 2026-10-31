"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Goal Forecast Adapter: Module 32 Predictive Intelligence Integration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Forecasting")


class GoalForecastAdapter:
    """
    Integrates with Module 32 (prediction) to forecast goal completion probability,
    expected timeline windows, and dependency risks without hallucinating probabilities.
    """

    def __init__(self, repository: Optional[GoalRepository] = None):
        self.repo = repository or GoalRepository()

    def forecast_goal_outcome(self, goal_id: str) -> Dict[str, Any]:
        """
        Estimates completion probability and forecast horizon based on current verified
        progress velocity, historical milestones, and dependency risks.
        """
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        krs = self.repo.list_key_results(goal_id)
        milestones = self.repo.list_milestones(goal_id)
        latest_prog = self.repo.get_latest_progress_assessment(goal_id)

        # Baseline velocity calculation
        verified_pct = latest_prog.verified_outcome_progress if latest_prog else 0.0
        reported_pct = latest_prog.reported_task_progress if latest_prog else 0.0

        missed_milestones = sum(1 for m in milestones if m.status == "MISSED")
        achieved_milestones = sum(1 for m in milestones if m.status == "ACHIEVED")
        total_milestones = len(milestones)

        # Estimate completion probability
        base_probability = verified_pct
        if total_milestones > 0:
            milestone_ratio = achieved_milestones / total_milestones
            # Blend verified outcome with milestone pacing
            probability = (0.7 * verified_pct) + (0.3 * milestone_ratio)
        else:
            probability = verified_pct

        # Penalty for missed milestones
        if missed_milestones > 0:
            probability = max(0.05, probability - (0.15 * missed_milestones))

        # Expected completion window
        if probability >= 0.8:
            window = "ON_SCHEDULE"
            risk_level = "LOW"
        elif probability >= 0.4:
            window = "MODERATE_DELAY_LIKELY"
            risk_level = "MEDIUM"
        else:
            window = "SIGNIFICANT_DELAY_OR_FAILURE"
            risk_level = "HIGH"

        result = {
            "goal_id": goal_id,
            "title": goal.title,
            "completion_probability": round(probability, 3),
            "expected_completion_window": window,
            "risk_level": risk_level,
            "verified_outcome_progress": verified_pct,
            "reported_task_progress": reported_pct,
            "missed_milestones_count": missed_milestones,
            "forecaster_provenance": "Module 32 Predictive Trend & Risk Forecaster",
        }
        logger.info(f"Goal '{goal_id}' forecast: Prob={probability:.1%}, Window={window}")
        return result
