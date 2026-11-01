"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
End-to-End Test Suite - test_software_delivery_e2e_module44.py

Tests the 18-step full operational delivery lifecycle drill:
1. Register source repository (Local / Git VCS).
2. Detect and record source revision and commit metadata.
3. Analyze changed files across modules, tests, config, and migration layers.
4. Generate traceable Change Impact Report with confidence scoring.
5. Plan tailored Delivery Pipeline matching detected components.
6. Start controlled pipeline execution.
7. Execute compilation and build inside isolated sandbox.
8. Execute selected unit and integration test suites.
9. Evaluate Software Quality Gate (pass rate, code coverage, zero unverified assumptions).
10. Execute Security Gate (secret detection and SAST audit).
11. Perform Dependency Intelligence assessment (vulnerabilities and drift).
12. Register built artifact and compute cryptographic SHA-256 digest.
13. Generate SLSA v1 provenance attestation linking commit, builder, and artifact.
14. Create Release Candidate (v1.0.0) with generated release notes.
15. Enforce Module 20 human approval token gate for production promotion.
16. Promote Release Candidate to QUALIFIED/PROMOTED.
17. Transfer deployment handoff to Module 43 (Autonomous Infrastructure Lifecycle).
18. Verify deployment callback evidence and transition Release Candidate to DEPLOYED.
"""

import os
import sqlite3
import unittest
import uuid
from typing import Any, Dict

from persistence.migrations import MIGRATION_V28, MIGRATION_V29
from software_delivery.models import (
    GateStatus,
    HandoffStatus,
    PipelineStatus,
    ReleaseStage,
    RepositoryType,
)
from software_delivery.persistence import SoftwareDeliveryRepository
from software_delivery.service import SoftwareDeliveryOrchestrator
from infrastructure_lifecycle.persistence import InfrastructureRepository
from infrastructure_lifecycle.service import InfrastructureLifecycleOrchestrator
from infrastructure_lifecycle.models import EnvironmentType, EnvironmentLifecycleState


class TestSoftwareDeliveryE2EModule44(unittest.TestCase):
    def setUp(self):
        self.test_db = f"test_delivery_e2e_{uuid.uuid4().hex[:8]}.db"
        conn = sqlite3.connect(self.test_db)
        conn.executescript(MIGRATION_V28)
        conn.executescript(MIGRATION_V29)
        conn.close()

        self.infra_repo = InfrastructureRepository(self.test_db)
        self.infra_service = InfrastructureLifecycleOrchestrator(repository=self.infra_repo)

        self.delivery_repo = SoftwareDeliveryRepository(self.test_db)
        self.service = SoftwareDeliveryOrchestrator(
            repository=self.delivery_repo,
            infrastructure_service=self.infra_service,
        )

    def tearDown(self):
        try:
            if hasattr(self, "test_db") and os.path.exists(self.test_db):
                os.remove(self.test_db)
        except Exception:
            pass

    def test_complete_software_delivery_lifecycle_drill(self):
        # Step 1: Register Source Repository
        repo = self.service.register_repository(
            name="omnia-core-engine",
            clone_url="git@github.com:omnia/core-engine.git",
            provider_type=RepositoryType.GIT_LOCAL,
        )
        self.assertEqual(repo.name, "omnia-core-engine")

        # Step 2 & 3: Detect Source Revision & Analyze Changed Files
        rev, impact = self.service.analyze_source_revision(
            repository_id=repo.repository_id,
            commit_hash="f0e1d2c3b4a5",
            branch="main",
            author="LO <author@omnia.org>",
            commit_message="feat(core): implement high-throughput stream batcher",
            changed_files=[
                "core/batcher.py",
                "core/config.yaml",
                "tests/test_batcher.py",
            ],
        )
        self.assertEqual(rev.commit_hash, "f0e1d2c3b4a5")

        # Step 4: Verify Change Impact Report
        self.assertIn("core", impact.impacted_modules)
        self.assertIn("test_core", impact.relevant_test_suites)
        self.assertEqual(impact.confidence_score, 0.95)

        # Step 5: Plan Tailored Delivery Pipeline
        pipe_def = self.service.plan_delivery_pipeline(
            repository_id=repo.repository_id,
            pipeline_name="Production-Delivery-Pipeline",
            impact_report=impact,
            target_environment="STAGING",
        )
        self.assertGreaterEqual(len(pipe_def.stages), 5)

        # Step 6, 7, 8: Execute Delivery Pipeline (Build, Test, Evaluate)
        pe, q_gate, sec = self.service.execute_pipeline(
            pipeline_id=pipe_def.pipeline_id,
            revision_id=rev.revision_id,
            simulate=True,
        )
        self.assertEqual(pe.status, PipelineStatus.SUCCEEDED)

        # Step 9: Verify Quality Gate
        self.assertEqual(q_gate.status, GateStatus.PASSED)
        self.assertGreaterEqual(q_gate.score, 0.9)

        # Step 10: Verify Security Gate
        self.assertTrue(sec.is_passing)
        self.assertEqual(sec.secrets_found_count, 0)

        # Step 11: Dependency Intelligence Assessment
        dep_ass = self.service.dependency_intel.assess_dependencies(revision_id=rev.revision_id)
        self.assertEqual(dep_ass.vulnerabilities_detected, 0)

        # Step 12 & 13: Register Build Artifact & SLSA Provenance Attestation
        art, att = self.service.register_artifact_and_attestation(
            pipeline_execution_id=pe.execution_id,
            name="omnia-batcher-1.0.0.tar.gz",
            artifact_type="TAR_GZ",
            storage_uri="s3://omnia-releases/batcher/1.0.0.tar.gz",
            source_repository=repo.clone_url,
            source_commit=rev.commit_hash,
            checksum_sha256="4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
        )
        self.assertEqual(art.name, "omnia-batcher-1.0.0.tar.gz")
        self.assertEqual(att.builder_id, "omnia-autonomous-builder-v1")
        self.assertEqual(att.source_commit, "f0e1d2c3b4a5")

        # Step 14: Create Release Candidate
        rc = self.service.release_manager.create_release_candidate(
            version="1.0.0",
            artifact_id=art.artifact_id,
            source_revision_id=rev.revision_id,
            release_notes="Production release for high-throughput batcher",
        )
        self.assertEqual(rc.stage, ReleaseStage.CANDIDATE)

        # Step 15: Module 20 Approval Gate for Production Promotion
        with self.assertRaises(PermissionError):
            self.service.release_manager.promote_release(
                candidate_id=rc.candidate_id,
                target_stage=ReleaseStage.PROMOTED,
                approval_token=None,
            )

        # Step 16: Promote with Valid Module 20 Token
        promoted = self.service.release_manager.promote_release(
            candidate_id=rc.candidate_id,
            target_stage=ReleaseStage.PROMOTED,
            approval_token="OMNIA_M20_APPROVAL_PROD_RELEASE_9981",
            approver="LO",
        )
        self.assertEqual(promoted.stage, ReleaseStage.PROMOTED)

        # Step 17: Provision Target Environment in Module 43
        bp = self.infra_service.register_blueprint(
            blueprint_id="bp-batcher-staging",
            name="Batcher Staging Blueprint",
            version="1.0.0",
            environment_type=EnvironmentType.STAGING,
            resource_definitions=[{"name": "batcher-proc", "type": "PROCESS"}],
        )
        target_env = self.infra_service.create_environment(
            name="Staging Environment",
            environment_type=EnvironmentType.STAGING,
            provider_id="provider-local-sandbox",
            blueprint_id=bp.blueprint_id,
        )
        plan43 = self.infra_service.plan_provisioning(target_env.environment_id)
        self.infra_service.execute_provisioning(plan43.plan_id)
        self.infra_service.environments.transition_state(target_env.environment_id, EnvironmentLifecycleState.READY)

        # Step 18: Transfer Deployment Handoff to Module 43 & Verify Callback
        handoff = self.service.handoff_deployment(
            release_candidate_id=promoted.candidate_id,
            target_environment_id=target_env.environment_id,
            deployment_strategy="DIRECT",
        )
        self.assertEqual(handoff.status, HandoffStatus.VERIFIED)
        self.assertIsNotNone(handoff.module43_deployment_id)
        self.assertTrue(handoff.verification_evidence.get("is_fully_verified"))

        # Invariant: Release candidate is marked DEPLOYED
        rc_final = self.delivery_repo.get_release_candidate(promoted.candidate_id)
        self.assertEqual(rc_final.stage, ReleaseStage.DEPLOYED)


if __name__ == "__main__":
    unittest.main()
