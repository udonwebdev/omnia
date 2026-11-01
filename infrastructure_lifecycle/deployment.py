"""
OMNIA Module 43: Autonomous Infrastructure Provisioning & Environment Lifecycle Management
Deployment Engine - deployment.py
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from infrastructure_lifecycle.models import (
    DeploymentRecord,
    DeploymentState,
    DeploymentStrategy,
    EnvironmentLifecycleState,
    EnvironmentRecord,
    EnvironmentType,
    ReleaseRecord,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository

logger = logging.getLogger("Omnia.Infrastructure.Deployment")


class DeploymentOrchestrator:
    """
    Coordinates application release deployments onto provisioned infrastructure environments.
    Supports DIRECT, ROLLING, BLUE_GREEN, and CANARY deployment strategies.
    Enforces Module 20 human approval token gate for PRODUCTION environments.
    """

    def __init__(self, repository: Optional[InfrastructureRepository] = None):
        self.repo = repository or InfrastructureRepository()

    def register_release(
        self,
        application_name: str,
        version: str,
        artifact_uri: str,
        checksum_sha256: str = "sha256:0000000000",
        source_revision: str = "main@head",
        release_id: Optional[str] = None,
    ) -> ReleaseRecord:
        rel_id = release_id or f"rel-{uuid.uuid4().hex[:8]}"
        rel = ReleaseRecord(
            release_id=rel_id,
            application_name=application_name,
            version=version,
            artifact_uri=artifact_uri,
            checksum_sha256=checksum_sha256,
            source_revision=source_revision,
        )
        self.repo.save_release(rel)
        logger.info(f"Registered deployable release: {rel_id} ({application_name} v{version})")
        return rel

    def start_deployment(
        self,
        environment_id: str,
        release_id: str,
        strategy: DeploymentStrategy = DeploymentStrategy.DIRECT,
        approval_token: Optional[str] = None,
    ) -> DeploymentRecord:
        env = self.repo.get_environment(environment_id)
        if not env:
            raise KeyError(f"Environment '{environment_id}' not found.")

        # Environment must be in READY or DEGRADED state to receive deployment
        if env.current_state not in (EnvironmentLifecycleState.READY, EnvironmentLifecycleState.DEGRADED):
            raise ValueError(
                f"Cannot deploy to environment in '{env.current_state.value}' state. Must be READY or DEGRADED."
            )

        # Gate for PRODUCTION
        if env.environment_type == EnvironmentType.PRODUCTION:
            if not approval_token or not (approval_token.startswith("OMNIA_M20_") or approval_token.startswith("M20_")):
                raise PermissionError(
                    f"Production deployment requires a valid Module 20 human approval token (got '{approval_token}')"
                )

        rel = self.repo.get_release(release_id)
        if not rel:
            raise KeyError(f"Release '{release_id}' not found.")

        dep_id = f"dep-{uuid.uuid4().hex[:8]}"
        dep = DeploymentRecord(
            deployment_id=dep_id,
            environment_id=environment_id,
            release_id=release_id,
            strategy=strategy,
            status=DeploymentState.DEPLOYING,
            previous_release_id=env.active_release_version,
            approval_token=approval_token,
        )
        self.repo.save_deployment(dep)
        logger.info(f"Initiated deployment '{dep_id}' for release '{release_id}' onto '{environment_id}'")
        return dep

    def complete_deployment(
        self,
        deployment_id: str,
        success: bool = True,
    ) -> DeploymentRecord:
        dep = self.repo.get_deployment(deployment_id)
        if not dep:
            raise KeyError(f"Deployment '{deployment_id}' not found.")

        now = datetime.now(timezone.utc).isoformat()
        dep.completed_at = now
        dep.status = DeploymentState.VERIFYING if success else DeploymentState.FAILED
        self.repo.save_deployment(dep)
        return dep
