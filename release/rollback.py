"""
OMNIA Module 37: Rollback Engine & Database Migration Safety
Performs controlled, safe rollbacks to the last verified healthy release.
Strictly classifies database migration safety and blocks destructive operations.
"""

import time
import uuid
import logging
from typing import Dict, Any, Optional
from release.models import (
    RollbackRecord,
    ReleaseRecord,
    ReleaseState,
    MigrationSafetyClass,
)
from release.adapters import DeploymentAdapter
from release.artifacts import ArtifactManager
from release.persistence import ReleaseRepository

logger = logging.getLogger("Omnia.Release.Rollback")


class RollbackEngine:
    """Coordinates safe release rollbacks with database safety boundaries."""

    def __init__(
        self,
        repo: ReleaseRepository,
        adapter: DeploymentAdapter,
        artifacts: ArtifactManager,
    ):
        self.repo = repo
        self.adapter = adapter
        self.artifacts = artifacts

    def execute_rollback(
        self,
        environment_id: str,
        failed_release_id: str,
        restored_release_id: str,
        reason: str,
        approval_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes controlled rollback:
        1. Validates migration safety (Blocks IRREVERSIBLE without manual intervention).
        2. Cryptographically verifies restored artifact integrity.
        3. Invokes provider rollback.
        4. Verifies post-rollback health before transitioning to ROLLED_BACK.
        """
        failed_rel = self.repo.get_release(failed_release_id)
        restored_rel = self.repo.get_release(restored_release_id)
        env = self.repo.get_environment(environment_id)

        if not failed_rel or not restored_rel or not env:
            return {"success": False, "error": "Invalid release or environment reference for rollback"}

        # Database safety check:
        # Never automatically rollback if migration was irreversible
        if failed_rel.migration_safety == MigrationSafetyClass.IRREVERSIBLE:
            logger.critical(f"AUTOMATIC ROLLBACK BLOCKED: Release {failed_release_id} has IRREVERSIBLE database migrations!")
            return {
                "success": False,
                "error": "Automatic rollback blocked: Release contains IRREVERSIBLE database migration. Requires manual database remediation.",
                "requires_intervention": True,
            }

        # Verify restored artifact integrity
        if not restored_rel.artifact_id:
            return {"success": False, "error": f"Restored release '{restored_release_id}' has no associated artifact"}

        art_check = self.artifacts.verify_artifact_integrity(restored_rel.artifact_id)
        if not art_check.get("verified", False):
            return {"success": False, "error": f"Restored artifact corrupted or missing: {art_check.get('error')}"}

        restored_art = self.repo.get_artifact(restored_rel.artifact_id)

        # Record rollback plan
        rb_id = f"rb-{uuid.uuid4().hex[:8]}"
        rollback_record = RollbackRecord(
            rollback_id=rb_id,
            failed_release_id=failed_release_id,
            restored_release_id=restored_release_id,
            environment_id=environment_id,
            reason=reason,
            migration_safety=failed_rel.migration_safety,
            status="IN_PROGRESS",
            approval_token=approval_token,
            created_at=time.time(),
        )
        self.repo.save_rollback(rollback_record)

        try:
            if failed_rel.state in (ReleaseState.DEPLOYED, ReleaseState.DEGRADED, ReleaseState.FAILED):
                failed_rel.transition_to(ReleaseState.ROLLBACK_PENDING, actor="RollbackEngine", reason=f"Rollback initiated: {reason}")
            failed_rel.transition_to(ReleaseState.ROLLING_BACK, actor="RollbackEngine", reason=f"Rollback to {restored_release_id}: {reason}")
            self.repo.save_release(failed_rel)

            # Provider rollback
            prov_res = self.adapter.rollback_to(
                target_endpoint=env.target_endpoint,
                previous_artifact_uri=restored_art.storage_uri,
                expected_digest=restored_art.digest_sha256,
            )
            if not prov_res.get("success", False):
                raise RuntimeError(f"Provider rollback execution failed: {prov_res.get('error')}")

            # Independent post-rollback verification
            actual = self.adapter.inspect_actual_state(env.target_endpoint)
            if actual.get("digest_sha256") != restored_art.digest_sha256:
                raise RuntimeError("Post-rollback digest verification failed")

            evidence = f"Rollback verified: Environment {environment_id} successfully restored to release {restored_release_id} (SHA-256 {restored_art.digest_sha256[:16]})"
            rollback_record.status = "SUCCEEDED"
            rollback_record.verification_evidence = evidence
            rollback_record.completed_at = time.time()
            self.repo.save_rollback(rollback_record)

            failed_rel.transition_to(ReleaseState.ROLLED_BACK, actor="RollbackEngine", reason=evidence)
            self.repo.save_release(failed_rel)

            env.current_release_id = restored_release_id
            env.current_artifact_digest = restored_art.digest_sha256
            env.last_verified_at = time.time()
            self.repo.save_environment(env)

            logger.info(f"Rollback {rb_id} SUCCEEDED: {evidence}")
            return {
                "success": True,
                "rollback_id": rb_id,
                "evidence": evidence,
                "restored_release_id": restored_release_id,
            }

        except Exception as e:
            rollback_record.status = "FAILED"
            rollback_record.error_message = str(e)
            self.repo.save_rollback(rollback_record)
            failed_rel.transition_to(ReleaseState.REQUIRES_INTERVENTION, actor="RollbackEngine", reason=f"Rollback failure: {e}")
            self.repo.save_release(failed_rel)
            logger.error(f"Rollback {rb_id} FAILED: {e}")
            return {"success": False, "error": str(e), "requires_intervention": True}
