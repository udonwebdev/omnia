"""
Unit and safety tests for OMNIA Module 36: Autonomous Observability, Diagnostics & Self-Healing Infrastructure Engine.
"""

import os
import gc
import tempfile
import unittest
import time
from observability.models import (
    ComponentHealthStatus,
    HealthCheckType,
    DependencyType,
    FailureCategory,
    RemediationAutonomyLevel,
    RecoveryVerificationStatus,
    OperationalMetric,
    TraceSpan,
    ComponentHealthRecord,
    HealthCheckDefinition,
    InfrastructureDependencyEdge,
    DiagnosticHypothesis,
    InfrastructureRemediationAction,
)
from observability.persistence import ObservabilityRepository
from observability.telemetry import OperationalTelemetryCollector
from observability.components import ComponentHealthRegistry
from observability.checks import HealthCheckManager
from observability.dependencies import DependencyGraphBuilder
from observability.detector import OperationalAnomalyDetector
from observability.diagnostics import DiagnosticEngine
from observability.remediation import RemediationPlanner
from observability.verification import RecoveryVerifier
from observability.service import ObservabilityService


class TestObservabilityModule36(unittest.TestCase):

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

    def test_telemetry_metric_and_secret_scrubbing(self):
        """Verifies telemetry captures metrics and aggressively scrubs secrets from logs and traces."""
        collector = self.service.telemetry
        dirty_log = "Error connecting with secret bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-ID and key sk-1234567890abcdefghijklmn"
        scrubbed = collector.sanitize_log_text(dirty_log)
        self.assertNotIn("sk-1234567890abcdefghijklmn", scrubbed)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", scrubbed)
        self.assertIn("[REDACTED_SECRET]", scrubbed)

        span = self.service.record_trace(
            operation_name="db_query",
            component_id="comp_db",
            duration_ms=45.2,
            status="ERROR",
            error=dirty_log,
        )
        self.assertNotIn("sk-1234567890", span.error_message)

    def test_component_health_contract(self):
        """Verifies component is HEALTHY only when liveness, readiness, and functional checks pass."""
        rec = self.service.register_component(
            component_id="comp_worker",
            component_name="Task Worker Service",
            module_ownership="Module 10",
        )
        self.assertEqual(rec.current_status, ComponentHealthStatus.HEALTHY)

        # Fail liveness probe -> UNAVAILABLE
        self.service.registry.update_health_status(
            component_id="comp_worker",
            status=ComponentHealthStatus.UNAVAILABLE,
            message="Heartbeat missing",
            liveness_ok=False,
        )
        status = self.service.registry.evaluate_component_health("comp_worker")
        self.assertEqual(status, ComponentHealthStatus.UNAVAILABLE)

        # Restore liveness, fail readiness -> DEGRADED
        self.service.registry.update_health_status(
            component_id="comp_worker",
            status=ComponentHealthStatus.DEGRADED,
            message="Queue saturated",
            liveness_ok=True,
            readiness_ok=False,
        )
        status = self.service.registry.evaluate_component_health("comp_worker")
        self.assertEqual(status, ComponentHealthStatus.DEGRADED)

        # Restore readiness, fail functional -> UNHEALTHY
        self.service.registry.update_health_status(
            component_id="comp_worker",
            status=ComponentHealthStatus.UNHEALTHY,
            message="Syntax errors in task output",
            liveness_ok=True,
            readiness_ok=True,
            functional_ok=False,
        )
        status = self.service.registry.evaluate_component_health("comp_worker")
        self.assertEqual(status, ComponentHealthStatus.UNHEALTHY)

    def test_dependency_graph_and_cascading_impact(self):
        """Verifies directed dependency edges and downstream cascading risk computation."""
        # A depends on B (Hard), B depends on C (Hard), D depends on B (Soft)
        self.service.add_dependency("comp_A", "comp_B", DependencyType.HARD, criticality=1.0)
        self.service.add_dependency("comp_B", "comp_C", DependencyType.HARD, criticality=1.0)
        self.service.add_dependency("comp_D", "comp_B", DependencyType.SOFT, criticality=0.5)

        # If C fails, cascading impact should reach B, then A and D
        impact = self.service.dependencies.calculate_cascading_impact("comp_C")
        self.assertEqual(impact["root_failure_component"], "comp_C")
        impacted_comps = {c["component_id"]: c for c in impact["impacted_components"]}
        self.assertIn("comp_B", impacted_comps)
        self.assertIn("comp_A", impacted_comps)
        self.assertIn("comp_D", impacted_comps)
        self.assertGreater(impacted_comps["comp_A"]["failure_risk"], impacted_comps["comp_D"]["failure_risk"])

    def test_root_cause_diagnosis_with_upstream_failure(self):
        """Verifies diagnostic engine pinpoints upstream root cause rather than downstream symptom."""
        self.service.register_component("db_primary", "Primary DB", "Storage")
        self.service.register_component("api_service", "API Gateway", "Gateway")
        self.service.add_dependency("api_service", "db_primary", DependencyType.HARD)

        # Simulate db_primary failing
        self.service.registry.update_health_status(
            "db_primary",
            ComponentHealthStatus.UNAVAILABLE,
            "SQLite lock timeout",
            liveness_ok=False,
        )
        # api_service becomes degraded
        self.service.registry.update_health_status(
            "api_service",
            ComponentHealthStatus.DEGRADED,
            "Upstream queries failing",
            readiness_ok=False,
        )

        hypos = self.service.diagnose_failure("api_service")
        self.assertTrue(len(hypos) > 0)
        top_hypo = hypos[0]
        self.assertEqual(top_hypo.suspected_component_id, "db_primary")
        self.assertEqual(top_hypo.failure_category, FailureCategory.DEPENDENCY_FAILURE)
        self.assertGreaterEqual(top_hypo.confidence, 0.90)

    def test_remediation_planning_and_approval_gate(self):
        """Verifies Autonomy Level 4 mandates approval token and refuses execution without it."""
        self.service.register_component("comp_svc", "Backend Svc", "Core")
        hypo = DiagnosticHypothesis(
            hypothesis_id="hypo_test",
            suspected_component_id="comp_svc",
            failure_category=FailureCategory.PROCESS_FAILURE,
            confidence=0.88,
            explanation="Process hung",
            supporting_evidence=["Thread blocked"],
        )
        # Action requires restart -> Level 4
        action = self.service.plan_remediation(
            target_component_id="comp_svc",
            hypothesis=hypo,
            autonomy_level=RemediationAutonomyLevel.LEVEL_4_APPROVAL_REQUIRED,
            proposed_action="restart_worker",
        )
        self.assertEqual(action.autonomy_level, RemediationAutonomyLevel.LEVEL_4_APPROVAL_REQUIRED)
        self.assertIsNotNone(action.approval_request_id)
        self.assertIsNone(action.approval_token)

        # Attempt execution without approval token -> fails closed
        res = self.service.execute_and_verify(action.action_id)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], RecoveryVerificationStatus.FAILED.value)
        self.assertIn("approval", res["error"].lower())

    def test_strict_recovery_verification_contract(self):
        """Verifies action execution is never reported as recovered without post-action check verification."""
        self.service.register_component("comp_cache", "Redis Cache", "Storage")
        # Register a health check probe that currently fails
        is_repaired = [False]
        def probe_cache():
            return {
                "success": is_repaired[0],
                "message": "Connected" if is_repaired[0] else "Connection refused",
            }

        self.service.checks.register_health_check(
            target_component_id="comp_cache",
            name="cache_ping",
            check_type=HealthCheckType.READINESS,
            probe_fn=probe_cache,
        )

        hypo = DiagnosticHypothesis(
            hypothesis_id="hypo_cache",
            suspected_component_id="comp_cache",
            failure_category=FailureCategory.NETWORK_FAILURE,
            confidence=0.90,
            explanation="Cache socket timeout",
            supporting_evidence=["TCP refused"],
        )
        action = self.service.plan_remediation(
            target_component_id="comp_cache",
            hypothesis=hypo,
            autonomy_level=RemediationAutonomyLevel.LEVEL_3_LOW_RISK_AUTO,
            proposed_action="reconnect_service",
        )

        # 1. Action executes, but probe still fails -> FAILED verification
        res = self.service.execute_and_verify(action.action_id)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], RecoveryVerificationStatus.FAILED.value)

        # 2. Fix the underlying issue, retry execution -> VERIFIED_RECOVERED
        is_repaired[0] = True
        # Reset component readiness flag to true so status becomes healthy
        self.service.registry.update_health_status(
            "comp_cache",
            ComponentHealthStatus.HEALTHY,
            "Healthy",
            liveness_ok=True,
            readiness_ok=True,
            functional_ok=True,
        )
        res2 = self.service.execute_and_verify(action.action_id)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["status"], RecoveryVerificationStatus.VERIFIED_RECOVERED.value)
        self.assertIn("verified", res2["evidence"].lower())


if __name__ == "__main__":
    unittest.main()
