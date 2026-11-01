"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Resilience Regression Detector: Historical Tracking & Degradation Alerting.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from reliability_engineering.models import (
    ResilienceRegressionRecord,
)
from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.Regression")


class ResilienceRegressionDetector:
    """
    Monitors reliability metrics over time to identify regressions where previously
    demonstrated recovery capabilities stop meeting objectives.
    """

    def __init__(self, repository: Optional[ReliabilityRepository] = None):
        self.repo = repository or ReliabilityRepository()

    def check_for_regression(
        self,
        component_id: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        threshold_degradation_pct: float = 20.0,
    ) -> Optional[ResilienceRegressionRecord]:
        """
        Detects if current recovery time or error rate has degraded significantly relative to baseline.
        """
        if baseline_value <= 0.0:
            return None

        # For recovery time / latency: higher current_value is a regression
        degradation_pct = ((current_value - baseline_value) / baseline_value) * 100.0
        if degradation_pct >= threshold_degradation_pct:
            rid = f"reg-{uuid.uuid4().hex[:8]}"
            record = ResilienceRegressionRecord(
                regression_id=rid,
                component_id=component_id,
                metric_name=metric_name,
                baseline_value=baseline_value,
                current_value=current_value,
                degradation_pct=round(degradation_pct, 2),
            )
            self.repo.save_resilience_regression(record)
            logger.warning(
                f"Resilience regression detected on '{component_id}' for '{metric_name}': "
                f"+{round(degradation_pct, 1)}% degradation (Baseline={baseline_value}, Current={current_value})"
            )
            return record
        return None

    def list_regressions(self) -> List[ResilienceRegressionRecord]:
        return self.repo.list_resilience_regressions()
