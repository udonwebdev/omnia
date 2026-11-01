"""
OMNIA Module 43: Autonomous Infrastructure Provisioning, Deployment & Environment Lifecycle Management
"""

from infrastructure_lifecycle.blueprints import InfrastructureBlueprintEngine
from infrastructure_lifecycle.cleanup import DecommissionEngine
from infrastructure_lifecycle.deployment import DeploymentOrchestrator
from infrastructure_lifecycle.environments import EnvironmentLifecycleManager
from infrastructure_lifecycle.models import (
    DecommissionPlanRecord,
    DeploymentRecord,
    DeploymentState,
    DeploymentStrategy,
    DeploymentVerificationRecord,
    DriftType,
    EnvironmentLifecycleState,
    EnvironmentRecord,
    EnvironmentResourceRecord,
    EnvironmentType,
    InfrastructureBlueprint,
    InfrastructureDriftRecord,
    InfrastructureProviderRecord,
    ProviderCapability,
    ProviderType,
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
from infrastructure_lifecycle.service import (
    InfrastructureLifecycleOrchestrator,
    infrastructure_lifecycle_service,
)
from infrastructure_lifecycle.validator import DeploymentValidator

# Backward compatible aliases
BlueprintManager = InfrastructureBlueprintEngine
EnvironmentManager = EnvironmentLifecycleManager
ProviderRegistry = InfrastructureProviderRegistry
InfrastructureLifecycleRepository = InfrastructureRepository

__all__ = [
    "ProviderType",
    "ProviderCapability",
    "EnvironmentType",
    "EnvironmentLifecycleState",
    "DeploymentStrategy",
    "DeploymentState",
    "DriftType",
    "InfrastructureProviderRecord",
    "InfrastructureBlueprint",
    "EnvironmentRecord",
    "EnvironmentResourceRecord",
    "ProvisioningPlanRecord",
    "ProvisioningExecutionRecord",
    "ReleaseRecord",
    "DeploymentRecord",
    "DeploymentVerificationRecord",
    "RollbackRecord",
    "InfrastructureDriftRecord",
    "DecommissionPlanRecord",
    "InfrastructureRepository",
    "InfrastructureLifecycleRepository",
    "BaseInfrastructureAdapter",
    "LocalSandboxProviderAdapter",
    "InfrastructureProviderRegistry",
    "ProviderRegistry",
    "InfrastructureBlueprintEngine",
    "BlueprintManager",
    "EnvironmentLifecycleManager",
    "EnvironmentManager",
    "ProvisioningEngine",
    "DeploymentOrchestrator",
    "DeploymentValidator",
    "RollbackController",
    "InfrastructureReconciler",
    "DecommissionEngine",
    "InfrastructureReporter",
    "InfrastructureLifecycleOrchestrator",
    "infrastructure_lifecycle_service",
]
