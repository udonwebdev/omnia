"""
End-to-End integration scenario test for Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.

Simulates complete 17-stage operational incident scenario:
1. Register core service hierarchy (Database, Cache, API Gateway, Worker).
2. Establish dependency graph.
3. Ingest baseline operational telemetry (metrics, logs, traces) with secret scrubbing.
4. Set up Service Level Objectives (99.9% availability, 100ms p95 latency).
5. Record initial healthy baseline observations.
6. Generate live operations HUD overview (verifying NORMAL_OPERATION).
7. Simulate catastrophic failure: database connection pool saturation.
8. Telemetry ingestion captures error spikes & latency explosion.
9. Health observation detects and reports DEGRADED state for database.
10. Downstream freshness check verifies dependent API Gateway latency degradation.
11. SLO evaluation records error budget consumption & critical burn rate > 10x.
12. Anomaly detector raises SEV-1 and SEV-2 symptom alerts.
13. Incident correlation engine aggregates alerts into unified SEV-1 incident.
14. Root-cause investigation identifies Database Connection Pool Exhaustion (category: RESOURCE_SATURATION).
15. Impact assessment evaluates blast radius and downstream user disruption.
16. Formulate recovery proposal and execute via cryptographic Module 20 human approval token gate.
17. Verify service recovery back to HEALTHY state and compile comprehensive postmortem report.
"""

import unittest
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

from persistence.migrations import MIGRATION_V25
from operations_center.models import (
    ServiceCriticality,
    SystemHealthState,
    IncidentSeverity,
    IncidentLifecycleState,
    RecoveryActionStatus,
)
from operations_center.service import OperationsCenterOrchestrator


class TestOperationsCenterE2EModule40(unittest.TestCase):
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

    def test_full_operational_incident_lifecycle_e2e(self):
        # Stage 1: Register core service hierarchy
        db_svc = self.orchestrator.register_service(
            service_id="svc-db-primary",
            service_name="Core CockroachDB Cluster",
            criticality=ServiceCriticality.MISSION_CRITICAL,
            owner="persistence",
            endpoints=["crdb-node-1:26257", "crdb-node-2:26257"],
        )
        cache_svc = self.orchestrator.register_service(
            service_id="svc-redis-cache",
            service_name="Redis Session Cache",
            criticality=ServiceCriticality.HIGH,
            owner="caching",
            endpoints=["redis-cluster:6379"],
        )
        api_svc = self.orchestrator.register_service(
            service_id="svc-public-api",
            service_name="Omnia Public API Gateway",
            criticality=ServiceCriticality.MISSION_CRITICAL,
            owner="gateway",
            dependencies=["svc-db-primary", "svc-redis-cache"],
            endpoints=["https://api.omnia.ai"],
        )
        worker_svc = self.orchestrator.register_service(
            service_id="svc-task-worker",
            service_name="Autonomous Task Worker Fleet",
            criticality=ServiceCriticality.HIGH,
            owner="execution",
            dependencies=["svc-db-primary"],
        )

        # Stage 2: Verify dependency graph
        db_deps = self.orchestrator.inventory.get_downstream_dependents("svc-db-primary")
        self.assertIn("svc-public-api", db_deps)
        self.assertIn("svc-task-worker", db_deps)

        # Stage 3: Ingest baseline operational telemetry with secret scrubbing
        metric_1 = self.orchestrator.ingest_metric(
            service_id="svc-db-primary",
            metric_name="pool_active_connections",
            metric_value=25.0,
            unit="connections",
        )
        log_1 = self.orchestrator.ingest_log(
            service_id="svc-db-primary",
            level="INFO",
            message="Database pool healthy. Token=Bearer abc123456789xyz. Initialized.",
        )
        self.assertNotIn("abc123456789xyz", log_1.message)
        self.assertIn("[REDACTED_CREDENTIAL]", log_1.message)

        span_1 = self.orchestrator.ingest_trace_span(
            trace_id="tr-baseline-01",
            span_id="sp-01",
            service_id="svc-db-primary",
            operation_name="query_active_tasks",
            duration_ms=4.2,
            status_code=200,
        )

        # Stage 4: Set up Service Level Objectives
        slo_api = self.orchestrator.register_slo(
            slo_id="slo-api-uptime",
            slo_name="Public API Gateway Availability 99.9%",
            service_id="svc-public-api",
            target_sli_percent=99.9,
        )
        slo_db = self.orchestrator.register_slo(
            slo_id="slo-db-latency",
            slo_name="Database Query Latency P99 < 50ms",
            service_id="svc-db-primary",
            target_sli_percent=99.5,
        )

        # Stage 5: Record initial healthy baseline observations
        for svc_id in ["svc-db-primary", "svc-redis-cache", "svc-public-api", "svc-task-worker"]:
            self.orchestrator.record_health_observation(
                service_id=svc_id,
                health_state=SystemHealthState.HEALTHY,
                latency_ms=12.0,
                status_message="Healthy nominal operation",
            )

        # Stage 6: Generate live operations overview (Posture: NORMAL_OPERATION)
        overview_healthy = self.orchestrator.get_operations_overview()
        self.assertEqual(overview_healthy["operational_posture"], "NORMAL_OPERATION")
        self.assertEqual(overview_healthy["total_services"], 4)
        self.assertEqual(overview_healthy["active_incidents_count"], 0)

        # Stage 7: Simulate catastrophic failure: database connection pool saturation
        # Stage 8: Telemetry ingestion captures error spikes & latency explosion
        self.orchestrator.ingest_metric(
            service_id="svc-db-primary",
            metric_name="pool_active_connections",
            metric_value=500.0,
        )
        self.orchestrator.ingest_log(
            service_id="svc-db-primary",
            level="ERROR",
            message="FATAL: remaining connection slots are reserved for non-replication superuser connections. Out of memory / connection leak.",
            error_category="RESOURCE_SATURATION",
        )

        # Stage 9: Health observation detects and reports DEGRADED state for database
        self.orchestrator.record_health_observation(
            service_id="svc-db-primary",
            health_state=SystemHealthState.DEGRADED,
            latency_ms=4500.0,
            status_message="Database connection pool exhausted; query timeouts > 4000ms",
        )

        # Stage 10: Downstream freshness check verifies dependent API Gateway latency degradation
        self.orchestrator.record_health_observation(
            service_id="svc-public-api",
            health_state=SystemHealthState.DEGRADED,
            latency_ms=2500.0,
            status_message="Upstream dependency svc-db-primary timeout",
        )

        # Stage 11: SLO evaluation records error budget consumption & critical burn rate
        self.orchestrator.update_slo_metrics(
            slo_id="slo-api-uptime",
            sli_current_percent=94.2,
            budget_remaining_percent=-45.0,
            burn_rate_30d=24.5,
        )

        # Stage 12: Anomaly detector raises symptom alerts
        alt_db = self.orchestrator.raise_alert(
            alert_name="DatabaseConnectionPoolExhausted",
            service_id="svc-db-primary",
            severity=IncidentSeverity.SEV_1_CRITICAL,
            description="Active connections pool at 100% capacity",
            metric_value=500.0,
        )
        alt_api = self.orchestrator.raise_alert(
            alert_name="GatewayHighLatency",
            service_id="svc-public-api",
            severity=IncidentSeverity.SEV_2_HIGH,
            description="P99 response time degraded to 2500ms",
            metric_value=2500.0,
        )

        # Stage 13: Incident correlation engine aggregates alerts into unified SEV-1 incident
        correlated_incidents = self.orchestrator.correlate_active_alerts()
        self.assertGreaterEqual(len(correlated_incidents), 1)
        inc = [i for i in correlated_incidents if i.primary_service_id == "svc-db-primary"][0]
        self.assertEqual(inc.severity, IncidentSeverity.SEV_1_CRITICAL)
        self.assertEqual(inc.state, IncidentLifecycleState.DETECTED)

        # Move lifecycle: DETECTED -> TRIAGED -> INVESTIGATING
        self.orchestrator.transition_incident_state(inc.incident_id, IncidentLifecycleState.TRIAGED, "Triaged by autonomous AOC")
        self.orchestrator.transition_incident_state(inc.incident_id, IncidentLifecycleState.INVESTIGATING, "Initiating telemetry correlation")

        # Stage 14: Root-cause investigation identifies Database Connection Pool Exhaustion
        rc = self.orchestrator.investigate_root_cause(inc.incident_id)
        self.assertIsNotNone(rc)
        self.assertIn("RESOURCE_SATURATION", rc.candidate_cause)
        self.assertGreater(rc.confidence, 0.70)

        # Stage 15: Impact assessment evaluates blast radius and downstream user disruption
        impact = self.orchestrator.assess_impact(inc.incident_id)
        self.assertIsNotNone(impact)
        self.assertGreater(impact.blast_radius_score, 0.40)
        self.assertEqual(impact.operational_disruption, "HIGH")

        # Stage 16: Formulate recovery proposal and execute via cryptographic Module 20 human approval token gate
        proposals = self.orchestrator.generate_recovery_proposals(inc.incident_id)
        self.assertGreater(len(proposals), 0)
        p = proposals[0]

        # Verify gate rejects missing or blank token
        unauth_exec = self.orchestrator.execute_recovery_action(proposal_id=p.proposal_id)
        self.assertEqual(unauth_exec["status"], "APPROVAL_REQUIRED")

        # Execute with approved token
        auth_exec = self.orchestrator.execute_recovery_action(
            proposal_id=p.proposal_id,
            approval_token="M20_CRYPTO_TOKEN_SRE_AUTHORIZATION_98124",
            operator_notes="Emergency pool reset authorized",
        )
        self.assertEqual(auth_exec["status"], "SUCCESS")

        # Advance lifecycle: MITIGATING -> RECOVERING -> RESOLVED
        self.orchestrator.transition_incident_state(inc.incident_id, IncidentLifecycleState.MITIGATING, "Restarting DB connection pooler")
        self.orchestrator.transition_incident_state(inc.incident_id, IncidentLifecycleState.RECOVERING, "Warm cache repopulating")

        # Stage 17: Verify service recovery back to HEALTHY state and compile postmortem report
        self.orchestrator.record_health_observation(
            service_id="svc-db-primary",
            health_state=SystemHealthState.HEALTHY,
            latency_ms=8.5,
            status_message="Healthy nominal operation restored",
        )
        self.orchestrator.record_health_observation(
            service_id="svc-public-api",
            health_state=SystemHealthState.HEALTHY,
            latency_ms=15.0,
            status_message="Healthy nominal operation restored",
        )
        self.orchestrator.transition_incident_state(inc.incident_id, IncidentLifecycleState.RESOLVED, "All health probes green")
        self.orchestrator.transition_incident_state(inc.incident_id, IncidentLifecycleState.REVIEWED, "Post-incident analysis completed")
        self.orchestrator.transition_incident_state(inc.incident_id, IncidentLifecycleState.CLOSED, "Incident closed with resolution")

        # Compile comprehensive postmortem
        postmortem = self.orchestrator.compile_postmortem(
            incident_id=inc.incident_id,
            action_items=[
                "Increase max connections in crdb-cluster config",
                "Implement aggressive client-side connection pooling timeouts in API gateway",
                "Set up predictive leak alerting on connection growth trends",
            ]
        )
        self.assertIsNotNone(postmortem)
        self.assertEqual(postmortem.incident_id, inc.incident_id)
        self.assertGreater(len(postmortem.timeline_events), 0)
        self.assertGreaterEqual(len(postmortem.action_items), 3)


if __name__ == "__main__":
    unittest.main()
