"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
End-to-End Lifecycle & Synthetic Scenario Test Suite - test_secops_e2e_module47.py

Executes a full 12-step autonomous defensive security operations drill:
1. Register authorized multi-cloud & identity telemetry sources.
2. Ingest and normalize heterogeneous telemetry with payload verification.
3. Establish behavioral baseline for API workloads, verifying cold-start safety.
4. Execute deterministic threat detection (brute-force login bursts).
5. Detect statistical anomaly for sudden API rate surges exceeding 3-sigma.
6. Ingest threat intelligence indicators (malicious C2 IP) with confidence scoring.
7. Correlate multiple discrete signals into a unified multi-stage attack graph.
8. Evaluate transparent contextual risk score factoring asset criticality and privilege.
9. Launch investigation workbench and maintain competing hypotheses.
10. Propose defensive response plan and attempt containment execution without approval (must fail closed).
11. Authorize containment via Module 20 human approval token and execute adapter action.
12. Assemble and cryptographically seal tamper-evident forensic evidence package (SHA-256).
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from persistence.migrations import MIGRATION_V32
from secops.containment_gateway import ContainmentAuthorizationError
from secops.models import (
    AlertStatus,
    BaselineStatus,
    EventResult,
    IncidentPriority,
    IncidentStatus,
    IndicatorType,
    OperationalRisk,
    ResponseActionType,
    SecuritySeverity,
)
from secops.persistence import SecOpsRepository
from secops.service import SecurityOperationsOrchestrator


class TestModule47SecOpsE2E(unittest.TestCase):
    """End-to-end integration and scenario drills for Module 47."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

        conn = sqlite3.connect(self.db_path)
        conn.executescript(MIGRATION_V32)
        conn.commit()
        conn.close()

        self.repo = SecOpsRepository(db_path=self.db_path)
        self.orchestrator = SecurityOperationsOrchestrator(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass

    def test_complete_soc_intelligence_lifecycle_drill(self):
        """Execute the complete 12-step SOC threat detection, correlation, and response drill."""
        # --- Step 1: Register Authorized Telemetry Sources ---
        idp_src = self.orchestrator.source_registry.register_source(
            provider="AUTH0_ENTERPRISE",
            environment="PRODUCTION",
            collection_method="WEBHOOK",
            auth_method="HMAC_SHA256",
            asset_scope=["identity:auth0:tenant-prod"],
            event_types_supported=["USER_LOGIN_FAILED", "USER_LOGIN_SUCCESS", "ROLE_ASSIGNMENT"],
        )
        api_src = self.orchestrator.source_registry.register_source(
            provider="KONG_API_GATEWAY",
            environment="PRODUCTION",
            collection_method="SYSLOG_TLS",
            auth_method="MTLS",
            asset_scope=["service:api-gateway-core", "service:payment-processing"],
            event_types_supported=["API_REQUEST", "RATE_LIMIT_EXCEEDED"],
        )
        self.assertEqual(idp_src.health_status, "HEALTHY")
        self.assertEqual(api_src.health_status, "HEALTHY")

        # --- Step 2: Normalization & Ingestion Integrity ---
        raw_login = {
            "event_type": "USER_LOGIN_FAILED",
            "category": "IDENTITY",
            "actor": "compromised_svc@omnia.internal",
            "target": "vault_service",
            "result": "FAILURE",
            "src_ip": "185.220.101.5",
        }
        event = self.orchestrator.normalizer.normalize_event(
            source_id=idp_src.source_id,
            provider=idp_src.provider,
            raw_payload=raw_login,
        )
        self.assertFalse(event.is_quarantined)
        self.assertIsNotNone(event.raw_payload_hash)

        # --- Step 3: Establish Behavioral Baseline ---
        actor_id = "compromised_svc@omnia.internal"
        # Seed 25 normal baseline observations around mean 5.0
        for _ in range(25):
            self.orchestrator.baselines.update_entity_metric(
                entity_id=actor_id,
                entity_type="SERVICE_ACCOUNT",
                metric_name="api_request_rate",
                observed_value=5.0,
            )
        # Settle baseline variance
        self.orchestrator.baselines.update_entity_metric(actor_id, "SERVICE_ACCOUNT", "api_request_rate", 6.0)
        self.orchestrator.baselines.update_entity_metric(actor_id, "SERVICE_ACCOUNT", "api_request_rate", 4.0)

        baseline = self.repo.get_baseline(actor_id, "api_request_rate")
        self.assertEqual(baseline.status, BaselineStatus.ESTABLISHED)
        self.assertGreaterEqual(baseline.confidence_level, 0.9)

        # --- Step 4: Deterministic Rule Detection (Brute Force) ---
        auth_alerts = self.orchestrator.ingest_and_detect(
            source_id=idp_src.source_id,
            provider=idp_src.provider,
            raw_payload=raw_login,
        )
        self.assertGreaterEqual(len(auth_alerts), 1)
        brute_alert = auth_alerts[0]
        self.assertEqual(brute_alert.rule_id, "RULE-AUTH-001")

        # --- Step 5: Statistical Anomaly Detection (API Surge) ---
        raw_surge = {
            "event_type": "API_REQUEST",
            "category": "API",
            "actor": actor_id,
            "target": "payment-processing",
            "result": "SUCCESS",
            "metadata": {"api_request_rate": 250.0},
        }
        anom_alerts = self.orchestrator.ingest_and_detect(
            source_id=api_src.source_id,
            provider=api_src.provider,
            raw_payload=raw_surge,
        )
        self.assertGreaterEqual(len(anom_alerts), 1)
        surge_alert = anom_alerts[0]
        self.assertEqual(surge_alert.rule_id, "RULE-ANOM-001")

        # --- Step 6: Threat Intelligence Enrichment ---
        c2_ip = "185.220.101.5"
        threat_rec = self.orchestrator.threat_intel.record_indicator(
            indicator_type=IndicatorType.IP,
            indicator_value=c2_ip,
            source_provider="ABUSE_CH_FEODO",
            threat_actor="APT-FIN-99",
            campaign="Credential-Drain-2026",
            confidence=0.92,
            mitre_techniques=["T1071", "T1078"],
        )
        self.assertEqual(threat_rec.threat_actor, "APT-FIN-99")

        # --- Step 7: Temporal Event & Alert Correlation ---
        corr_graph = self.orchestrator.correlation_engine.correlate_alerts_by_entity(
            alerts=[brute_alert, surge_alert],
            entity_id=actor_id,
            correlation_title="Multi-Stage Credential Attack and API Data Surge",
        )
        self.assertIsNotNone(corr_graph)
        self.assertEqual(len(corr_graph.attack_chain_sequence), 2)
        self.assertGreaterEqual(corr_graph.correlation_confidence, 0.8)

        # --- Step 8: Multi-Dimensional Transparent Risk Scoring ---
        risk_result = self.orchestrator.risk_scorer.evaluate_risk(
            severity=SecuritySeverity.CRITICAL,
            confidence=0.92,
            asset_criticality="MISSION_CRITICAL",
            actor_is_privileged=True,
            correlated_events_count=len(corr_graph.participating_event_ids),
        )
        self.assertGreaterEqual(risk_result["risk_score"], 85.0)
        self.assertEqual(risk_result["priority"], IncidentPriority.P0_IMMEDIATE)

        # --- Step 9: Incident & Investigation Workbench ---
        incident = self.orchestrator.incident_manager.create_incident(
            title="Active Compromised Service Account Hijack",
            description=f"Entity {actor_id} exhibiting brute force login followed by 250 rps API surge from known C2 {c2_ip}.",
            severity=SecuritySeverity.CRITICAL,
            priority=risk_result["priority"],
            affected_assets=["service:payment-processing"],
            affected_identities=[actor_id],
            related_alert_ids=[brute_alert.alert_id, surge_alert.alert_id],
            assigned_owner="lead_soc_analyst",
        )
        self.assertEqual(incident.status, IncidentStatus.DETECTED)

        investigation = self.orchestrator.incident_manager.create_investigation(
            title=f"Forensic Investigation on {actor_id}",
            assigned_analyst="lead_soc_analyst",
            primary_hypothesis="Compromised service account credential leaked to external C2 node.",
            supporting_event_ids=corr_graph.participating_event_ids,
            affected_assets=["service:payment-processing"],
            affected_identities=[actor_id],
        )
        self.assertEqual(investigation.status, "OPEN")

        # --- Step 10: Response Planning & Fail-Closed Containment Gate ---
        response_plan = self.orchestrator.response_planner.generate_response_plan(
            incident_id=incident.incident_id,
            action_type=ResponseActionType.DISABLE_ACCOUNT,
            target_identifier=actor_id,
            justification="Halt active unauthorized API exfiltration",
            operational_risk=OperationalRisk.HIGH,
        )
        self.assertTrue(response_plan.requires_approval)

        # Containment execution without Module 20 human approval must fail closed
        with self.assertRaises(ContainmentAuthorizationError):
            self.orchestrator.containment_gateway.execute_containment(
                plan_id=response_plan.plan_id,
                operator="auto_soc_guard",
                approval_token=None,
            )

        # --- Step 11: Execute Approved Containment ---
        containment_record = self.orchestrator.containment_gateway.execute_containment(
            plan_id=response_plan.plan_id,
            operator="auto_soc_guard",
            approval_token="M20-APPROVAL-SEC-DEFENSE-47",
        )
        self.assertEqual(containment_record.status, "EXECUTED")
        self.assertTrue(containment_record.execution_result.get("account_locked"))

        # Incident status is now CONTAINED
        updated_inc = self.repo.get_incident(incident.incident_id)
        self.assertEqual(updated_inc.status, IncidentStatus.CONTAINED)

        # --- Step 12: Evidence Preservation Package ---
        evidence_pkg = self.orchestrator.evidence_engine.seal_incident_evidence_package(
            incident_id=incident.incident_id,
            sealed_by="SOC Incident Commander",
            investigation_id=investigation.investigation_id,
            additional_evidence={"c2_intel": threat_rec.indicator_value, "correlation_id": corr_graph.correlation_id},
        )
        self.assertIsNotNone(evidence_pkg.package_digest_sha256)
        self.assertGreater(len(evidence_pkg.package_digest_sha256), 32)
        self.assertEqual(evidence_pkg.sealed_by, "SOC Incident Commander")

        # --- Step 13: Benchmark Evaluation Metrics ---
        eval_metrics = self.orchestrator.evaluator.evaluate_benchmark(
            dataset_name="SYNTHETIC_SOC_BENCHMARK_M47",
            true_positives=95,
            false_positives=2,
            false_negatives=3,
            true_negatives=900,
        )
        self.assertGreaterEqual(eval_metrics.precision_score, 0.95)
        self.assertGreaterEqual(eval_metrics.recall_score, 0.95)
        self.assertGreaterEqual(eval_metrics.f1_score, 0.95)


if __name__ == "__main__":
    unittest.main()
