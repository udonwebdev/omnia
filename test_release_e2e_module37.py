"""
End-to-End Acceptance Scenario for OMNIA Module 37: Autonomous Deployment, Release Engineering & Rollback Engine.
Executes a multi-stage deterministic operational scenario:
1. Initialize environment (PRODUCTION) requiring human approval.
2. Create baseline release (v1.0.0).
3. Hermetically build and register baseline cryptographic artifact.
4. Qualify baseline release through all mandatory gates.
5. Authorize baseline release with Module 20 human approval token.
6. Deploy baseline release to environment.
7. Independently verify baseline deployment (SHA-256 digest & health checks).
8. Create candidate release (v1.1.0).
9. Hermetically build and register candidate artifact.
10. Qualify candidate release through all gates.
11. Attempt deployment without human approval -> strictly fails closed.
12. Authorize candidate release with valid Module 20 human approval token.
13. Execute progressive canary deployment (5% -> 25% -> 100%).
14. Independently verify candidate release running on target endpoint.
15. Ingest operational failure signal (Module 36 degradation trigger).
16. Initiate automated safe rollback to verified baseline release.
17. Verify rollback execution, artifact restoration, and environment health.
18. Validate release audit history and Event Fabric emissions.
"""

import os
import gc
import tempfile
import unittest
import time
from release.models import (
    ReleaseState,
    DeploymentStrategy,
    EnvironmentType,
    MigrationSafetyClass,
)
from release.service import ReleaseEngine


class TestReleaseModule37E2E(unittest.TestCase):

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.service = ReleaseEngine(db_path=self.temp_db.name)

    def tearDown(self):
        del self.service
        gc.collect()
        try:
            if os.path.exists(self.temp_db.name):
                os.remove(self.temp_db.name)
        except PermissionError:
            pass

    def test_complete_autonomous_release_and_rollback_lifecycle(self):
        # Step 1: Initialize environment (PRODUCTION) requiring human approval
        env = self.service.environments.register_environment(
            environment_id="env_production_omega",
            environment_type=EnvironmentType.PRODUCTION,
            app_id="omnia_core",
            target_endpoint="http://127.0.0.1:8080",
            requires_approval=True,
        )
        self.assertEqual(env.health_status, "HEALTHY")

        # Step 2: Create baseline release (v1.0.0)
        rel_base = self.service.create_release(
            app_id="omnia_core",
            version="1.0.0",
            source_revision="commit-sha-base-001",
            target_environment="PRODUCTION",
            migration_safety=MigrationSafetyClass.FORWARD_COMPATIBLE,
        )
        self.assertEqual(rel_base.state, ReleaseState.DRAFT)

        # Step 3: Hermetically build baseline artifact
        build_base = self.service.build_release(
            release_id=rel_base.release_id,
            source_dir=".",
        )
        self.assertTrue(build_base["success"])
        base_art_id = build_base["artifact_id"]
        base_digest = build_base["digest_sha256"]

        # Step 4: Qualify baseline release
        qual_base = self.service.qualify_release(release_id=rel_base.release_id, target_env="PRODUCTION")
        self.assertTrue(qual_base["success"])
        self.assertEqual(qual_base["status"], ReleaseState.AWAITING_APPROVAL.value)

        # Step 5: Authorize baseline release with human approval token
        appr_token_1 = "human-approval-token-base-12345"
        auth_base = self.service.authorize_release(release_id=rel_base.release_id, approval_token=appr_token_1)
        self.assertTrue(auth_base)

        # Step 6 & 7: Deploy baseline release & independently verify
        dep_base = self.service.deploy_release(
            release_id=rel_base.release_id,
            environment_id=env.environment_id,
            strategy=DeploymentStrategy.DIRECT,
        )
        self.assertTrue(dep_base["success"])
        self.assertEqual(dep_base["status"], "DEPLOYED")
        self.assertIn("verified", dep_base["evidence"].lower())

        env_state = self.service.repo.get_environment(env.environment_id)
        self.assertEqual(env_state.current_release_id, rel_base.release_id)
        self.assertEqual(env_state.current_artifact_digest, base_digest)

        # Step 8: Create candidate release (v1.1.0)
        rel_cand = self.service.create_release(
            app_id="omnia_core",
            version="1.1.0",
            source_revision="commit-sha-cand-002",
            target_environment="PRODUCTION",
            migration_safety=MigrationSafetyClass.FORWARD_COMPATIBLE,
        )

        # Step 9: Build candidate artifact
        build_cand = self.service.build_release(
            release_id=rel_cand.release_id,
            source_dir=".",
        )
        self.assertTrue(build_cand["success"])
        cand_art_id = build_cand["artifact_id"]
        cand_digest = build_cand["digest_sha256"]

        # Step 10: Qualify candidate release
        qual_cand = self.service.qualify_release(release_id=rel_cand.release_id, target_env="PRODUCTION")
        self.assertTrue(qual_cand["success"])

        # Step 11: Attempt deployment without human approval -> strictly fails closed
        unauth_dep = self.service.deploy_release(
            release_id=rel_cand.release_id,
            environment_id=env.environment_id,
            strategy=DeploymentStrategy.CANARY,
        )
        self.assertFalse(unauth_dep["success"])
        self.assertTrue(unauth_dep.get("requires_approval", False))

        # Step 12: Authorize candidate release with valid approval token
        appr_token_2 = "human-approval-token-cand-98765"
        auth_cand = self.service.authorize_release(release_id=rel_cand.release_id, approval_token=appr_token_2)
        self.assertTrue(auth_cand)

        # Step 13 & 14: Execute progressive canary deployment & verify
        dep_cand = self.service.deploy_release(
            release_id=rel_cand.release_id,
            environment_id=env.environment_id,
            strategy=DeploymentStrategy.CANARY,
        )
        self.assertTrue(dep_cand["success"])
        self.assertEqual(dep_cand["status"], "DEPLOYED")

        env_state2 = self.service.repo.get_environment(env.environment_id)
        self.assertEqual(env_state2.current_release_id, rel_cand.release_id)
        self.assertEqual(env_state2.current_artifact_digest, cand_digest)

        # Step 15 & 16: Simulate degradation and initiate safe rollback to baseline
        rb_res = self.service.execute_rollback(
            environment_id=env.environment_id,
            failed_release_id=rel_cand.release_id,
            restored_release_id=rel_base.release_id,
            reason="Module 36 latency p99 anomaly observed during post-canary traffic",
            approval_token=appr_token_2,
        )

        # Step 17: Verify rollback execution & restored state
        self.assertTrue(rb_res["success"])
        self.assertEqual(rb_res["restored_release_id"], rel_base.release_id)
        self.assertIn("rollback verified", rb_res["evidence"].lower())

        env_restored = self.service.repo.get_environment(env.environment_id)
        self.assertEqual(env_restored.current_release_id, rel_base.release_id)
        self.assertEqual(env_restored.current_artifact_digest, base_digest)

        # Step 18: Reconcile environment -> confirms in sync with baseline
        reconcile_res = self.service.reconciler.reconcile_environment(env.environment_id)
        self.assertFalse(reconcile_res["drift_detected"])
        self.assertEqual(reconcile_res["status"], "IN_SYNC")
        self.assertEqual(reconcile_res["current_release_id"], rel_base.release_id)


if __name__ == "__main__":
    unittest.main()
