"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Behavioral Baseline Engine - baselines.py
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from secops.models import BaselineStatus, BehavioralBaseline
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.Baselines")


class BehavioralBaselineEngine:
    """
    Computes and maintains rolling statistical profiles for users, service accounts, and workloads.
    Handles cold-start marking, Welford's algorithm for online variance/mean tracking, and anomaly z-score tests.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def update_entity_metric(
        self,
        entity_id: str,
        entity_type: str,
        metric_name: str,
        observed_value: float,
    ) -> BehavioralBaseline:
        baseline = self.repo.get_baseline(entity_id, metric_name)
        now_iso = datetime.now(timezone.utc).isoformat()

        if not baseline:
            bid = f"base-{uuid.uuid4().hex[:8]}"
            baseline = BehavioralBaseline(
                baseline_id=bid,
                entity_id=entity_id,
                entity_type=entity_type,
                metric_name=metric_name,
                rolling_mean=observed_value,
                rolling_stddev=0.0,
                sample_count=1,
                confidence_level=0.1,  # Initial cold-start confidence
                status=BaselineStatus.COLD_START,
                seasonality_model={"baseline_observations": [observed_value]},
                first_seen_at=now_iso,
                last_updated_at=now_iso,
            )
            self.repo.save_baseline(baseline)
            return baseline

        # Welford's algorithm for online mean and sample variance
        n = baseline.sample_count + 1
        delta = observed_value - baseline.rolling_mean
        new_mean = baseline.rolling_mean + (delta / n)
        delta2 = observed_value - new_mean

        # Variance estimate
        old_var = baseline.rolling_stddev ** 2
        new_var = ((old_var * (n - 2)) + (delta * delta2)) / (n - 1) if n > 1 else 0.0
        new_stddev = math.sqrt(max(0.0, new_var))

        baseline.rolling_mean = new_mean
        baseline.rolling_stddev = new_stddev
        baseline.sample_count = n
        baseline.last_updated_at = now_iso

        # Update status and confidence based on sample sufficiency
        if n < 5:
            baseline.status = BaselineStatus.COLD_START
            baseline.confidence_level = min(0.3, n * 0.06)
        elif n < 20:
            baseline.status = BaselineStatus.LEARNING
            baseline.confidence_level = min(0.7, 0.3 + (n * 0.02))
        else:
            baseline.status = BaselineStatus.ESTABLISHED
            baseline.confidence_level = 0.95

        self.repo.save_baseline(baseline)
        return baseline

    def evaluate_anomaly(
        self,
        entity_id: str,
        metric_name: str,
        observed_value: float,
        z_threshold: float = 3.0,
    ) -> Tuple[bool, float, float]:
        """
        Calculates Z-score deviation against established baseline.
        Returns (is_anomaly, z_score, confidence).
        Cold-start entities with insufficient samples return False to avoid false positives.
        """
        baseline = self.repo.get_baseline(entity_id, metric_name)
        if not baseline or baseline.sample_count < 5 or baseline.rolling_stddev <= 0.0001:
            return False, 0.0, baseline.confidence_level if baseline else 0.0

        z_score = abs(observed_value - baseline.rolling_mean) / baseline.rolling_stddev
        is_anomaly = bool(z_score >= z_threshold and baseline.confidence_level >= 0.5)

        return is_anomaly, z_score, baseline.confidence_level
