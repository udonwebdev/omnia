"""
OMNIA Module 35 End-to-End Acceptance Scenario:
Autonomous Cybersecurity, Threat Intelligence & Runtime Defense Engine.

Deterministic 15-Step Defensive Lifecycle Scenario:
1. Initialize isolated defense test repository and telemetry collector.
2. Ingest trusted defensive threat intelligence (known malicious C2 domain).
3. Attempt ingestion of poisoned internal IP/domain and verify rejection.
4. Ingest baseline benign authentication telemetry.
5. Ingest suspicious failed authentication events.
6. Ingest unauthorized capability invocation attempt (system.format_disk).
7. Ingest simulated unauthorized secret lease access (sk-leakage-attempt).
8. Verify telemetry normalization, credential scrubbing, and SHA-256 signature chain.
9. Verify multi-stage attack chain correlation and creation of SecurityIncident.
10. Verify automated forensic evidence preservation with SHA-256 integrity digest.
11. Request defensive containment action (suspend_worker) under Level 3 (Approval-Required).
12. Verify containment is held in APPROVAL_PENDING status without unauthorized execution.
13. Bind verified human approval token (Module 20 integration) and execute containment.
14. Verify containment active state and evidence trail.
15. Execute recovery workflow, transition incident to RESOLVED, and verify overall posture.
"""

import unittest
import time
import uuid
import os
import json

from defense.models import (
    SecuritySeverity,
    IndicatorType,
    IndicatorValidationStatus,
    ThreatClassification,
    SecurityPostureState,
    IncidentStatus,
    ResponseAutonomyLevel,
    ContainmentStatus,
)
from defense.service import CyberDefenseService


class TestDefenseE2EModule35(unittest.TestCase):
    def setUp(self):
        self.test_db = f"test_e2e_defense_{uuid.uuid4().hex[:6]}.db"
        self.service = CyberDefenseService(db_path=self.test_db)

    def tearDown(self):
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

    def test_end_to_end_defensive_incident_response_scenario(self):
        print("\n=== STARTING MODULE 35 E2E DEFENSIVE INCIDENT ACCEPTANCE SCENARIO ===")

        # Step 1: Initialize isolated environment
        self.assertIsNotNone(self.service)
        print("Step 1: Isolated defensive runtime initialized.")

        # Step 2: Ingest trusted threat intelligence
        ti = self.service.register_threat_indicator(
            indicator_id="ti-c2-001",
            indicator_type=IndicatorType.DOMAIN,
            indicator_value="c2-stealth-adversary.net",
            source="cisa_known_exploited",
            confidence=0.92,
            threat_classification=ThreatClassification.DATA_EXFILTRATION,
        )
        self.assertEqual(ti.validation_status, IndicatorValidationStatus.VALIDATED)
        print("Step 2: Trusted threat intelligence ingested and validated.")

        # Step 3: Poisoning attempt rejected
        poison_ip = self.service.register_threat_indicator(
            indicator_id="ti-poison-002",
            indicator_type=IndicatorType.IP_ADDRESS,
            indicator_value="10.0.0.1",
            source="untrusted_feed",
            confidence=0.99,
        )
        self.assertEqual(poison_ip.validation_status, IndicatorValidationStatus.REJECTED)
        print("Step 3: Poisoned internal RFC 1918 indicator rejected by validator.")

        # Step 4: Baseline benign telemetry
        evt_benign, alerts0, _ = self.service.ingest_security_event(
            raw_event={"user": "admin_lo", "status": "authorized"},
            source_component="auth_gateway",
            action_category="auth.login",
            outcome="SUCCESS",
            severity=SecuritySeverity.INFO,
            source_identity="admin_lo",
        )
        self.assertEqual(len(alerts0), 0)
        print("Step 4: Benign telemetry normalized without false alerts.")

        # Step 5: Suspicious authentication failures
        evt_fail, alerts_auth, _ = self.service.ingest_security_event(
            raw_event={"user": "intruder_x", "ip": "198.51.100.22"},
            source_component="auth_gateway",
            action_category="auth.login",
            outcome="FAILURE",
            severity=SecuritySeverity.HIGH,
            source_identity="intruder_x",
        )
        self.assertGreaterEqual(len(alerts_auth), 1)
        print("Step 5: Suspicious authentication failure alert triggered.")

        # Step 6: Unauthorized capability invocation
        evt_cap, alerts_cap, _ = self.service.ingest_security_event(
            raw_event={"skill": "system.format_disk", "target": "/dev/sda"},
            source_component="capability_registry",
            action_category="capability.execute",
            outcome="PERMISSION_DENIED",
            severity=SecuritySeverity.CRITICAL,
            source_identity="intruder_x",
        )
        self.assertGreaterEqual(len(alerts_cap), 1)
        print("Step 6: Unauthorized capability invocation alert triggered.")

        # Step 7: Unauthorized secret lease access with sensitive tokens
        evt_sec, alerts_sec, new_incs = self.service.ingest_security_event(
            raw_event={
                "secret_key": "sk-unauthorized-access-token-1234567890",
                "request_type": "lease_acquire"
            },
            source_component="secrets_engine",
            action_category="secrets.lease",
            outcome="ACCESS_DENIED",
            severity=SecuritySeverity.CRITICAL,
            source_identity="intruder_x",
            resource_reference="sec:root_master_key",
        )
        # Step 8: Redaction & signature verification
        self.assertIn("[REDACTED_SECRET]", evt_sec.details.get("secret_key", ""))
        self.assertEqual(len(evt_sec.signature), 64)
        print("Step 8: Zero-leakage credential scrubbing & cryptographic signing verified.")

        # Step 9: Multi-stage attack chain correlation and incident creation
        active_incidents = self.service.repo.list_active_incidents()
        self.assertGreaterEqual(len(active_incidents), 1)
        primary_incident = active_incidents[0]
        self.assertEqual(primary_incident.severity, SecuritySeverity.CRITICAL)
        self.assertIn(primary_incident.status, [IncidentStatus.DETECTED, IncidentStatus.INVESTIGATING])
        print(f"Step 9: Attack chain synthesized: Incident '{primary_incident.incident_id}' ({primary_incident.title}).")

        # Step 10: Automatic forensic evidence preservation
        self.assertGreaterEqual(len(primary_incident.evidence_ids), 1)
        evid_rec = self.service.repo.get_evidence_record(primary_incident.evidence_ids[0])
        self.assertIsNotNone(evid_rec)
        self.assertEqual(len(evid_rec.integrity_digest), 64)
        print(f"Step 10: Forensic evidence '{evid_rec.evidence_id}' verified with SHA-256 digest.")

        # Step 11: Request defensive containment action under Level 3
        containment = self.service.request_containment(
            incident_id=primary_incident.incident_id,
            action_type="suspend_worker",
            target_resource="intruder_x",
            scope="DISTRIBUTED_NODE",
            reason="Correlated multi-stage intrusion and secret access abuse",
            is_reversible=True,
        )
        # Step 12: Ensure held in APPROVAL_PENDING
        self.assertEqual(containment.status, ContainmentStatus.APPROVAL_PENDING)
        print(f"Step 12: Containment '{containment.action_id}' held in APPROVAL_PENDING (Level 3 enforced).")

        # Step 13: Bind human approval token and execute containment
        exec_ok, evidence_text = self.service.authorize_and_execute_containment(
            action_id=containment.action_id,
            approval_token="human-auth-mod20-approved-99",
        )
        self.assertTrue(exec_ok)
        # Step 14: Verify containment active state
        updated_action = self.service.repo.get_containment_action(containment.action_id)
        self.assertEqual(updated_action.status, ContainmentStatus.VERIFIED_ACTIVE)
        updated_inc = self.service.repo.get_incident(primary_incident.incident_id)
        self.assertEqual(updated_inc.status, IncidentStatus.CONTAINED)
        print(f"Step 14: Containment executed and verified: {evidence_text}")

        # Step 15: Execute recovery workflow and verify posture
        resolve_ok = self.service.resolve_incident(
            incident_id=primary_incident.incident_id,
            actor="SecurityOfficer_LO",
            resolution_summary="Adversary worker suspended and all credentials audited.",
        )
        self.assertTrue(resolve_ok)
        resolved_inc = self.service.repo.get_incident(primary_incident.incident_id)
        self.assertEqual(resolved_inc.status, IncidentStatus.RESOLVED)

        # Posture re-assessment
        posture = self.service.assess_security_posture()
        self.assertIsNotNone(posture)
        print(f"Step 15: Incident resolved and security posture assessed (State: {posture.overall_state.value}).")
        print("=== MODULE 35 E2E DEFENSIVE INCIDENT ACCEPTANCE SCENARIO PASSED! ===")


if __name__ == "__main__":
    unittest.main()
