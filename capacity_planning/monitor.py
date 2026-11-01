"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Continuous Capacity Monitor: Forecast Accuracy Evaluation & Capacity Regression Detection.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from capacity_planning.models import (
    ForecastAccuracyEvaluation,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Monitor")


class ContinuousCapacityMonitor:
    """
    Compares historical forecasts against realized workload measurements.
    Measures Mean Absolute Percentage Error (MAPE) and flags capacity drift.
    """

    def __init__(self, repository: Optional[CapacityRepository] = None):
        self.repo = repository or CapacityRepository()

    def evaluate_forecast_accuracy(
        self,
        forecast_id: str,
        actual_demand: float,
    ) -> ForecastAccuracyEvaluation:
        with self.repo._get_connection() as conn:
            row = conn.execute("SELECT * FROM cap_forecasts WHERE forecast_id = ?", (forecast_id,)).fetchone()
            if not row:
                raise KeyError(f"Forecast '{forecast_id}' does not exist.")
            predicted = row["forecasted_demand"]
            rid = row["resource_id"]
            lower = row["confidence_lower_bound"]
            upper = row["confidence_upper_bound"]

        abs_error = abs(actual_demand - predicted)
        pct_error = (abs_error / max(0.001, actual_demand)) * 100.0
        within_bounds = (lower <= actual_demand <= upper)

        eid = f"eval-{uuid.uuid4().hex[:8]}"
        eval_rec = ForecastAccuracyEvaluation(
            evaluation_id=eid,
            forecast_id=forecast_id,
            resource_id=rid,
            predicted_demand=predicted,
            actual_demand=actual_demand,
            absolute_error=round(abs_error, 4),
            percentage_error=round(pct_error, 2),
            within_confidence_bounds=within_bounds,
        )
        self.repo.save_accuracy_evaluation(eval_rec)
        logger.info(
            f"Forecast Evaluation '{eid}' on '{rid}': Predicted={predicted}, Actual={actual_demand}, "
            f"Error={pct_error:.1f}%, InBounds={within_bounds}"
        )
        return eval_rec

    def list_accuracy_evaluations(self) -> List[ForecastAccuracyEvaluation]:
        return self.repo.list_accuracy_evaluations()
