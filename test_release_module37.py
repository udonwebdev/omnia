"""
Unit and safety tests for OMNIA Module 37: Autonomous Deployment, Release Engineering & Rollback Engine.
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
    QualificationGateStatus,
)
from release.service import ReleaseEngine


class TestReleaseModule37(unittest.TestCase):

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

    def test_release_lifecycle_state_machine(self):
        """Verifies state machine enforces legal transitions and rejects invalid state jumps."""
        rel = self.service.create_release(
            app_id="app_core",
            version="1.0.0",
            source_revision="git-commit-abc1234",
            description="Test release lifecycle",
        )
        self.assertEqual(rel.state, ReleaseState.DRAFT)

        # Illegal jump: DRAFT -> DEPLOYED should raise ValueError
        with self.assertRaises(ValueError):
            rel.transition_to(ReleaseState.DEPLOYED)

        # Valid transition: DRAFT -> PREPARING
        rel.transition_to(ReleaseState.PREPARING)
        self.assertEqual(rel.state, ReleaseState.PREPARING)

    def test_artifact_cryptographic_integrity_and_tampering(self):
        """Verifies artifact registration computes SHA-256 and detects tampering."""
        # Create a temp package file
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".pkg")
        tf.write(b"SAMPLE_COMPILED_BYTECODE_CONTENT")
        tf.close()

        try:
            art = self.service.artifacts.register_artifact(
                artifact_id="art-test-1",
                app_id="app_core",
                version="1.0.0",
                source_revision="rev-1",
                build_id="bld-1",
                file_path=tf.name,
            )
            self.assertTrue(art.is_tamper_verified)

            # Verification passes on unmodified artifact
            verify_res = self.service.artifacts.verify_artifact_integrity("art-test-1")
            self.assertTrue(verify_res["verified"])
            self.assertEqual(verify_res["digest_sha256"], art.digest_sha256)

            # Tamper with file
            with open(art.storage_uri, "ab") as f:
                f.write(b"_TAMPERED_MALICIOUS_BYTES")

            tamper_res = self.service.artifacts.verify_artifact_integrity("art-test-1")
            self.assertFalse(tamper_res["verified"])
            self.assertIn("mismatch", tamper_res["error"].lower())

        finally:
            if os.path.exists(tf.name):
                os.remove(tf.name)

    def test_qualification_gates_block_on_mandatory_failure(self):
        """Verifies mandatory gate failures transition release to QUALIFICATION_FAILED."""
        rel = self.service.create_release(
            app_id="app_core",
            version="1.1.0",
            source_revision="rev-2",
        )
        # Create mock artifact
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".pkg")
        tf.write(b"SAFE_CONTENT")
        tf.close()
        try:
            art = self.service.artifacts.register_artifact(
                artifact_id="art-test-2",
                app_id="app_core",
                version="1.1.0",
                source_revision="rev-2",
                build_id="bld-2",
                file_path=tf.name,
            )
            rel.artifact_id = art.artifact_id
            rel.transition_to(ReleaseState.PREPARING)
            rel.transition_to(ReleaseState.BUILDING)
            rel.transition_to(ReleaseState.ARTIFACT_READY)
            self.service.repo.save_release(rel)

            # Qualify with a simulated unit test failure
            q_res = self.service.qualify_release(
                release_id=rel.release_id,
                custom_checks={"unit_tests": False, "security_tests": True},
            )
            self.assertFalse(q_res["success"])
            self.assertEqual(q_res["status"], "QUALIFICATION_FAILED")

            updated_rel = self.service.repo.get_release(rel.release_id)
            self.assertEqual(updated_rel.state, ReleaseState.QUALIFICATION_FAILED)

        finally:
            if os.path.exists(tf.name):
                os.remove(tf.name)

    def test_database_migration_safety_blocks_irreversible_rollback(self):
        """Verifies automatic rollback is blocked if the failed release contains IRREVERSIBLE schema changes."""
        rel_failed = self.service.create_release(
            app_id="app_core",
            version="2.0.0",
            source_revision="rev-3",
            migration_safety=MigrationSafetyClass.IRREVERSIBLE,
        )
        rel_restored = self.service.create_release(
            app_id="app_core",
            version="1.9.0",
            source_revision="rev-1",
            migration_safety=MigrationSafetyClass.REVERSIBLE,
        )
        env = self.service.environments.register_environment(
            environment_id="env_prod",
            environment_type=EnvironmentType.PRODUCTION,
            app_id="app_core",
        )

        res = self.service.execute_rollback(
            environment_id="env_prod",
            failed_release_id=rel_failed.release_id,
            restored_release_id=rel_restored.release_id,
            reason="High error rate post-deployment",
        )
        self.assertFalse(res["success"])
        self.assertTrue(res.get("requires_intervention", False))
        self.assertIn("irreversible", res["error"].lower())


if __name__ == "__main__":
    unittest.main()
