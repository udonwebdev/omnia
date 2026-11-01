"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Unit Test Suite - test_software_delivery_module44.py

Tests:
1. Source repository registration and revision tracking.
2. Change impact analysis and categorization (Code, Test, Config, Migration, Security).
3. Pipeline planner stage tailoring based on impact report.
4. Build execution recording and status transitions.
5. Intelligent test orchestration and pass/fail metric isolation.
6. Quality gate evaluation and threshold enforcement.
7. Dependency intelligence and vulnerability detection.
8. Security gate SAST & secret scanning with severity blocking.
9. Artifact integrity check and SLSA provenance attestation.
10. Autonomous repair coordinator retry bounds (preventing infinite loops).
11. Release candidate promotion and Module 20 human approval token gate.
12. Module 43 deployment handoff bridge.
"""

import os
import sqlite3
import unittest
import uuid
from typing import Dict, Any

from persistence.migrations import MIGRATION_V29
from software_delivery.models import (
    BuildStatus,
    ChangeCategory,
    GateStatus,
    HandoffStatus,
    PipelineStageType,
    PipelineStatus,
    ReleaseStage,
    RepositoryType,
    TestStatus,
)
from software_delivery.persistence import SoftwareDeliveryRepository
from software_delivery.source_analyzer import SourceAnalyzer
from software_delivery.change_impact import ChangeImpactEngine
from software_delivery.pipeline_planner import PipelinePlanner
from software_delivery.build_engine import BuildEngine
from software_delivery.test_orchestrator import TestOrchestrator
from software_delivery.quality_gate import QualityGateEngine
from software_delivery.dependency_intel import DependencyIntelligenceEngine
from software_delivery.security_gate import SecurityGateEngine
from software_delivery.artifact_manager import ArtifactManager
from software_delivery.provenance import ProvenanceEngine
from software_delivery.regression import RegressionDetector
from software_delivery.repair_coordinator import RepairCoordinator
from software_delivery.release_manager import ReleaseManager
from software_delivery.handoff import DeploymentHandoffBridge


class TestSoftwareDeliveryModule44(unittest.TestCase):
    def setUp(self):
        self.test_db = f"test_delivery_{uuid.uuid4().hex[:8]}.db"
        conn = sqlite3.connect(self.test_db)
        conn.executescript(MIGRATION_V29)
        conn.close()

        self.repo = SoftwareDeliveryRepository(self.test_db)
        self.source_analyzer = SourceAnalyzer(self.repo)
        self.change_impact = ChangeImpactEngine(self.repo, self.source_analyzer)
        self.pipeline_planner = PipelinePlanner(self.repo)
        self.build_engine = BuildEngine(self.repo)
        self.test_orchestrator = TestOrchestrator(self.repo)
        self.quality_gate = QualityGateEngine(self.repo)
        self.dependency_intel = DependencyIntelligenceEngine(self.repo)
        self.security_gate = SecurityGateEngine(self.repo)
        self.artifact_manager = ArtifactManager(self.repo)
        self.provenance = ProvenanceEngine(self.repo)
        self.regression = RegressionDetector(self.repo)
        self.repair = RepairCoordinator(self.repo)
        self.release_manager = ReleaseManager(self.repo)
        self.handoff_bridge = DeploymentHandoffBridge(self.repo, None)

    def tearDown(self):
        try:
            if hasattr(self, "test_db") and os.path.exists(self.test_db):
                os.remove(self.test_db)
        except Exception:
            pass

    def test_repository_registration_and_revision(self):
        """Test repository registration and revision recording."""
        repo = self.source_analyzer.register_repository(
            name="core-service",
            clone_url="git@github.com:omnia/core.git",
            provider_type=RepositoryType.GITHUB,
        )
        self.assertEqual(repo.name, "core-service")
        self.assertTrue(repo.is_active)

        rev = self.source_analyzer.record_revision(
            repository_id=repo.repository_id,
            commit_hash="a1b2c3d4e5f6",
            branch="main",
            author="LO",
            commit_message="Feat: new feature",
        )
        self.assertEqual(rev.commit_hash, "a1b2c3d4e5f6")
        fetched = self.repo.get_revision(rev.revision_id)
        self.assertIsNotNone(fetched)

    def test_change_impact_and_categorization(self):
        """Test change categorization and architectural module impact analysis."""
        repo = self.source_analyzer.register_repository("app", "git@github.com:omnia/app.git")
        rev = self.source_analyzer.record_revision(repo.repository_id, "11223344", "main", "LO", "commit")

        impact = self.change_impact.analyze_changes(
            revision_id=rev.revision_id,
            changed_files=[
                "persistence/migrations.py",
                "auth/security_tokens.py",
                "requirements.txt",
                "tests/test_auth.py",
            ],
        )
        self.assertTrue(impact.migration_detected)
        self.assertTrue(impact.security_sensitive)
        self.assertIn(ChangeCategory.DATABASE_MIGRATION, impact.change_categories)
        self.assertIn(ChangeCategory.SECURITY_CRITICAL, impact.change_categories)
        self.assertIn("persistence", impact.impacted_modules)
        self.assertIn("test_migrations", impact.relevant_test_suites)

    def test_pipeline_planner(self):
        """Test delivery pipeline planning based on change impact."""
        repo = self.source_analyzer.register_repository("app", "git@github.com:omnia/app.git")
        rev = self.source_analyzer.record_revision(repo.repository_id, "55667788", "main", "LO", "commit")
        impact = self.change_impact.analyze_changes(
            revision_id=rev.revision_id,
            changed_files=["core/service.py"],
        )
        plan = self.pipeline_planner.create_pipeline_plan(
            repository_id=repo.repository_id,
            name="PR-Pipeline",
            impact_report=impact,
            target_environment="TESTING",
        )
        self.assertIn(PipelineStageType.SOURCE_VALIDATION, plan.stages)
        self.assertIn(PipelineStageType.BUILD_COMPILE, plan.stages)
        self.assertIn(PipelineStageType.UNIT_TEST, plan.stages)
        self.assertIn(PipelineStageType.QUALITY_GATE, plan.stages)

    def test_build_and_test_execution(self):
        """Test controlled build execution and test runner."""
        b = self.build_engine.execute_build(
            pipeline_execution_id="exec_test_01",
            command="echo building",
            simulate=True,
        )
        self.assertEqual(b.status, BuildStatus.SUCCESS)

        t = self.test_orchestrator.run_test_suite(
            pipeline_execution_id="exec_test_01",
            suite_name="test_core",
            simulate=True,
            simulate_failure=False,
        )
        self.assertEqual(t.status, TestStatus.PASSED)
        self.assertEqual(t.passed_tests, 12)

    def test_quality_and_security_gates(self):
        """Test quality gate thresholds and security audit blocks."""
        b = self.build_engine.execute_build("exec_02", "build", simulate=True)
        t = self.test_orchestrator.run_test_suite("exec_02", "test_core", simulate=True, simulate_failure=False)

        q = self.quality_gate.evaluate_quality(
            pipeline_execution_id="exec_02",
            build_records=[b],
            test_records=[t],
            min_coverage_pct=75.0,
        )
        self.assertEqual(q.status, GateStatus.PASSED)

        # Security pass
        s_pass = self.security_gate.audit_security(
            revision_id="rev_02",
            simulate_findings=[],
        )
        self.assertTrue(s_pass.is_passing)

        # Security fail on CRITICAL
        s_fail = self.security_gate.audit_security(
            revision_id="rev_02",
            simulate_findings=[{"category": "SECRET_LEAK", "severity": "CRITICAL", "file": "aws_key.pem"}],
        )
        self.assertFalse(s_fail.is_passing)

    def test_artifact_attestation_and_provenance(self):
        """Test artifact registration, digest calculation, and SLSA provenance attestation."""
        art = self.artifact_manager.register_artifact(
            pipeline_execution_id="exec_03",
            name="service-bundle.tar.gz",
            artifact_type="TAR_GZ",
            storage_uri="s3://releases/service-bundle.tar.gz",
            checksum_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        self.assertEqual(art.name, "service-bundle.tar.gz")
        self.assertTrue(self.artifact_manager.verify_artifact_integrity(art.artifact_id, art.checksum_sha256))

        att = self.provenance.generate_attestation(
            artifact_id=art.artifact_id,
            source_repository="git@github.com:omnia/core.git",
            source_commit="commit_12345",
        )
        self.assertEqual(att.artifact_id, art.artifact_id)
        self.assertEqual(att.predicate_type, "https://slsa.dev/provenance/v1")

    def test_repair_coordinator_and_retry_limit(self):
        """Test autonomous repair formulation and strict retry limits."""
        # Attempt 1 should succeed
        rep1 = self.repair.propose_and_apply_repair(
            pipeline_execution_id="exec_04",
            failure_type="AssertionError",
            error_context="Expected 200, got 500",
            retry_count=1,
            max_retries_allowed=3,
        )
        self.assertTrue(rep1.applied)

        # Attempt exceeding max retries must fail closed
        with self.assertRaises(RuntimeError):
            self.repair.propose_and_apply_repair(
                pipeline_execution_id="exec_04",
                failure_type="AssertionError",
                error_context="Expected 200, got 500",
                retry_count=4,
                max_retries_allowed=3,
            )

    def test_release_promotion_and_handoff(self):
        """Test release candidate promotion and deployment handoff."""
        art = self.artifact_manager.register_artifact(
            pipeline_execution_id="exec_05",
            name="app.wheel",
            artifact_type="WHEEL",
            storage_uri="s3://artifacts/app.whl",
        )
        rc = self.release_manager.create_release_candidate(
            version="1.2.0",
            artifact_id=art.artifact_id,
            source_revision_id="rev_05",
            release_notes="Version 1.2.0 release",
        )
        self.assertEqual(rc.stage, ReleaseStage.CANDIDATE)

        # Invariant: Promoting to PROMOTED / PRODUCTION requires Module 20 token
        with self.assertRaises(PermissionError):
            self.release_manager.promote_release(
                candidate_id=rc.candidate_id,
                target_stage=ReleaseStage.PROMOTED,
                approval_token=None,
            )

        # Promote with Module 20 approval token
        promoted = self.release_manager.promote_release(
            candidate_id=rc.candidate_id,
            target_stage=ReleaseStage.PROMOTED,
            approval_token="OMNIA_M20_APPROVAL_RELEASE_01",
            approver="LO",
        )
        self.assertEqual(promoted.stage, ReleaseStage.PROMOTED)

        # Deployment handoff
        handoff = self.handoff_bridge.request_deployment_handoff(
            release_candidate_id=promoted.candidate_id,
            target_environment_id="env_staging",
            deployment_strategy="DIRECT",
        )
        self.assertIn(handoff.status, (HandoffStatus.VERIFIED, HandoffStatus.ACCEPTED))


if __name__ == "__main__":
    unittest.main()
