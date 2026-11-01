"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
What-If Capacity Simulator: Counterfactual Workload Surges & Failure Impact Assessment.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from capacity_planning.models import (
    CapacityScenarioDefinition,
    CapacitySimulationResult,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Simulator")


class WhatIfCapacitySimulator:
    """
    Simulates counterfactual capacity scenarios:
    - 2x, 5x, 10x traffic surges.
    - Loss of primary compute node or worker zone.
    - Quota cuts and connection constraints.
    Reuses principles from Module 34 Digital Twin Simulation.
    """

    def __init__(self, repository: Optional[CapacityRepository] = None):
        self.repo = repository or CapacityRepository()

    def define_scenario(
        self,
        scenario_name: str,
        workload_multiplier: float,
        unavailable_resources: Optional[List[str]] = None,
        quota_reduction_pct: float = 0.0,
        description: str = "",
    ) -> CapacityScenarioDefinition:
        sid = f"scen-{uuid.uuid4().hex[:8]}"
        sc = CapacityScenarioDefinition(
            scenario_id=sid,
            scenario_name=scenario_name,
            workload_multiplier=workload_multiplier,
            unavailable_resources=unavailable_resources or [],
            quota_reduction_pct=quota_reduction_pct,
            description=description,
        )
        self.repo.save_scenario(sc)
        logger.info(f"Defined what-if scenario '{sid}' ({scenario_name}, Multiplier={workload_multiplier}x)")
        return sc

    def run_simulation(self, scenario_id: str) -> CapacitySimulationResult:
        """Executes simulation model against active inventory and current measurements."""
        latest_meas = self.repo.get_latest_measurements()
        resources = {r.resource_id: r for r in self.repo.list_resources(active_only=True)}

        with self.repo._get_connection() as conn:
            row = conn.execute("SELECT * FROM cap_scenarios WHERE scenario_id = ?", (scenario_id,)).fetchone()
            if not row:
                raise KeyError(f"Scenario '{scenario_id}' does not exist.")
            import json
            mult = row["workload_multiplier"]
            unavail = json.loads(row["unavailable_resources_json"] or "[]")
            quota_cut = row["quota_reduction_pct"]

        bottlenecks = []
        max_util = 0.0

        for rid, res in resources.items():
            eff_capacity = res.total_capacity * (1.0 - (quota_cut / 100.0))
            if rid in unavail:
                eff_capacity = 0.0

            m = latest_meas.get(rid)
            current_val = m.current_value if (m and m.collection_status == "VALID") else (res.total_capacity * 0.3)
            sim_val = current_val * mult

            sim_util = (sim_val / eff_capacity * 100.0) if eff_capacity > 0 else 999.0
            if sim_util > max_util:
                max_util = sim_util

            if sim_util >= 90.0:
                bottlenecks.append(rid)

        is_resilient = max_util < 95.0
        deg_pct = 0.0 if is_resilient else round(min(90.0, (max_util - 90.0) * 1.5), 1)
        latency_factor = 1.0 if is_resilient else round(1.0 + ((max_util - 90.0) / 30.0), 2)
        rec_action = (
            "No scaling required; infrastructure absorbs load surge."
            if is_resilient
            else f"Proactively scale out {len(bottlenecks)} bottleneck resource(s): {bottlenecks}"
        )

        sim_id = f"sim-{uuid.uuid4().hex[:8]}"
        res = CapacitySimulationResult(
            simulation_id=sim_id,
            scenario_id=scenario_id,
            max_projected_utilization_pct=round(max_util, 2),
            bottleneck_resources=bottlenecks,
            throughput_degradation_pct=deg_pct,
            latency_increase_factor=latency_factor,
            estimated_additional_cost_hr=round(len(bottlenecks) * 0.15, 2),
            recommended_scaling_action=rec_action,
            is_resilient=is_resilient,
        )
        self.repo.save_simulation(res)
        logger.info(
            f"Simulation '{sim_id}' for '{scenario_id}': MaxUtil={max_util:.1f}%, "
            f"Bottlenecks={len(bottlenecks)}, Resilient={is_resilient}"
        )
        return res
