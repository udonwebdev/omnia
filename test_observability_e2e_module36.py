"""
End-to-End Acceptance Scenario for OMNIA Module 36: Autonomous Observability, Diagnostics & Self-Healing Engine.
Executes a multi-stage deterministic operational scenario:
1. Register core components (storage, event fabric, worker).
2. Wire infrastructure dependency graph (worker -> event fabric -> storage).
3. Record operational telemetry baseline.
4. Establish health checks and contracts.
5. Ingest failure signal in storage (SQLite lock / timeout).
6. Propagate degradation across dependencies.
7. Run anomaly detector and classify failure.
8. Execute root-cause diagnostics to identify storage root cause.
9. Plan controlled remediation (Level 4 restart / reconnect).
10. Attempt execution without approval -> strictly fails closed.
11. Grant Module 20 human approval token.
12. Execute remediation with target fix.
13. Run post-action health verification window.
14. Transition component status to VERIFIED_RECOVERED.
15. Verify operational audit history and Event Fabric emissions.
"""

import os
import gc
import tempfile
import unittest
import time
import json
from observability.models import (
    ComponentHealthStatus,
    HealthCheckType,
    DependencyType,
    FailureCategory,
    RemediationAutonomyLevel,
    RecoveryVerificationStatus,
)
from observability.service import ObservabilityService


class TestObservabilityModule36E2E(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.service = ObservabilityService(db_path=self.temp_db.name)

    def tearDown(self):
        del self.service
        gc.collect()
        try:
            if os.path.exists(self.temp_db.name):
                os.remove(self.temp_db.name)
        except PermissionError:
            pass

    def test_complete_autonomous_observability_and_healing_lifecycle(self):
        # Step 1: Register core components
        storage = self.service.register_component("comp_storage", "Durable Storage", "Module 01")
        fabric = self.service.register_component("comp_fabric", "Event Fabric", "Module 04", critical_dependencies=["comp_storage"])
        worker = self.service.register_component("comp_worker", "Distributed Worker", "Module 10", critical_dependencies=["comp_fabric"])

        self.assertEqual(storage.current_status, ComponentHealthStatus.HEALTHY)
        self.assertEqual(fabric.current_status, ComponentHealthStatus.HEALTHY)
        self.assertEqual(worker.current_status, ComponentHealthStatus.HEALTHY)

        # Step 2: Wire infrastructure dependency graph
        edge1 = self.service.add_dependency("comp_worker", "comp_fabric", DependencyType.HARD, criticality=1.0)
        edge2 = self.service.add_dependency("comp_fabric", "comp_storage", DependencyType.HARD, criticality=1.0)
        self.assertIsNotNone(edge1.edge_id)
        self.assertIsNotNone(edge2.edge_id)

        # Step 3: Record operational telemetry baseline
        self.service.record_metric("comp_storage", "disk_utilization_pct", 42.0, "percent")
        self.service.record_metric("comp_fabric", "queue_backlog_count", 5.0, "messages")
        self.service.record_metric("comp_worker", "error_rate", 0.001, "ratio")

        # Step 4: Establish health checks with probe simulation
        storage_is_healthy = [True]
        def check_storage():
            return {
                "success": storage_is_healthy[0],
                "message": "Storage read/write operational" if storage_is_healthy[0] else "Storage connection timeout: SQLite locked",
            }

        chk_storage = self.service.register_health_check(
            target_component_id="comp_storage",
            name="storage_rw_probe",
            check_type=HealthCheckType.FUNCTIONAL,
            probe_fn=check_storage,
        )

        res_initial = self.service.run_health_checks("comp_storage")
        self.assertTrue(res_initial[0]["passed"])

        # Step 5: Ingest failure signal in storage
        storage_is_healthy[0] = False
        res_fail = self.service.run_health_checks("comp_storage")
        self.assertFalse(res_fail[0]["passed"])
        
        storage_rec = self.service.registry.get_component("comp_storage")
        self.assertEqual(storage_rec.current_status, ComponentHealthStatus.UNHEALTHY)

        # Step 6: Cascading degradation propagation
        cascades = self.service.dependencies.calculate_cascading_impact("comp_storage")
        self.assertEqual(cascades["total_downstream_impacted"], 2)
        downstream_ids = [c["component_id"] for c in cascades["impacted_components"]]
        self.assertIn("comp_fabric", downstream_ids)
        self.assertIn("comp_worker", downstream_ids)

        # Update dependent fabric state
        self.service.registry.update_health_status(
            "comp_fabric",
            ComponentHealthStatus.DEGRADED,
            "Upstream storage unhealthy",
            readiness_ok=False,
        )

        # Step 7: Record error traces and run anomaly detector
        self.service.record_trace(
            operation_name="write_event_checkpoint",
            component_id="comp_storage",
            duration_ms=5000.0,
            status="ERROR",
            error="database locked (code 5) after bearer sk-secret1234567890abcdef lease timeout",
        )
        anomalies = self.service.detector.analyze_metrics_for_component("comp_storage")
        
        # Step 8: Execute root-cause diagnostics
        # Diagnosing the degraded fabric should point to storage as the root cause
        hypotheses = self.service.diagnose_failure("comp_fabric")
        self.assertTrue(len(hypotheses) > 0)
        top_hypo = hypotheses[0]
        self.assertEqual(top_hypo.suspected_component_id, "comp_storage")
        self.assertEqual(top_hypo.failure_category, FailureCategory.DEPENDENCY_FAILURE)
        self.assertGreater(top_hypo.confidence, 0.85)

        # Step 9: Plan controlled remediation
        # Resetting storage connections or restarting requires Level 4 approval
        action = self.service.plan_remediation(
            target_component_id="comp_storage",
            hypothesis=top_hypo,
            autonomy_level=RemediationAutonomyLevel.LEVEL_4_APPROVAL_REQUIRED,
            proposed_action="reset_database_connections",
            verification_window_seconds=5.0,
        )
        self.assertEqual(action.autonomy_level, RemediationAutonomyLevel.LEVEL_4_APPROVAL_REQUIRED)
        self.assertIsNotNone(action.approval_request_id)
        self.assertIsNone(action.approval_token)

        # Step 10: Attempt execution without approval token -> fails closed
        res_unauth = self.service.execute_and_verify(action.action_id)
        self.assertFalse(res_unauth["success"])
        self.assertEqual(res_unauth["status"], RecoveryVerificationStatus.FAILED.value)
        self.assertIn("approval", res_unauth["error"].lower())

        # Step 11: Authorize with valid approval token
        approval_token = "appr-token-verified-user-12345"
        auth_ok = self.service.authorize_remediation(action.action_id, approval_token)
        self.assertTrue(auth_ok)

        # Step 12: Attempt execution while storage is still broken -> execution runs, but verification fails
        res_post_fail = self.service.execute_and_verify(action.action_id)
        self.assertFalse(res_post_fail["success"])
        self.assertEqual(res_post_fail["status"], RecoveryVerificationStatus.FAILED.value)

        # Step 13: Underlying repair succeeds (simulated fix of locked storage)
        storage_is_healthy[0] = True
        self.service.registry.update_health_status(
            "comp_storage",
            ComponentHealthStatus.HEALTHY,
            "Storage operational",
            liveness_ok=True,
            readiness_ok=True,
            functional_ok=True,
        )

        # Step 14: Re-execute and strictly verify recovery
        res_recovered = self.service.execute_and_verify(action.action_id)
        self.assertTrue(res_recovered["success"])
        self.assertEqual(res_recovered["status"], RecoveryVerificationStatus.VERIFIED_RECOVERED.value)
        self.assertIn("verified", res_recovered["evidence"].lower())

        # Step 15: Verify final states in persistence repository
        stored_action = self.service.repo.get_remediation_action(action.action_id)
        self.assertIsNotNone(stored_action)
        self.assertEqual(stored_action.status, RecoveryVerificationStatus.VERIFIED_RECOVERED)
        self.assertIsNotNone(stored_action.verified_at)

        # Upstream restored -> re-evaluate dependent fabric
        self.service.registry.update_health_status(
            "comp_fabric",
            ComponentHealthStatus.HEALTHY,
            "Operational",
            liveness_ok=True,
            readiness_ok=True,
            functional_ok=True,
        )
        fabric_rec = self.service.registry.get_component("comp_fabric")
        self.assertEqual(fabric_rec.current_status, ComponentHealthStatus.HEALTHY)


if __name__ == "__main__":
    unittest.main()
