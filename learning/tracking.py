"""
Omnia Module 33: Strategy Performance Tracker
Continuously aggregates execution metrics across tasks, forecasts,
retrieval sessions, and planning operations.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from learning.models import LearningSignal, SignalQualityStatus


class StrategyPerformanceTracker:
    """
    Maintains running metrics, sample counts, and confidence bounds
    for all active strategies and model versions.
    """

    def __init__(self) -> None:
        pass

    def calculate_strategy_metrics(
        self,
        strategy_id: str,
        signals: List[LearningSignal],
        metric_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Computes sample size, mean, variance, standard deviation,
        min, max, and 95% confidence intervals for strategy metrics.
        """
        filtered = [
            s for s in signals
            if s.strategy_id == strategy_id
            and s.quality_status in (SignalQualityStatus.VERIFIED, SignalQualityStatus.PENDING)
            and (metric_name is None or s.metric_name == metric_name)
        ]

        if not filtered:
            return {
                "strategy_id": strategy_id,
                "metric_name": metric_name or "all",
                "sample_count": 0,
                "mean": 0.0,
                "std_dev": 0.0,
                "min": 0.0,
                "max": 0.0,
                "confidence_interval_95": (0.0, 0.0),
                "last_observed_at": None,
            }

        # Group by metric if none specified
        if metric_name is None:
            by_metric: Dict[str, List[float]] = {}
            for s in filtered:
                by_metric.setdefault(s.metric_name, []).append(s.metric_value)
            
            summary = {}
            for m_name, values in by_metric.items():
                summary[m_name] = self._compute_stats(values)
            return {
                "strategy_id": strategy_id,
                "metrics": summary,
                "total_signals": len(filtered),
            }

        values = [s.metric_value for s in filtered]
        stats = self._compute_stats(values)
        stats["strategy_id"] = strategy_id
        stats["metric_name"] = metric_name
        stats["last_observed_at"] = max(s.observed_at for s in filtered).isoformat()
        return stats

    def _compute_stats(self, values: List[float]) -> Dict[str, Any]:
        n = len(values)
        if n == 0:
            return {
                "sample_count": 0,
                "mean": 0.0,
                "std_dev": 0.0,
                "variance": 0.0,
                "min": 0.0,
                "max": 0.0,
                "ci_95_lower": 0.0,
                "ci_95_upper": 0.0,
            }

        mean = sum(values) / n
        if n > 1:
            variance = sum((x - mean) ** 2 for x in values) / (n - 1)
            std_dev = math.sqrt(variance)
            # 95% confidence interval using standard error (z ~ 1.96)
            margin = 1.96 * (std_dev / math.sqrt(n))
            ci_lower = mean - margin
            ci_upper = mean + margin
        else:
            variance = 0.0
            std_dev = 0.0
            ci_lower = mean
            ci_upper = mean

        return {
            "sample_count": n,
            "mean": round(mean, 4),
            "variance": round(variance, 6),
            "std_dev": round(std_dev, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "ci_95_lower": round(ci_lower, 4),
            "ci_95_upper": round(ci_upper, 4),
        }
