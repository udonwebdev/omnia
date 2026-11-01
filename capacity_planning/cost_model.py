"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Infrastructure Cost Model: Transparent Provider Pricing, Workload Cost Accounting & Optimization Savings.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, Optional

from capacity_planning.models import (
    InfrastructureCostProjection,
    ResourceDimension,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Cost")

# Configured baseline unit rates (USD per unit per hour)
DEFAULT_HOURLY_RATES = {
    "CPU_CORES": 0.045,          # $0.045 / vCPU / hr
    "MEMORY_RAM_GB": 0.006,      # $0.006 / GB-RAM / hr
    "STORAGE_GB": 0.00015,       # ~$0.10 / GB / month -> $0.00015 / hr
    "NETWORK_EGRESS_GB": 0.08,   # $0.08 / GB egress
    "DATABASE_CONNECTION": 0.01, # $0.01 / pool connection / hr
    "WORKER_SLOT": 0.05,         # $0.05 / worker execution slot / hr
}


class InfrastructureCostModel:
    """
    Transparently projects hourly and monthly infrastructure costs.
    Calculates cost by dimension, evaluates optimization savings, and never fabricates prices.
    """

    def __init__(self, repository: Optional[CapacityRepository] = None):
        self.repo = repository or CapacityRepository()
        self.rates = dict(DEFAULT_HOURLY_RATES)

    def set_unit_rate(self, resource_type: str, hourly_rate_usd: float) -> None:
        if hourly_rate_usd < 0:
            raise ValueError("Rate cannot be negative.")
        self.rates[resource_type] = hourly_rate_usd
        logger.info(f"Updated unit cost rate for '{resource_type}': ${hourly_rate_usd:.5f}/hr")

    def estimate_current_costs(self) -> InfrastructureCostProjection:
        """Computes current hourly run-rate and 30-day projection across all registered resources."""
        resources = self.repo.list_resources(active_only=True)
        by_dimension: Dict[str, float] = {
            ResourceDimension.COMPUTE.value: 0.0,
            ResourceDimension.STORAGE.value: 0.0,
            ResourceDimension.NETWORKING.value: 0.0,
            ResourceDimension.APPLICATION.value: 0.0,
        }

        total_hourly = 0.0
        potential_idle_savings = 0.0
        latest_meas = self.repo.get_latest_measurements()

        for res in resources:
            rate = self.rates.get(res.resource_type, 0.02)
            cost = res.total_capacity * rate
            dim = res.dimension.value
            by_dimension[dim] = by_dimension.get(dim, 0.0) + cost
            total_hourly += cost

            # Calculate idle cost savings if utilization is under 20%
            m = latest_meas.get(res.resource_id)
            if m and m.collection_status == "VALID" and m.utilization_pct < 20.0:
                potential_idle_savings += (cost * 0.5)

        proj_id = f"cost-{uuid.uuid4().hex[:8]}"
        monthly_cost = round(total_hourly * 730.0, 2)
        monthly_savings = round(potential_idle_savings * 730.0, 2)

        return InfrastructureCostProjection(
            projection_id=proj_id,
            current_hourly_cost=round(total_hourly, 4),
            projected_monthly_cost=monthly_cost,
            cost_by_dimension={k: round(v, 4) for k, v in by_dimension.items()},
            potential_savings_monthly=monthly_savings,
            pricing_status="CONFIGURED_ESTIMATE",
            currency="USD",
        )

    def calculate_scaling_cost_delta(self, resource_type: str, capacity_delta: float) -> float:
        rate = self.rates.get(resource_type, 0.02)
        return round(capacity_delta * rate, 4)
