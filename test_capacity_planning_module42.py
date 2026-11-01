"""
Unit Tests for Module 42:
Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.

Covers:
1. Resource inventory registration across dimensions & validation of positive capacities
2. Telemetry ingestion, exact headroom/utilization calculation & unavailable telemetry handling
3. Workload demand profiling, rolling consumption updates & burstiness index
4. Capacity forecasting with linear trends, uncertainty intervals & saturation TTS estimation
5. Saturation risk & bottleneck detection with deduplication
6. Transparent infrastructure cost modeling & what-if counterfactual simulation
7. Governed scaling proposal execution with Module 20 human approval token gate
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


class TestCapacityPlanningModule42(unittest.TestCase):
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

    def test_01_resource_inventory_registration_and_validation(self):
        """Test multi-dimensional resource registration and negative capacity rejection."""
        # Valid Compute resource
        cpu_res = self.orchestrator.register_resource(
            resource_id="res-cpu-cluster-01",
            resource_name="Cluster 01 Core Pool",
            dimension=ResourceDimension.COMPUTE,
            resource_type="CPU_CORES",
            source="KUBERNETES_CLUSTER",
            total_capacity=64.0,
            unit=MetricUnit.CORES,
            associated_service="worker-engine",
        )
        self.assertEqual(cpu_res.resource_id, "res-cpu-cluster-01")
        self.assertEqual(cpu_res.total_capacity, 64.0)

        # Invalid capacity <= 0
        with self.assertRaises(ValueError):
            self.orchestrator.register_resource(
                resource_id="res-invalid",
                resource_name="Invalid Resource",
                dimension=ResourceDimension.COMPUTE,
                resource_type="CPU_CORES",
                source="HOST",
                total_capacity=-4.0,
                unit=MetricUnit.CORES,
            )

    def test_02_telemetry_collector_and_unavailable_handling(self):
        """Test telemetry recording, exact utilization, and unavailable metric handling."""
        self.orchestrator.register_resource(
            resource_id="res-ram-01",
            resource_name="Main Memory Pool",
            dimension=ResourceDimension.COMPUTE,
            resource_type="MEMORY_RAM_GB",
            source="HOST",
            total_capacity=128.0,
            unit=MetricUnit.GIGABYTES,
        )

        # 1. Valid measurement
        m_valid = self.orchestrator.record_measurement(
            resource_id="res-ram-01",
            current_value=96.0,
            data_confidence=0.95,
        )
        self.assertEqual(m_valid.utilization_pct, 75.0)
        self.assertEqual(m_valid.available_headroom, 32.0)
        self.assertEqual(m_valid.collection_status, "VALID")

        # 2. Unavailable telemetry: Never interpret as zero consumption
        m_unavail = self.orchestrator.record_measurement(
            resource_id="res-ram-01",
            current_value=None,
        )
        self.assertEqual(m_unavail.collection_status, "UNAVAILABLE")
        self.assertEqual(m_unavail.data_confidence, 0.0)

    def test_03_workload_demand_profiling_and_burstiness(self):
        """Test demand profiling, sample rolling updates, and burstiness index computation."""
        p = self.orchestrator.record_demand(
            category=WorkloadCategory.BATCH_PROCESSING,
            workload_name="media_transcoding_pipeline",
            cpu_consumption=8.0,
            memory_mb=16384.0,
            duration_sec=120.0,
            peak_cpu_consumption=24.0,
            concurrency_requirement=4,
        )
        self.assertEqual(p.workload_name, "media_transcoding_pipeline")
        self.assertEqual(p.burstiness_index, 3.0)  # 24.0 / 8.0 = 3.0
        self.assertEqual(p.sample_count, 1)

        # Second sample updates average
        p2 = self.orchestrator.record_demand(
            category=WorkloadCategory.BATCH_PROCESSING,
            workload_name="media_transcoding_pipeline",
            cpu_consumption=12.0,
            memory_mb=16384.0,
            duration_sec=100.0,
            peak_cpu_consumption=24.0,
        )
        self.assertEqual(p2.sample_count, 2)
        self.assertEqual(p2.avg_cpu_consumption, 10.0)  # (8 + 12) / 2 = 10.0

    def test_04_capacity_forecasting_and_saturation_tts(self):
        """Test multi-horizon forecasting, linear trend slope, and saturation time estimation."""
        self.orchestrator.register_resource(
            resource_id="res-db-conns",
            resource_name="Postgres Connection Pool",
            dimension=ResourceDimension.APPLICATION,
            resource_type="DATABASE_CONNECTION",
            source="POSTGRES",
            total_capacity=100.0,
            unit=MetricUnit.CONNECTIONS,
        )

        # Ingest growing measurement trend: 50 -> 60 -> 70 -> 80
        for val in [50.0, 60.0, 70.0, 80.0]:
            self.orchestrator.record_measurement("res-db-conns", current_value=val)

        fc = self.orchestrator.forecast_capacity("res-db-conns", horizon=ForecastHorizon.TWENTY_FOUR_HOURS)
        self.assertGreater(fc.forecasted_demand, 80.0)
        self.assertGreater(fc.projected_utilization_pct, 80.0)
        self.assertIsNotNone(fc.estimated_saturation_hours)
        self.assertLess(fc.estimated_saturation_hours, 10.0)  # Saturation approaching quickly

    def test_05_saturation_risk_detection_and_deduplication(self):
        """Test threshold alerts and deduplication of open saturation risks."""
        self.orchestrator.register_resource(
            resource_id="res-worker-slots",
            resource_name="Distributed Worker Slots",
            dimension=ResourceDimension.APPLICATION,
            resource_type="WORKER_SLOT",
            source="SCHEDULER_MESH",
            total_capacity=50.0,
            unit=MetricUnit.COUNT,
        )

        # High consumption (47 / 50 = 94% -> CRITICAL)
        self.orchestrator.record_measurement("res-worker-slots", current_value=47.0)
        risks = self.orchestrator.detect_saturation_risks()
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].severity, SaturationRiskSeverity.CRITICAL)

        # Duplicate scan without state change should not duplicate open risk
        risks2 = self.orchestrator.detect_saturation_risks()
        self.assertEqual(len(risks2), 0)

    def test_06_cost_model_and_what_if_simulation(self):
        """Test transparent pricing calculations and counterfactual simulation."""
        self.orchestrator.register_resource(
            resource_id="res-cpu-srv",
            resource_name="Server Compute",
            dimension=ResourceDimension.COMPUTE,
            resource_type="CPU_CORES",
            source="HOST",
            total_capacity=10.0,
            unit=MetricUnit.CORES,
        )
        self.orchestrator.record_measurement("res-cpu-srv", current_value=4.0)

        cost = self.orchestrator.get_cost_projection()
        self.assertGreater(cost.current_hourly_cost, 0.0)
        self.assertGreater(cost.projected_monthly_cost, 0.0)

        # 5x Workload surge simulation -> 4.0 * 5 = 20.0 > 10.0 capacity
        sim = self.orchestrator.simulate_capacity_scenario(
            scenario_name="5x Holiday Surge",
            workload_multiplier=5.0,
        )
        self.assertFalse(sim.is_resilient)
        self.assertGreaterEqual(sim.max_projected_utilization_pct, 100.0)
        self.assertIn("res-cpu-srv", sim.bottleneck_resources)

    def test_07_governed_scaling_proposal_and_module20_gate(self):
        """Test plan synthesis, proposal creation, and Module 20 human approval token gate."""
        self.orchestrator.register_resource(
            resource_id="res-scale-target",
            resource_name="Elastic Worker Pool",
            dimension=ResourceDimension.APPLICATION,
            resource_type="WORKER_SLOT",
            source="SCHEDULER_MESH",
            total_capacity=20.0,
            unit=MetricUnit.COUNT,
        )

        plan = self.orchestrator.create_capacity_plan(
            title="Q4 Elastic Capacity Plan",
            horizon=ForecastHorizon.TWENTY_FOUR_HOURS,
            governance_mode=ScalingGovernanceMode.APPROVAL_REQUIRED,
        )
        self.assertEqual(plan.status, "PROPOSED")

        prop = self.orchestrator.submit_scaling_proposal(
            plan_id=plan.plan_id,
            resource_id="res-scale-target",
            strategy_type=ScalingStrategyType.WORKER_POOL_EXPANSION,
            to_capacity=40.0,
        )
        self.assertEqual(prop.to_capacity, 40.0)

        # 1. Attempt scaling without approval token -> Must fail
        with self.assertRaises(PermissionError):
            self.orchestrator.execute_scaling_proposal(
                proposal_id=prop.proposal_id,
                approval_token="",
            )

        # 2. Execute with valid Module 20 cryptographic token -> Must succeed
        valid_token = "OMNIA_M20_SCALING_TOKEN_SIG_9981"
        exec_rec = self.orchestrator.execute_scaling_proposal(
            proposal_id=prop.proposal_id,
            approval_token=valid_token,
        )
        self.assertEqual(exec_rec.status, "SUCCESS")
        self.assertEqual(exec_rec.applied_capacity, 40.0)

        # Verify updated capacity in inventory
        updated_res = self.orchestrator.inventory.get_resource("res-scale-target")
        self.assertEqual(updated_res.total_capacity, 40.0)


if __name__ == "__main__":
    unittest.main()
