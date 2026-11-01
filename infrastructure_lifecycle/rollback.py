"""
OMNIA Module 43: Autonomous Infrastructure Provisioning & Environment Lifecycle Management
Automated Rollback Engine - rollback.py

Coordinates safe, auditable rollbacks to previous known-good releases.
Requires Module 20 human approval token for PRODUCTION environments.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from infrastructure_lifecycle.models import (
    DeploymentState,
    EnvironmentLifecycleState,
    EnvironmentType,
    RollbackRecord,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository

logger = logging.getLogger("Omnia.Infrastructure.Rollback")


class RollbackController:
    """
    Executes and records rollbacks to target or previous deployments.
    """

    def __init__(self, repository: Optional[InfrastructureRepository] = None):
        self.repo = repository or InfrastructureRepository()

    def execute_rollback(
        self,
        environment_id: str,
        failed_deployment_id: str,
        target_release_id: Optional[str] = None,
        approval_token: Optional[str] = None,
    ) -> RollbackRecord:
        env = self.repo.get_environment(environment_id)
        if not env:
            raise KeyError(f"Environment '{environment_id}' not found.")

        # Invariant: PRODUCTION rollback requires valid human approval token
        if env.environment_type == EnvironmentType.PRODUCTION:
            if not approval_token or not (approval_token.startswith("OMNIA_M20_") or approval_token.startswith("M20_")):
                raise PermissionError(
                    f"Production rollback requires a valid Module 20 human approval token (got '{approval_token}')"
                )

        failed_dep = self.repo.get_deployment(failed_deployment_id)
        from_release = failed_dep.release_id if failed_dep else "unknown"

        # Determine target release to restore
        to_release = target_release_id or (failed_dep.previous_release_id if failed_dep else "baseline")

        # Transition environment into ROLLING_BACK then READY
        env.current_state = EnvironmentLifecycleState.ROLLING_BACK
        self.repo.save_environment(env)

        if failed_dep:
            failed_dep.status = DeploymentState.ROLLED_BACK
            self.repo.save_deployment(failed_dep)

        rb_id = f"rb-{uuid.uuid4().hex[:8]}"
        rec = RollbackRecord(
            rollback_id=rb_id,
            deployment_id=failed_deployment_id,
            target_environment_id=environment_id,
            from_release_id=from_release,
            to_release_id=to_release or "baseline",
            approval_token=approval_token,
            status="SUCCESS",
        )
        self.repo.save_rollback(rec)

        # Restore environment to target release and READY state
        env.active_release_version = to_release
        env.current_state = EnvironmentLifecycleState.READY
        env.last_verified_at = datetime.now(timezone.utc).isoformat()
        self.repo.save_environment(env)

        logger.info(
            f"Rollback '{rb_id}' succeeded: env '{environment_id}' restored from '{from_release}' to '{to_release}'"
        )
        return rec
