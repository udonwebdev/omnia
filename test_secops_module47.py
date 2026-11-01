"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Unit Test Suite - test_secops_module47.py
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from persistence.migrations import MIGRATION_V32
from secops.models import (
    AlertStatus,
    BaselineStatus,
    EventCategory,
    EventResult,
    IncidentPriority,
    IncidentStatus,
    IndicatorType,
    OperationalRisk,
    ResponseActionType,
    RuleType,
    SecuritySeverity,
)
from secops.persistence import SecOpsRepository
from secops.service import SecurityOperationsOrchestrator
from secops.containment_gateway import ContainmentAuthorizationError


class TestModule47SecOps(unittest.TestCase):
    """Unit tests for Module 47 components."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

        # Apply schema v32 directly to temp database
        conn = sqlite3.connect(self.db_path)
        conn.executescript(MIGRATION_V32)
        conn.commit()
        conn.close()

        self.repo = SecOpsRepository(db_path=self.db_path)
        self.orchestrator = SecurityOperationsOrchestrator(db_path=self.db_path)

        # Register standard telemetry source
        self.source = self.orchestrator.source_registry.register_source(
            provider="AWS_CLOUDTRAIL",
            environment="PRODUCTION",
            collection_method="WEBHOOK",
            auth_method="IAM_ROLE",
            asset_scope=["arn:aws:iam::123456789012:role/*", "arn:aws:s3:::production-vault"],
            event_types_supported=["USER_LOGIN_FAILED", "ROLE_ASSIGNMENT", "CONFIG_CHANGE", "API_REQUEST"],
        )
        self.source_id = self.source.source_id

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass

    def test_source_registration_and_health(self):
        """Test telemetry source registration, coverage tracking, and health toggling."""
        src = self.orchestrator.source_registry.register_source(
            provider="OKTA_IDP",
            environment="PRODUCTION",
            collection_method="EVENT_HOOK",
            auth_method="BEARER_TOKEN",
            coverage_limitations=["No MFA failure reason metadata"],
        )
        self.assertEqual(src.health_status, "HEALTHY")
        self.assertIn("No MFA failure reason metadata", src.coverage_limitations)

        self.orchestrator.source_registry.update_source_health(src.source_id, False, "Connection refused")
        updated = self.repo.get_source(src.source_id)
        self.assertEqual(updated.health_status, "UNAVAILABLE")
        self.assertEqual(updated.metadata.get("health_note"), "Connection refused")

    def test_event_normalization_and_payload_hashing(self):
        """Test normalization of heterogeneous telemetry, SHA-256 integrity hash, and quarantine."""
        raw_valid = {
            "event_type": "USER_LOGIN_FAILED",
            "category": "IDENTITY",
            "actor": "compromised_user@omnia.internal",
            "target": "login_portal",
            "result": "FAILURE",
            "src_ip": "198.51.100.24",
            "metadata": {"failure_count": 5},
        }
        event = self.orchestrator.normalizer.normalize_event(
            source_id=self.source_id,
            provider="AWS_CLOUDTRAIL",
            raw_payload=raw_valid,
        )
        self.assertFalse(event.is_quarantined)
        self.assertIsNotNone(event.raw_payload_hash)
        self.assertEqual(event.event_category, EventCategory.IDENTITY)
        self.assertEqual(event.result, EventResult.FAILURE)

        # Test quarantine of malformed telemetry (missing event_type)
        raw_invalid = {"category": "WORKLOAD", "data": "corrupt"}
        quarantined = self.orchestrator.normalizer.normalize_event(
            source_id=self.source_id,
            provider="AWS_CLOUDTRAIL",
            raw_payload=raw_invalid,
        )
        self.assertTrue(quarantined.is_quarantined)
        self.assertIn("Missing or unclassifiable event_type", quarantined.quarantine_reason)

    def test_behavioral_baseline_and_anomaly_detection(self):
        """Test online Welford statistical baselining, cold-start handling, and Z-score outlier detection."""
        actor = "service-account-batch"
        metric = "api_request_rate"

        # Cold start phase (< 5 samples)
        b1 = self.orchestrator.baselines.update_entity_metric(actor, "SERVICE_ACCOUNT", metric, 10.0)
        self.assertEqual(b1.status, BaselineStatus.COLD_START)
        self.assertLess(b1.confidence_level, 0.5)

        # Verify anomaly is not triggered prematurely on cold-start entity
        is_anom, _, conf = self.orchestrator.baselines.evaluate_anomaly(actor, metric, 50.0)
        self.assertFalse(is_anom)

        # Train baseline with 25 normal samples around mean 10.0
        for _ in range(25):
            self.orchestrator.baselines.update_entity_metric(actor, "SERVICE_ACCOUNT", metric, 10.0)

        established = self.repo.get_baseline(actor, metric)
        self.assertEqual(established.status, BaselineStatus.ESTABLISHED)
        self.assertGreaterEqual(established.confidence_level, 0.9)

        # Add slight variance so stddev is non-zero
        self.orchestrator.baselines.update_entity_metric(actor, "SERVICE_ACCOUNT", metric, 11.0)
        self.orchestrator.baselines.update_entity_metric(actor, "SERVICE_ACCOUNT", metric, 9.0)

        # Huge spike to 200.0 should trigger anomaly
        is_spike_anom, z_score, _ = self.orchestrator.baselines.evaluate_anomaly(actor, metric, 200.0, z_threshold=3.0)
        self.assertTrue(is_spike_anom)
        self.assertGreater(z_score, 10.0)

    def test_deterministic_threat_detection_rules(self):
        """Test deterministic rule firing for brute force, privilege escalation, and logging tampering."""
        # 1. Brute force alert
        raw_auth_fail = {
            "event_type": "USER_LOGIN_FAILED",
            "category": "IDENTITY",
            "actor": "attacker@dark.net",
            "asset_id": "auth-service",
            "result": "FAILURE",
        }
        alerts1 = self.orchestrator.ingest_and_detect(self.source_id, "AWS_CLOUDTRAIL", raw_auth_fail)
        self.assertEqual(len(alerts1), 1)
        self.assertEqual(alerts1[0].rule_id, "RULE-AUTH-001")

        # 2. Privilege Escalation alert
        raw_priv = {
            "event_type": "ROLE_ASSIGNMENT",
            "category": "IDENTITY",
            "actor": "rogue-contractor",
            "asset_id": "iam-directory",
            "result": "SUCCESS",
            "metadata": {"role_granted": "SUPER_ADMIN"},
        }
        alerts2 = self.orchestrator.ingest_and_detect(self.source_id, "AWS_CLOUDTRAIL", raw_priv)
        self.assertEqual(len(alerts2), 1)
        self.assertEqual(alerts2[0].rule_id, "RULE-PRIV-001")

        # 3. Audit logging disabled alert
        raw_tamper = {
            "event_type": "CONFIG_CHANGE",
            "category": "CONFIG",
            "actor": "shadow-actor",
            "asset_id": "siem-collector",
            "result": "SUCCESS",
            "metadata": {"audit_logging_disabled": True},
        }
        alerts3 = self.orchestrator.ingest_and_detect(self.source_id, "AWS_CLOUDTRAIL", raw_tamper)
        self.assertEqual(len(alerts3), 1)
        self.assertEqual(alerts3[0].rule_id, "RULE-TAMPER-001")

    def test_multi_alert_correlation_engine(self):
        """Test multi-stage alert correlation chaining sequential attacks across an entity."""
        actor = "infiltrator_007"

        # Trigger failed login alert
        e1 = {
            "event_type": "USER_LOGIN_FAILED",
            "category": "IDENTITY",
            "actor": actor,
            "asset_id": "corp-api-gw",
            "result": "FAILURE",
        }
        a1 = self.orchestrator.ingest_and_detect(self.source_id, "AWS_CLOUDTRAIL", e1)[0]

        # Trigger admin escalation alert
        e2 = {
            "event_type": "ROLE_ASSIGNMENT",
            "category": "IDENTITY",
            "actor": actor,
            "asset_id": "iam-gw",
            "result": "SUCCESS",
            "metadata": {"role_granted": "ENTERPRISE_ADMIN"},
        }
        a2 = self.orchestrator.ingest_and_detect(self.source_id, "AWS_CLOUDTRAIL", e2)[0]

        # Correlate
        graph = self.orchestrator.correlation_engine.correlate_alerts_by_entity([a1, a2], entity_id=actor)
        self.assertIsNotNone(graph)
        self.assertEqual(len(graph.participating_alert_ids), 2)
        self.assertEqual(len(graph.attack_chain_sequence), 2)
        self.assertGreaterEqual(graph.correlation_confidence, 0.8)

    def test_transparent_risk_scoring(self):
        """Test multi-factor risk scoring incorporating asset criticality and actor privilege."""
        risk = self.orchestrator.risk_scorer.evaluate_risk(
            severity=SecuritySeverity.CRITICAL,
            confidence=0.95,
            asset_criticality="MISSION_CRITICAL",
            actor_is_privileged=True,
            correlated_events_count=3,
        )
        self.assertGreaterEqual(risk["risk_score"], 80.0)
        self.assertEqual(risk["priority"], IncidentPriority.P0_IMMEDIATE)
        self.assertIn("MISSION_CRITICAL", risk["explanation"])

    def test_scoped_threat_hunting(self):
        """Test read-only bounded threat hunting queries over stored telemetry."""
        # Ingest 3 events
        for idx in range(3):
            self.orchestrator.normalizer.normalize_event(
                source_id=self.source_id,
                provider="AWS_CLOUDTRAIL",
                raw_payload={"event_type": "FILE_READ", "actor": "analyst-target", "asset_id": "data-lake"},
            )

        events = self.orchestrator.hunter.hunt_telemetry(
            analyst_operator="sec-hunter-1",
            actor_id="analyst-target",
            event_type="FILE_READ",
        )
        self.assertGreaterEqual(len(events), 3)
        for e in events:
            self.assertEqual(e.actor_id, "analyst-target")

    def test_defensive_response_and_containment_gate(self):
        """Test defensive response proposal, approval enforcement, and safe execution."""
        inc = self.orchestrator.incident_manager.create_incident(
            title="Credential Compromise in Payments Service",
            description="Active session hijacking detected.",
            severity=SecuritySeverity.CRITICAL,
            priority=IncidentPriority.P0_IMMEDIATE,
            affected_identities=["finance_user_1"],
        )

        # 1. High risk response requires approval
        plan = self.orchestrator.response_planner.generate_response_plan(
            incident_id=inc.incident_id,
            action_type=ResponseActionType.DISABLE_ACCOUNT,
            target_identifier="finance_user_1",
            justification="Compromised credentials actively used",
            operational_risk=OperationalRisk.HIGH,
        )
        self.assertTrue(plan.requires_approval)

        # Attempt execution without approval token must raise ContainmentAuthorizationError
        with self.assertRaises(ContainmentAuthorizationError):
            self.orchestrator.containment_gateway.execute_containment(
                plan_id=plan.plan_id,
                operator="auto-responder",
                approval_token=None,
            )

        # Execute with Module 20 human approval token
        action = self.orchestrator.containment_gateway.execute_containment(
            plan_id=plan.plan_id,
            operator="auto-responder",
            approval_token="M20-APPROVE-SOC-47",
        )
        self.assertEqual(action.status, "EXECUTED")
        self.assertTrue(action.execution_result.get("account_locked"))

        # Incident status must transition to CONTAINED
        updated_inc = self.repo.get_incident(inc.incident_id)
        self.assertEqual(updated_inc.status, IncidentStatus.CONTAINED)

        # 2. Seal immutable evidence package
        pkg = self.orchestrator.evidence_engine.seal_incident_evidence_package(
            incident_id=inc.incident_id,
            sealed_by="Lead Forensics Officer",
        )
        self.assertIsNotNone(pkg.package_digest_sha256)
        self.assertEqual(pkg.sealed_by, "Lead Forensics Officer")


if __name__ == "__main__":
    unittest.main()
