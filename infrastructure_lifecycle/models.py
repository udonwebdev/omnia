"""
Omnia Module 43: Autonomous Infrastructure Provisioning, Deployment & Environment Lifecycle Management.
Domain Models, Enums, and Value Objects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ProviderType(str, enum.Enum):
    LOCAL_PROCESS = "LOCAL_PROCESS"
    DOCKER = "DOCKER"
    KUBERNETES = "KUBERNETES"
    CLOUD_GCP = "CLOUD_GCP"
    CLOUD_AWS = "CLOUD_AWS"
    CLOUD_AZURE = "CLOUD_AZURE"
    SIMULATED_SANDBOX = "SIMULATED_SANDBOX"


class ProviderCapability(str, enum.Enum):
    DISCOVERY = "DISCOVERY"
    PROVISION = "PROVISION"
    MUTATE = "MUTATE"
    RESTART = "RESTART"
    DECOMMISSION = "DECOMMISSION"
    INSPECT = "INSPECT"
    LOGS = "LOGS"


class EnvironmentType(str, enum.Enum):
    DEVELOPMENT = "DEVELOPMENT"
    TESTING = "TESTING"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"
    TEMPORARY = "TEMPORARY"
    ISOLATED_EXPERIMENTATION = "ISOLATED_EXPERIMENTATION"
    DISASTER_RECOVERY = "DISASTER_RECOVERY"


class EnvironmentLifecycleState(str, enum.Enum):
    REQUESTED = "REQUESTED"
    PLANNED = "PLANNED"
    APPROVED = "APPROVED"
    PROVISIONING = "PROVISIONING"
    INITIALIZING = "INITIALIZING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    ROLLING_BACK = "ROLLING_BACK"
    DECOMMISSIONED = "DECOMMISSIONED"
    FAILED = "FAILED"


class DeploymentStrategy(str, enum.Enum):
    DIRECT = "DIRECT"
    ROLLING = "ROLLING"
    BLUE_GREEN = "BLUE_GREEN"
    CANARY = "CANARY"
    RECREATE = "RECREATE"


class DeploymentState(str, enum.Enum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    DEPLOYING = "DEPLOYING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class DriftType(str, enum.Enum):
    MISSING_RESOURCE = "MISSING_RESOURCE"
    UNEXPECTED_RESOURCE = "UNEXPECTED_RESOURCE"
    CONFIGURATION_DRIFT = "CONFIGURATION_DRIFT"
    VERSION_DRIFT = "VERSION_DRIFT"


@dataclass
class InfrastructureProviderRecord:
    provider_id: str
    name: str
    provider_type: ProviderType
    supported_capabilities: List[ProviderCapability] = field(default_factory=list)
    auth_secret_ref: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class InfrastructureBlueprint:
    blueprint_id: str
    name: str
    version: str
    environment_type: EnvironmentType
    resource_definitions: List[Dict[str, Any]] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    network_spec: Dict[str, Any] = field(default_factory=dict)
    storage_spec: Dict[str, Any] = field(default_factory=dict)
    compute_spec: Dict[str, Any] = field(default_factory=dict)
    required_secrets: List[str] = field(default_factory=list)
    lifecycle_ttl_hours: Optional[float] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class EnvironmentRecord:
    environment_id: str
    name: str
    environment_type: EnvironmentType
    provider_id: str
    blueprint_id: str
    current_state: EnvironmentLifecycleState = EnvironmentLifecycleState.REQUESTED
    region: str = "local"
    owner: str = "omnia-infra"
    active_release_version: Optional[str] = None
    active_configuration_version: str = "1.0.0"
    expiration_timestamp: Optional[str] = None
    last_verified_at: Optional[str] = None
    is_locked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class EnvironmentResourceRecord:
    resource_id: str
    environment_id: str
    resource_name: str
    resource_type: str  # VM, CONTAINER, DATABASE, NETWORK_SWITCH, STORAGE_BUCKET
    status: str = "PROVISIONED"
    provider_resource_ref: str = ""
    capacity_allocated: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProvisioningPlanRecord:
    plan_id: str
    environment_id: str
    blueprint_id: str
    actions: List[Dict[str, Any]] = field(default_factory=list)
    dependency_order: List[str] = field(default_factory=list)
    capacity_verified: bool = False
    estimated_cost_usd: float = 0.0
    requires_approval: bool = True
    approval_token: Optional[str] = None
    status: str = "PLANNED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProvisioningExecutionRecord:
    execution_id: str
    plan_id: str
    environment_id: str
    status: str = "SUCCESS"  # SUCCESS, FAILED, PARTIAL
    executed_actions: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReleaseRecord:
    release_id: str
    application_name: str
    version: str
    artifact_uri: str
    checksum_sha256: str
    source_revision: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DeploymentRecord:
    deployment_id: str
    environment_id: str
    release_id: str
    strategy: DeploymentStrategy
    status: DeploymentState = DeploymentState.REQUESTED
    previous_release_id: Optional[str] = None
    approval_token: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None


@dataclass
class DeploymentVerificationRecord:
    verification_id: str
    deployment_id: str
    environment_id: str
    infrastructure_ready: bool
    application_ready: bool
    operational_ready: bool
    is_fully_verified: bool
    check_results: Dict[str, Any] = field(default_factory=dict)
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RollbackRecord:
    rollback_id: str
    deployment_id: str
    target_environment_id: str
    from_release_id: str
    to_release_id: str
    approval_token: Optional[str] = None
    status: str = "SUCCESS"
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class InfrastructureDriftRecord:
    drift_id: str
    environment_id: str
    drift_type: DriftType
    resource_id: str
    expected_state: str
    actual_state: str
    remediation_suggestion: str
    is_reconciled: bool = False
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DecommissionPlanRecord:
    decommission_id: str
    environment_id: str
    resources_to_delete: List[str] = field(default_factory=list)
    data_retention_preserved: bool = True
    approval_token: Optional[str] = None
    status: str = "PROPOSED"
    executed_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
