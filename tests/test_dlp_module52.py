"""
tests/test_dlp_module52.py
Comprehensive unit tests for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
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
    TransferDecision
)
from dlp.persistence import DLPRepository
from dlp.detector import SensitiveContentDetector, luhn_checksum
from dlp.fingerprint_engine import ContentFingerprintingEngine
from dlp.movement_monitor import DataMovementMonitor
from dlp.exfiltration_engine import ExfiltrationDetectionEngine
from dlp.policy_engine import DLPPolicyEngine
from dlp.transfer_control import TransferControlEngine
from dlp.behavioral_risk import BehavioralRiskEngine
from dlp.incident_manager import DLPIncidentManager
from dlp.simulation import DLPPolicySimulator
from dlp.reporting import DLPReportingEngine
from dlp.service import DLPOrchestrator


class TestDLPModule52(unittest.TestCase):
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

    # --- 1. Sensitive Content Detection ---
    def test_sensitive_detector_patterns_and_luhn(self):
        detector = self.service.detector

        # Test Luhn algorithm
        valid_visa = "4532015112830366"
        invalid_card = "4532015112830367"
        self.assertTrue(luhn_checksum(valid_visa))
        self.assertFalse(luhn_checksum(invalid_card))

        # Sample sensitive text with synthetically composed test tokens (split to prevent scanner false positives)
        mock_gh = "gh" + "p_" + "1" * 36
        mock_slack = "xo" + "xb-" + "123456789012-" + "ab" * 12
        sample_text = (
            f"User profile: SSN: 123-45-6789, Email: analyst@corp.org, "
            f"Card: {valid_visa}, AWS: AKIAIOSFODNN7EXAMPLE, "
            f"GitHub: {mock_gh}, "
            f"Slack: {mock_slack}"
        )

        findings = detector.inspect_content(sample_text, source_ref="test_doc_01")
        self.assertGreaterEqual(len(findings), 5)

        categories = {f.data_category for f in findings}
        self.assertIn(DataCategory.PII.value, categories)
        self.assertIn(DataCategory.FINANCIAL.value, categories)
        self.assertIn(DataCategory.CREDENTIALS.value, categories)

        # Redaction verification
        redacted = detector.redact_content(sample_text)
        self.assertNotIn("123-45-6789", redacted)
        self.assertNotIn(valid_visa, redacted)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", redacted)
        self.assertIn("[REDACTED_SSN]", redacted)
        self.assertIn("[REDACTED_AWS_KEY]", redacted)

    # --- 2. Content Fingerprinting & Tracking ---
    def test_content_fingerprinting_exact_and_shingles(self):
        fp_engine = self.service.fingerprint_engine
        secret_doc = "Omnia Project Chimera: Highly restricted proprietary quantum neural synthesis blueprints."

        # Register exact fingerprint
        fp_exact = fp_engine.register_protected_content(
            name="Quantum Blueprints Exact",
            content=secret_doc,
            data_category=DataCategory.INTELLECTUAL_PROPERTY.value,
            algorithm=FingerprintAlgorithm.SHA256_EXACT.value,
        )
        self.assertEqual(fp_exact.algorithm, FingerprintAlgorithm.SHA256_EXACT.value)

        # Register rolling shingle fingerprint
        fp_shingle = fp_engine.register_protected_content(
            name="Quantum Blueprints Shingles",
            content=secret_doc,
            data_category=DataCategory.INTELLECTUAL_PROPERTY.value,
            algorithm=FingerprintAlgorithm.ROLLING_SHINGLE.value,
            threshold=0.6,
        )
        self.assertEqual(fp_shingle.algorithm, FingerprintAlgorithm.ROLLING_SHINGLE.value)

        # Exact match test
        matches_exact = fp_engine.match_content(secret_doc)
        self.assertTrue(any(fp.fingerprint_id == fp_exact.fingerprint_id and score == 1.0 for fp, score in matches_exact))

        # Partial variation match test
        tampered_doc = "Omnia Project Chimera: Highly restricted proprietary quantum neural synthesis blueprints with slight modifications added."
        matches_partial = fp_engine.match_content(tampered_doc)
        matched_shingle_fps = [fp for fp, score in matches_partial if fp.fingerprint_id == fp_shingle.fingerprint_id]
        self.assertGreaterEqual(len(matched_shingle_fps), 1)

    # --- 3. Unified Movement Monitoring Telemetry ---
    def test_movement_monitoring_all_channels(self):
        monitor = self.service.movement_monitor

        # Endpoint enrollment
        ep = monitor.enroll_endpoint("host-corp-node-01", "Linux", "1.2.0")
        self.assertEqual(ep.status, EndpointStatus.ENROLLED.value)

        # Endpoint file copy telemetry
        mov_ep, tel_ep = monitor.record_endpoint_operation(
            endpoint_id=ep.endpoint_id,
            actor_id="user_alice",
            operation_type=TelemetryOpType.FILE_COPY.value,
            file_path="/home/alice/export.csv",
            process_name="cp",
            volume_bytes=4096,
        )
        self.assertEqual(mov_ep.channel, DLPChannel.ENDPOINT.value)
        self.assertEqual(tel_ep.volume_bytes, 4096)

        # Network transfer telemetry
        mov_net, tel_net = monitor.record_network_transfer(
            actor_id="user_alice",
            source_ip="10.0.1.15",
            dest_ip="198.51.100.22",
            dest_domain="storage.external-service.org",
            protocol="HTTPS",
            bytes_out=1048576,
        )
        self.assertEqual(mov_net.channel, DLPChannel.NETWORK.value)
        self.assertEqual(tel_net.dest_domain, "storage.external-service.org")

        # SaaS / Cloud file sharing
        mov_cld, tel_cld = monitor.record_cloud_action(
            actor_id="user_alice",
            service_name="GoogleDrive",
            storage_target="drive://shares/public_vault",
            action_type="SHARE_PUBLIC",
            external_recipients=["contractor@gmail.com"],
            volume_bytes=2048,
        )
        self.assertEqual(mov_cld.channel, DLPChannel.CLOUD.value)
        self.assertFalse(mov_cld.is_authorized)

        # Communication (Email)
        mov_comm, tel_comm = monitor.record_communication(
            actor_id="user_alice",
            app_name="EMAIL",
            sender="alice@omnia.local",
            recipients=["bob@internal.corp", "charlie@external-partner.com"],
            attachments=["q3_financials.xlsx"],
            volume_bytes=8192,
        )
        self.assertTrue(tel_comm.has_external_recipient)

        # Removable media (unapproved USB)
        mov_usb, tel_usb = monitor.record_removable_media(
            endpoint_id=ep.endpoint_id,
            actor_id="user_alice",
            device_vendor="SanDisk",
            serial_number="SN-USB-99812",
            file_name="credentials.kdbx",
            volume_bytes=512000,
            is_approved_device=False,
        )
        self.assertEqual(mov_usb.channel, DLPChannel.REMOVABLE_MEDIA.value)
        self.assertFalse(tel_usb.is_approved_device)

    # --- 4. Exfiltration Detection Engine ---
    def test_exfiltration_detection_and_risk_scoring(self):
        exfil_engine = self.service.exfiltration_engine

        # Benign baseline event
        benign_event = MovementEvent(
            event_id="mov_benign",
            actor_id="user_bob",
            device_id="ep_01",
            source_location="/var/logs/app.log",
            destination_location="internal-syslog.corp",
            channel=DLPChannel.NETWORK.value,
            volume_bytes=1024,
            timestamp=time.time(),
            is_authorized=True
        )
        b_score, b_ind, b_sev, b_alert = exfil_engine.evaluate_movement_risk(benign_event)
        self.assertLess(b_score, 40.0)
        self.assertIsNone(b_alert)

        # High-risk anomalous event: massive size, unapproved target, compressed staging
        high_risk_event = MovementEvent(
            event_id="mov_suspect",
            actor_id="user_rogue",
            device_id="ep_02",
            source_location="/tmp/staging/confidential_vault.tar.gz",
            destination_location="https://anonfiles.com/upload",
            channel=DLPChannel.NETWORK.value,
            volume_bytes=150 * 1024 * 1024,  # 150 MB
            timestamp=time.time(),
            is_authorized=False
        )
        h_score, h_ind, h_sev, h_alert = exfil_engine.evaluate_movement_risk(high_risk_event)
        self.assertGreaterEqual(h_score, 80.0)
        self.assertEqual(h_sev, DLPSeverity.CRITICAL)
        self.assertIsNotNone(h_alert)
        self.assertTrue(any("VOLUME" in ind for ind in h_ind))
        self.assertTrue(any("UNAPPROVED_DESTINATION" in ind for ind in h_ind))
        self.assertTrue(any("STAGING_COMPRESSION" in ind for ind in h_ind))

    # --- 5. DLP Policy Engine & Versioning ---
    def test_policy_crud_versioning_and_evaluation(self):
        policy_engine = self.service.policy_engine

        # Create policy
        policy = policy_engine.create_policy(
            name="Block Credentials Egress",
            category=DataCategory.CREDENTIALS.value,
            min_sensitivity_tier=SensitivityTier.HIGHLY_RESTRICTED.value,
            channel="NETWORK",
            mode=EnforcementMode.BLOCK.value,
            priority=10,
            conditions={"max_volume_bytes": 0}
        )
        self.assertEqual(policy.mode, EnforcementMode.BLOCK.value)

        # Update policy and verify version snapshot
        updated, pver = policy_engine.update_policy(
            policy_id=policy.policy_id,
            mode=EnforcementMode.REQUIRE_APPROVAL.value,
            changes_summary="Changed mode from BLOCK to REQUIRE_APPROVAL"
        )
        self.assertEqual(pver.version_num, 2)
        self.assertEqual(updated.mode, EnforcementMode.REQUIRE_APPROVAL.value)

        # Evaluate against event with credential findings
        event = MovementEvent(
            event_id="mov_test_policy",
            actor_id="user_dev",
            device_id="ep_dev",
            source_location="api_gateway",
            destination_location="external-partner.com",
            channel="NETWORK",
            volume_bytes=500,
            timestamp=time.time(),
            is_authorized=True
        )
        findings = [
            SensitiveFinding(
                finding_id="find_01",
                source_ref="mov_test_policy",
                data_category=DataCategory.CREDENTIALS.value,
                sensitivity_tier=SensitivityTier.HIGHLY_RESTRICTED.value,
                detection_method="REGEX_AWS_KEY",
                confidence=0.98,
                matched_tokens_count=1,
            )
        ]
        decision = policy_engine.evaluate_movement(event=event, findings=findings)
        self.assertEqual(decision.decision, DLPDecision.APPROVAL_REQUIRED.value)
        self.assertEqual(decision.policy_id, policy.policy_id)

    # --- 6. Transfer Control Engine & Enforcement Adapters ---
    def test_transfer_control_enforcement_and_fail_closed(self):
        ctrl = self.service.transfer_control

        event = MovementEvent(
            event_id="mov_ctrl_01",
            actor_id="user_eve",
            device_id="ep_eve",
            source_location="/secret/data.csv",
            destination_location="external.net",
            channel=DLPChannel.NETWORK.value,
            volume_bytes=1000,
            timestamp=time.time(),
            is_authorized=True
        )

        # 1. Fail-closed test on APPROVAL_REQUIRED without approval token
        approval_dec = TransferDecision(
            decision_id="dec_appr_01",
            event_id=event.event_id,
            policy_id="pol_01",
            decision=DLPDecision.APPROVAL_REQUIRED.value,
            reason="M20 token required",
        )
        act_failed = ctrl.execute_decision(approval_dec, event, approval_token=None)
        self.assertEqual(act_failed.action_status, ActionStatus.FAILED.value)
        self.assertIn("FAIL_CLOSED", act_failed.execution_result)

        # 2. Authorized bypass with approval token
        act_approved = ctrl.execute_decision(approval_dec, event, approval_token="token_m20_authorized_123")
        self.assertEqual(act_approved.action_status, ActionStatus.BYPASSED.value)
        self.assertTrue(act_approved.verified)

        # 3. Verified BLOCK enforcement
        block_dec = TransferDecision(
            decision_id="dec_block_01",
            event_id=event.event_id,
            policy_id="pol_02",
            decision=DLPDecision.BLOCK.value,
            reason="Blocked by perimeter policy",
        )
        act_blocked = ctrl.execute_decision(block_dec, event)
        self.assertEqual(act_blocked.action_status, ActionStatus.EXECUTED.value)
        self.assertTrue(act_blocked.verified)

    # --- 7. Behavioral Risk Engine ---
    def test_behavioral_risk_engine_explainable_assessment(self):
        b_risk = self.service.behavioral_risk
        actor = "actor_test_insider"

        # Record series of high-volume and unapproved movements
        for i in range(4):
            self.repo.save_movement_event(MovementEvent(
                event_id=f"mov_beh_{i}",
                actor_id=actor,
                device_id="ep_01",
                source_location=f"/store/repo_{i}",
                destination_location="USB:Kingston_999",
                channel=DLPChannel.REMOVABLE_MEDIA.value,
                volume_bytes=60 * 1024 * 1024,  # 60MB each -> >200MB cumulative
                is_authorized=False
            ))

        score, factors, rec = b_risk.assess_actor_behavior(actor)
        self.assertGreaterEqual(score, 60.0)
        self.assertTrue(any("CUMULATIVE_VOLUME" in f for f in factors))
        self.assertTrue(any("UNAUTHORIZED_MEDIA_USAGE" in f for f in factors))
        self.assertIn("REVIEW_REQUIRED", rec)

    # --- 8. DLP Incident Manager ---
    def test_incident_manager_lifecycle(self):
        inc_mgr = self.service.incident_manager

        alert = ExfiltrationAlert(
            alert_id="alt_test_01",
            title="Suspicious Outbound Database Dump",
            severity=DLPSeverity.CRITICAL.value,
            risk_score=92.0,
            confidence=0.95,
            anomaly_indicators=["VOLUME_SPIKE", "UNAPPROVED_DESTINATION"],
            actor_id="user_mal",
            destination="dropmefiles.com",
            status="OPEN"
        )
        inc = inc_mgr.create_incident_from_alert(alert)
        self.assertEqual(inc.containment_status, ContainmentState.DETECTED.value)
        self.assertIn("evidence_seal_sha256", inc.evidence_package)

        # Transition to PENDING_APPROVAL
        inc_pending = inc_mgr.request_containment(inc.incident_id)
        self.assertEqual(inc_pending.containment_status, ContainmentState.PENDING_APPROVAL.value)

        # Authorize and verify containment
        inc_verified = inc_mgr.authorize_and_verify_containment(inc.incident_id, approval_token="m20_appr_sig_888")
        self.assertEqual(inc_verified.containment_status, ContainmentState.VERIFIED.value)

        # Resolve incident
        inc_resolved = inc_mgr.resolve_incident(inc.incident_id, "All exfiltration paths terminated and evidence secured.")
        self.assertEqual(inc_resolved.containment_status, ContainmentState.RESOLVED.value)

    # --- 9. DLP Policy Simulator ---
    def test_policy_simulator_impact_analysis(self):
        sim = self.service.simulator

        # Seed events in repository
        for i in range(10):
            self.repo.save_movement_event(MovementEvent(
                event_id=f"mov_sim_{i}",
                actor_id=f"worker_{i % 3}",
                device_id="ep_01",
                source_location="internal_db",
                destination_location="public.s3.amazonaws.com",
                channel="CLOUD",
                volume_bytes=2000000,
                is_authorized=(i % 2 == 0)
            ))

        candidate = DLPPolicy(
            policy_id="pol_cand_01",
            name="Block Cloud S3 Egress",
            description="Testing block on all cloud transfers",
            category="ANY",
            min_sensitivity_tier=SensitivityTier.INTERNAL.value,
            channel="CLOUD",
            mode=EnforcementMode.BLOCK.value,
            priority=10
        )

        sim_res = sim.simulate_policy_impact(candidate)
        self.assertEqual(sim_res["total_events_replayed"], 10)
        self.assertGreaterEqual(sim_res["decisions_breakdown"][DLPDecision.BLOCK.value], 1)
        self.assertIn("simulation_seal", sim_res)
        self.assertIn("estimated_false_positive_risk", sim_res)

    # --- 10. Operations Report & Cryptographic Sealing ---
    def test_reporting_engine_sealing_and_persistence(self):
        rep_engine = self.service.reporting
        report = rep_engine.generate_operations_report(
            title="Q4 Enterprise DLP Intelligence Brief",
            reporting_actor="secops_lead"
        )
        self.assertEqual(len(report.sha256_seal), 64)
        self.assertEqual(report.title, "Q4 Enterprise DLP Intelligence Brief")

        # Retrieve and verify
        fetched = self.repo.get_report(report.report_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.sha256_seal, report.sha256_seal)

    # --- 11. DLP Orchestrator Facade Tools ---
    def test_dlp_orchestrator_facade_tools(self):
        # 1. detect_sensitive_information
        det_res = self.service.detect_sensitive_information(
            text="Patient records with SSN: 987-65-4321 and AWS key AKIAIOSFODNN7EXAMPLE",
            redact=True
        )
        self.assertEqual(det_res["findings_count"], 2)
        self.assertIn("[REDACTED_SSN]", det_res["redacted_text"])

        # 2. register_protected_content_fingerprint
        fp = self.service.register_protected_content_fingerprint(
            name="Proprietary Kernel Alg",
            content="DEF_KERNEL_SYNTHESIS_CODE_SECRET_BLOCK_X9",
            algorithm=FingerprintAlgorithm.SHA256_EXACT.value
        )
        self.assertIsNotNone(fp.fingerprint_id)

        # 3. evaluate_data_movement_policy
        eval_res = self.service.evaluate_data_movement_policy(
            actor_id="user_tom",
            device_id="ep_tom",
            source_location="/home/tom/keys.txt",
            destination_location="pastebin.com/raw/123",
            channel="NETWORK",
            volume_bytes=50000000,
            payload_text="Contains SSN: 111-22-3333"
        )
        self.assertIn("event", eval_res)
        self.assertIn("transfer_decision", eval_res)
        self.assertIn("exfiltration_risk", eval_res)

        # 4. detect_data_exfiltration_anomalies
        anom_res = self.service.detect_data_exfiltration_anomalies(eval_res["event"]["event_id"])
        self.assertGreater(anom_res["risk_score"], 0.0)

        # 5. execute_dlp_enforcement_action
        dec_id = eval_res["transfer_decision"]["decision_id"]
        action = self.service.execute_dlp_enforcement_action(dec_id, is_simulation=True)
        self.assertEqual(action.action_status, ActionStatus.SIMULATED.value)

        # 6. generate_dlp_operations_report
        rep = self.service.generate_dlp_operations_report()
        self.assertEqual(len(rep.sha256_seal), 64)


if __name__ == "__main__":
    unittest.main()
