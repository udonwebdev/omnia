"""
tests/test_dlp_e2e_module52.py
End-to-End Enterprise Scenario Drill for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.

12-Step Enterprise Drill:
1. Protected Content Fingerprint Registration (Exact + Rolling Shingles)
2. Endpoint Fleet Enrollment & Telemetry Capture
3. Multi-Layer Sensitive Content Inspection (PII, Financial, Luhn)
4. Format-Preserving Content Redaction
5. Egress Staging Movement Telemetry Ingestion
6. Multi-Factor Exfiltration Anomaly Correlation & Alert Generation
7. Prioritized Policy Evaluation & Transfer Decision
8. Fail-Closed Transfer Control Interception (Missing Token)
9. M20 Human Authorization & Verified Controlled Bypass
10. Removable Media (USB) Hardware Defense Execution
11. Historical Policy Replay & Synthetic Scenario Simulation
12. Operations Center Intelligence Synthesis & Cryptographically Sealed Reporting
"""

import unittest
import sqlite3
import tempfile
import os
import json
import time

from persistence.migrations import MIGRATION_V36
from dlp.models import (
    EnforcementMode, DLPChannel, DLPDecision, DLPSeverity,
    ContainmentState, EndpointStatus, FingerprintAlgorithm,
    DataCategory, SensitivityTier, ActionStatus, TelemetryOpType,
    DLPPolicy, MovementEvent, SensitiveFinding, ExfiltrationAlert,
    TransferDecision, EnforcementAction
)
from dlp.service import DLPOrchestrator


class TestDLPE2EEnterpriseDrill(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        conn = sqlite3.connect(self.temp_db_path)
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.executescript(MIGRATION_V36)
        conn.close()

        self.service = DLPOrchestrator(db_path=self.temp_db_path)
        self.repo = self.service.repo

    def tearDown(self):
        try:
            os.close(self.temp_db_fd)
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_full_enterprise_dlp_scenario_drill(self):
        """Executes the comprehensive 12-step enterprise DLP security drill."""

        # -------------------------------------------------------------
        # STEP 1: Protected Content Fingerprint Registration
        # -------------------------------------------------------------
        secret_project_charter = (
            "OMNIA PROJECT PROMETHEUS: Autonomous Self-Securing Cognitive Architecture. "
            "Internal confidential design parameters, zero-knowledge proof contracts, and cryptographic seed tables. "
            "Strictly proprietary intellectual property of Omnia Corp. Unauthorized transfer strictly forbidden."
        )

        fp_exact = self.service.register_protected_content_fingerprint(
            name="Project Prometheus Charter (Exact)",
            content=secret_project_charter,
            data_category=DataCategory.INTELLECTUAL_PROPERTY.value,
            algorithm=FingerprintAlgorithm.SHA256_EXACT.value,
        )
        self.assertIsNotNone(fp_exact.fingerprint_id)
        self.assertEqual(len(fp_exact.fingerprint_hash), 64)

        fp_shingle = self.service.register_protected_content_fingerprint(
            name="Project Prometheus Charter (Shingles)",
            content=secret_project_charter,
            data_category=DataCategory.INTELLECTUAL_PROPERTY.value,
            algorithm=FingerprintAlgorithm.ROLLING_SHINGLE.value,
            threshold=0.60
        )
        self.assertIn("shingles", fp_shingle.metadata)
        self.assertGreaterEqual(fp_shingle.metadata["shingle_count"], 1)

        # -------------------------------------------------------------
        # STEP 2: Endpoint Fleet Enrollment & Telemetry Capture
        # -------------------------------------------------------------
        ep = self.service.movement_monitor.enroll_endpoint(
            hostname="fin-workstation-902",
            os_type="Windows",
            agent_version="2.4.1"
        )
        self.assertEqual(ep.status, EndpointStatus.ENROLLED.value)

        mov_ep, tel_ep = self.service.movement_monitor.record_endpoint_operation(
            endpoint_id=ep.endpoint_id,
            actor_id="user_fin_analyst",
            operation_type=TelemetryOpType.FILE_COPY.value,
            file_path="C:\\Vault\\payroll_export_2026.csv",
            process_name="powershell.exe",
            volume_bytes=1048576,
        )
        self.assertEqual(mov_ep.channel, DLPChannel.ENDPOINT.value)
        self.assertEqual(tel_ep.volume_bytes, 1048576)

        # -------------------------------------------------------------
        # STEP 3: Multi-Layer Sensitive Content Inspection
        # -------------------------------------------------------------
        raw_payroll_payload = (
            "Employee Payroll Export:\n"
            "Alice Jenkins | SSN: 219-45-8821 | Email: alice@omnia.corp | Card: 4532015112830366\n"
            "Bob Henderson | SSN: 312-78-9943 | Email: bob@omnia.corp | Card: 5425233430109903\n"
            "Service Credential: AWS_KEY=AKIAIOSFODNN7EXAMPLE\n"
            "Reference Document: " + secret_project_charter[:80]
        )

        det_result = self.service.detect_sensitive_information(
            text=raw_payroll_payload,
            source_ref="payroll_export_2026.csv"
        )
        self.assertGreaterEqual(det_result["findings_count"], 4)
        found_categories = {f["data_category"] for f in det_result["findings"]}
        self.assertIn(DataCategory.PII.value, found_categories)
        self.assertIn(DataCategory.FINANCIAL.value, found_categories)
        self.assertIn(DataCategory.CREDENTIALS.value, found_categories)

        # -------------------------------------------------------------
        # STEP 4: Format-Preserving Redaction
        # -------------------------------------------------------------
        sanitized_doc = self.service.detector.redact_content(raw_payroll_payload)
        self.assertNotIn("219-45-8821", sanitized_doc)
        self.assertNotIn("4532015112830366", sanitized_doc)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", sanitized_doc)
        self.assertIn("[REDACTED_SSN]", sanitized_doc)
        self.assertIn("[REDACTED_FINANCIAL_CARD_****0366]", sanitized_doc)
        self.assertIn("[REDACTED_AWS_KEY]", sanitized_doc)

        # -------------------------------------------------------------
        # STEP 5: Egress Staging Telemetry Ingestion
        # -------------------------------------------------------------
        staged_archive_name = "C:\\Users\\user_fin_analyst\\AppData\\Local\\Temp\\exfil_dump.zip"
        mov_egress = self.service.movement_monitor.record_movement(
            actor_id="user_fin_analyst",
            device_id=ep.endpoint_id,
            source_location=staged_archive_name,
            destination_location="https://mega.nz/api/v2/upload",
            channel=DLPChannel.NETWORK.value,
            volume_bytes=80 * 1024 * 1024,  # 80 MB
            is_authorized=False,
            metadata={"archive_type": "ZIP", "compression": "deflate"}
        )
        self.assertFalse(mov_egress.is_authorized)

        # -------------------------------------------------------------
        # STEP 6: Multi-Factor Exfiltration Anomaly Correlation
        # -------------------------------------------------------------
        anom_res = self.service.detect_data_exfiltration_anomalies(mov_egress.event_id)
        self.assertGreaterEqual(anom_res["risk_score"], 80.0)
        self.assertEqual(anom_res["severity"], DLPSeverity.CRITICAL.value)
        self.assertIsNotNone(anom_res["alert"])
        self.assertIn("UNAPPROVED_DESTINATION", " ".join(anom_res["anomaly_indicators"]))
        self.assertIn("STAGING_COMPRESSION", " ".join(anom_res["anomaly_indicators"]))

        # -------------------------------------------------------------
        # STEP 7: Prioritized Policy Evaluation & Transfer Decision
        # -------------------------------------------------------------
        policy_credentials = self.service.policy_engine.create_policy(
            name="Strict Financial & Credential Egress Gate",
            category=DataCategory.FINANCIAL.value,
            min_sensitivity_tier=SensitivityTier.HIGHLY_RESTRICTED.value,
            channel="NETWORK",
            mode=EnforcementMode.REQUIRE_APPROVAL.value,
            priority=5,
            conditions={"max_volume_bytes": 1000}
        )

        findings_objs = [
            SensitiveFinding(
                finding_id="f_fin_01",
                source_ref=mov_egress.event_id,
                data_category=DataCategory.FINANCIAL.value,
                sensitivity_tier=SensitivityTier.HIGHLY_RESTRICTED.value,
                detection_method="LUHN_VALIDATED_CREDIT_CARD",
                confidence=0.99,
                matched_tokens_count=2,
            )
        ]

        alert_obj = ExfiltrationAlert(
            alert_id=anom_res["alert"]["alert_id"],
            title=anom_res["alert"]["title"],
            severity=anom_res["alert"]["severity"],
            risk_score=anom_res["alert"]["risk_score"],
            confidence=anom_res["alert"]["confidence"],
            anomaly_indicators=anom_res["anomaly_indicators"],
            actor_id=mov_egress.actor_id,
            destination=mov_egress.destination_location,
            status="OPEN"
        )

        decision = self.service.policy_engine.evaluate_movement(
            event=mov_egress,
            findings=findings_objs,
            alert=alert_obj
        )
        self.assertEqual(decision.decision, DLPDecision.APPROVAL_REQUIRED.value)
        self.assertEqual(decision.policy_id, policy_credentials.policy_id)

        # -------------------------------------------------------------
        # STEP 8: Fail-Closed Enforcement Verification (Missing Token)
        # -------------------------------------------------------------
        act_unauth = self.service.execute_dlp_enforcement_action(
            decision_id=decision.decision_id,
            approval_token=None
        )
        self.assertEqual(act_unauth.action_status, ActionStatus.FAILED.value)
        self.assertIn("FAIL_CLOSED", act_unauth.execution_result)

        # -------------------------------------------------------------
        # STEP 9: M20 Human Authorization & Verified Controlled Bypass
        # -------------------------------------------------------------
        act_auth = self.service.execute_dlp_enforcement_action(
            decision_id=decision.decision_id,
            approval_token="m20_human_sign_valid_auth_token_99182"
        )
        self.assertEqual(act_auth.action_status, ActionStatus.BYPASSED.value)
        self.assertTrue(act_auth.verified)

        # -------------------------------------------------------------
        # STEP 10: Removable Media (USB) Hardware Defense Execution
        # -------------------------------------------------------------
        policy_usb = self.service.policy_engine.create_policy(
            name="Block Unapproved Removable Media",
            category="ANY",
            min_sensitivity_tier=SensitivityTier.INTERNAL.value,
            channel="REMOVABLE_MEDIA",
            mode=EnforcementMode.BLOCK.value,
            priority=1,
            conditions={"unapproved_only": True}
        )

        mov_usb, tel_usb = self.service.movement_monitor.record_removable_media(
            endpoint_id=ep.endpoint_id,
            actor_id="user_fin_analyst",
            device_vendor="UnknownVendor",
            serial_number="USB-ROGUE-007",
            file_name="shadow_copy.kdbx",
            volume_bytes=2048576,
            is_approved_device=False
        )

        usb_decision = self.service.policy_engine.evaluate_movement(event=mov_usb)
        self.assertEqual(usb_decision.decision, DLPDecision.BLOCK.value)

        usb_enforcement = self.service.execute_dlp_enforcement_action(decision_id=usb_decision.decision_id)
        self.assertEqual(usb_enforcement.action_status, ActionStatus.EXECUTED.value)
        self.assertTrue(usb_enforcement.verified)
        self.assertIn("WRITE_ACCESS_DENIED", usb_enforcement.execution_result)

        # -------------------------------------------------------------
        # STEP 11: Policy Simulation & False-Positive Analysis
        # -------------------------------------------------------------
        candidate_sim_policy = DLPPolicy(
            policy_id="pol_sim_strict_egress",
            name="Simulated Total External Cloud Block",
            description="Assess impact of blocking all cloud channel operations",
            category="ANY",
            min_sensitivity_tier=SensitivityTier.INTERNAL.value,
            channel="NETWORK",
            mode=EnforcementMode.BLOCK.value,
            priority=1
        )
        sim_report = self.service.simulator.simulate_policy_impact(
            candidate_policy=candidate_sim_policy,
            events=[mov_ep, mov_egress, mov_usb]
        )
        self.assertEqual(sim_report["total_events_replayed"], 3)
        self.assertIn("simulation_seal", sim_report)
        self.assertGreaterEqual(len(sim_report["simulation_seal"]), 64)

        # -------------------------------------------------------------
        # STEP 12: Operations Center Intelligence Synthesis & Cryptographic Seal
        # -------------------------------------------------------------
        ops_report = self.service.generate_dlp_operations_report(
            title="Enterprise Data Protection & Exfiltration Defense Operational Briefing",
            reporting_actor="omnia_secops_director"
        )
        self.assertIsNotNone(ops_report.report_id)
        self.assertGreaterEqual(ops_report.findings_count, 1)
        self.assertGreaterEqual(ops_report.blocked_transfers_count, 1)
        self.assertEqual(len(ops_report.sha256_seal), 64)

        # Verify tamper-proof persistence in repo
        persisted_report = self.service.repo.get_report(ops_report.report_id)
        self.assertIsNotNone(persisted_report)
        self.assertEqual(persisted_report.sha256_seal, ops_report.sha256_seal)
        self.assertEqual(persisted_report.report_data["reporting_actor"], "omnia_secops_director")


if __name__ == "__main__":
    unittest.main()
