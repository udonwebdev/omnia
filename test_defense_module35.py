"""
OMNIA Module 35 Unit and Adversarial Tests:
Autonomous Cybersecurity, Threat Intelligence & Runtime Defense Engine.
Tests:
1. Telemetry normalization, credential scrubbing, and SHA-256 signature calculation.
2. Threat intelligence ingestion, anti-poisoning defenses (whitelists & private RFC networks), and expiration.
3. Deterministic rule evaluation, confidence & severity separation, and suppression windows.
4. Behavioral anomaly detection and rate threshold violations.
5. Multi-stage attack chain correlation and incident creation.
6. Incident lifecycle state machine enforcement (invalid transitions strictly rejected).
7. Defense autonomy levels (0 to 4) and approval token binding for containment.
8. Forensic evidence collection, tamper-evident digests, and payload verification.
9. Security posture assessment and missing telemetry source detection.
"""

import unittest
import time
import uuid
import os

from defense.models import (
    SecurityTelemetryEvent,
    ThreatIndicator,
    SecurityDetectionRule,
    ThreatAlert,
    SecurityIncident,
    ContainmentAction,
    ForensicEvidenceRecord,
    SecurityPostureAssessment,
    SecuritySeverity,
    IndicatorType,
    IndicatorValidationStatus,
    ThreatClassification,
    SecurityPostureState,
    IncidentStatus,
    ResponseAutonomyLevel,
    ContainmentStatus,
)
from defense.telemetry import SecurityEventNormalizer, SecurityTelemetryCollector
from defense.intelligence import ThreatIntelligenceManager, IndicatorValidator
from defense.detector import ThreatDetectionEngine, BehavioralAnomalyDetector
from defense.correlation import ThreatCorrelationEngine
from defense.posture import SecurityPostureAnalyzer
from defense.containment import ContainmentCoordinator
from defense.forensics import ForensicEvidenceManager
from defense.recovery import RecoveryCoordinator
from defense.persistence import DefenseRepository
from defense.service import CyberDefenseService


class TestDefenseModule35(unittest.TestCase):
    def setUp(self):
        self.test_db = f"test_defense_{uuid.uuid4().hex[:6]}.db"
        self.service = CyberDefenseService(db_path=self.test_db)

    def tearDown(self):
        # Allow Windows file lock release before removing
        try:
            import gc
            gc.collect()
            if os.path.exists(self.test_db):
                try:
                    os.remove(self.test_db)
                except PermissionError:
                    pass
        except Exception:
            pass

    def test_01_telemetry_normalization_and_secret_redaction(self):
        normalizer = SecurityEventNormalizer()
        raw = {
            "token": "sk-secret-leakage-attempt-1234567890abcdef",
            "user_id": "attacker_01",
            "details": {
                "password": "SuperSecretPassword123",
                "nested_token": "ghp_0123456789abcdef0123456789abcdef0123",
                "command": "cat /etc/passwd",
            }
        }
        evt = normalizer.normalize(
            raw_event=raw,
            source_component="auth_gateway",
            action_category="auth.login",
            outcome="FAILURE",
            severity=SecuritySeverity.HIGH,
            source_identity="attacker_01",
        )
        self.assertEqual(evt.source_component, "auth_gateway")
        self.assertEqual(evt.details["password"], "[REDACTED_SECRET]")
        self.assertEqual(evt.details["nested_token"], "[REDACTED_SECRET]")
        self.assertEqual(len(evt.signature), 64)
        print("      [35] Telemetry Normalization & Redaction ... PASS")

    def test_02_threat_intelligence_anti_poisoning(self):
        intel_mgr = ThreatIntelligenceManager()

        # 1. Private RFC 1918 poisoning attempt must be rejected
        ind_priv = intel_mgr.ingest_indicator(
            indicator_id="ti-priv-01",
            indicator_type=IndicatorType.IP_ADDRESS,
            indicator_value="192.168.1.100",
            source="untrusted_feed",
        )
        self.assertEqual(ind_priv.validation_status, IndicatorValidationStatus.REJECTED)

        # 2. Whitelisted internal infrastructure domain must be rejected
        ind_white = intel_mgr.ingest_indicator(
            indicator_id="ti-white-01",
            indicator_type=IndicatorType.DOMAIN,
            indicator_value="omniacloud.internal",
            source="untrusted_feed",
        )
        self.assertEqual(ind_white.validation_status, IndicatorValidationStatus.REJECTED)

        # 3. Valid external indicator accepted
        ind_valid = intel_mgr.ingest_indicator(
            indicator_id="ti-valid-01",
            indicator_type=IndicatorType.DOMAIN,
            indicator_value="c2-malicious-domain.org",
            source="cisa_known_exploited",
            confidence=0.90,
            ttl_seconds=3600.0,
        )
        self.assertEqual(ind_valid.validation_status, IndicatorValidationStatus.VALIDATED)

        # 4. Lookup verification
        hit = intel_mgr.lookup_indicator("c2-malicious-domain.org")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.indicator_id, "ti-valid-01")
        print("      [35] Threat Intel Anti-Poisoning Valid .. PASS")

    def test_03_deterministic_rule_matching_and_suppression(self):
        detector = ThreatDetectionEngine()
        normalizer = SecurityEventNormalizer()

        # Generate unauthorized capability invocation
        evt = normalizer.normalize(
            raw_event={"skill": "system.format_drive"},
            source_component="capability_registry",
            action_category="capability.execute",
            outcome="PERMISSION_DENIED",
            severity=SecuritySeverity.CRITICAL,
            source_identity="rogue_worker_42",
        )
        alerts1 = detector.evaluate_event(evt)
        self.assertEqual(len(alerts1), 1)
        self.assertEqual(alerts1[0].rule_id, "RULE-CAP-002")
        self.assertEqual(alerts1[0].severity, SecuritySeverity.CRITICAL)

        # Duplicate event within suppression window must be suppressed
        alerts2 = detector.evaluate_event(evt)
        self.assertEqual(len(alerts2), 0)
        print("      [35] Deterministic Rules & Suppression .. PASS")

    def test_04_behavioral_anomaly_rate_detection(self):
        anomaly_det = BehavioralAnomalyDetector(window_sec=60.0, rate_threshold=3)
        now = time.time()
        # Entity performs 4 actions in 60s
        for _ in range(3):
            is_anom, _, _ = anomaly_det.record_and_evaluate("user_spammer", "api.call", now)
            self.assertFalse(is_anom)

        # 4th action trips threshold
        is_anom, score, exp = anomaly_det.record_and_evaluate("user_spammer", "api.call", now + 1.0)
        self.assertTrue(is_anom)
        self.assertGreater(score, 0.5)
        self.assertIn("Rate anomaly", exp)
        print("      [35] Behavioral Anomaly Rate Detector .. PASS")

    def test_05_multi_stage_attack_chain_correlation(self):
        corr_engine = ThreatCorrelationEngine(correlation_window_sec=60.0)
        now = time.time()

        alert1 = ThreatAlert(
            alert_id="a1",
            rule_id="RULE-AUTH-001",
            title="Authentication Failure",
            threat_classification=ThreatClassification.UNAUTHORIZED_ACCESS,
            severity=SecuritySeverity.MEDIUM,
            confidence=0.8,
            trigger_event_ids=["evt-1"],
            affected_resources=["auth_service"],
            explanation="Bad password",
            timestamp=now,
            source_identity="hacker_x",
        )
        # First alert does not trigger an incident immediately (unless critical)
        incs1 = corr_engine.correlate_alerts([alert1], now)
        self.assertEqual(len(incs1), 0)

        alert2 = ThreatAlert(
            alert_id="a2",
            rule_id="RULE-CAP-002",
            title="Capability Abuse",
            threat_classification=ThreatClassification.CAPABILITY_ABUSE,
            severity=SecuritySeverity.HIGH,
            confidence=0.9,
            trigger_event_ids=["evt-2"],
            affected_resources=["admin_tool"],
            explanation="Restricted skill execution",
            timestamp=now + 5.0,
            source_identity="hacker_x",
        )
        # Second correlated alert for hacker_x synthesizes a multi-stage incident
        incs2 = corr_engine.correlate_alerts([alert2], now + 5.0)
        self.assertEqual(len(incs2), 1)
        inc = incs2[0]
        self.assertIn("Correlated Attack Chain", inc.title)
        self.assertEqual(inc.severity, SecuritySeverity.HIGH)
        self.assertEqual(sorted(inc.related_event_ids), ["evt-1", "evt-2"])
        print("      [35] Attack Chain Correlation .......... PASS")

    def test_06_incident_lifecycle_state_machine_enforcement(self):
        inc = SecurityIncident(
            incident_id="inc-test-01",
            title="Test Incident",
            threat_classification=ThreatClassification.UNAUTHORIZED_ACCESS,
            severity=SecuritySeverity.HIGH,
            confidence=0.9,
            detection_source="Test",
            affected_assets=["node_1"],
            related_event_ids=["evt-1"],
            status=IncidentStatus.DETECTED,
        )
        # Valid transition: DETECTED -> TRIAGED
        inc.transition_to(IncidentStatus.TRIAGED, "SecAnalyst", "Triaging alert")
        self.assertEqual(inc.status, IncidentStatus.TRIAGED)

        # Invalid transition: TRIAGED -> RESOLVED (cannot jump straight to resolved)
        with self.assertRaises(ValueError):
            inc.transition_to(IncidentStatus.RESOLVED, "SecAnalyst", "Invalid jump")

        # Valid path: TRIAGED -> INVESTIGATING -> RESOLVED -> CLOSED
        inc.transition_to(IncidentStatus.INVESTIGATING, "SecAnalyst", "Investigating")
        inc.transition_to(IncidentStatus.RESOLVED, "SecAnalyst", "Resolved after analysis")
        inc.transition_to(IncidentStatus.CLOSED, "SecAnalyst", "Closed")
        self.assertEqual(inc.status, IncidentStatus.CLOSED)
        print("      [35] Incident Lifecycle State Machine .. PASS")

    def test_07_containment_response_levels_and_approval(self):
        coord = ContainmentCoordinator(current_autonomy_level=ResponseAutonomyLevel.LEVEL_3_APPROVAL_REQUIRED)
        inc = SecurityIncident(
            incident_id="inc-contain-01",
            title="Rogue Worker",
            threat_classification=ThreatClassification.CAPABILITY_ABUSE,
            severity=SecuritySeverity.CRITICAL,
            confidence=0.95,
            detection_source="Test",
            affected_assets=["worker-99"],
            related_event_ids=["evt-99"],
        )

        # In Level 3, containment must be APPROVAL_PENDING
        action = coord.plan_containment(
            incident=inc,
            action_type="suspend_worker",
            target_resource="worker-99",
            scope="LOCAL_NODE",
            reason="Repeated policy violations",
        )
        self.assertEqual(action.status, ContainmentStatus.APPROVAL_PENDING)

        # Cannot execute without approval token
        ok_fail, err = coord.execute_containment(action.action_id)
        self.assertFalse(ok_fail)

        # Bind approval token from human
        appr_ok = coord.record_approval(action.action_id, "human-token-xyz")
        self.assertTrue(appr_ok)
        self.assertEqual(action.status, ContainmentStatus.APPROVED)

        # Now execute and verify active
        exec_ok, evidence = coord.execute_containment(action.action_id)
        self.assertTrue(exec_ok)
        self.assertEqual(action.status, ContainmentStatus.VERIFIED_ACTIVE)
        print("      [35] Containment Autonomy & Approvals .. PASS")

    def test_08_forensic_evidence_integrity_and_verification(self):
        forensics = ForensicEvidenceManager()
        payload = {
            "api_key": "sk-top-secret-do-not-leak",
            "attacker_ip": "203.0.113.195",
            "command": "whoami",
        }
        evid = forensics.preserve_evidence(
            incident_id="inc-for-01",
            artifact_type="command_execution",
            source_identifier="shell_01",
            raw_payload=payload,
        )
        self.assertNotIn("sk-top-secret", evid.raw_payload_redacted)
        self.assertIn("[REDACTED_SECRET]", evid.raw_payload_redacted)
        self.assertTrue(forensics.verify_evidence_integrity(evid.evidence_id))

        # Tampering with payload fails integrity check
        evid.raw_payload_redacted += " "
        self.assertFalse(forensics.verify_evidence_integrity(evid.evidence_id))
        print("      [35] Forensic Tamper-Evident Integrity . PASS")

    def test_09_security_posture_and_missing_sources(self):
        analyzer = SecurityPostureAnalyzer()
        # All sources missing -> AT_RISK or DEGRADED
        assessment = analyzer.assess_posture(
            active_incidents=[],
            recent_alerts=[],
            missing_sources=["auth_gateway", "secrets_engine", "policy_enforcer"],
        )
        self.assertIn(assessment.overall_state, [SecurityPostureState.AT_RISK, SecurityPostureState.DEGRADED])
        self.assertEqual(assessment.component_posture["auth_gateway"], SecurityPostureState.UNKNOWN)
        self.assertNotEqual(assessment.overall_state, SecurityPostureState.HEALTHY)
        print("      [35] Posture & Telemetry Blind Spots ... PASS")


if __name__ == "__main__":
    unittest.main()
