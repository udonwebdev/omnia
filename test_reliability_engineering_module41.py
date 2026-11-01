"""
Unit tests for Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.

Covers:
1. Reliability inventory registration and failure domains
2. Failure mode analysis (FMEA) and Single Point of Failure (SPOF) detection
3. Controlled failure scenario synthesis and safe environment gating
4. Fault injection lifecycle with Module 20 human approval token enforcement
5. Backup inventory registration and cryptographic checksum validation
6. Disaster recovery drill execution, demonstrated RTO/RPO measurement, and verification
"""

import unittest
import os
import sqlite3
import tempfile

from persistence.migrations import MIGRATION_V26
from reliability_engineering.models import (
    BackupType,
    ComponentReliabilityCriticality,
    ExperimentLifecycleState,
    FailoverReadinessState,
    FailureDomain,
    RecoveryStrategy,
    ValidationStatus,
)
from reliability_engineering.service import ReliabilityEngineeringOrchestrator


class TestReliabilityEngineeringModule41(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        # Initialize schema directly for testing speed
        conn = sqlite3.connect(self.db_path)
        conn.executescript(MIGRATION_V26)
        conn.close()
        self.orchestrator = ReliabilityEngineeringOrchestrator(db_path=self.db_path)
        self.repo = self.orchestrator.repo

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_01_component_inventory_and_dependencies(self):
        """Test registering critical reliability components and checking downstream dependencies."""
        db_comp = self.orchestrator.register_component(
            component_id="comp-db",
            component_name="Core Database Cluster",
            criticality=ComponentReliabilityCriticality.MISSION_CRITICAL,
            failure_domain=FailureDomain.ZONE,
            data_ownership="STATEFUL",
            redundancy_config="N+2",
        )
        self.assertEqual(db_comp.component_id, "comp-db")
        self.assertEqual(db_comp.criticality, ComponentReliabilityCriticality.MISSION_CRITICAL)

        api_comp = self.orchestrator.register_component(
            component_id="comp-api",
            component_name="Public API Gateway",
            criticality=ComponentReliabilityCriticality.HIGH,
            failure_domain=FailureDomain.PROCESS,
            dependencies=["comp-db"],
        )
        self.assertIn("comp-db", api_comp.dependencies)

        dependents = self.orchestrator.inventory.get_downstream_dependents("comp-db")
        self.assertIn("comp-api", dependents)

    def test_02_fmea_and_spof_detection(self):
        """Test FMEA risk calculation and automatic Single Point of Failure (SPOF) identification."""
        # Non-SPOF mode (has redundancy and controls)
        fm_normal = self.orchestrator.evaluate_failure_mode(
            component_id="comp-api",
            failure_mode_name="ProcessCrash",
            potential_causes=["Out of memory"],
            local_impact="Pod killed by runtime",
            downstream_impact="Traffic shifted to replica",
            detectability_score=2,
            severity_score=4,
            probability_score=3,
            existing_controls=["K8s ReplicaSet", "Health Probe"],
        )
        self.assertEqual(fm_normal.risk_priority_number, 24)
        self.assertFalse(fm_normal.is_spof)

        # Register standalone component without redundancy
        self.orchestrator.register_component(
            component_id="comp-single-master",
            component_name="Singleton Master Coordinator",
            criticality=ComponentReliabilityCriticality.MISSION_CRITICAL,
            redundancy_config="STANDALONE",
        )
        # SPOF mode (severity >= 8, standalone, no controls)
        fm_spof = self.orchestrator.evaluate_failure_mode(
            component_id="comp-single-master",
            failure_mode_name="StorageCorruption",
            potential_causes=["Disk controller failure"],
            local_impact="Total node crash",
            downstream_impact="System-wide orchestration halt",
            detectability_score=8,
            severity_score=9,
            probability_score=4,
            existing_controls=[],
            recommended_mitigation="Deploy Raft 3-node consensus cluster",
        )
        self.assertEqual(fm_spof.risk_priority_number, 288)
        self.assertTrue(fm_spof.is_spof)

        spofs = self.orchestrator.list_spofs()
        self.assertEqual(len(spofs), 1)
        self.assertEqual(spofs[0].mode_id, fm_spof.mode_id)

    def test_03_failure_scenario_safety_constraints(self):
        """Test failure scenario generation and strict production target blocking."""
        # Allowed in sandbox
        sc = self.orchestrator.generate_scenario(
            title="Database Latency Spike Scenario",
            category="INFRASTRUCTURE",
            affected_components=["comp-db"],
            expected_behavior="API gateway should backoff and return 503 instead of cascading hang",
            target_environment="ISOLATED_SANDBOX",
        )
        self.assertEqual(sc.target_environment, "ISOLATED_SANDBOX")
        self.assertIn("comp-db", sc.affected_components)

        # Blocked in production without sandbox wrapper
        with self.assertRaises(PermissionError):
            self.orchestrator.generate_scenario(
                title="Unsafe Production Wipe",
                category="INFRASTRUCTURE",
                affected_components=["comp-db"],
                expected_behavior="Fail",
                target_environment="PRODUCTION",
            )

    def test_04_fault_injection_and_human_approval_gate(self):
        """Test fault injection lifecycle and Module 20 human approval token enforcement."""
        sc = self.orchestrator.generate_scenario(
            title="Network Packet Loss Simulation",
            category="DISTRIBUTED",
            affected_components=["comp-db"],
            expected_behavior="Cluster detects partition and promotes standby",
            target_environment="ISOLATED_SANDBOX",
        )

        # 1. Start WITHOUT token -> Must raise PermissionError
        with self.assertRaises(PermissionError):
            self.orchestrator.run_fault_experiment(
                scenario_id=sc.scenario_id,
                hypothesis="Simulated packet drop does not corrupt replicated logs",
                approval_token="",
            )

        # 2. Start WITH valid Module 20 human approval token -> Must succeed
        valid_token = "OMNIA_M20_CRYPTO_TOKEN_FAULT_EXP_8812"
        exp = self.orchestrator.run_fault_experiment(
            scenario_id=sc.scenario_id,
            hypothesis="Simulated packet drop does not corrupt replicated logs",
            approval_token=valid_token,
        )
        self.assertEqual(exp.lifecycle_state, ExperimentLifecycleState.COMPLETED)
        self.assertTrue(exp.containment_successful)
        self.assertFalse(exp.cascading_failure_detected)
        self.assertEqual(exp.approval_token, valid_token)

    def test_05_backup_inventory_and_integrity_validation(self):
        """Test backup cataloging, cryptographic hash matching, and corruption detection."""
        b = self.orchestrator.register_backup(
            data_source="omnia.db",
            backup_type=BackupType.SNAPSHOT,
            version="1.0.0",
            record_count=5000,
            size_bytes=1048576,
        )
        self.assertEqual(b.validation_status, ValidationStatus.PENDING)

        # Successful validation drill
        val_ok = self.orchestrator.validate_backup_integrity(
            backup_id=b.backup_id,
            simulate_restore=True,
            simulate_corruption=False,
        )
        self.assertEqual(val_ok.status, ValidationStatus.VERIFIED)
        self.assertTrue(val_ok.checksum_verified)
        self.assertTrue(val_ok.isolated_restore_tested)

        # Corruption detection
        b_bad = self.orchestrator.register_backup(
            data_source="tasks.db",
            backup_type=BackupType.FULL,
            version="1.0.0",
        )
        val_bad = self.orchestrator.validate_backup_integrity(
            backup_id=b_bad.backup_id,
            simulate_restore=False,
            simulate_corruption=True,
        )
        self.assertEqual(val_bad.status, ValidationStatus.CORRUPTED)
        self.assertFalse(val_bad.checksum_verified)

    def test_06_dr_plan_execution_and_rto_rpo_verification(self):
        """Test disaster recovery drill sequencing, Module 20 gate, and demonstrated RTO/RPO proof."""
        # Register components first
        self.orchestrator.register_component(
            component_id="comp-db",
            component_name="Core Database Cluster",
            criticality=ComponentReliabilityCriticality.MISSION_CRITICAL,
            failure_domain=FailureDomain.ZONE,
            data_ownership="STATEFUL",
            redundancy_config="N+2",
        )
        self.orchestrator.register_component(
            component_id="comp-api",
            component_name="Public API Gateway",
            criticality=ComponentReliabilityCriticality.HIGH,
            failure_domain=FailureDomain.PROCESS,
            dependencies=["comp-db"],
        )

        plan = self.orchestrator.create_dr_plan(
            title="Database Cluster Recovery Drill",
            disaster_scenario="Primary storage pool wiped out",
            affected_services=["comp-db", "comp-api"],
            dependency_order=["comp-db", "comp-api"],
            strategy=RecoveryStrategy.RESTORE_FROM_BACKUP,
            target_rto_sec=120.0,
            target_rpo_sec=30.0,
        )
        self.assertEqual(plan.strategy, RecoveryStrategy.RESTORE_FROM_BACKUP)

        # 1. Attempt DR drill without approval token -> Must fail
        with self.assertRaises(PermissionError):
            self.orchestrator.execute_recovery_drill(plan_id=plan.plan_id, approval_token="")

        # 2. Execute with Module 20 token
        valid_token = "OMNIA_M20_DR_APPROVAL_SIG_9001"
        exec_rec = self.orchestrator.execute_recovery_drill(
            plan_id=plan.plan_id,
            approval_token=valid_token,
        )
        self.assertEqual(exec_rec.status, "COMPLETED")
        self.assertEqual(len(exec_rec.steps_executed), 2)

        # 3. Verify recovery independently
        ver = self.orchestrator.verify_recovery(
            execution_id=exec_rec.execution_id,
            component_id="comp-db",
            actual_rto_sec=45.0,  # Below 120s target
            actual_rpo_sec=10.0,  # Below 30s target
            service_responsive=True,
            data_integrity_verified=True,
        )
        self.assertTrue(ver.rto_compliant)
        self.assertTrue(ver.rpo_compliant)
        self.assertEqual(ver.actual_rto_sec, 45.0)

        # Check reliability overview report
        overview = self.orchestrator.get_reliability_overview()
        self.assertIn("overall_posture", overview)
        self.assertGreaterEqual(overview["total_monitored_components"], 2)


if __name__ == "__main__":
    unittest.main()
