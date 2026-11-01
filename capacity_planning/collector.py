"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Capacity Telemetry Collector: Metric Normalization, Validation, and Utilization Computing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from capacity_planning.models import (
    MetricUnit,
    ResourceMeasurementRecord,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Collector")


class CapacityTelemetryCollector:
    """
    Ingests and normalizes real-time metrics across all resource dimensions.
    Enforces invariant: never interpret missing telemetry as zero consumption.
    Calculates exact headroom and utilization percentage.
    """

    def __init__(self, repository: Optional[CapacityRepository] = None):
        self.repo = repository or CapacityRepository()

    def record_measurement(
        self,
        resource_id: str,
        current_value: Optional[float],
        configured_capacity: Optional[float] = None,
        data_confidence: float = 1.0,
        timestamp: Optional[str] = None,
    ) -> ResourceMeasurementRecord:
        """
        Records a telemetry point for a resource.
        If current_value is None, collection_status is UNAVAILABLE and confidence is 0.0.
        """
        res = self.repo.get_resource(resource_id)
        if not res:
            raise KeyError(f"Cannot record measurement: Resource '{resource_id}' does not exist in inventory.")

        cap = configured_capacity if configured_capacity is not None else res.total_capacity
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        mid = f"meas-{uuid.uuid4().hex[:10]}"

        if current_value is None:
            # Unavailable telemetry invariant
            rec = ResourceMeasurementRecord(
                measurement_id=mid,
                resource_id=resource_id,
                timestamp=ts,
                current_value=-1.0,
                configured_capacity=cap,
                available_headroom=0.0,
                utilization_pct=0.0,
                unit=res.unit,
                collection_status="UNAVAILABLE",
                data_confidence=0.0,
            )
        else:
            if current_value < 0.0:
                raise ValueError(f"Measurement value cannot be negative: {current_value}")

            headroom = max(0.0, cap - current_value)
            util_pct = (current_value / cap) * 100.0 if cap > 0 else 100.0
            rec = ResourceMeasurementRecord(
                measurement_id=mid,
                resource_id=resource_id,
                timestamp=ts,
                current_value=current_value,
                configured_capacity=cap,
                available_headroom=round(headroom, 4),
                utilization_pct=round(util_pct, 2),
                unit=res.unit,
                collection_status="VALID",
                data_confidence=max(0.0, min(1.0, data_confidence)),
            )

        self.repo.save_measurement(rec)
        return rec

    def get_latest_measurements(self) -> Dict[str, ResourceMeasurementRecord]:
        return self.repo.get_latest_measurements()

    def get_history(self, resource_id: str, limit: int = 50) -> List[ResourceMeasurementRecord]:
        return self.repo.get_historical_measurements(resource_id, limit=limit)
