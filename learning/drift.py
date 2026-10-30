"""
Omnia Module 33: Multi-Horizon Drift & Degradation Monitor
Monitors input distribution shifts, concept drift, and performance degradation.
Separates harmless world shifts from genuine behavioral degradation.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional

from learning.models import DriftRecord, DriftSeverity, DriftType


class DriftMonitor:
    """
    Detects data drift, concept drift, and model performance decay
    using statistical distance metrics (Population Stability Index).
    """

    def __init__(self) -> None:
        pass

    def evaluate_feature_drift(
        self,
        model_id: str,
        version_id: str,
        feature_name: str,
        baseline_distribution: List[float],
        current_distribution: List[float],
        psi_threshold_warning: float = 0.1,
        psi_threshold_critical: float = 0.25,
    ) -> DriftRecord:
        """
        Calculates Population Stability Index (PSI) between baseline and current distributions.
        """
        psi = self._compute_psi(baseline_distribution, current_distribution)

        if psi >= psi_threshold_critical:
            severity = DriftSeverity.CRITICAL
        elif psi >= psi_threshold_warning:
            severity = DriftSeverity.MEDIUM
        else:
            severity = DriftSeverity.LOW

        return DriftRecord(
            record_id=f"drift-feat-{feature_name}-{int(time.time())}",
            model_id=model_id,
            version_id=version_id,
            drift_type=DriftType.FEATURE_DRIFT,
            feature_or_metric=feature_name,
            baseline_value=0.0,
            observed_value=round(psi, 4),
            drift_metric_value=round(psi, 4),
            threshold=psi_threshold_warning,
            severity=severity,
            recommendation="RETRAIN_REQUIRED" if severity == DriftSeverity.CRITICAL else ("INVESTIGATE" if severity == DriftSeverity.MEDIUM else "CONTINUE_MONITORING"),
            assessed_at=time.time(),
        )

    def evaluate_performance_decay(
        self,
        model_id: str,
        version_id: str,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        decay_tolerance: float = 0.05,
    ) -> DriftRecord:
        """
        Evaluates whether a model or strategy's core metric has degraded past acceptable tolerance.
        """
        if baseline_value != 0:
            rel_drop = (baseline_value - current_value) / baseline_value
        else:
            rel_drop = 0.0

        if rel_drop > (decay_tolerance * 2):
            severity = DriftSeverity.CRITICAL
        elif rel_drop > decay_tolerance:
            severity = DriftSeverity.HIGH
        else:
            severity = DriftSeverity.LOW

        return DriftRecord(
            record_id=f"drift-perf-{metric_name}-{int(time.time())}",
            model_id=model_id,
            version_id=version_id,
            drift_type=DriftType.PERFORMANCE_DEGRADATION,
            feature_or_metric=metric_name,
            baseline_value=round(baseline_value, 4),
            observed_value=round(current_value, 4),
            drift_metric_value=round(rel_drop, 4),
            threshold=decay_tolerance,
            severity=severity,
            recommendation="TRIGGER_ROLLBACK" if severity == DriftSeverity.CRITICAL else ("SCHEDULE_EVALUATION" if severity == DriftSeverity.HIGH else "CONTINUE_MONITORING"),
            assessed_at=time.time(),
        )

    def _compute_psi(self, baseline: List[float], current: List[float], bins: int = 5) -> float:
        if not baseline or not current:
            return 0.0

        all_vals = sorted(baseline + current)
        min_v = all_vals[0]
        max_v = all_vals[-1]

        if min_v == max_v:
            return 0.0

        bin_width = (max_v - min_v) / bins
        bin_edges = [min_v + i * bin_width for i in range(bins + 1)]

        def get_counts(data: List[float]) -> List[int]:
            counts = [0] * bins
            for x in data:
                for i in range(bins):
                    if bin_edges[i] <= x <= bin_edges[i + 1]:
                        counts[i] += 1
                        break
            return counts

        base_counts = get_counts(baseline)
        curr_counts = get_counts(current)

        base_total = len(baseline)
        curr_total = len(current)

        psi = 0.0
        for b_cnt, c_cnt in zip(base_counts, curr_counts):
            b_pct = max(b_cnt / base_total, 0.0001)
            c_pct = max(c_cnt / curr_total, 0.0001)
            psi += (c_pct - b_pct) * math.log(c_pct / b_pct)

        return max(0.0, psi)
