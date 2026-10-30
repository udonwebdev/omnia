"""
OMNIA Module 37: Master Release Engine & Event Fabric Integration
Unified facade for building, qualifying, packaging, deploying, monitoring,
verifying, and safely rolling back authorized software releases.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional
from release.models import (
    ReleaseRecord,
    ArtifactRecord,
    EnvironmentRecord,
    DeploymentRecord,
    RollbackRecord,
    ReleaseState,
    DeploymentStrategy,
    EnvironmentType,
    MigrationSafetyClass,
)
from release.persistence import ReleaseRepository
from release.artifacts import ArtifactManager
from release.build import BuildOrchestrator
from release.qualification import ReleaseQualifier
from release.environments import EnvironmentManager
from release.adapters import LocalProcessAdapter
from release.rollout import RolloutController
from release.verification import DeploymentVerifier
from release.rollback import RollbackEngine
from release.reconciler import ReleaseReconciler

logger = logging.getLogger("Omnia.Release.Engine")


class ReleaseEngine:
    """Master facade for autonomous software release lifecycle management."""

    def __init__(self, db_path: str = "omnia.db", event_bus: Optional[Any] = None):
        self.repo = ReleaseRepository(db_path=db_path)
        self.artifacts = ArtifactManager(self.repo)
        self.build = BuildOrchestrator(self.repo, self.artifacts)
        self.qualification = ReleaseQualifier(self.repo, self.artifacts)
        self.environments = EnvironmentManager(self.repo)
        self.adapter = LocalProcessAdapter()
        self.rollout = RolloutController(self.repo, self.adapter)
        self.verifier = DeploymentVerifier(self.repo, self.adapter)
        self.rollback = RollbackEngine(self.repo, self.adapter, self.artifacts)
        self.reconciler = ReleaseReconciler(self.repo, self.adapter)
        self.event_bus = event_bus

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publishes release events to the Omnia Event Fabric."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                from events.models import EventEnvelope
                envelope = EventEnvelope(
                    topic=topic,
                    payload=payload,
                    source="release.engine",
                )
                self.event_bus.publish(envelope)
            except Exception as e:
                logger.debug(f"Event bus emit skipped or failed: {e}")

    # Core Operations
    def create_release(
        self,
        app_id: str,
        version: str,
        source_revision: str,
        target_environment: str = "PRODUCTION",
        description: str = "",
        migration_safety: MigrationSafetyClass = MigrationSafetyClass.FORWARD_COMPATIBLE,
        created_by: str = "developer",
    ) -> ReleaseRecord:
        """Creates a new release record in DRAFT state."""
        rel_id = f"rel-{uuid.uuid4().hex[:8]}"
        record = ReleaseRecord(
            release_id=rel_id,
            app_id=app_id,
            version=version,
            source_revision=source_revision,
            state=ReleaseState.DRAFT,
            target_environment=target_environment,
            description=description,
            migration_safety=migration_safety,
            created_by=created_by,
        )
        self.repo.save_release(record)
        self._emit_event("release.created", record.to_dict())
        logger.info(f"Created release '{rel_id}' (v{version}) for app '{app_id}'")
        return record

    def build_release(self, release_id: str, source_dir: str) -> Dict[str, Any]:
        """Orchestrates build for a release."""
        res = self.build.execute_build(release_id=release_id, source_dir=source_dir)
        if res.get("success", False):
            self._emit_event("release.artifact.created", res)
        else:
            self._emit_event("release.build.failed", res)
        return res

    def qualify_release(
        self,
        release_id: str,
        target_env: str = "PRODUCTION",
        custom_checks: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        """Runs qualification gates against release."""
        res = self.qualification.qualify_release(
            release_id=release_id,
            target_env=target_env,
            custom_checks=custom_checks,
        )
        if res.get("success", False):
            self._emit_event("release.qualification.passed", res)
        else:
            self._emit_event("release.qualification.failed", res)
        return res

    def authorize_release(self, release_id: str, approval_token: str) -> bool:
        """Binds a Module 20 human approval token to a production release."""
        release = self.repo.get_release(release_id)
        if not release:
            return False
        if not approval_token or len(approval_token) < 8:
            logger.warning(f"Invalid approval token provided for release {release_id}")
            return False

        release.approval_token = approval_token
        if release.state == ReleaseState.AWAITING_APPROVAL:
            release.transition_to(ReleaseState.APPROVED, actor="ApprovalGateway", reason="Human approval granted")
        self.repo.save_release(release)
        self._emit_event("release.approval.granted", {"release_id": release_id, "token": approval_token[:8]})
        return True

    def deploy_release(
        self,
        release_id: str,
        environment_id: str,
        strategy: DeploymentStrategy = DeploymentStrategy.CANARY,
    ) -> Dict[str, Any]:
        """
        Orchestrates full deployment lifecycle:
        1. Validates environment approval policy and lease.
        2. Progressively advances rollout stages.
        3. Independently verifies actual endpoint digest and health.
        """
        release = self.repo.get_release(release_id)
        env = self.repo.get_environment(environment_id)
        if not release or not env:
            return {"success": False, "error": "Invalid release or environment ID"}

        # Enforce approval for production
        if env.requires_approval and not release.approval_token:
            return {
                "success": False,
                "error": f"Deployment blocked: Environment '{environment_id}' requires human approval token",
                "requires_approval": True,
            }

        # Validate artifact
        art = self.repo.get_artifact(release.artifact_id)
        if not art:
            return {"success": False, "error": f"Artifact '{release.artifact_id}' not found"}

        # Acquire lock
        node_id = f"node-{uuid.uuid4().hex[:6]}"
        if not self.environments.acquire_environment_lease(environment_id, node_id):
            return {"success": False, "error": f"Environment '{environment_id}' is locked by another deployment"}

        dep_id = f"dep-{uuid.uuid4().hex[:8]}"
        stages = self.rollout.initialize_stages(strategy)

        deployment = DeploymentRecord(
            deployment_id=dep_id,
            release_id=release_id,
            artifact_id=art.artifact_id,
            environment_id=environment_id,
            strategy=strategy,
            stages=[s.to_dict() for s in stages],
        )
        self.repo.save_deployment(deployment)

        release.active_deployment_id = dep_id
        if release.state == ReleaseState.APPROVED:
            release.transition_to(ReleaseState.DEPLOYMENT_QUEUED, actor="ReleaseEngine", reason=f"Queued deployment {dep_id}")
        release.transition_to(ReleaseState.DEPLOYING, actor="ReleaseEngine", reason=f"Started deployment {dep_id}")
        self.repo.save_release(release)
        self._emit_event("release.deployment.started", deployment.to_dict())

        try:
            # Advance through all rollout stages
            for _ in range(len(stages)):
                stage_res = self.rollout.advance_rollout_stage(
                    deployment_id=dep_id,
                    target_endpoint=env.target_endpoint,
                    artifact_uri=art.storage_uri,
                    expected_digest=art.digest_sha256,
                )
                if not stage_res.get("success", False):
                    raise RuntimeError(f"Rollout stage progression failed: {stage_res.get('error')}")

            # Transition to VERIFYING
            release.transition_to(ReleaseState.VERIFYING, actor="ReleaseEngine", reason="Rollout complete, initiating independent verification")
            self.repo.save_release(release)

            # Independent post-deployment verification
            verify_res = self.verifier.verify_deployment(
                deployment_id=dep_id,
                target_endpoint=env.target_endpoint,
                expected_digest=art.digest_sha256,
            )
            if not verify_res.get("verified", False):
                raise RuntimeError(f"Independent verification failed: {verify_res.get('error')}")

            # Mark DEPLOYED only after verified evidence is confirmed
            release.transition_to(ReleaseState.DEPLOYED, actor="ReleaseEngine", reason=verify_res["evidence"])
            self.repo.save_release(release)

            env.current_release_id = release_id
            env.current_artifact_digest = art.digest_sha256
            env.last_verified_at = time.time()
            self.repo.save_environment(env)

            self._emit_event("release.deployed", {"release_id": release_id, "deployment_id": dep_id})

            return {
                "success": True,
                "deployment_id": dep_id,
                "release_id": release_id,
                "status": "DEPLOYED",
                "evidence": verify_res["evidence"],
            }

        except Exception as e:
            logger.error(f"Deployment {dep_id} failed: {e}")
            release.transition_to(ReleaseState.FAILED, actor="ReleaseEngine", reason=str(e))
            self.repo.save_release(release)
            self._emit_event("release.deployment.failed", {"release_id": release_id, "error": str(e)})
            return {"success": False, "deployment_id": dep_id, "error": str(e)}

        finally:
            self.environments.release_environment_lease(environment_id, node_id)

    def execute_rollback(
        self,
        environment_id: str,
        failed_release_id: str,
        restored_release_id: str,
        reason: str,
        approval_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes safe rollback."""
        res = self.rollback.execute_rollback(
            environment_id=environment_id,
            failed_release_id=failed_release_id,
            restored_release_id=restored_release_id,
            reason=reason,
            approval_token=approval_token,
        )
        if res.get("success", False):
            self._emit_event("release.rollback.completed", res)
        else:
            self._emit_event("release.rollback.failed", res)
        return res


# Global singleton
release_engine = ReleaseEngine()
