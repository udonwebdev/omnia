"""
OMNIA Module 43: Autonomous Infrastructure Provisioning & Environment Lifecycle Management
Subsystem Orchestrator & Facade - service.py
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure_lifecycle.blueprints import InfrastructureBlueprintEngine
from infrastructure_lifecycle.cleanup import DecommissionEngine
from infrastructure_lifecycle.deployment import DeploymentOrchestrator
from infrastructure_lifecycle.environments import EnvironmentLifecycleManager
from infrastructure_lifecycle.models import (
    DecommissionPlanRecord,
    DeploymentRecord,
    DeploymentStrategy,
    DeploymentVerificationRecord,
    EnvironmentLifecycleState,
    EnvironmentRecord,
    EnvironmentType,
    InfrastructureBlueprint,
    InfrastructureDriftRecord,
    InfrastructureProviderRecord,
    ProvisioningExecutionRecord,
    ProvisioningPlanRecord,
    ReleaseRecord,
    RollbackRecord,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository
from infrastructure_lifecycle.providers import (
    BaseInfrastructureAdapter,
    InfrastructureProviderRegistry,
    LocalSandboxProviderAdapter,
)
from infrastructure_lifecycle.provisioning import ProvisioningEngine
from infrastructure_lifecycle.reconciliation import InfrastructureReconciler
from infrastructure_lifecycle.reporting import InfrastructureReporter
from infrastructure_lifecycle.rollback import RollbackController
from infrastructure_lifecycle.validator import DeploymentValidator

logger = logging.getLogger("Omnia.Infrastructure.Service")


class InfrastructureLifecycleOrchestrator:
    """
    Unified entry point and coordinator for Module 43.
    """

    def __init__(
        self,
        repository: Optional[InfrastructureRepository] = None,
        event_fabric: Optional[Any] = None,
        capacity_planning_service: Optional[Any] = None,
    ):
        self.repo = repository or InfrastructureRepository()
        self.event_fabric = event_fabric
        self.capacity_service = capacity_planning_service

        self.registry = InfrastructureProviderRegistry(self.repo)
        self.blueprints = InfrastructureBlueprintEngine(self.repo)
        self.environments = EnvironmentLifecycleManager(self.repo)
        self.provisioning = ProvisioningEngine(self.repo, self.registry, self.environments)
        self.deployment = DeploymentOrchestrator(self.repo)
        self.validator = DeploymentValidator(self.repo, self.registry)
        self.rollback = RollbackController(self.repo)
        self.reconciler = InfrastructureReconciler(self.repo, self.registry)
        self.cleanup = DecommissionEngine(self.repo, self.registry)
        self.reporter = InfrastructureReporter(self.repo)

        self._ensure_default_providers()

    def _ensure_default_providers(self) -> None:
        default_pid = "sandbox_default"
        if not self.repo.get_provider(default_pid):
            adapter = LocalSandboxProviderAdapter(default_pid)
            self.registry.register_adapter(adapter)
            self.repo.save_provider(adapter.get_record())
        elif not self.registry.get_adapter(default_pid):
            adapter = LocalSandboxProviderAdapter(default_pid)
            self.registry.register_adapter(adapter)

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if not self.event_fabric:
            return
        try:
            from events.models import Event, EventEnvelope
            envelope = EventEnvelope(
                event_type=event_type,
                source="module43.infrastructure_lifecycle",
            )
            ev = Event(envelope=envelope, payload=payload)
            self.event_fabric.publish(ev)
        except Exception as e:
            logger.debug(f"Failed to publish event {event_type}: {e}")

    def register_provider(self, adapter: BaseInfrastructureAdapter) -> InfrastructureProviderRecord:
        self.registry.register_adapter(adapter)
        rec = adapter.get_record()
        self.repo.save_provider(rec)
        self._publish_event("infrastructure.provider_registered", {"provider_id": rec.provider_id})
        return rec

    def register_blueprint(
        self,
        blueprint_id: str,
        name: str,
        version: str,
        environment_type: EnvironmentType,
        resource_definitions: List[Dict[str, Any]],
        dependencies: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> InfrastructureBlueprint:
        bp = self.blueprints.register_blueprint(
            blueprint_id=blueprint_id,
            name=name,
            version=version,
            environment_type=environment_type,
            resource_definitions=resource_definitions,
            dependencies=dependencies,
            **kwargs,
        )
        self._publish_event("infrastructure.blueprint_registered", {"blueprint_id": bp.blueprint_id})
        return bp

    def create_environment(
        self,
        name: str,
        environment_type: EnvironmentType,
        provider_id: str,
        blueprint_id: str,
        environment_id: Optional[str] = None,
        **kwargs: Any,
    ) -> EnvironmentRecord:
        env = self.environments.create_environment(
            name=name,
            environment_type=environment_type,
            provider_id=provider_id,
            blueprint_id=blueprint_id,
            environment_id=environment_id,
            **kwargs,
        )
        self._publish_event(
            "infrastructure.environment_requested",
            {"environment_id": env.environment_id, "type": env.environment_type.value},
        )
        return env

    def plan_provisioning(self, environment_id: str, estimated_cost_usd: float = 0.0) -> ProvisioningPlanRecord:
        plan = self.provisioning.create_provisioning_plan(environment_id, estimated_cost_usd=estimated_cost_usd)
        self._publish_event(
            "infrastructure.provisioning_planned",
            {"plan_id": plan.plan_id, "environment_id": environment_id},
        )
        return plan

    def execute_provisioning(
        self,
        plan_id: str,
        approval_token: Optional[str] = None,
    ) -> ProvisioningExecutionRecord:
        exec_rec = self.provisioning.execute_provisioning(plan_id, approval_token=approval_token)
        self._publish_event(
            "infrastructure.provisioning_executed",
            {"execution_id": exec_rec.execution_id, "plan_id": plan_id, "status": exec_rec.status},
        )
        return exec_rec

    def register_release(
        self,
        application_name: str,
        version: str,
        artifact_uri: str,
        checksum_sha256: str = "sha256:0000000000",
        source_revision: str = "main@head",
    ) -> ReleaseRecord:
        rel = self.deployment.register_release(
            application_name=application_name,
            version=version,
            artifact_uri=artifact_uri,
            checksum_sha256=checksum_sha256,
            source_revision=source_revision,
        )
        self._publish_event("infrastructure.release_registered", {"release_id": rel.release_id})
        return rel

    def deploy_release(
        self,
        environment_id: str,
        release_id: str,
        strategy: DeploymentStrategy = DeploymentStrategy.DIRECT,
        approval_token: Optional[str] = None,
    ) -> DeploymentRecord:
        dep = self.deployment.start_deployment(
            environment_id=environment_id,
            release_id=release_id,
            strategy=strategy,
            approval_token=approval_token,
        )
        self._publish_event(
            "infrastructure.deployment_started",
            {"deployment_id": dep.deployment_id, "environment_id": environment_id},
        )
        return dep

    def verify_deployment(
        self,
        deployment_id: str,
        simulate_checks: bool = True,
        override_failure_reason: Optional[str] = None,
    ) -> DeploymentVerificationRecord:
        ver = self.validator.verify_deployment(
            deployment_id=deployment_id,
            simulate_checks=simulate_checks,
            override_failure_reason=override_failure_reason,
        )
        self._publish_event(
            "infrastructure.deployment_verified",
            {"verification_id": ver.verification_id, "is_fully_verified": ver.is_fully_verified},
        )
        return ver

    def rollback_deployment(
        self,
        environment_id: str,
        failed_deployment_id: str,
        target_release_id: Optional[str] = None,
        approval_token: Optional[str] = None,
    ) -> RollbackRecord:
        rb = self.rollback.execute_rollback(
            environment_id=environment_id,
            failed_deployment_id=failed_deployment_id,
            target_release_id=target_release_id,
            approval_token=approval_token,
        )
        self._publish_event(
            "infrastructure.rollback_executed",
            {"rollback_id": rb.rollback_id, "environment_id": environment_id},
        )
        return rb

    def reconcile_drift(
        self,
        environment_id: str,
        auto_reconcile: bool = False,
    ) -> List[InfrastructureDriftRecord]:
        findings = self.reconciler.reconcile_environment(environment_id, auto_reconcile=auto_reconcile)
        self._publish_event(
            "infrastructure.drift_reconciled",
            {"environment_id": environment_id, "drift_count": len(findings)},
        )
        return findings

    def create_decommission_plan(
        self,
        environment_id: str,
        preserve_data: bool = True,
    ) -> DecommissionPlanRecord:
        plan = self.cleanup.create_decommission_plan(environment_id, preserve_data=preserve_data)
        self._publish_event(
            "infrastructure.decommission_planned",
            {"decommission_id": plan.decommission_id, "environment_id": environment_id},
        )
        return plan

    def execute_decommission(
        self,
        decommission_id: str,
        approval_token: Optional[str] = None,
    ) -> DecommissionPlanRecord:
        plan = self.cleanup.execute_decommission(decommission_id, approval_token=approval_token)
        self._publish_event(
            "infrastructure.decommission_executed",
            {"decommission_id": decommission_id, "environment_id": plan.environment_id},
        )
        return plan

    def get_posture_report(self) -> Dict[str, Any]:
        return self.reporter.generate_posture_report()


# Module-level singleton instance
infrastructure_lifecycle_service = InfrastructureLifecycleOrchestrator()
