"""
End-to-End Test Suite for Module 41:
Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery

Covers the full disaster resilience lifecycle:
1. Register critical component hierarchy with dependencies & redundancy configs.
2. Conduct FMEA & automatically flag Single Points of Failure (SPOFs).
3. Establish measurable Resilience Objectives (RTO/RPO).
4. Synthesize controlled failure scenario and verify safety boundary checks.
5. Execute fault injection experiment gated by Module 20 human approval token.
6. Verify blast radius containment and failure isolation.
7. Register backup artifact, verify cryptographic SHA-256 checksum, and conduct sandbox restore drill.
8. Create versioned Disaster Recovery (DR) Plan with strict dependency ordering.
9. Orchestrate DR drill gated by Module 20 cryptographic token.
10. Execute distributed state consistency audit across epochs, checkpoints, and consensus logs.
11. Perform independent recovery verification and generate demonstrated RTO/RPO proof.
12. Detect resilience regressions against established performance baselines.
13. Produce comprehensive executive reliability overview report.
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
    ResilienceObjectiveRecord,
    ResilienceObjectiveType,
    ValidationStatus,
)
from reliability_engineering.service import ReliabilityEngineeringOrchestrator


class TestReliabilityEngineeringE2EModule41(unittest.TestCase):
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

    def test_full_autonomous_resilience_and_disaster_recovery_lifecycle(self):
        # -------------------------------------------------------------
        # STEP 1: Inventory Registration
        # -------------------------------------------------------------
        core_db = self.orchestrator.register_component(
            component_id="e2e-core-db",
            component_name="Core Database Cluster",
            criticality=ComponentReliabilityCriticality.MISSION_CRITICAL,
            failure_domain=FailureDomain.REGION,
            data_ownership="STATEFUL",
            redundancy_config="ACTIVE_ACTIVE_3X",
            failover_readiness=FailoverReadinessState.READY,
        )
        self.assertEqual(core_db.component_id, "e2e-core-db")

        auth_svc = self.orchestrator.register_component(
            component_id="e2e-auth-svc",
            component_name="Authentication Service",
            criticality=ComponentReliabilityCriticality.HIGH,
            failure_domain=FailureDomain.PROCESS,
            redundancy_config="N+1",
            dependencies=["e2e-core-db"],
        )
        self.assertIn("e2e-core-db", auth_svc.dependencies)

        legacy_cache = self.orchestrator.register_component(
            component_id="e2e-legacy-cache",
            component_name="Legacy Single Node Cache",
            criticality=ComponentReliabilityCriticality.HIGH,
            failure_domain=FailureDomain.PROCESS,
            redundancy_config="NONE",
            dependencies=["e2e-core-db"],
        )
        self.assertEqual(legacy_cache.redundancy_config, "NONE")

        # -------------------------------------------------------------
        # STEP 2: FMEA & SPOF Identification
        # -------------------------------------------------------------
        # Evaluate normal distributed DB failure mode
        fmea_db = self.orchestrator.evaluate_failure_mode(
            component_id="e2e-core-db",
            failure_mode_name="ReplicaPartition",
            potential_causes=["Network switch failure"],
            local_impact="Quorum degraded",
            downstream_impact="Temporary write quorum latency increase",
            severity_score=6,
            probability_score=4,
            detectability_score=3,
            existing_controls=["HealthChecker", "AutomaticLeaderElection"],
        )
        self.assertEqual(fmea_db.risk_priority_number, 72)
        self.assertFalse(fmea_db.is_spof)

        # Evaluate legacy cache failure mode (Severe, no redundancy -> Must flag as SPOF)
        fmea_cache = self.orchestrator.evaluate_failure_mode(
            component_id="e2e-legacy-cache",
            failure_mode_name="OOMCrash",
            potential_causes=["Unbounded cache key growth"],
            local_impact="Cache service crash",
            downstream_impact="Total session cache eviction and downstream cascade",
            severity_score=9,
            probability_score=7,
            detectability_score=6,
            existing_controls=[],
        )
        self.assertEqual(fmea_cache.risk_priority_number, 378)
        self.assertTrue(fmea_cache.is_spof)

        spofs = self.orchestrator.list_spofs()
        self.assertEqual(len(spofs), 1)
        self.assertEqual(spofs[0].component_id, "e2e-legacy-cache")

        # -------------------------------------------------------------
        # STEP 3: Resilience Objectives Formulation
        # -------------------------------------------------------------
        rto_obj = ResilienceObjectiveRecord(
            objective_id="obj-rto-e2e-core-db",
            component_id="e2e-core-db",
            objective_type=ResilienceObjectiveType.RTO,
            target_value=120.0,
            unit="seconds",
        )
        self.orchestrator.repo.save_objective(rto_obj)

        rpo_obj = ResilienceObjectiveRecord(
            objective_id="obj-rpo-e2e-core-db",
            component_id="e2e-core-db",
            objective_type=ResilienceObjectiveType.RPO,
            target_value=30.0,
            unit="seconds",
        )
        self.orchestrator.repo.save_objective(rpo_obj)

        # -------------------------------------------------------------
        # STEP 4: Controlled Failure Scenario Synthesis & Safety Guards
        # -------------------------------------------------------------
        # Blocked in production without sandbox wrapper
        with self.assertRaises(PermissionError):
            self.orchestrator.generate_scenario(
                title="Unsafe Production Partition",
                category="INFRASTRUCTURE",
                affected_components=["e2e-core-db"],
                expected_behavior="Cluster failure",
                target_environment="PRODUCTION",
            )

        # Valid isolated sandbox scenario
        scenario = self.orchestrator.generate_scenario(
            title="Isolated Latency Spike Simulation",
            category="PERFORMANCE",
            affected_components=["e2e-auth-svc"],
            expected_behavior="Auth client degrades gracefully and applies circuit breaking",
            target_environment="ISOLATED_SANDBOX",
        )
        self.assertEqual(scenario.target_environment, "ISOLATED_SANDBOX")
        self.assertIn("e2e-auth-svc", scenario.affected_components)

        # -------------------------------------------------------------
        # STEP 5 & 6: Fault Injection Lifecycle & Containment Check
        # -------------------------------------------------------------
        # Fault injection without M20 approval token must be rejected
        with self.assertRaises(PermissionError):
            self.orchestrator.run_fault_experiment(
                scenario_id=scenario.scenario_id,
                hypothesis="Simulated latency does not cause thread pool exhaustion",
                approval_token="",
            )

        # Run experiment with valid M20 cryptographic token
        exp = self.orchestrator.run_fault_experiment(
            scenario_id=scenario.scenario_id,
            hypothesis="Simulated latency does not cause thread pool exhaustion",
            approval_token="M20_CRYPTO_TOKEN_EXPERIMENT_AUTH_7718",
            target_environment="ISOLATED_SANDBOX",
        )
        self.assertEqual(exp.lifecycle_state, ExperimentLifecycleState.COMPLETED)
        self.assertTrue(exp.containment_successful)
        self.assertFalse(exp.cascading_failure_detected)

        # -------------------------------------------------------------
        # STEP 7: Backup Inventory, Cryptographic Checksum & Restore Drill
        # -------------------------------------------------------------
        backup = self.orchestrator.register_backup(
            data_source="e2e-core-db.sqlite",
            backup_type=BackupType.SNAPSHOT,
            version="26.0.0",
            storage_reference="gs://omnia-backups/drill/20261101/core-db-snapshot.bin",
            record_count=10000,
            size_bytes=4194304,
        )
        self.assertTrue(len(backup.checksum_sha256) == 64)

        # Validate with isolated restore drill simulation
        val = self.orchestrator.validate_backup_integrity(
            backup_id=backup.backup_id,
            simulate_restore=True,
            simulate_corruption=False,
        )
        self.assertEqual(val.status, ValidationStatus.VERIFIED)
        self.assertTrue(val.checksum_verified)
        self.assertTrue(val.isolated_restore_tested)
        self.assertTrue(val.schema_compatible)

        # -------------------------------------------------------------
        # STEP 8 & 9: DR Plan Authoring & Execution with M20 Token
        # -------------------------------------------------------------
        dr_plan = self.orchestrator.create_dr_plan(
            title="E2E Full Data Center Failover Drill",
            disaster_scenario="Primary region network partition and storage corruption",
            affected_services=["e2e-core-db", "e2e-auth-svc"],
            dependency_order=["e2e-core-db", "e2e-auth-svc"],
            strategy=RecoveryStrategy.RESTORE_FROM_BACKUP,
            target_rto_sec=120.0,
            target_rpo_sec=30.0,
        )
        self.assertEqual(dr_plan.strategy, RecoveryStrategy.RESTORE_FROM_BACKUP)

        # Unauthorized execution blocked
        with self.assertRaises(PermissionError):
            self.orchestrator.execute_recovery_drill(
                plan_id=dr_plan.plan_id,
                approval_token="",
            )

        # Execute recovery drill with legitimate M20 cryptographic token
        dr_exec = self.orchestrator.execute_recovery_drill(
            plan_id=dr_plan.plan_id,
            approval_token="OMNIA_M20_DR_DRILL_AUTHORIZATION_KEY_4421",
        )
        self.assertEqual(dr_exec.status, "COMPLETED")
        self.assertEqual(len(dr_exec.steps_executed), 2)

        # -------------------------------------------------------------
        # STEP 10: Distributed State Consistency Audit
        # -------------------------------------------------------------
        # Healthy audit
        audit_healthy = self.orchestrator.audit_state_consistency(
            subsystem="persistence",
            expected_epoch=108,
            reported_epoch=108,
            checkpoint_count=10,
            replica_lag_sec=0.05,
        )
        self.assertEqual(len(audit_healthy), 0)

        # Split-brain & stale epoch audit
        audit_stale = self.orchestrator.audit_state_consistency(
            subsystem="consensus",
            expected_epoch=108,
            reported_epoch=99,
            checkpoint_count=0,
            replica_lag_sec=45.0,
        )
        self.assertGreaterEqual(len(audit_stale), 2)
        divergence_types = [f.divergence_type for f in audit_stale]
        self.assertIn("SPLIT_BRAIN_STALE_EPOCH", divergence_types)
        self.assertIn("MISSING_CHECKPOINT_STATE", divergence_types)

        # -------------------------------------------------------------
        # STEP 11: Independent Recovery Verification & Demonstrated Proof
        # -------------------------------------------------------------
        ver = self.orchestrator.verify_recovery(
            execution_id=dr_exec.execution_id,
            component_id="e2e-core-db",
            actual_rto_sec=38.5,  # Well under 120.0s target
            actual_rpo_sec=5.2,   # Well under 30.0s target
            service_responsive=True,
            data_integrity_verified=True,
        )
        self.assertTrue(ver.service_responsive)
        self.assertTrue(ver.data_integrity_verified)
        self.assertTrue(ver.rto_compliant)
        self.assertTrue(ver.rpo_compliant)
        self.assertEqual(ver.actual_rto_sec, 38.5)

        # Verify resilience objectives are now flagged as demonstrated
        objs = self.orchestrator.repo.get_objectives_for_component("e2e-core-db")
        rto_found = next(o for o in objs if o.objective_type == ResilienceObjectiveType.RTO)
        self.assertTrue(rto_found.is_demonstrated)
        self.assertEqual(rto_found.demonstrated_value, 38.5)

        # -------------------------------------------------------------
        # STEP 12: Resilience Regression Detection
        # -------------------------------------------------------------
        # Baseline RTO was 38.5s; test regression of 85.0s (+120.7% degradation)
        regr = self.orchestrator.check_resilience_regression(
            component_id="e2e-core-db",
            metric_name="RECOVERY_TIME_OBJECTIVE_SEC",
            baseline_value=38.5,
            current_value=85.0,
        )
        self.assertIsNotNone(regr)
        self.assertGreater(regr.degradation_pct, 100.0)

        # -------------------------------------------------------------
        # STEP 13: Executive Reliability Overview Report
        # -------------------------------------------------------------
        overview = self.orchestrator.get_reliability_overview()
        self.assertEqual(overview["total_monitored_components"], 3)
        self.assertEqual(overview["single_points_of_failure_count"], 1)
        self.assertEqual(overview["single_points_of_failure"][0]["component_id"], "e2e-legacy-cache")
        self.assertEqual(overview["active_regressions_count"], 1)
        self.assertIn(overview["overall_posture"], ["NORMAL", "ELEVATED_RISK", "RESILIENCE_REGRESSION"])


if __name__ == "__main__":
    unittest.main()
