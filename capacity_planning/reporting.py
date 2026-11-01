"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Executive Capacity Reporter: Scorecards, Saturation Summary & HUD Telemetry Synthesis.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from capacity_planning.cost_model import InfrastructureCostModel
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Reporting")


class CapacityReporter:
    """
    Synthesizes overall infrastructure capacity health, active saturation risks,
    monthly projected cost, and active scaling proposals into an executive HUD report.
    """

    def __init__(self, repository: CapacityRepository, cost_model: InfrastructureCostModel):
        self.repo = repository
        self.cost_model = cost_model

    def generate_capacity_overview(self) -> Dict[str, Any]:
        resources = self.repo.list_resources(active_only=True)
        latest_meas = self.repo.get_latest_measurements()
        risks = self.repo.list_unresolved_risks()
        costs = self.cost_model.estimate_current_costs()
        evals = self.repo.list_accuracy_evaluations()

        # Dimension breakdown
        dim_counts: Dict[str, int] = {}
        for r in resources:
            d = r.dimension.value
            dim_counts[d] = dim_counts.get(d, 0) + 1

        # Posture assessment
        posture = "OPTIMAL"
        if len(risks) > 0:
            posture = "CONSTRAINED"
        if any(r.severity.value == "CRITICAL" for r in risks):
            posture = "CRITICAL_HEADROOM"

        avg_error = 0.0
        if evals:
            avg_error = round(sum(e.percentage_error for e in evals) / len(evals), 2)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_posture": posture,
            "total_monitored_resources": len(resources),
            "resource_breakdown_by_dimension": dim_counts,
            "active_saturation_risks_count": len(risks),
            "critical_risks": [
                {
                    "risk_id": r.risk_id,
                    "resource_id": r.resource_id,
                    "severity": r.severity.value,
                    "utilization_pct": r.observed_utilization_pct,
                    "tts_hours": r.estimated_time_to_saturation_hours,
                    "mitigation": r.recommended_mitigation,
                }
                for r in risks
                if r.severity.value in ("CRITICAL", "HIGH")
            ],
            "projected_hourly_cost_usd": costs.current_hourly_cost,
            "projected_monthly_cost_usd": costs.projected_monthly_cost,
            "potential_monthly_savings_usd": costs.potential_savings_monthly,
            "historical_forecast_mape_pct": avg_error,
        }
