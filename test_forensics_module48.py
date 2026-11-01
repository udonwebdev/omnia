"""
test_forensics_module48.py
Unit tests for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import unittest
import os
import shutil
import json
import sqlite3
import time

from forensics.models import (
    ForensicCase, CaseStatus, EvidenceArtifact, ArtifactType,
    CustodyOperation, TimelineEvent, EvidenceCorrelation,
    ForensicHypothesis, HypothesisStatus, StatementCategory,
    EvidenceReliabilityTier
)
from forensics.persistence import ForensicsRepository
from forensics.vault import EvidenceVault
from forensics.custody_manager import CustodyManager
from forensics.acquisition import EvidenceAcquisitionEngine
from forensics.artifact_parsers import SafeArtifactParser
from forensics.timeline import TimelineReconstructionEngine
from forensics.correlation import EvidenceCorrelationEngine
from forensics.hypothesis_engine import HypothesisEngine
from forensics.report_generator import ForensicReportGenerator
from forensics.service import DigitalForensicsOrchestrator
from persistence.migrations import MIGRATION_V33


class TestForensicsModule48(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db = "test_forensics_temp.db"
        cls.test_vault_dir = "artifacts/test_forensics_vault"
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
        import gc
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

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_case_lifecycle(self):
        case = self.service.open_investigation_case(
            title="Unauthorized Credential Access",
            description="Investigation into anomalous IDP tokens",
            incident_id="inc_sec_991",
            scope_definition={"allowed_sources": ["identity_logs", "cloud_audit"]}
        )
        self.assertEqual(case.status, CaseStatus.OPEN)
        self.assertTrue(case.case_id.startswith("case_"))

        fetched = self.service.get_case(case.case_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Unauthorized Credential Access")

        closed = self.service.close_investigation_case(case.case_id)
        self.assertTrue(closed)
        closed_case = self.service.get_case(case.case_id)
        self.assertEqual(closed_case.status, CaseStatus.CLOSED)
        self.assertIsNotNone(closed_case.closed_at)

    def test_artifact_acquisition_and_vault_integrity(self):
        case = self.service.open_investigation_case(
            title="Artifact Preservation Test",
            description="Preserving test telemetry"
        )
        raw_log = json.dumps([
            {"user": "alice@corp.internal", "action": "LOGIN_SUCCESS", "ip_address": "198.51.100.12", "timestamp": "2026-11-01T06:00:00Z"},
            {"user": "alice@corp.internal", "action": "MFA_BYPASS_ATTEMPT", "ip_address": "203.0.113.44", "timestamp": "2026-11-01T06:02:00Z"}
        ]).encode("utf-8")

        artifact = self.service.acquire_artifact(
            case_id=case.case_id,
            source_type=ArtifactType.IDENTITY_AUDIT,
            source_identifier="idp.corp.internal/auth_logs",
            artifact_name="idp_auth_stream_20261101.json",
            raw_data=raw_log,
            classification="RESTRICTED"
        )

        self.assertTrue(artifact.artifact_id.startswith("art_"))
        self.assertEqual(artifact.integrity_status, "VERIFIED")
        self.assertTrue(os.path.exists(artifact.storage_uri))

        # Check unbroken custody chain
        custody_res = self.service.verify_artifact_custody(case.case_id, artifact.artifact_id)
        self.assertTrue(custody_res["valid"])
        self.assertEqual(custody_res["integrity_status"], "VERIFIED_UNBROKEN")

    def test_sensitive_source_authorization_guard(self):
        case = self.service.open_investigation_case(title="Sensitive Acquisition", description="Testing approval guard")
        
        # Acquisition without approval token must fail
        with self.assertRaises(PermissionError):
            self.service.acquire_artifact(
                case_id=case.case_id,
                source_type=ArtifactType.MEMORY_METADATA,
                source_identifier="MEMORY_DUMP",
                artifact_name="core_dump.raw",
                raw_data=b"DUMP_PAYLOAD",
                approval_token=None
            )

        # Acquisition with approval token must succeed
        artifact = self.service.acquire_artifact(
            case_id=case.case_id,
            source_type=ArtifactType.MEMORY_METADATA,
            source_identifier="MEMORY_DUMP",
            artifact_name="core_dump.raw",
            raw_data=b"DUMP_PAYLOAD",
            approval_token="appr_human_token_valid_9988"
        )
        self.assertIsNotNone(artifact)

    def test_timeline_reconstruction_and_correlation(self):
        case = self.service.open_investigation_case(title="Timeline Test", description="Testing multi-source events")
        
        # Artifact 1: IDP Logs
        idp_data = json.dumps([
            {"user": "mallory@corp.internal", "action": "LOGIN_SUCCESS", "ip_address": "198.51.100.99", "timestamp": "2026-11-01T06:10:00Z"}
        ]).encode("utf-8")
        self.service.acquire_artifact(
            case_id=case.case_id,
            source_type=ArtifactType.IDENTITY_AUDIT,
            source_identifier="idp_logs",
            artifact_name="idp.json",
            raw_data=idp_data
        )

        # Artifact 2: Process Logs
        proc_data = json.dumps([
            {"user": "mallory@corp.internal", "process_name": "powershell.exe", "pid": 4120, "command_line": "powershell.exe -enc AAAA", "timestamp": "2026-11-01T06:12:00Z"}
        ]).encode("utf-8")
        self.service.acquire_artifact(
            case_id=case.case_id,
            source_type=ArtifactType.ENDPOINT_PROCESS,
            source_identifier="endpoint_telemetry",
            artifact_name="proc.json",
            raw_data=proc_data
        )

        timeline = self.service.reconstruct_case_timeline(case.case_id)
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0].actor, "mallory@corp.internal")
        self.assertEqual(timeline[1].event_category, "PROCESS")

        # Correlate evidence across artifacts
        correlations = self.service.correlate_evidence(case.case_id)
        self.assertGreaterEqual(len(correlations), 1)
        self.assertEqual(correlations[0].correlation_type, "SHARED_ACTOR")
        self.assertEqual(correlations[0].correlation_key, "mallory@corp.internal")

    def test_hypothesis_evaluation(self):
        case = self.service.open_investigation_case(title="Hypothesis Test", description="Testing competing theories")
        
        h1 = self.service.create_hypothesis(
            case_id=case.case_id,
            title="External Credential Stuffing",
            theory_description="Attacker utilized leaked credentials from public pastebin."
        )

        # Add support
        res = self.service.evaluate_hypothesis(
            hypothesis_id=h1.hypothesis_id,
            supporting_evidence=[
                "IP 198.51.100.99 observed in recent public darknet proxy list",
                "User password hash matches breached credential dump"
            ]
        )
        self.assertEqual(res["status"], HypothesisStatus.SUPPORTED.value)
        self.assertGreaterEqual(res["support_score"], 2.0)

        # Add contradiction to another hypothesis
        h2 = self.service.create_hypothesis(
            case_id=case.case_id,
            title="Insider Threat",
            theory_description="Employee intentionally exported proprietary documents."
        )
        res2 = self.service.evaluate_hypothesis(
            hypothesis_id=h2.hypothesis_id,
            contradictory_evidence=[
                "Employee physical badge access confirmed off-site during incident",
                "Endpoint forensic memory confirms active remote Trojan session"
            ]
        )
        self.assertEqual(res2["status"], HypothesisStatus.REFUTED.value)
        self.assertGreaterEqual(res2["refutation_score"], 2.0)

    def test_structured_forensic_report_generation(self):
        case = self.service.open_investigation_case(title="Report Test", description="Testing epistemic reporting")
        
        # Add artifact & reconstruct
        data = json.dumps([
            {"user": "admin", "action": "IAM_ROLE_ASSIGNED", "timestamp": "2026-11-01T06:30:00Z"}
        ]).encode("utf-8")
        self.service.acquire_artifact(
            case_id=case.case_id,
            source_type=ArtifactType.CLOUD_AUDIT_LOG,
            source_identifier="gcp_audit_log",
            artifact_name="audit.json",
            raw_data=data
        )
        self.service.reconstruct_case_timeline(case.case_id)

        report = self.service.generate_report(case_id=case.case_id, investigator="detective_eni")
        self.assertIsNotNone(report)
        self.assertTrue(report.report_id.startswith("rep_"))
        self.assertGreater(len(report.facts), 0)
        self.assertTrue(all(f.category == StatementCategory.FACT for f in report.facts))
        self.assertGreater(len(report.recommendations), 0)
        self.assertTrue(len(report.cryptographic_seal) == 64)  # Valid SHA-256 hex seal


if __name__ == "__main__":
    unittest.main()
