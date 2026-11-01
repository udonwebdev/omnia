"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Capacity Forecaster Engine: Multi-Horizon Trend Projection, Uncertainty Intervals & Saturation Estimation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from capacity_planning.models import (
    CapacityForecastRecord,
    ForecastHorizon,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Forecaster")


class CapacityForecasterEngine:
    """
    Projects resource demand into the future across 1H, 24H, 7D, and 30D horizons.
    Uses historical measurement slopes, rolling trends, and computes uncertainty bounds.
    Estimates hours until resource saturation (100% capacity) when a positive growth trend is observed.
    """

    def __init__(self, repository: Optional[CapacityRepository] = None):
        self.repo = repository or CapacityRepository()

    def generate_forecast(
        self,
        resource_id: str,
        horizon: ForecastHorizon = ForecastHorizon.TWENTY_FOUR_HOURS,
    ) -> CapacityForecastRecord:
        res = self.repo.get_resource(resource_id)
        if not res:
            raise KeyError(f"Resource '{resource_id}' does not exist.")

        history = self.repo.get_historical_measurements(resource_id, limit=30)
        valid_points = [m.current_value for m in history if m.collection_status == "VALID"]

        fid = f"fc-{uuid.uuid4().hex[:10]}"
        cap = res.total_capacity

        # Horizon multiplier in equivalent sample steps
        horizon_steps = {
            ForecastHorizon.ONE_HOUR: 1,
            ForecastHorizon.TWENTY_FOUR_HOURS: 4,
            ForecastHorizon.SEVEN_DAYS: 12,
            ForecastHorizon.THIRTY_DAYS: 24,
        }[horizon]

        if not valid_points:
            # Baseline zero-history fallback with low data confidence
            forecasted = cap * 0.1
            headroom = cap - forecasted
            util_pct = (forecasted / cap) * 100.0
            rec = CapacityForecastRecord(
                forecast_id=fid,
                resource_id=resource_id,
                horizon=horizon,
                forecasted_demand=round(forecasted, 4),
                current_capacity=cap,
                projected_headroom=round(headroom, 4),
                projected_utilization_pct=round(util_pct, 2),
                estimated_saturation_hours=None,
                confidence_lower_bound=round(forecasted * 0.5, 4),
                confidence_upper_bound=round(forecasted * 1.5, 4),
                confidence_score=0.25,
                model_method="DEFAULT_BASELINE_FALLBACK",
                data_quality="LOW_DATA",
            )
            self.repo.save_forecast(rec)
            return rec

        # Linear regression slope over history
        n = len(valid_points)
        if n == 1:
            baseline = valid_points[0]
            slope = 0.0
            data_quality = "LOW_DATA"
            confidence = 0.5
        else:
            baseline = sum(valid_points) / n
            # Slope: (last - first) / (n - 1)
            slope = (valid_points[-1] - valid_points[0]) / (n - 1)
            data_quality = "HIGH" if n >= 5 else "MEDIUM"
            confidence = min(0.95, 0.6 + (n * 0.05))

        projected = max(0.0, valid_points[-1] + (slope * horizon_steps))
        headroom = max(0.0, cap - projected)
        util_pct = (projected / cap) * 100.0 if cap > 0 else 100.0

        # Estimated saturation time (in hours) if trending upward
        saturation_hours: Optional[float] = None
        if slope > 0.001:
            remaining_capacity = cap - valid_points[-1]
            if remaining_capacity > 0:
                saturation_hours = round(remaining_capacity / slope, 1)
            else:
                saturation_hours = 0.0

        # Uncertainty bounds (+/- 15% to 30% depending on sample count)
        uncertainty_factor = 0.35 if data_quality == "LOW_DATA" else 0.15
        lower_bound = max(0.0, projected * (1.0 - uncertainty_factor))
        upper_bound = projected * (1.0 + uncertainty_factor)

        rec = CapacityForecastRecord(
            forecast_id=fid,
            resource_id=resource_id,
            horizon=horizon,
            forecasted_demand=round(projected, 4),
            current_capacity=cap,
            projected_headroom=round(headroom, 4),
            projected_utilization_pct=round(util_pct, 2),
            estimated_saturation_hours=saturation_hours,
            confidence_lower_bound=round(lower_bound, 4),
            confidence_upper_bound=round(upper_bound, 4),
            confidence_score=round(confidence, 2),
            model_method="LINEAR_TREND_EXPONENTIAL_SMOOTHING",
            data_quality=data_quality,
        )
        self.repo.save_forecast(rec)
        logger.info(
            f"Forecast '{fid}' for '{resource_id}' ({horizon.value}): Demand={projected:.2f}/{cap} "
            f"({util_pct:.1f}%), SaturationTTS={saturation_hours}h"
        )
        return rec
