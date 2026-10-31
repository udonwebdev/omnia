"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Outcome Definition Engine & Key Result Manager.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from goals.models import (
    KeyResultDefinition,
    MetricType,
    VerificationTier,
)
from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Outcomes")


class OutcomeDefinitionEngine:
    """Manages Key Result definitions, validation rules, and progress calculations."""

    def __init__(self, repository: Optional[GoalRepository] = None):
        self.repo = repository or GoalRepository()

    def register_key_result(
        self,
        goal_id: str,
        metric_name: str,
        description: str,
        unit: str,
        metric_type: MetricType,
        baseline_value: float,
        target_value: float,
        measurement_frequency: str = "DAILY",
        calculation_method: str = "DIRECT",
        required_verification_tier: VerificationTier = VerificationTier.SYSTEM_OBSERVED,
        key_result_id: Optional[str] = None,
    ) -> KeyResultDefinition:
        """Registers a measurable key result definition for a given goal."""
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        # Validation rules
        if metric_type == MetricType.INCREASING and target_value <= baseline_value:
            raise ValueError(f"For INCREASING metric, target ({target_value}) must be greater than baseline ({baseline_value}).")
        if metric_type == MetricType.DECREASING and target_value >= baseline_value:
            raise ValueError(f"For DECREASING metric, target ({target_value}) must be less than baseline ({baseline_value}).")
        if metric_type == MetricType.BINARY and target_value not in (0.0, 1.0):
            raise ValueError(f"BINARY metric target must be 0.0 or 1.0 (got {target_value}).")

        krid = key_result_id or f"kr-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        kr = KeyResultDefinition(
            key_result_id=krid,
            goal_id=goal_id,
            metric_name=metric_name,
            description=description,
            unit=unit,
            metric_type=metric_type,
            baseline_value=baseline_value,
            target_value=target_value,
            current_reported_value=baseline_value,
            current_verified_value=baseline_value,
            measurement_frequency=measurement_frequency,
            calculation_method=calculation_method,
            required_verification_tier=required_verification_tier,
            confidence=1.0,
            is_satisfied=False,
            last_updated=now,
        )
        self.repo.save_key_result(kr)
        logger.info(f"Registered Key Result '{krid}' for goal '{goal_id}': {metric_name} [{metric_type.value}]")
        return kr

    def calculate_progress_ratio(self, kr: KeyResultDefinition, value: float) -> float:
        """
        Calculates normalized progress (0.0 to 1.0) strictly adhering to metric semantics.
        Never allows negative progress or infinite ratios.
        """
        if kr.metric_type == MetricType.INCREASING:
            span = kr.target_value - kr.baseline_value
            if span == 0:
                return 1.0 if value >= kr.target_value else 0.0
            ratio = (value - kr.baseline_value) / span
            return max(0.0, min(1.0, ratio))

        elif kr.metric_type == MetricType.DECREASING:
            span = kr.baseline_value - kr.target_value
            if span == 0:
                return 1.0 if value <= kr.target_value else 0.0
            # For lower-is-better, if value dropped from 100 to 20 (target 10):
            # progress is (100 - 20) / (100 - 10) = 80 / 90 = 0.888
            ratio = (kr.baseline_value - value) / span
            return max(0.0, min(1.0, ratio))

        elif kr.metric_type in (MetricType.THRESHOLD, MetricType.BINARY):
            if kr.metric_type == MetricType.BINARY:
                return 1.0 if value >= 1.0 else 0.0
            # Threshold: check if target is met
            if kr.target_value >= kr.baseline_value:
                return 1.0 if value >= kr.target_value else 0.0
            else:
                return 1.0 if value <= kr.target_value else 0.0

        elif kr.metric_type in (MetricType.MILESTONE, MetricType.QUALITATIVE, MetricType.COMPOSITE):
            span = kr.target_value - kr.baseline_value
            if span == 0:
                return 1.0 if value >= kr.target_value else 0.0
            ratio = (value - kr.baseline_value) / span
            return max(0.0, min(1.0, ratio))

        return 0.0

    def evaluate_key_result_satisfaction(self, kr: KeyResultDefinition) -> bool:
        """Evaluates whether the key result is satisfied based strictly on verified value."""
        progress = self.calculate_progress_ratio(kr, kr.current_verified_value)
        return progress >= 1.0
