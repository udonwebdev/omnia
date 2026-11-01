"""
Unit Tests for OMNIA Module 46:
Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
"""
import unittest
import os
import uuid
import sqlite3
from datetime import datetime, timezone, timedelta

from persistence.migrations import MIGRATION_V31
from app_security.models import (
    AssetType, Criticality, EnvironmentTier, ExposureTier, FindingCategory,
    FindingStatus, PriorityLevel, Severity, ValidationOutcome
)
from app_security.persistence import AppSecurityRepository
from app_security.authorization_registry import (
    AuthorizationRegistry, ScopeViolationError, AuthorizationExpiredError
)
from app_security.application_analyzer import ApplicationSecurityAnalyzer
from app_security.api_security_analyzer import APISecurityAnalyzer
from app_security.dependency_analyzer import DependencyVulnerabilityAnalyzer
from app_security.secret_detector import SecretExposureDetector
from app_security.safe_validation import SafeValidationEngine
from app_security.risk_prioritizer import RiskPrioritizer
from app_security.remediation_planner import RemediationPlanner
from app_security.regression_monitor import SecurityRegressionMonitor
from app_security.service import AppSecurityOrchestrator


class TestModule46AppSecurity(unittest.TestCase):

    def setUp(self):
        self.db_name = f"test_sec_{uuid.uuid4().hex[:8]}.db"
        conn = sqlite3.connect(self.db_name)
        conn.executescript(MIGRATION_V31)
        conn.close()

        self.repo = AppSecurityRepository(db_path=self.db_name)
        self.orchestrator = AppSecurityOrchestrator(db_path=self.db_name)

        self.asset = self.orchestrator.register_authorized_asset(
            name="Omnia Core Auth Service",
            asset_type=AssetType.APPLICATION,
            owner="sec-team",
            environment=EnvironmentTier.STAGING,
            exposure_tier=ExposureTier.RESTRICTED,
            criticality=Criticality.HIGH
        )
        self.asset_id = self.asset.asset_id

        future_iso = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        self.auth = self.orchestrator.create_assessment_authorization(
            name="Staging AppSec Testing",
            operator="auditor-1",
            owner_approval_ref="M20-APPROVE-46",
            assessment_purpose="Pre-release security audit",
            environment_tier=EnvironmentTier.STAGING,
            valid_until=future_iso,
            permitted_techniques=["FULL_ASSESSMENT", "STATIC_ANALYSIS", "SAFE_API_PROBE"]
        )
        self.auth_id = self.auth.authorization_id

        # Register scope
        self.orchestrator.auth_registry.register_scope(
            authorization_id=self.auth_id,
            asset_id=self.asset_id,
            permitted_endpoints=["*"],
            excluded_endpoints=["/api/v1/billing/charge_live_card"]
        )

        # Create base assessment for tests
        self.assessment_id = "asm-unit-test-46"
        from app_security.models import SecurityAssessment
        self.repo.save_assessment(
            SecurityAssessment(
                assessment_id=self.assessment_id,
                authorization_id=self.auth_id,
                asset_id=self.asset_id,
                assessment_type="FULL_ASSESSMENT"
            )
        )

    def tearDown(self):
        if os.path.exists(self.db_name):
            try:
                os.remove(self.db_name)
            except Exception:
                pass

    def test_scope_validation_and_rejection(self):
        """Test strict authorization boundaries, allowed targets, and out-of-scope rejection."""
        registry = self.orchestrator.auth_registry

        # In-scope path passes
        self.assertTrue(
            registry.validate_target_access(
                authorization_id=self.auth_id,
                asset_id=self.asset_id,
                target_endpoint_or_file="/api/v1/auth/login",
                requested_technique="STATIC_ANALYSIS"
            )
        )

        # Excluded endpoint is rejected
        with self.assertRaises(ScopeViolationError):
            registry.validate_target_access(
                authorization_id=self.auth_id,
                asset_id=self.asset_id,
                target_endpoint_or_file="/api/v1/billing/charge_live_card",
                requested_technique="STATIC_ANALYSIS"
            )

        # Unpermitted technique is rejected
        with self.assertRaises(ScopeViolationError):
            registry.validate_target_access(
                authorization_id=self.auth_id,
                asset_id=self.asset_id,
                target_endpoint_or_file="/api/v1/auth/login",
                requested_technique="ACTIVE_FUZZING_EXPLOIT"
            )

    def test_authorization_expiration_and_emergency_kill(self):
        """Test expired authorization rejection and emergency kill switch lockdown."""
        registry = self.orchestrator.auth_registry

        # Expired authorization
        past_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        expired_auth = registry.grant_authorization(
            name="Expired Grant",
            operator="auditor-2",
            owner_approval_ref="M20-OLD",
            assessment_purpose="Expired",
            environment_tier=EnvironmentTier.STAGING,
            valid_until=past_iso,
            permitted_techniques=["STATIC_ANALYSIS"]
        )
        registry.register_scope(expired_auth.authorization_id, self.asset_id)

        with self.assertRaises(AuthorizationExpiredError):
            registry.validate_target_access(
                authorization_id=expired_auth.authorization_id,
                asset_id=self.asset_id,
                target_endpoint_or_file="/api/v1/auth",
                requested_technique="STATIC_ANALYSIS"
            )

        # Emergency Kill Switch
        registry.activate_emergency_kill_switch("sec-ops", "Critical incident suspected")
        with self.assertRaises(ScopeViolationError):
            registry.validate_target_access(
                authorization_id=self.auth_id,
                asset_id=self.asset_id,
                target_endpoint_or_file="/api/v1/auth",
                requested_technique="STATIC_ANALYSIS"
            )

        registry.deactivate_emergency_kill_switch("sec-ops")
        self.assertTrue(
            registry.validate_target_access(
                authorization_id=self.auth_id,
                asset_id=self.asset_id,
                target_endpoint_or_file="/api/v1/auth",
                requested_technique="STATIC_ANALYSIS"
            )
        )

    def test_static_ast_application_analysis(self):
        """Test AST analysis finding SQL injection, command injection, and deserialization."""
        analyzer = self.orchestrator.app_analyzer

        vulnerable_code = """
import os, subprocess, pickle

def handle_user(user_id, raw_cmd):
    # SQL injection via format string
    cursor.execute(f"SELECT * FROM users WHERE id = '{user_id}'")
    
    # Command injection
    os.system("ping -c 1 " + raw_cmd)
    
    # Insecure deserialization
    obj = pickle.loads(user_id.encode())
"""
        findings = analyzer.analyze_source_code(
            assessment_id=self.assessment_id,
            asset_id=self.asset_id,
            filename="user_handler.py",
            source_code=vulnerable_code
        )
        self.assertGreaterEqual(len(findings), 3)
        categories = {f.category for f in findings}
        self.assertIn(FindingCategory.INJECTION, categories)

    def test_secret_exposure_detection_and_redaction(self):
        """Test credential detection, immediate redaction, and SHA-256 evidence hashing."""
        detector = self.orchestrator.secret_detector

        code_with_secrets = """
DATABASE_URL = "postgresql://admin:super_secret_password_12345@10.0.0.1:5432/production_db"
API_KEY = "AKIA1234567890ABCDEF"
GITHUB_TOKEN = "ghp_123456789012345678901234567890123456"
"""
        findings = detector.scan_content_for_secrets(
            assessment_id=self.assessment_id,
            asset_id=self.asset_id,
            filename="config.py",
            content=code_with_secrets
        )
        self.assertEqual(len(findings), 3)

        for f in findings:
            self.assertEqual(f.category, FindingCategory.SECRET_LEAK)
            masked = f.evidence_redacted.get("masked_sample", "")
            self.assertIn("*", masked)
            self.assertNotIn("super_secret_password_12345", masked)
            self.assertIn("secret_sha256", f.evidence_redacted)

    def test_dependency_vulnerability_correlation(self):
        """Test lockfile parsing and exact version vulnerability matching."""
        analyzer = self.orchestrator.dep_analyzer

        reqs = """
requests==2.28.1
urllib3==1.26.5
pyyaml==5.3
numpy==1.24.0
"""
        findings = analyzer.analyze_requirements_txt(
            assessment_id=self.assessment_id,
            asset_id=self.asset_id,
            requirements_content=reqs
        )
        self.assertGreaterEqual(len(findings), 3)
        cves = [f.evidence_redacted["cve"] for f in findings]
        self.assertIn("CVE-2023-32681", cves)  # requests
        self.assertIn("CVE-2020-14343", cves)  # pyyaml

    def test_safe_vulnerability_validation(self):
        """Test safe non-destructive validation probe and status update."""
        finding = self.orchestrator.app_analyzer._create_finding(
            assessment_id=self.assessment_id,
            asset_id=self.asset_id,
            title="Potential SSRF in webhook handler",
            category=FindingCategory.SSRF,
            severity=Severity.HIGH,
            cwe_id="CWE-918",
            component_ref="webhook.py",
            location_ref="Line 42",
            evidence={"url": "http://169.254.169.254"}
        )
        self.repo.save_finding(finding)
        fid = finding.finding_id

        def safe_probe():
            return ValidationOutcome.CONFIRMED, "Synthetic request isolated internal metadata response."

        val = self.orchestrator.safe_validation.validate_finding_safely(
            finding_id=fid,
            method="SAFE_SYNTHETIC_PROBE",
            probe_runner=safe_probe
        )
        self.assertEqual(val.outcome, ValidationOutcome.CONFIRMED)
        updated = self.repo.get_finding(fid)
        self.assertEqual(updated.status, FindingStatus.VALIDATED)

    def test_contextual_risk_prioritization(self):
        """Test risk evaluation incorporating exposure tier, criticality, and live exploit factor."""
        finding = self.orchestrator.app_analyzer._create_finding(
            assessment_id=self.assessment_id,
            asset_id=self.asset_id,
            title="Critical Remote Code Execution",
            category=FindingCategory.INJECTION,
            severity=Severity.CRITICAL,
            cwe_id="CWE-94",
            component_ref="core.py",
            location_ref="Line 10",
            evidence={}
        )
        self.repo.save_finding(finding)
        fid = finding.finding_id

        risk = self.orchestrator.risk_prioritizer.evaluate_finding_risk(
            finding_id=fid,
            is_known_exploited=True,
            compensating_controls_active=False
        )
        self.assertEqual(risk.priority_level, PriorityLevel.P0_IMMEDIATE)
        self.assertGreaterEqual(risk.contextual_risk_score, 80.0)

    def test_remediation_planning_and_fix_verification(self):
        """Test remediation plan synthesis and fix verification with zero regressions."""
        finding = self.orchestrator.app_analyzer._create_finding(
            assessment_id=self.assessment_id,
            asset_id=self.asset_id,
            title="Vulnerable requests dependency",
            category=FindingCategory.VULN_DEPENDENCY,
            severity=Severity.MEDIUM,
            cwe_id="CWE-200",
            component_ref="requests==2.28.1",
            location_ref="requirements.txt",
            evidence={"package": "requests", "installed_version": "2.28.1", "fixed_version": "2.31.0"}
        )
        self.repo.save_finding(finding)
        fid = finding.finding_id

        # 1. Generate Plan
        plan = self.orchestrator.remediation_planner.generate_plan_for_finding(fid)
        self.assertEqual(plan.recommended_action, "UPGRADE_DEPENDENCY")
        self.assertIsNotNone(plan.patch_diff)

        # 2. Verify fix with regression (fails)
        verif_reg = self.orchestrator.regression_monitor.verify_fix_with_evidence(
            finding_id=fid,
            plan_id=plan.plan_id,
            recheck_probe_fn=lambda: True,
            regressions_detected=1
        )
        self.assertFalse(verif_reg.is_fully_resolved)
        self.assertNotEqual(self.repo.get_finding(fid).status, FindingStatus.RESOLVED)

        # 3. Verify fix cleanly (passes)
        verif_clean = self.orchestrator.regression_monitor.verify_fix_with_evidence(
            finding_id=fid,
            plan_id=plan.plan_id,
            recheck_probe_fn=lambda: True,
            regressions_detected=0
        )
        self.assertTrue(verif_clean.is_fully_resolved)
        self.assertEqual(self.repo.get_finding(fid).status, FindingStatus.RESOLVED)


if __name__ == "__main__":
    unittest.main()
