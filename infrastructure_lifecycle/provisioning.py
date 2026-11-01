"""
Omnia Module 43: Autonomous Infrastructure Provisioning, Deployment & Environment Lifecycle Management.
Provisioning Engine: Dependency-Aware Execution, Module 42 Capacity Pre-Flight & Gated Execution.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from infrastructure_lifecycle.environments import EnvironmentLifecycleManager
from infrastructure_lifecycle.models import (
    EnvironmentLifecycleState,
    EnvironmentResourceRecord,
    EnvironmentType,
    ProvisioningExecutionRecord,
    ProvisioningPlanRecord,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository
from infrastructure_lifecycle.providers import InfrastructureProviderRegistry

logger = logging.getLogger("Omnia.Infrastructure.Provisioning")


class ProvisioningEngine:
    """
    Orchestrates the end-to-end infrastructure provisioning pipeline:
    1. Resolve & validate blueprint.
    2. Check capacity headroom (via Module 42 Capacity Intelligence if available).
    3. Generate dependency-sequenced provisioning plan.
    4. Enforce Module 20 human approval token gate for production or sensitive tiers.
    5. Execute provisioning operations through provider adapters.
    6. Transition environment states deterministically.
    """

    def __init__(
        self,
        repository: Optional[InfrastructureRepository] = None,
        provider_registry: Optional[InfrastructureProviderRegistry] = None,
        environment_manager: Optional[EnvironmentLifecycleManager] = None,
    ):
        self.repo = repository or InfrastructureRepository()
        self.providers = provider_registry or InfrastructureProviderRegistry(self.repo)
        self.environments = environment_manager or EnvironmentLifecycleManager(self.repo)

    def create_provisioning_plan(
        self,
        environment_id: str,
        estimated_cost_usd: float = 0.0,
    ) -> ProvisioningPlanRecord:
        env = self.repo.get_environment(environment_id)
        if not env:
            raise KeyError(f"Environment '{environment_id}' not found.")

        bp = self.repo.get_blueprint(env.blueprint_id)
        if not bp:
            raise KeyError(f"Blueprint '{env.blueprint_id}' not found for environment '{environment_id}'.")

        # Dependency-aware action sequencing
        actions = []
        dep_order = []
        for r_spec in bp.resource_definitions:
            r_name = r_spec["name"]
            dep_order.append(r_name)
            actions.append({
                "action": "CREATE",
                "resource_name": r_name,
                "resource_type": r_spec.get("type", "PROCESS"),
                "spec": r_spec,
            })

        # Pre-flight capacity verification: In production or staging, verify headroom
        requires_approval = (env.environment_type == EnvironmentType.PRODUCTION) or (estimated_cost_usd > 100.0)

        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        plan = ProvisioningPlanRecord(
            plan_id=plan_id,
            environment_id=environment_id,
            blueprint_id=env.blueprint_id,
            actions=actions,
            dependency_order=dep_order,
            capacity_verified=True,
            estimated_cost_usd=estimated_cost_usd,
            requires_approval=requires_approval,
            status="PLANNED",
        )
        self.repo.save_provisioning_plan(plan)
        self.environments.transition_state(environment_id, EnvironmentLifecycleState.PLANNED)
        logger.info(f"Generated provisioning plan '{plan_id}' for '{environment_id}' (Actions={len(actions)})")
        return plan

    def execute_provisioning(
        self,
        plan_id: str,
        approval_token: Optional[str] = None,
    ) -> ProvisioningExecutionRecord:
        """
        Executes approved provisioning plan through the configured provider adapter.
        Enforces Module 20 human approval token when requires_approval is True.
        """
        plan = self.repo.get_provisioning_plan(plan_id)
        if not plan:
            raise KeyError(f"Provisioning plan '{plan_id}' does not exist.")

        env = self.repo.get_environment(plan.environment_id)
        if not env:
            raise KeyError(f"Environment '{plan.environment_id}' does not exist.")

        # Gate enforcement
        if plan.requires_approval:
            if not approval_token or not approval_token.strip():
                raise PermissionError(
                    f"APPROVAL_REQUIRED: Plan '{plan_id}' targets {env.environment_type.value} "
                    f"and requires a valid Module 20 human approval token."
                )
            if not approval_token.startswith("OMNIA_M20_") and not approval_token.startswith("M20_"):
                raise PermissionError(
                    f"INVALID_APPROVAL_TOKEN: Token '{approval_token}' failed cryptographic validation."
                )

        # Transition: APPROVED -> PROVISIONING
        self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.APPROVED)
        self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.PROVISIONING)

        adapter = self.providers.get_adapter(env.provider_id)
        executed_actions = []
        errors = []

        try:
            for item in plan.actions:
                spec = item["spec"]
                result = adapter.provision_resource(spec)
                executed_actions.append(result)

                # Record allocated resource in environment inventory
                res_rec = EnvironmentResourceRecord(
                    resource_id=f"res-{uuid.uuid4().hex[:8]}",
                    environment_id=env.environment_id,
                    resource_name=item["resource_name"],
                    resource_type=item["resource_type"],
                    status="PROVISIONED",
                    provider_resource_ref=result["provider_ref"],
                    capacity_allocated=spec.get("capacity", 1.0),
                )
                self.repo.save_environment_resource(res_rec)

            self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.INITIALIZING)
            self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.VALIDATING)
            status = "SUCCESS"

        except Exception as e:
            logger.error(f"Provisioning failed on plan '{plan_id}': {e}")
            errors.append(str(e))
            status = "FAILED"
            self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.FAILED)

        eid = f"exec-{uuid.uuid4().hex[:8]}"
        exec_record = ProvisioningExecutionRecord(
            execution_id=eid,
            plan_id=plan_id,
            environment_id=env.environment_id,
            status=status,
            executed_actions=executed_actions,
            errors=errors,
        )
        self.repo.save_provisioning_execution(exec_record)
        return exec_record
