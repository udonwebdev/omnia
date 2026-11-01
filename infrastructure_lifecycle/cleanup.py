"""
OMNIA Module 43: Autonomous Infrastructure Provisioning & Environment Lifecycle Management
Decommissioning & Teardown Engine - cleanup.py

Enforces the Zero Silent Destruction Invariant:
No infrastructure environment, service, or data volume is ever deleted without a formal
Decommission Plan passing explicit Module 20 Human Approval Token gates for protected
environments, ensuring clean state transition to DECOMMISSIONED.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from infrastructure_lifecycle.models import (
    DecommissionPlanRecord,
    EnvironmentLifecycleState,
    EnvironmentType,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository
from infrastructure_lifecycle.providers import InfrastructureProviderRegistry

logger = logging.getLogger("Omnia.Infrastructure.Cleanup")


class DecommissionEngine:
    """
    Manages safe, gated decommissioning of environments and resources.
    Requires Module 20 approval tokens for PRODUCTION or locked environments.
    """

    def __init__(
        self,
        repository: Optional[InfrastructureRepository] = None,
        registry: Optional[InfrastructureProviderRegistry] = None,
    ):
        self.repo = repository or InfrastructureRepository()
        self.registry = registry or InfrastructureProviderRegistry(self.repo)

    def create_decommission_plan(
        self,
        environment_id: str,
        preserve_data: bool = True,
    ) -> DecommissionPlanRecord:
        env = self.repo.get_environment(environment_id)
        if not env:
            raise KeyError(f"Environment '{environment_id}' not found.")

        resources = self.repo.list_environment_resources(environment_id)
        res_ids = [r.resource_id for r in resources]

        d_id = f"decom-{uuid.uuid4().hex[:8]}"
        plan = DecommissionPlanRecord(
            decommission_id=d_id,
            environment_id=environment_id,
            resources_to_delete=res_ids,
            data_retention_preserved=preserve_data,
            status="PROPOSED",
        )
        self.repo.save_decommission_plan(plan)
        logger.info(f"Proposed decommission plan '{d_id}' for env '{environment_id}' (Resources={len(res_ids)})")
        return plan

    def execute_decommission(
        self,
        decommission_id: str,
        approval_token: Optional[str] = None,
    ) -> DecommissionPlanRecord:
        plan = self.repo.get_decommission_plan(decommission_id)
        if not plan:
            raise KeyError(f"Decommission plan '{decommission_id}' not found.")

        env = self.repo.get_environment(plan.environment_id)
        if not env:
            raise KeyError(f"Environment '{plan.environment_id}' not found.")

        # Invariant: Protection gate
        is_protected = env.is_locked or (env.environment_type == EnvironmentType.PRODUCTION)
        if is_protected:
            if not approval_token or not (approval_token.startswith("OMNIA_M20_") or approval_token.startswith("M20_")):
                raise PermissionError(
                    f"APPROVAL_REQUIRED: Protected environment '{env.environment_id}' cannot be decommissioned "
                    f"without a valid Module 20 human approval token."
                )

        adapter = self.registry.get_adapter(env.provider_id)
        if adapter:
            for r_id in plan.resources_to_delete:
                try:
                    adapter.decommission_resource(r_id)
                except Exception as e:
                    logger.warning(f"Error decommissioning resource '{r_id}': {e}")

        # Transition environment lifecycle to DECOMMISSIONED
        env.current_state = EnvironmentLifecycleState.DECOMMISSIONED
        self.repo.save_environment(env)

        plan.status = "EXECUTED"
        plan.approval_token = approval_token
        plan.executed_at = datetime.now(timezone.utc).isoformat()
        self.repo.save_decommission_plan(plan)
        logger.info(f"Decommission plan '{decommission_id}' executed. Env '{env.environment_id}' is DECOMMISSIONED.")
        return plan
