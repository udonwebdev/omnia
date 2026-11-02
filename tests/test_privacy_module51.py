"""
tests/test_privacy_module51.py
Comprehensive unit tests covering all components of Module 51:
Autonomous Privacy Engineering, Data Governance & Information Protection Intelligence.
"""

import unittest
import sqlite3
import tempfile
import os
import json
import time

from persistence.migrations import MIGRATION_V35
from privacy.models import (
    SensitivityTier, DataCategory, AssetType, DSRType, DSRStatus,
    DeletionStatus, ConsentStatus, PIAStatus, PIAType, LawfulBasis,
    TransferMechanism, IncidentSeverity, ContainmentStatus
)
from privacy.persistence import PrivacyRepository
from privacy.inventory import EnterpriseDataInventory
from privacy.classifier import DataClassificationEngine, luhn_checksum_valid
from privacy.discovery import SensitiveDataDiscoveryEngine
from privacy.lineage import DataLineageTracker
from privacy.processing_registry import ProcessingActivityRegistry
from privacy.consent import ConsentManager
from privacy.minimization import DataMinimizationEngine
from privacy.retention import RetentionLifecycleManager
from privacy.dsr_manager import DataSubjectRequestManager
from privacy.assessment import PrivacyAssessmentEngine
from privacy.access_governance import AccessGovernanceEngine
from privacy.vendor_governance import VendorGovernanceManager
from privacy.cross_border import CrossBorderTransferGovernor
from privacy.transformations import PrivacyTransformationEngine
from privacy.incident_manager import PrivacyIncidentManager
from privacy.ai_governance import AIPrivacyGovernor
from privacy.reporting import PrivacyReportingEngine
from privacy.service import PrivacyEngineeringOrchestrator


class TestPrivacyModule51(unittest.TestCase):
    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        conn = sqlite3.connect(self.temp_db_path)
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.executescript(MIGRATION_V35)
        conn.close()

        self.service = PrivacyEngineeringOrchestrator(db_path=self.temp_db_path)
        self.repo = self.service.repo

    def tearDown(self):
        try:
            os.close(self.temp_db_fd)
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except Exception:
            pass

    def test_01_asset_inventory_registration_and_update(self):
        """Tests asset registration, metadata updates, and retrieval."""
        asset = self.service.inventory.register_asset(
            name="users_primary",
            asset_type="TABLE",
            storage_location="postgres://prod-db/users",
            owner="data_platform",
            residency_country="US",
            sensitivity_tier="CONFIDENTIAL",
            metadata={"row_count": 50000}
        )
        self.assertIsNotNone(asset.asset_id)
        self.assertEqual(asset.name, "users_primary")
        self.assertEqual(asset.residency_country, "US")

        # Update asset
        updated = self.service.inventory.update_asset(
            asset.asset_id,
            residency_country="EU",
            sensitivity_tier="RESTRICTED"
        )
        self.assertEqual(updated.residency_country, "EU")
        self.assertEqual(updated.sensitivity_tier, SensitivityTier.RESTRICTED)

        # List assets
        assets = self.service.inventory.list_assets(residency="EU")
        self.assertEqual(len(assets), 1)

    def test_02_data_classification_rules_and_luhn(self):
        """Tests pattern, name, and Luhn-based classification for sensitive fields."""
        # Luhn test
        self.assertTrue(luhn_checksum_valid("4532015112830366"))
        self.assertFalse(luhn_checksum_valid("4532015112830367"))

        # SSN classification
        c_ssn = self.service.classifier.classify_field(
            asset_id="test_ast",
            field_name="user_ssn",
            sample_values=["123-45-6789"]
        )
        self.assertEqual(c_ssn.category, DataCategory.GOV_ID)
        self.assertEqual(c_ssn.sensitivity_tier, SensitivityTier.HIGHLY_RESTRICTED)
        self.assertGreaterEqual(c_ssn.confidence, 0.90)

        # Email classification
        c_email = self.service.classifier.classify_field(
            asset_id="test_ast",
            field_name="contact_email",
            sample_values=["alice@example.com"]
        )
        self.assertEqual(c_email.category, DataCategory.PII)
        self.assertEqual(c_email.sensitivity_tier, SensitivityTier.CONFIDENTIAL)

        # Credit card classification
        c_cc = self.service.classifier.classify_field(
            asset_id="test_ast",
            field_name="card_num",
            sample_values=["4532015112830366"]
        )
        self.assertEqual(c_cc.category, DataCategory.FINANCIAL)
        self.assertEqual(c_cc.sensitivity_tier, SensitivityTier.HIGHLY_RESTRICTED)

        # Health/Biometric/Credentials
        c_health = self.service.classifier.classify_field("test_ast", "patient_diagnosis")
        self.assertEqual(c_health.category, DataCategory.HEALTH)

        c_bio = self.service.classifier.classify_field("test_ast", "iris_biometric_template")
        self.assertEqual(c_bio.category, DataCategory.BIOMETRIC)

        c_token = self.service.classifier.classify_field("test_ast", "api_secret_key")
        self.assertEqual(c_token.category, DataCategory.CREDENTIALS)

    def test_03_controlled_sensitive_data_discovery(self):
        """Tests read-only scoped discovery without persisting raw sensitive values."""
        scan = self.service.discovery.run_discovery_scan(
            target_scope="analytics_clickstream",
            scanner_identity="audit_worker_01",
            field_names=["ip_address", "session_id", "email"],
            sample_payload={"email": "victim@omnia.org", "ip_address": "192.168.1.1"}
        )
        self.assertEqual(scan.status, "COMPLETED")
        self.assertGreaterEqual(scan.findings_count, 1)

        # Crucial invariant check: raw email should NOT appear in persisted findings
        findings_str = json.dumps(scan.sensitive_fields)
        self.assertNotIn("victim@omnia.org", findings_str)

    def test_04_data_lineage_and_cascading_tracing(self):
        """Tests lineage recording and graph traversal for downstream cascading deletion."""
        self.service.lineage.record_lineage("db_primary", "dw_warehouse", "ETL_REPLICATE", "ANALYTICS")
        self.service.lineage.record_lineage("dw_warehouse", "redis_cache", "CACHE_LOAD", "PERF")
        self.service.lineage.record_lineage("dw_warehouse", "ai_feature_store", "FEATURE_EXTRACT", "AI_INFERENCE")

        downstream = self.service.lineage.trace_downstream("db_primary")
        self.assertIn("dw_warehouse", downstream)
        self.assertIn("redis_cache", downstream)
        self.assertIn("ai_feature_store", downstream)

        upstream = self.service.lineage.trace_upstream("redis_cache")
        self.assertIn("dw_warehouse", upstream)
        self.assertIn("db_primary", upstream)

        graph = self.service.lineage.get_lineage_graph("db_primary")
        self.assertEqual(graph["root_asset"], "db_primary")
        self.assertEqual(graph["downstream_count"], 3)

    def test_05_processing_activity_ropa_and_purpose_validation(self):
        """Tests GDPR Art 30 RoPA registration, DPO approval, and purpose binding validation."""
        act = self.service.processing_registry.register_activity(
            name="customer_billing_service",
            purpose="CUSTOMER_BILLING",
            lawful_basis="CONTRACT",
            owner="finance_team",
            data_categories=["FINANCIAL", "PII"],
            is_approved=False
        )
        self.assertFalse(act.is_approved)

        # Validation should fail because unapproved
        valid, reason = self.service.processing_registry.validate_processing("CUSTOMER_BILLING")
        self.assertFalse(valid)
        self.assertIn("UNAPPROVED", reason)

        # Approve activity
        self.service.processing_registry.approve_activity(act.activity_id, approver="dpo_alice")
        valid, msg = self.service.processing_registry.validate_processing("CUSTOMER_BILLING", ["FINANCIAL"])
        self.assertTrue(valid)

        # Mismatch category
        valid_mismatch, reason_mismatch = self.service.processing_registry.validate_processing(
            "CUSTOMER_BILLING", ["BIOMETRIC"]
        )
        self.assertFalse(valid_mismatch)
        self.assertIn("CATEGORY_MISMATCH", reason_mismatch)

    def test_06_consent_lifecycle_and_withdrawal(self):
        """Tests granular purpose-specific consent granting and immediate withdrawal cessation."""
        subject = "user_8829"
        purpose = "MARKETING_EMAILS"

        self.assertFalse(self.service.consent.has_valid_consent(subject, purpose))

        # Grant consent
        c_grant = self.service.consent.grant_consent(subject, purpose, policy_version="2.1")
        self.assertEqual(c_grant.status, ConsentStatus.GRANTED)
        self.assertTrue(self.service.consent.has_valid_consent(subject, purpose))

        # Withdraw consent
        c_withdrawn = self.service.consent.withdraw_consent(subject, purpose)
        self.assertEqual(c_withdrawn.status, ConsentStatus.WITHDRAWN)
        self.assertFalse(self.service.consent.has_valid_consent(subject, purpose))

        history = self.service.consent.get_consent_history(subject)
        self.assertGreaterEqual(len(history), 1)

    def test_07_data_minimization_and_privacy_by_design(self):
        """Tests detection of excessive categories and over-retention."""
        fields = [
            {"field_name": "email", "category": "PII", "sensitivity_tier": "CONFIDENTIAL"},
            {"field_name": "user_ssn", "category": "GOV_ID", "sensitivity_tier": "HIGHLY_RESTRICTED"},
            {"field_name": "retina_scan", "category": "BIOMETRIC", "sensitivity_tier": "HIGHLY_RESTRICTED"}
        ]
        result = self.service.minimization.evaluate_schema_minimization(
            purpose="NEWSLETTER",
            classified_fields=fields,
            proposed_retention_days=1000
        )
        self.assertFalse(result["is_minimized"])
        self.assertGreaterEqual(len(result["excessive_fields"]), 2)
        self.assertIn("retina_scan", result["high_risk_fields"])
        self.assertIsNotNone(result["retention_warning"])

    def test_08_retention_legal_hold_and_verified_deletion(self):
        """Tests legal hold enforcement blocking deletion, followed by multi-store cascading verified deletion with SHA-256 proof."""
        asset = self.service.inventory.register_asset("customer_db", "DATABASE", "us-east-1", "core_team")
        replica = self.service.inventory.register_asset("customer_cache", "CACHE", "us-east-1", "core_team")
        self.service.lineage.record_lineage(asset.asset_id, replica.asset_id, "REPLICATE", "CACHING")

        # 1. Place Legal Hold
        self.service.retention.register_legal_hold("user_litigation_99", "Subpoena 2026-CV-9912")

        # 2. Attempt Deletion while Legal Hold is active -> MUST BE BLOCKED
        blocked_req = self.service.retention.orchestrate_deletion(
            asset_id=asset.asset_id,
            target_selector="user_litigation_99",
            reason="User GDPR request",
            requested_by="support_agent",
            approval_token="appr_tok_1"
        )
        self.assertEqual(blocked_req.status, DeletionStatus.BLOCKED_LEGAL_HOLD)
        self.assertFalse(blocked_req.verified)
        self.assertIn("Subpoena", blocked_req.reason)

        # 3. Release Legal Hold
        self.service.retention.release_legal_hold("user_litigation_99")

        # 4. Attempt Deletion again -> Success with cryptographic proof and cascading
        approved_req = self.service.retention.orchestrate_deletion(
            asset_id=asset.asset_id,
            target_selector="user_litigation_99",
            reason="User GDPR request",
            requested_by="support_agent",
            approval_token="appr_tok_2"
        )
        self.assertEqual(approved_req.status, DeletionStatus.COMPLETED)
        self.assertTrue(approved_req.verified)
        self.assertIsNotNone(approved_req.verification_proof)
        self.assertEqual(len(approved_req.verification_proof), 64)

        # Check cascading deletion on replica
        replica_deletions = self.repo.list_deletion_requests(asset_id=replica.asset_id)
        self.assertEqual(len(replica_deletions), 1)
        self.assertEqual(replica_deletions[0].status, DeletionStatus.COMPLETED)

    def test_09_dsr_request_lifecycle(self):
        """Tests DSR submission, requester identity verification, legal hold guard, and fulfillment."""
        # Submit DSR
        dsr = self.service.dsr.submit_request(
            subject_id="sub_551",
            request_type="DELETION",
            requester_email="sub551@example.com",
            verification_token="token_xyz"
        )
        self.assertEqual(dsr.status, DSRStatus.VERIFIED)

        # Put subject on legal hold
        self.service.retention.register_legal_hold("sub_551", "SEC Inquiry 2026")

        # Fulfill should be blocked by legal hold
        blocked_dsr = self.service.dsr.fulfill_request(dsr.dsr_id, approval_token="token_sec")
        self.assertEqual(blocked_dsr.status, DSRStatus.BLOCKED_LEGAL_HOLD)

        # Release hold and fulfill
        self.service.retention.release_legal_hold("sub_551")
        fulfilled_dsr = self.service.dsr.fulfill_request(dsr.dsr_id, approval_token="token_sec")
        self.assertEqual(fulfilled_dsr.status, DSRStatus.FULFILLED)

    def test_10_privacy_impact_assessment_scoring(self):
        """Tests multi-factor PIA/DPIA risk calculation and safeguard generation."""
        act = self.service.processing_registry.register_activity(
            name="ai_medical_analytics",
            purpose="HEALTHCARE_AI",
            lawful_basis="CONSENT",
            owner="health_lab",
            data_categories=["HEALTH", "BIOMETRIC"],
            is_approved=True
        )
        assessment = self.service.assessment.conduct_assessment(
            activity_id=act.activity_id,
            assessment_type="DPIA",
            involves_ai=True,
            involves_third_parties=True,
            subject_count=500000,
            has_encryption=True
        )
        self.assertGreater(assessment.risk_score, 50.0)
        self.assertIn(assessment.approval_status, (PIAStatus.REVIEW_REQUIRED, PIAStatus.REJECTED))
        self.assertGreaterEqual(len(assessment.safeguards), 2)

    def test_11_access_governance_least_privilege(self):
        """Tests purpose-aware access control and sanitized logging."""
        asset = self.service.inventory.register_asset(
            name="vault_keys",
            asset_type="TABLE",
            storage_location="kms://prod",
            owner="security",
            sensitivity_tier="HIGHLY_RESTRICTED"
        )
        # Access without justification to HIGHLY_RESTRICTED asset should be rejected
        auth, log = self.service.access.authorize_and_log_access(
            actor_id="dev_bob",
            asset_id=asset.asset_id,
            purpose="DEBUGGING",
            justification=None
        )
        self.assertFalse(auth)
        self.assertFalse(log.authorized)

        # Access with documented justification succeeds
        auth_ok, log_ok = self.service.access.authorize_and_log_access(
            actor_id="dev_bob",
            asset_id=asset.asset_id,
            purpose="AUDIT",
            justification="Ticket INC-4991 Authorized Debug"
        )
        self.assertTrue(auth_ok)
        self.assertTrue(log_ok.authorized)

    def test_12_vendor_and_cross_border_governance(self):
        """Tests vendor DPA compliance and cross-border adequacy checks."""
        # Vendor check
        vnd = self.service.vendor.register_vendor(
            name="AcmeCloud",
            service_type="OBJECT_STORAGE",
            dpa_status="PENDING",
            residency="US"
        )
        comp = self.service.vendor.evaluate_vendor_compliance(vnd.vendor_id)
        self.assertFalse(comp["compliant"])

        self.service.vendor.update_dpa_status(vnd.vendor_id, "SIGNED")
        comp_signed = self.service.vendor.evaluate_vendor_compliance(vnd.vendor_id)
        self.assertTrue(comp_signed["compliant"])

        # Cross-border check: EEA to EEA adequate
        valid_eea, msg_eea = self.service.cross_border.validate_transfer("DE", "FR")
        self.assertTrue(valid_eea)

        # Cross-border check: EEA to non-adequate country without SCC
        valid_non, msg_non = self.service.cross_border.validate_transfer("DE", "CN")
        self.assertFalse(valid_non)

        # Cross-border check with SCCs
        valid_scc, msg_scc = self.service.cross_border.validate_transfer("DE", "CN", "STANDARD_CONTRACTUAL_CLAUSES")
        self.assertTrue(valid_scc)

    def test_13_privacy_transformations(self):
        """Tests HMAC tokenization, format-preserving masking, redaction, and k-anonymity."""
        t = self.service.transformer

        # HMAC tokenization
        tok1 = t.tokenize("secret_payload")
        tok2 = t.tokenize("secret_payload")
        tok3 = t.tokenize("other_payload")
        self.assertEqual(tok1, tok2)
        self.assertNotEqual(tok1, tok3)
        self.assertTrue(tok1.startswith("tok_"))

        # Masking
        self.assertEqual(t.mask("testuser@example.com"), "t******r@example.com")
        self.assertEqual(t.mask("123-45-6789"), "***-**-6789")
        self.assertEqual(t.mask("4532015112830366"), "************0366")

        # Redaction
        redacted = t.redact("Contact me at alice@test.com with SSN 000-12-3456.")
        self.assertIn("[REDACTED:EMAIL]", redacted)
        self.assertIn("[REDACTED:SSN]", redacted)
        self.assertNotIn("alice@test.com", redacted)
        self.assertNotIn("000-12-3456", redacted)

        # k-anonymity aggregation
        data = [
            {"zip": "94101", "age": "30", "diagnosis": "Flu"},
            {"zip": "94101", "age": "30", "diagnosis": "Cold"},
            {"zip": "94101", "age": "30", "diagnosis": "Cough"},
            {"zip": "90210", "age": "50", "diagnosis": "Headache"}
        ]
        anon = t.aggregate_k_anonymity(data, quasi_identifiers=["zip", "age"], k=3)
        self.assertEqual(len(anon), 4)
        # Unique row should have suppressed quasi-identifiers
        self.assertEqual(anon[3]["zip"], "*SUPPRESSED*")
        self.assertEqual(anon[0]["zip"], "94101")

    def test_14_incident_management_and_ai_governance(self):
        """Tests privacy incident 72-hour reportability and AI prompt redaction/training bans."""
        # Incident
        inc = self.service.incident.record_incident(
            incident_type="UNAUTHORIZED_EXFILTRATION",
            affected_assets=["ast_01"],
            affected_categories=["CREDENTIALS", "FINANCIAL"],
            severity="CRITICAL"
        )
        self.assertTrue(inc.reportable)
        rep = self.service.incident.assess_reportability(inc.incident_id)
        self.assertTrue(rep["requires_supervisory_authority_notice"])
        self.assertLessEqual(rep["regulatory_notice_deadline_hours"], 72.0)

        # AI Governance
        ai_cfg = self.service.ai_governance.configure_model(
            model_id="gpt-internal-v1",
            provider="AzureOpenAI",
            training_permitted=False,
            prompt_redaction_enabled=True,
            retention_policy="ZERO_DAY"
        )
        comp_ai = self.service.ai_governance.verify_model_compliance(ai_cfg.model_id)
        self.assertTrue(comp_ai["compliant"])

        prompt = "Hello my SSN is 123-45-6789 and email bob@example.com"
        clean_prompt = self.service.ai_governance.sanitize_prompt(ai_cfg.model_id, prompt)
        self.assertNotIn("123-45-6789", clean_prompt)
        self.assertIn("[REDACTED:SSN]", clean_prompt)

    def test_15_reporting_facts_vs_estimates_and_cryptographic_seal(self):
        """Tests posture reporting, distinction of facts vs estimates, and SHA-256 seal."""
        report = self.service.reporting.generate_posture_report("ciso_lead")
        self.assertIsNotNone(report.report_id)
        self.assertEqual(len(report.cryptographic_seal), 64)
        self.assertGreaterEqual(len(report.summary_facts), 4)
        self.assertGreaterEqual(len(report.estimates), 1)
        self.assertTrue(all(f.startswith("FACT:") for f in report.summary_facts))
        self.assertTrue(all(e.startswith("ESTIMATE:") for e in report.estimates))


if __name__ == "__main__":
    unittest.main()
