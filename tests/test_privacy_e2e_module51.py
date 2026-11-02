"""
tests/test_privacy_e2e_module51.py
12-Step Enterprise Scenario Drill for OMNIA Module 51:
Autonomous Privacy Engineering, Data Governance & Information Protection Intelligence.
"""

import unittest
import sqlite3
import tempfile
import os
import json
import hashlib
import time

from persistence.migrations import MIGRATION_V35
from privacy.models import (
    SensitivityTier, DataCategory, AssetType, DSRType, DSRStatus,
    DeletionStatus, ConsentStatus, PIAStatus, LawfulBasis
)
from privacy.service import PrivacyEngineeringOrchestrator


class TestPrivacyE2EModule51(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        conn = sqlite3.connect(self.temp_db_path)
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.executescript(MIGRATION_V35)
        conn.close()

        self.service = PrivacyEngineeringOrchestrator(db_path=self.temp_db_path)

    def tearDown(self):
        try:
            os.close(self.temp_db_fd)
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_full_enterprise_privacy_governance_drill(self):
        """Executes the comprehensive 12-step enterprise data governance & privacy intelligence drill."""
        print("\n--- Starting 12-Step Enterprise Privacy Drill ---")

        # Step 1: Asset Registration (Multi-tier enterprise assets)
        primary_db = self.service.inventory.register_asset(
            name="customer_master_db",
            asset_type="DATABASE",
            storage_location="aws://us-east-1/rds/customers",
            owner="core_data_team",
            residency_country="US",
            sensitivity_tier="CONFIDENTIAL"
        )
        replica_cache = self.service.inventory.register_asset(
            name="customer_redis_cache",
            asset_type="CACHE",
            storage_location="aws://us-east-1/elasticache/sessions",
            owner="core_data_team",
            residency_country="US",
            sensitivity_tier="INTERNAL"
        )
        ai_feature_store = self.service.inventory.register_asset(
            name="customer_features_ai",
            asset_type="AI_MODEL",
            storage_location="gcp://us-central1/vertex/features",
            owner="ai_platform_team",
            residency_country="US",
            sensitivity_tier="INTERNAL"
        )
        self.assertIsNotNone(primary_db.asset_id)
        self.assertIsNotNone(replica_cache.asset_id)
        print("  [Step 1] Multi-store enterprise assets registered: PASS")

        # Step 2: Schema Classification with Sensitivity Rollup
        fields = [
            {"name": "user_id", "sample_values": ["usr_1001", "usr_1002"]},
            {"name": "full_name", "sample_values": ["Alice Wonderland", "Bob Builder"]},
            {"name": "email_address", "sample_values": ["alice@example.com", "bob@example.com"]},
            {"name": "gov_ssn", "sample_values": ["987-65-4321"]},
            {"name": "card_number", "sample_values": ["4532015112830366"]},
            {"name": "medical_mrn", "sample_values": ["MRN-883921"]}
        ]
        classifications = self.service.classifier.classify_schema(primary_db.asset_id, fields)
        self.assertEqual(len(classifications), 6)

        # Recalculate sensitivity tier for primary_db (should escalate to HIGHLY_RESTRICTED due to SSN/Card/MRN)
        new_tier = self.service.inventory.recalculate_asset_sensitivity(primary_db.asset_id)
        self.assertEqual(new_tier, SensitivityTier.HIGHLY_RESTRICTED)
        print("  [Step 2] Schema classification & asset tier escalation to HIGHLY_RESTRICTED: PASS")

        # Step 3: Scoped Sensitive Data Discovery Scan
        scan = self.service.discovery.run_discovery_scan(
            target_scope="customer_master_db.public.users",
            scanner_identity="omnia_privacy_agent_51",
            sample_payload={
                "email_address": "john.doe@company.internal",
                "gov_ssn": "111-22-3333",
                "card_number": "4532015112830366"
            }
        )
        self.assertEqual(scan.status, "COMPLETED")
        self.assertGreaterEqual(scan.findings_count, 3)
        # Verify read-only boundary: no raw sensitive values in persisted findings
        persisted_scan_text = json.dumps(scan.sensitive_fields)
        self.assertNotIn("111-22-3333", persisted_scan_text)
        self.assertNotIn("4532015112830366", persisted_scan_text)
        print("  [Step 3] Read-only discovery completed with zero plaintext leakage: PASS")

        # Step 4: Lineage Graph Tracing (Primary -> Cache -> AI Model)
        self.service.lineage.record_lineage(primary_db.asset_id, replica_cache.asset_id, "REPLICATION", "SESSION_LOOKUP")
        self.service.lineage.record_lineage(primary_db.asset_id, ai_feature_store.asset_id, "TRANSFORMATION", "INFERENCE_EMBEDDING")

        downstream = self.service.lineage.trace_downstream(primary_db.asset_id)
        self.assertIn(replica_cache.asset_id, downstream)
        self.assertIn(ai_feature_store.asset_id, downstream)
        print("  [Step 4] Lineage provenance graph constructed and traversed: PASS")

        # Step 5: RoPA Processing Activity Registration & Purpose Binding
        activity = self.service.processing_registry.register_activity(
            name="personalized_recommendations",
            purpose="PRODUCT_RECOMMENDATION",
            lawful_basis="CONSENT",
            owner="growth_team",
            data_categories=["PII", "BEHAVIORAL"],
            retention_schedule="P1Y",
            is_approved=False
        )
        # Processing blocked prior to DPO review
        valid, _ = self.service.processing_registry.validate_processing("PRODUCT_RECOMMENDATION")
        self.assertFalse(valid)

        # Formally approve RoPA entry
        self.service.processing_registry.approve_activity(activity.activity_id, approver="dpo_sarah")
        valid_post_approval, _ = self.service.processing_registry.validate_processing("PRODUCT_RECOMMENDATION", ["PII"])
        self.assertTrue(valid_post_approval)
        print("  [Step 5] RoPA purpose binding & DPO review workflow validated: PASS")

        # Step 6: Consent Lifecycle (Grant -> Cessation upon Withdrawal)
        subject_id = "user_drill_772"
        self.service.consent.grant_consent(subject_id, "PRODUCT_RECOMMENDATION", policy_version="3.0")
        self.assertTrue(self.service.consent.has_valid_consent(subject_id, "PRODUCT_RECOMMENDATION"))

        # User withdraws consent
        self.service.consent.withdraw_consent(subject_id, "PRODUCT_RECOMMENDATION")
        self.assertFalse(self.service.consent.has_valid_consent(subject_id, "PRODUCT_RECOMMENDATION"))
        print("  [Step 6] Purpose-specific consent grant & withdrawal enforcement: PASS")

        # Step 7: Data Minimization & Privacy-by-Design Check
        minimization_res = self.service.minimization.evaluate_schema_minimization(
            purpose="NEWSLETTER",
            classified_fields=[
                {"field_name": "email", "category": "PII", "sensitivity_tier": "CONFIDENTIAL"},
                {"field_name": "retina_scan", "category": "BIOMETRIC", "sensitivity_tier": "HIGHLY_RESTRICTED"}
            ],
            proposed_retention_days=1825
        )
        self.assertFalse(minimization_res["is_minimized"])
        self.assertIn("retina_scan", minimization_res["high_risk_fields"])
        self.assertIsNotNone(minimization_res["retention_warning"])
        print("  [Step 7] Data minimization engine flagged excessive biometrics & over-retention: PASS")

        # Step 8: Legal Hold Overrides (NEVER Delete Data Under Legal Hold!)
        self.service.retention.register_legal_hold(subject_id, "Court Order 2026-CV-8802 (State AG)")

        # Attempt deletion
        blocked_del = self.service.retention.orchestrate_deletion(
            asset_id=primary_db.asset_id,
            target_selector=f"subject_id={subject_id}",
            reason="User GDPR Deletion Request",
            requested_by="compliance_officer",
            approval_token="appr_tok_temp"
        )
        self.assertEqual(blocked_del.status, DeletionStatus.BLOCKED_LEGAL_HOLD)
        self.assertFalse(blocked_del.verified)
        print("  [Step 8] Active legal hold strictly blocked deletion across all stores: PASS")

        # Step 9: Cascading Multi-Store Verified Deletion
        self.service.retention.release_legal_hold(subject_id, released_by="legal_counsel_lead")

        # Re-execute deletion with formal approval token
        approved_del = self.service.retention.orchestrate_deletion(
            asset_id=primary_db.asset_id,
            target_selector=f"subject_id={subject_id}",
            reason="User GDPR Deletion Request",
            requested_by="compliance_officer",
            approval_token="appr_formal_dpo_2026"
        )
        self.assertEqual(approved_del.status, DeletionStatus.COMPLETED)
        self.assertTrue(approved_del.verified)
        self.assertIsNotNone(approved_del.verification_proof)

        # Check cascading deletion records on replica stores
        cache_dels = self.service.repo.list_deletion_requests(asset_id=replica_cache.asset_id)
        ai_dels = self.service.repo.list_deletion_requests(asset_id=ai_feature_store.asset_id)
        self.assertEqual(len(cache_dels), 1)
        self.assertEqual(len(ai_dels), 1)
        self.assertEqual(cache_dels[0].status, DeletionStatus.COMPLETED)
        self.assertEqual(ai_dels[0].status, DeletionStatus.COMPLETED)
        print("  [Step 9] Cascading verified deletion executed with cryptographic proofs: PASS")

        # Step 10: Data Subject Rights (DSR/DSAR) Access & Correction
        dsr_access = self.service.dsr.submit_request(
            subject_id="user_dsr_99",
            request_type="ACCESS",
            requester_email="user99@example.com",
            verification_token="vtoken_99"
        )
        self.assertEqual(dsr_access.status, DSRStatus.VERIFIED)

        # Fulfill DSR access
        fulfilled_access = self.service.dsr.fulfill_request(dsr_access.dsr_id, approval_token="dpo_approved_dsr")
        self.assertEqual(fulfilled_access.status, DSRStatus.FULFILLED)
        self.assertIn("user_dsr_99", fulfilled_access.result_summary)
        print("  [Step 10] DSR Access request verified and fulfilled: PASS")

        # Step 11: Vendor Governance & Cross-Border Adequacy Validation
        vendor = self.service.vendor.register_vendor(
            name="GlobalTranscribe AI",
            service_type="AUDIO_PROCESSING",
            dpa_status="SIGNED",
            residency="DE",
            subprocessors=["AWS_Frankfurt"]
        )
        transfer = self.service.cross_border.register_transfer(
            source_country="FR",
            dest_country="DE",
            recipient=vendor.name,
            purpose="VOICE_TRANSCRIPTION"
        )
        self.assertTrue(transfer.is_approved)
        print("  [Step 11] Vendor DPA and EEA-EEA adequacy transfer approved: PASS")

        # Step 12: Comprehensive Privacy Posture Intelligence Report
        report = self.service.reporting.generate_posture_report(generated_by="chief_privacy_officer")
        self.assertIsNotNone(report.report_id)
        self.assertGreater(report.overall_posture_score, 0.0)
        self.assertEqual(len(report.cryptographic_seal), 64)
        self.assertGreaterEqual(len(report.summary_facts), 5)
        print(f"  [Step 12] Sealed Privacy Posture Report generated: Score={report.overall_posture_score}, Seal={report.cryptographic_seal[:16]}...: PASS")

        print("--- 12-Step Enterprise Privacy Drill Completed Successfully! ---\n")


if __name__ == "__main__":
    unittest.main()
