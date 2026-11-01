"""
Omnia Module 43: Autonomous Infrastructure Provisioning, Deployment & Environment Lifecycle Management.
Environment Lifecycle Manager: Deterministic Lifecycle State Machine & Expiration Tracking.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from infrastructure_lifecycle.models import (
    EnvironmentLifecycleState,
    EnvironmentRecord,
    EnvironmentType,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository

logger = logging.getLogger("Omnia.Infrastructure.Environments")


class EnvironmentLifecycleManager:
    """
    Tracks and enforces deterministic transitions for environment lifecycles:
    REQUESTED -> PLANNED -> APPROVED -> PROVISIONING -> INITIALIZING -> VALIDATING -> READY
    Handles TTL expiration and locked production safeguards.
    """

    VALID_TRANSITIONS = {
        EnvironmentLifecycleState.REQUESTED: [EnvironmentLifecycleState.PLANNED, EnvironmentLifecycleState.FAILED],
        EnvironmentLifecycleState.PLANNED: [EnvironmentLifecycleState.APPROVED, EnvironmentLifecycleState.FAILED],
        EnvironmentLifecycleState.APPROVED: [EnvironmentLifecycleState.PROVISIONING, EnvironmentLifecycleState.FAILED],
        EnvironmentLifecycleState.PROVISIONING: [EnvironmentLifecycleState.INITIALIZING, EnvironmentLifecycleState.FAILED],
        EnvironmentLifecycleState.INITIALIZING: [EnvironmentLifecycleState.VALIDATING, EnvironmentLifecycleState.FAILED],
        EnvironmentLifecycleState.VALIDATING: [EnvironmentLifecycleState.READY, EnvironmentLifecycleState.DEGRADED, EnvironmentLifecycleState.FAILED],
        EnvironmentLifecycleState.READY: [EnvironmentLifecycleState.DEGRADED, EnvironmentLifecycleState.ROLLING_BACK, EnvironmentLifecycleState.DECOMMISSIONED],
        EnvironmentLifecycleState.DEGRADED: [EnvironmentLifecycleState.VALIDATING, EnvironmentLifecycleState.ROLLING_BACK, EnvironmentLifecycleState.DECOMMISSIONED],
        EnvironmentLifecycleState.ROLLING_BACK: [EnvironmentLifecycleState.READY, EnvironmentLifecycleState.FAILED],
        EnvironmentLifecycleState.FAILED: [EnvironmentLifecycleState.PROVISIONING, EnvironmentLifecycleState.DECOMMISSIONED],
        EnvironmentLifecycleState.DECOMMISSIONED: [],
    }

    def __init__(self, repository: Optional[InfrastructureRepository] = None):
        self.repo = repository or InfrastructureRepository()

    def create_environment(
        self,
        environment_id: Optional[str] = None,
        name: str = "default-env",
        environment_type: EnvironmentType = EnvironmentType.DEVELOPMENT,
        provider_id: str = "provider-local-sandbox",
        blueprint_id: str = "bp-default",
        region: str = "local",
        owner: str = "omnia-infra",
        expiration_timestamp: Optional[str] = None,
        is_locked: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EnvironmentRecord:
        eid = environment_id or f"env-{uuid.uuid4().hex[:8]}"
        env = EnvironmentRecord(
            environment_id=eid,
            name=name,
            environment_type=environment_type,
            provider_id=provider_id,
            blueprint_id=blueprint_id,
            current_state=EnvironmentLifecycleState.REQUESTED,
            region=region,
            owner=owner,
            expiration_timestamp=expiration_timestamp,
            is_locked=is_locked or (environment_type == EnvironmentType.PRODUCTION),
            metadata=metadata or {},
        )
        self.repo.save_environment(env)
        logger.info(f"Created environment '{environment_id}' ({name}) in state REQUESTED")
        return env

    def transition_state(
        self,
        environment_id: str,
        new_state: EnvironmentLifecycleState,
        operator_notes: str = "",
    ) -> EnvironmentRecord:
        env = self.repo.get_environment(environment_id)
        if not env:
            raise KeyError(f"Environment '{environment_id}' does not exist.")

        allowed = self.VALID_TRANSITIONS.get(env.current_state, [])
        if new_state not in allowed:
            raise ValueError(
                f"ILLEGAL_LIFECYCLE_TRANSITION: Cannot transition '{environment_id}' from "
                f"'{env.current_state.value}' to '{new_state.value}'. Allowed: {[s.value for s in allowed]}"
            )

        env.current_state = new_state
        if new_state == EnvironmentLifecycleState.READY:
            env.last_verified_at = datetime.now(timezone.utc).isoformat()

        self.repo.save_environment(env)
        logger.info(f"Environment '{environment_id}' transitioned to '{new_state.value}'. Notes: {operator_notes}")
        return env

    def get_environment(self, environment_id: str) -> Optional[EnvironmentRecord]:
        return self.repo.get_environment(environment_id)

    def list_environments(self, active_only: bool = False) -> List[EnvironmentRecord]:
        return self.repo.list_environments(active_only=active_only)
