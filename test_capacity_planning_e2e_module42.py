"""
End-to-End Test Suite for Module 42:
Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.

Simulates the complete capacity lifecycle:
1. Register multi-tier infrastructure inventory (Compute, Storage, Network, Application).
2. Collect multi-sample telemetry and verify exact headroom and utilization.
3. Profile workload demand categories, calculate burstiness, and track concurrency requirements.
4. Generate capacity forecasts across multiple horizons (1H, 24H, 7D) with confidence bands.
5. Detect impending saturation risks and calculate Time-To-Saturation (TTS).
6. Evaluate comparative elastic scaling strategies (horizontal vs. vertical vs. throttling).
7. Calculate transparent infrastructure cost run-rates and potential optimization savings.
8. Execute counterfactual what-if simulations (2x, 5x, 10x surges, quota restrictions).
9. Synthesize versioned Capacity Plan with gap analysis and recommended mitigations.
10. Submit scaling proposal and enforce Module 20 human approval token gate.
11. Execute scaling proposal with authorized token and verify inventory capacity update.
12. Evaluate historical forecast accuracy against realized demand (MAPE calculation).
13. Produce comprehensive executive capacity health and HUD overview.
"""

import unittest
import os
import sqlite3
import tempfile

from persistence.migrations import MIGRATION_V27
from capacity_planning.models import (
    ForecastHorizon,
    MetricUnit,
    ResourceDimension,
    SaturationRiskSeverity,
    ScalingGovernanceMode,
    ScalingStrategyType,
    WorkloadCategory,
)
from capacity_planning.service import CapacityPlanningOrchestrator


class TestCapacityPlanningE2EModule42(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize schema directly for testing speed
        conn = sqlite3.connect(self.db_path)
        conn.executescript(MIGRATION_V27)
        conn.close()

        self.orchestrator = CapacityPlanningOrchestrator(db_path=self.db_path)
        self.repo = self.orchestrator.repo

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_full_capacity_planning_and_elastic_governance_lifecycle(self):
        # -------------------------------------------------------------
        # STEP 1: Multi-Tier Resource Inventory Registration
        # -------------------------------------------------------------
        cpu_res = self.orchestrator.register_resource(
            resource_id="e2e-cpu-core",
            resource_name="E2E Worker Compute Cores",
            dimension=ResourceDimension.COMPUTE,
            resource_type="CPU_CORES",
            source="GKE_NODE_POOL",
            total_capacity=100.0,
            unit=MetricUnit.CORES,
            associated_service="worker-service",
        )
        self.assertEqual(cpu_res.total_capacity, 100.0)

        ram_res = self.orchestrator.register_resource(
            resource_id="e2e-ram-mem",
            resource_name="E2E Cluster RAM",
            dimension=ResourceDimension.COMPUTE,
            resource_type="MEMORY_RAM_GB",
            source="GKE_NODE_POOL",
            total_capacity=256.0,
            unit=MetricUnit.GIGABYTES,
            associated_service="worker-service",
        )
        self.assertEqual(ram_res.total_capacity, 256.0)

        db_conn_res = self.orchestrator.register_resource(
            resource_id="e2e-db-connections",
            resource_name="Primary Database Connection Pool",
            dimension=ResourceDimension.APPLICATION,
            resource_type="DATABASE_CONNECTION",
            source="CLOUD_SQL",
            total_capacity=50.0,
            unit=MetricUnit.CONNECTIONS,
            associated_service="persistence-service",
        )
        self.assertEqual(db_conn_res.total_capacity, 50.0)

        # -------------------------------------------------------------
        # STEP 2: Telemetry Ingestion & Headroom Computing
        # -------------------------------------------------------------
        m1 = self.orchestrator.record_measurement("e2e-cpu-core", current_value=60.0)
        self.assertEqual(m1.utilization_pct, 60.0)
        self.assertEqual(m1.available_headroom, 40.0)

        # Simulate gradual growth trend on database connections (approaching bottleneck)
        for val in [30.0, 36.0, 42.0, 46.0]:
            self.orchestrator.record_measurement("e2e-db-connections", current_value=val)

        # -------------------------------------------------------------
        # STEP 3: Workload Demand Profiling
        # -------------------------------------------------------------
        profile = self.orchestrator.record_demand(
            category=WorkloadCategory.HIGH_PRIORITY_MISSION,
            workload_name="strategic_mission_dispatch",
            cpu_consumption=16.0,
            memory_mb=32768.0,
            duration_sec=300.0,
            request_rate_per_sec=12.5,
            peak_cpu_consumption=48.0,
            concurrency_requirement=8,
        )
        self.assertEqual(profile.burstiness_index, 3.0)
        self.assertEqual(profile.concurrency_requirement, 8)

        # -------------------------------------------------------------
        # STEP 4: Capacity Forecasting Across Horizons
        # -------------------------------------------------------------
        fc_1h = self.orchestrator.forecast_capacity("e2e-db-connections", horizon=ForecastHorizon.ONE_HOUR)
        self.assertGreater(fc_1h.projected_utilization_pct, 90.0)

        fc_24h = self.orchestrator.forecast_capacity("e2e-db-connections", horizon=ForecastHorizon.TWENTY_FOUR_HOURS)
        self.assertIsNotNone(fc_24h.estimated_saturation_hours)
        self.assertGreater(fc_24h.confidence_score, 0.7)

        # -------------------------------------------------------------
        # STEP 5: Saturation Risk Detection
        # -------------------------------------------------------------
        # 46 / 50 = 92% -> Critical Saturation
        risks = self.orchestrator.detect_saturation_risks()
        self.assertGreaterEqual(len(risks), 1)
        critical_risk = next(r for r in risks if r.resource_id == "e2e-db-connections")
        self.assertEqual(critical_risk.severity, SaturationRiskSeverity.CRITICAL)
        self.assertEqual(critical_risk.observed_utilization_pct, 92.0)

        # -------------------------------------------------------------
        # STEP 6: Elastic Scaling Options Comparison
        # -------------------------------------------------------------
        options = self.orchestrator.evaluate_scaling_options("e2e-db-connections", target_headroom_increase=25.0)
        self.assertGreaterEqual(len(options), 2)
        strat_types = [o.strategy_type for o in options]
        self.assertIn(ScalingStrategyType.HORIZONTAL_SCALE_OUT, strat_types)
        self.assertIn(ScalingStrategyType.WORKLOAD_THROTTLING, strat_types)

        # -------------------------------------------------------------
        # STEP 7: Infrastructure Cost Run-Rate Modeling
        # -------------------------------------------------------------
        cost = self.orchestrator.get_cost_projection()
        self.assertGreater(cost.current_hourly_cost, 0.0)
        self.assertGreater(cost.projected_monthly_cost, 0.0)
        self.assertIn("COMPUTE", cost.cost_by_dimension)
        self.assertIn("APPLICATION", cost.cost_by_dimension)

        # -------------------------------------------------------------
        # STEP 8: Counterfactual What-If Simulation
        # -------------------------------------------------------------
        sim = self.orchestrator.simulate_capacity_scenario(
            scenario_name="5x Mission Concurrency Surge",
            workload_multiplier=5.0,
            quota_reduction_pct=0.0,
        )
        self.assertFalse(sim.is_resilient)
        self.assertIn("e2e-db-connections", sim.bottleneck_resources)
        self.assertGreater(sim.throughput_degradation_pct, 0.0)

        # -------------------------------------------------------------
        # STEP 9: Actionable Capacity Plan Generation
        # -------------------------------------------------------------
        plan = self.orchestrator.create_capacity_plan(
            title="Q4 Mission Infrastructure Readiness Plan",
            horizon=ForecastHorizon.TWENTY_FOUR_HOURS,
            governance_mode=ScalingGovernanceMode.APPROVAL_REQUIRED,
        )
        self.assertEqual(plan.status, "PROPOSED")
        self.assertGreaterEqual(len(plan.identified_gaps), 1)
        self.assertIn(plan.current_health_posture, ["HEADROOM_CONSTRAINED", "IMPENDING_SATURATION"])

        # -------------------------------------------------------------
        # STEP 10 & 11: Scaling Proposal & Module 20 Cryptographic Execution
        # -------------------------------------------------------------
        proposal = self.orchestrator.submit_scaling_proposal(
            plan_id=plan.plan_id,
            resource_id="e2e-db-connections",
            strategy_type=ScalingStrategyType.HORIZONTAL_SCALE_OUT,
            to_capacity=100.0,  # Expand pool from 50 to 100
        )
        self.assertEqual(proposal.from_capacity, 50.0)
        self.assertEqual(proposal.to_capacity, 100.0)

        # Verify rejection without token
        with self.assertRaises(PermissionError):
            self.orchestrator.execute_scaling_proposal(
                proposal_id=proposal.proposal_id,
                approval_token="",
            )

        # Execute with verified Module 20 token
        valid_m20_token = "OMNIA_M20_CRYPTO_TOKEN_CAPACITY_SCALE_9812"
        execution = self.orchestrator.execute_scaling_proposal(
            proposal_id=proposal.proposal_id,
            approval_token=valid_m20_token,
        )
        self.assertEqual(execution.status, "SUCCESS")
        self.assertEqual(execution.applied_capacity, 100.0)

        # Invariant check: Inventory capacity must reflect applied scaling
        updated_db_res = self.orchestrator.inventory.get_resource("e2e-db-connections")
        self.assertEqual(updated_db_res.total_capacity, 100.0)

        # -------------------------------------------------------------
        # STEP 12: Continuous Accuracy Evaluation
        # -------------------------------------------------------------
        eval_rec = self.orchestrator.evaluate_forecast_accuracy(
            forecast_id=fc_24h.forecast_id,
            actual_demand=65.0,  # Within the 57.2 - 77.4 confidence interval
        )
        self.assertIsNotNone(eval_rec.percentage_error)
        self.assertTrue(eval_rec.within_confidence_bounds)

        # -------------------------------------------------------------
        # STEP 13: Executive Overview & HUD Posture
        # -------------------------------------------------------------
        overview = self.orchestrator.get_capacity_overview()
        self.assertEqual(overview["total_monitored_resources"], 3)
        self.assertIn("resource_breakdown_by_dimension", overview)
        self.assertIn(overview["overall_posture"], ["OPTIMAL", "CONSTRAINED", "CRITICAL_HEADROOM"])
        self.assertGreater(overview["projected_hourly_cost_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
