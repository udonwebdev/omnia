"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
End-to-End Comprehensive Lifecycle Test - test_app_security_e2e_module46.py

Executes a complete 14-step end-to-end security drill:
1. Register target application asset with MISSION_CRITICAL asset tier and PUBLIC exposure.
2. Issue security testing authorization with strict scope and allowed techniques.
3. Validate strict zero-trust boundary by verifying rejection of out-of-scope targets.
4. Execute AST code analysis identifying SQL and command injections.
5. Execute Secret Exposure detection with mandatory redaction and SHA-256 evidence hashing.
6. Execute API surface security analysis (unauthenticated sensitive endpoints, wildcard CORS).
7. Execute dependency vulnerability correlation.
8. Ingest external threat intelligence advisories (CISA KEV, CVE CVSS).
9. Safely validate findings non-destructively to confirm real vulnerabilities.
10. Evaluate contextual risk prioritization factoring in asset exposure, criticality, and live exploitation.
11. Synthesize multi-hop attack paths spanning trust boundaries.
12. Formulate actionable remediation plans with code patch diffs.
13. Execute fix verification and prove regression prevention.
14. Exercise emergency kill switch and verify immediate fail-closed protection.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from app_security.models import (
    AssetType,
    Criticality,
    EnvironmentTier,
    ExposureTier,
    FindingCategory,
    FindingStatus,
    PriorityLevel,
    SecurityAsset,
    SecurityAssessment,
    Severity,
    ValidationOutcome,
)
from app_security.persistence import AppSecurityRepository
from app_security.service import AppSecurityOrchestrator
from app_security.authorization_registry import ScopeViolationError
from persistence.migrations import MIGRATION_V31


class TestModule46AppSecurityE2E(unittest.TestCase):
    """Full lifecycle integration tests for Module 46."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

        conn = sqlite3.connect(self.db_path)
        conn.executescript(MIGRATION_V31)
        conn.commit()
        conn.close()

        self.orchestrator = AppSecurityOrchestrator(db_path=self.db_path)
        self.repo = self.orchestrator.repo

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except OSError:
                pass

    def test_complete_security_testing_and_validation_lifecycle(self):
        """Execute the complete 14-step autonomous defensive validation lifecycle."""
        # --- Step 1: Register Target Asset ---
        asset = self.orchestrator.register_authorized_asset(
            name="Fintech Payment Gateway Core",
            asset_type=AssetType.SERVICE,
            owner="fintech-ops",
            environment=EnvironmentTier.STAGING,
            exposure_tier=ExposureTier.PUBLIC,
            criticality=Criticality.MISSION_CRITICAL,
            technology_stack=["python", "fastapi", "postgresql"]
        )
        self.assertIsNotNone(asset)
        self.assertEqual(asset.criticality, Criticality.MISSION_CRITICAL)
        self.assertEqual(asset.exposure_tier, ExposureTier.PUBLIC)

        # --- Step 2: Issue Security Testing Authorization ---
        valid_until_iso = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        auth = self.orchestrator.create_assessment_authorization(
            name="Fintech Drill 2026",
            operator="lead-security-auditor",
            owner_approval_ref="M20-CHIEF-SEC-OFFICER-APPROVED",
            assessment_purpose="Mandatory automated vulnerability evaluation",
            environment_tier=EnvironmentTier.STAGING,
            valid_until=valid_until_iso,
            permitted_techniques=["STATIC_ANALYSIS", "DEPENDENCY_SCA", "SECRET_DETECTION", "API_AUDIT", "SAFE_API_PROBE"]
        )
        self.assertIsNotNone(auth)

        # Define Scope
        self.orchestrator.auth_registry.register_scope(
            authorization_id=auth.authorization_id,
            asset_id=asset.asset_id,
            permitted_endpoints=["/api/v1/*"],
            excluded_endpoints=["/api/v1/live-settlement"],
            permitted_components=["src/*", "requirements.txt", "Dockerfile"],
            excluded_components=["src/legacy_crypto.py"]
        )

        # --- Step 3: Zero-Trust Boundary Validation ---
        # Excluded target must raise ScopeViolationError
        with self.assertRaises(ScopeViolationError):
            self.orchestrator.auth_registry.validate_target_access(
                authorization_id=auth.authorization_id,
                asset_id=asset.asset_id,
                target_endpoint_or_file="/api/v1/live-settlement",
                requested_technique="API_AUDIT"
            )

        # Disallowed technique must raise ScopeViolationError
        with self.assertRaises(ScopeViolationError):
            self.orchestrator.auth_registry.validate_target_access(
                authorization_id=auth.authorization_id,
                asset_id=asset.asset_id,
                target_endpoint_or_file="/api/v1/users",
                requested_technique="FUZZING_HIGH_LOAD"
            )

        # Valid target and technique must pass
        self.assertTrue(
            self.orchestrator.auth_registry.validate_target_access(
                authorization_id=auth.authorization_id,
                asset_id=asset.asset_id,
                target_endpoint_or_file="src/gateway.py",
                requested_technique="STATIC_ANALYSIS"
            )
        )

        # Create Assessment Run
        assessment = SecurityAssessment(
            assessment_id="asm-e2e-drill-001",
            authorization_id=auth.authorization_id,
            asset_id=asset.asset_id,
            assessment_type="COMPREHENSIVE",
            status="IN_PROGRESS"
        )
        self.repo.save_assessment(assessment)

        # --- Step 4: AST Code Security Analysis ---
        vulnerable_py = """
import sqlite3, os

def query_user(user_input):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # SQL injection vulnerability
    cursor.execute(f"SELECT * FROM accounts WHERE id = '{user_input}'")
    
    # Command injection vulnerability
    os.system(f"echo Log query for {user_input} >> audit.log")
"""
        ast_findings = self.orchestrator.app_analyzer.analyze_source_code(
            assessment_id=assessment.assessment_id,
            asset_id=asset.asset_id,
            filename="src/gateway.py",
            source_code=vulnerable_py
        )
        self.assertEqual(len(ast_findings), 2)
        sqli_finding = next(f for f in ast_findings if f.cwe_id == "CWE-89")
        self.assertEqual(sqli_finding.severity, Severity.HIGH)

        # --- Step 5: Secret Exposure Detection & Redaction ---
        config_with_secrets = """
DATABASE_URL = "postgresql://dbuser:production_super_secret_master_pw@db.omnia.internal:5432/core"
AWS_SECRET_KEY = "AKIA1234567890EXAMPLE"
"""
        secret_findings = self.orchestrator.secret_detector.scan_content_for_secrets(
            assessment_id=assessment.assessment_id,
            asset_id=asset.asset_id,
            filename="src/config.py",
            content=config_with_secrets
        )
        self.assertGreaterEqual(len(secret_findings), 1)
        for sf in secret_findings:
            sample = sf.evidence_redacted["masked_sample"]
            self.assertIn("*", sample)
            self.assertNotIn("production_super_secret_master_pw", sample)
            self.assertIn("secret_sha256", sf.evidence_redacted)

        # --- Step 6: REST API Surface Auditing ---
        api_findings = []
        # Test sensitive endpoint without auth
        f1 = self.orchestrator.api_analyzer.audit_api_endpoint_spec(
            assessment_id=assessment.assessment_id,
            asset_id=asset.asset_id,
            endpoint_path="/api/v1/users/export",
            method="POST",
            spec_metadata={"requires_auth": False, "rate_limiting_enabled": False}
        )
        api_findings.extend(f1)
        # Test CORS wildcard with credentials
        f2 = self.orchestrator.api_analyzer.audit_api_endpoint_spec(
            assessment_id=assessment.assessment_id,
            asset_id=asset.asset_id,
            endpoint_path="/api/v1/auth/token",
            method="POST",
            spec_metadata={"requires_auth": True, "cors": {"allow_origin": "*", "allow_credentials": True}}
        )
        api_findings.extend(f2)
        self.assertGreaterEqual(len(api_findings), 2)

        # --- Step 7: Dependency Vulnerability Correlation ---
        reqs = "requests==2.28.1\nurllib3==1.26.5\n"
        dep_findings = self.orchestrator.dep_analyzer.analyze_requirements_txt(
            assessment_id=assessment.assessment_id,
            asset_id=asset.asset_id,
            requirements_content=reqs
        )
        self.assertGreaterEqual(len(dep_findings), 2)

        # --- Step 8: Vulnerability Intelligence Feed Ingestion ---
        vsource = self.orchestrator.vulnerability_intel.register_advisory_source("NVD", "https://nvd.nist.gov")
        vuln_rec = self.orchestrator.vulnerability_intel.ingest_vulnerability_record(
            vulnerability_id="CVE-2023-32681",
            source_id=vsource.source_id,
            title="Requests Unintended Leak of Proxy-Authorization Header",
            description="Requests redirects leak credentials to third-party endpoints",
            severity=Severity.HIGH,
            cvss_score=8.1,
            cwe_id="CWE-200",
            affected_package="requests",
            affected_version_ranges=["<2.31.0"],
            fixed_versions=["2.31.0"],
            is_known_exploited=True
        )
        self.assertTrue(vuln_rec.is_known_exploited)

        # --- Step 9: Safe Non-Destructive Vulnerability Validation ---
        val_result = self.orchestrator.safe_validation.validate_finding_safely(
            finding_id=sqli_finding.finding_id,
            method="SAFE_SYNTHETIC_PROBE",
            probe_runner=lambda: (ValidationOutcome.CONFIRMED, "Safe parameterized query syntax error returned without modifying records.")
        )
        self.assertEqual(val_result.outcome, ValidationOutcome.CONFIRMED)
        self.assertEqual(self.repo.get_finding(sqli_finding.finding_id).status, FindingStatus.VALIDATED)

        # --- Step 10: Contextual Risk Prioritization ---
        risk_result = self.orchestrator.risk_prioritizer.evaluate_finding_risk(
            finding_id=sqli_finding.finding_id,
            is_known_exploited=True,
            compensating_controls_active=False
        )
        self.assertEqual(risk_result.priority_level, PriorityLevel.P0_IMMEDIATE)
        self.assertGreaterEqual(risk_result.contextual_risk_score, 85.0)

        # --- Step 11: Attack Path Synthesis ---
        dep_find = dep_findings[0]
        attack_path = self.orchestrator.attack_path_analyzer.synthesize_attack_path(
            assessment_id=assessment.assessment_id,
            entry_asset_id=asset.asset_id,
            target_asset_id="asset-fintech-db",
            contributing_findings=[sqli_finding, dep_find],
            hops_description=[
                "External public request triggers SQL injection in gateway.py",
                "Crosses Trust Boundary: Gateway escalates to internal database subnet via vulnerable requests proxy"
            ]
        )
        self.assertEqual(len(attack_path.path_hops), 2)
        self.assertTrue(attack_path.path_hops[1]["trust_boundary_crossed"])

        # --- Step 12: Remediation Planning & Patch Diff Generation ---
        plan = self.orchestrator.remediation_planner.generate_plan_for_finding(sqli_finding.finding_id)
        self.assertEqual(plan.recommended_action, "PARAMETERIZE_QUERY")
        self.assertIsNotNone(plan.patch_diff)
        self.assertIn("SELECT * FROM t WHERE id = ?", plan.patch_diff)

        # --- Step 13: Fix Verification & Regression Prevention ---
        verif_failed = self.orchestrator.regression_monitor.verify_fix_with_evidence(
            finding_id=sqli_finding.finding_id,
            plan_id=plan.plan_id,
            recheck_probe_fn=lambda: True,
            regressions_detected=1
        )
        self.assertFalse(verif_failed.is_fully_resolved)
        self.assertNotEqual(self.repo.get_finding(sqli_finding.finding_id).status, FindingStatus.RESOLVED)

        verif_success = self.orchestrator.regression_monitor.verify_fix_with_evidence(
            finding_id=sqli_finding.finding_id,
            plan_id=plan.plan_id,
            recheck_probe_fn=lambda: True,
            regressions_detected=0
        )
        self.assertTrue(verif_success.is_fully_resolved)
        self.assertEqual(self.repo.get_finding(sqli_finding.finding_id).status, FindingStatus.RESOLVED)

        # --- Step 14: Emergency Kill-Switch Drill ---
        self.orchestrator.auth_registry.activate_emergency_kill_switch("sec-incident-commander", "Suspected testing anomaly")
        with self.assertRaises(ScopeViolationError) as cm:
            self.orchestrator.auth_registry.validate_target_access(
                authorization_id=auth.authorization_id,
                asset_id=asset.asset_id,
                target_endpoint_or_file="src/gateway.py",
                requested_technique="STATIC_ANALYSIS"
            )
        self.assertIn("EMERGENCY_KILL_SWITCH_ACTIVE", str(cm.exception))

        # Restore operations
        self.orchestrator.auth_registry.deactivate_emergency_kill_switch("sec-incident-commander")
        self.assertTrue(
            self.orchestrator.auth_registry.validate_target_access(
                authorization_id=auth.authorization_id,
                asset_id=asset.asset_id,
                target_endpoint_or_file="src/gateway.py",
                requested_technique="STATIC_ANALYSIS"
            )
        )


if __name__ == "__main__":
    unittest.main()
