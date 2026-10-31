"""
Unit tests for Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.

Covers:
1. Service Inventory Registration and Dependency Graph
2. Telemetry Ingestion with Credential Scrubbing (metrics, logs, spans)
3. Freshness-aware Health Assessment & Stale State Degradation
4. SLO Tracking and Error Budget Burn Rate
5. Alert Creation, Anomaly Detection & Incident Correlation
6. Incident Lifecycle Transitions and Human-in-the-Loop Recovery Gate
"""

import unittest
import os
import sqlite3
import tempfile

from persistence.migrations import MIGRATION_V25
from operations_center.models import (
    ServiceCriticality,
    SystemHealthState,
    IncidentSeverity,
    IncidentLifecycleState,
    RecoveryActionStatus,
    IncidentRecord,
)
from operations_center.service import OperationsCenterOrchestrator


class TestOperationsCenterModule40(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        # Initialize Module 40 schema tables directly
        conn = sqlite3.connect(self.db_path)
        conn.executescript(MIGRATION_V25)
        conn.close()
        self.orchestrator = OperationsCenterOrchestrator(db_path=self.db_path)
        self.repo = self.orchestrator.repo

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    def test_01_service_inventory_and_dependencies(self):
        """Test registering services with dependencies and retrieving them."""
        # Register database service
        db_svc = self.orchestrator.register_service(
            service_id="svc-postgres",
            service_name="PostgreSQL Database",
            criticality=ServiceCriticality.MISSION_CRITICAL,
            owner="persistence",
            endpoints=["localhost:5432"],
        )
        self.assertEqual(db_svc.service_id, "svc-postgres")
        self.assertEqual(db_svc.criticality, ServiceCriticality.MISSION_CRITICAL)

        # Register API gateway depending on DB
        api_svc = self.orchestrator.register_service(
            service_id="svc-api-gateway",
            service_name="API Gateway",
            criticality=ServiceCriticality.HIGH,
            owner="gateway",
            dependencies=["svc-postgres"],
            endpoints=["https://api.omnia.local"],
        )
        self.assertIn("svc-postgres", api_svc.dependencies)

        # Check downstream dependents
        dependents = self.orchestrator.inventory.get_downstream_dependents("svc-postgres")
        self.assertIn("svc-api-gateway", dependents)

    def test_02_telemetry_ingestion_and_secret_scrubbing(self):
        """Test multi-tier telemetry ingestion and zero-credential credential scrubbing."""
        # 1. Metric ingestion
        m = self.orchestrator.ingest_metric(
            service_id="svc-api-gateway",
            metric_name="http_request_duration_ms",
            metric_value=45.2,
            unit="milliseconds",
        )
        self.assertEqual(m.metric_name, "http_request_duration_ms")
        self.assertEqual(m.value, 45.2)

        # 2. Log ingestion with sensitive bearer token and password
        dirty_log = "User auth failed. Provided token: Bearer eyJhbGciOiJIUzI1Ni. Secret password=SuperSecretP@ss123"
        log_rec = self.orchestrator.ingest_log(
            service_id="svc-api-gateway",
            level="ERROR",
            message=dirty_log,
        )
        # Verify scrubbing
        self.assertNotIn("eyJhbGciOiJIUzI1Ni", log_rec.message)
        self.assertNotIn("SuperSecretP@ss123", log_rec.message)
        self.assertIn("[REDACTED_CREDENTIAL]", log_rec.message)

        # 3. Trace span ingestion
        span = self.orchestrator.ingest_trace_span(
            trace_id="tr-100",
            span_id="sp-200",
            service_id="svc-api-gateway",
            operation_name="authenticate_request",
            duration_ms=12.4,
            status_code=200,
        )
        self.assertEqual(span.trace_id, "tr-100")
        self.assertEqual(span.duration_ms, 12.4)

    def test_03_health_freshness_and_stale_degradation(self):
        """Test that fresh observations report current state and stale ones degrade to UNKNOWN."""
        # Register service
        self.orchestrator.register_service(
            service_id="svc-worker-1",
            service_name="Background Worker 1",
            criticality=ServiceCriticality.MEDIUM,
            owner="execution",
        )

        # Fresh observation
        fresh_obs = self.orchestrator.record_health_observation(
            service_id="svc-worker-1",
            health_state=SystemHealthState.HEALTHY,
            latency_ms=5.0,
            status_message="Healthy heartbeat",
        )
        self.assertEqual(fresh_obs.health_state, SystemHealthState.HEALTHY)
        self.assertFalse(fresh_obs.is_stale)

        # Retrieve through health aggregator
        latest = self.orchestrator.get_service_health("svc-worker-1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.health_state, SystemHealthState.HEALTHY)

        # Record stale health check by passing max_freshness_seconds=0
        stale_check = self.orchestrator.get_service_health("svc-worker-1", max_freshness_seconds=0.0)
        self.assertIsNotNone(stale_check)
        self.assertTrue(stale_check.is_stale)
        self.assertEqual(stale_check.health_state, SystemHealthState.UNKNOWN)

    def test_04_slo_management_and_burn_rate(self):
        """Test SLO registration, SLI updates, error budget depletion, and burn rate tracking."""
        slo = self.orchestrator.register_slo(
            slo_id="slo-api-availability",
            slo_name="API Gateway Availability 99.9%",
            service_id="svc-api-gateway",
            target_sli_percent=99.9,
        )
        self.assertEqual(slo.target_pct, 99.9)
        self.assertEqual(slo.error_budget_remaining_pct, 100.0)

        # Update with high error burn
        updated = self.orchestrator.update_slo_metrics(
            slo_id="slo-api-availability",
            sli_current_percent=98.5,
            budget_remaining_percent=-50.0,
            burn_rate_30d=14.4,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.current_sli_pct, 98.5)
        self.assertEqual(updated.error_budget_remaining_pct, -50.0)
        self.assertEqual(updated.burn_rate, 14.4)

    def test_05_alert_raising_and_incident_correlation(self):
        """Test raising deduplicated alerts and clustering them into correlated incidents."""
        # Raise alert on primary service
        a1 = self.orchestrator.raise_alert(
            alert_name="HighErrorRate",
            service_id="svc-postgres",
            severity=IncidentSeverity.SEV_1_CRITICAL,
            description="PostgreSQL connection pool exhaustion",
            metric_value=100.0,
        )
        self.assertEqual(a1.severity, IncidentSeverity.SEV_1_CRITICAL)
        self.assertIsNone(a1.correlated_incident_id)

        # Correlate alerts
        incidents = self.orchestrator.correlate_active_alerts()
        self.assertEqual(len(incidents), 1)
        inc = incidents[0]
        self.assertEqual(inc.primary_service_id, "svc-postgres")
        self.assertEqual(inc.severity, IncidentSeverity.SEV_1_CRITICAL)
        self.assertEqual(inc.state, IncidentLifecycleState.DETECTED)

        # Raise another alert for the same service
        a2 = self.orchestrator.raise_alert(
            alert_name="HighLatency",
            service_id="svc-postgres",
            severity=IncidentSeverity.SEV_2_HIGH,
            description="Query latency spike",
        )
        # Correlate again: alert should get assigned
        incidents_after = self.orchestrator.correlate_active_alerts()
        self.assertEqual(len(incidents_after), 1)

    def test_06_lifecycle_and_human_approval_recovery_gate(self):
        """Test deterministic incident state transitions and cryptographic approval gate for recovery."""
        # Set up an incident
        inc = IncidentRecord(
            incident_id="inc-test-40",
            title="Service Degraded Incident",
            severity=IncidentSeverity.SEV_2_HIGH,
            state=IncidentLifecycleState.DETECTED,
            primary_service_id="svc-api-gateway",
            correlated_alert_ids=["alt-1"],
        )
        self.repo.save_incident(inc)

        # Transition DETECTED -> TRIAGED -> INVESTIGATING
        t1 = self.orchestrator.transition_incident_state("inc-test-40", IncidentLifecycleState.TRIAGED, "Triaged by SRE")
        self.assertEqual(t1.state, IncidentLifecycleState.TRIAGED)

        t2 = self.orchestrator.transition_incident_state("inc-test-40", IncidentLifecycleState.INVESTIGATING, "Root cause search")
        self.assertEqual(t2.state, IncidentLifecycleState.INVESTIGATING)

        # Formulate recovery proposal
        proposals = self.orchestrator.generate_recovery_proposals("inc-test-40")
        self.assertGreater(len(proposals), 0)
        p = proposals[0]

        # 1. Attempt execution WITHOUT approval token -> Must FAIL / APPROVAL_REQUIRED
        rejected_result = self.orchestrator.execute_recovery_action(proposal_id=p.proposal_id)
        self.assertEqual(rejected_result["status"], "APPROVAL_REQUIRED")
        self.assertIn("Module 20", rejected_result["reason"])

        # 2. Execute WITH valid Module 20 human approval token -> Must SUCCEED
        valid_token = "OMNIA_M20_APPROVED_SIG_d93a7c001"
        approved_result = self.orchestrator.execute_recovery_action(
            proposal_id=p.proposal_id,
            approval_token=valid_token,
            operator_notes="Approved by Primary On-Call Engineer",
        )
        self.assertEqual(approved_result["status"], "SUCCESS")
        self.assertEqual(approved_result["approval_token"], valid_token)

        # Verify proposal status in repo
        updated_p = self.repo.get_recovery_proposal(p.proposal_id)
        self.assertEqual(updated_p.status, RecoveryActionStatus.VERIFIED)


if __name__ == "__main__":
    unittest.main()
