"""
OMNIA Module 37: Autonomous Deployment, Release Engineering & Rollback Models
Provides typed data contracts for releases, artifacts, qualification gates,
environments, deployment strategies, rollout stages, verifications, and rollbacks.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class ReleaseState(str, Enum):
    DRAFT = "DRAFT"
    PREPARING = "PREPARING"
    BUILDING = "BUILDING"
    BUILD_FAILED = "BUILD_FAILED"
    ARTIFACT_READY = "ARTIFACT_READY"
    QUALIFYING = "QUALIFYING"
    QUALIFICATION_FAILED = "QUALIFICATION_FAILED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    DEPLOYMENT_QUEUED = "DEPLOYMENT_QUEUED"
    DEPLOYING = "DEPLOYING"
    CANARY = "CANARY"
    PROGRESSIVE_ROLLOUT = "PROGRESSIVE_ROLLOUT"
    VERIFYING = "VERIFYING"
    DEPLOYED = "DEPLOYED"
    DEGRADED = "DEGRADED"
    ROLLBACK_PENDING = "ROLLBACK_PENDING"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    REQUIRES_INTERVENTION = "REQUIRES_INTERVENTION"


class DeploymentStrategy(str, Enum):
    DIRECT = "DIRECT"
    ROLLING = "ROLLING"
    BLUE_GREEN = "BLUE_GREEN"
    CANARY = "CANARY"


class EnvironmentType(str, Enum):
    LOCAL_DEV = "LOCAL_DEV"
    SHARED_DEV = "SHARED_DEV"
    TESTING = "TESTING"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"
    RECOVERY = "RECOVERY"


class MigrationSafetyClass(str, Enum):
    REVERSIBLE = "REVERSIBLE"
    FORWARD_COMPATIBLE = "FORWARD_COMPATIBLE"
    EXPAND_CONTRACT = "EXPAND_CONTRACT"
    IRREVERSIBLE = "IRREVERSIBLE"
    MANUAL_INTERVENTION_REQUIRED = "MANUAL_INTERVENTION_REQUIRED"


class QualificationGateStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    PENDING = "PENDING"


@dataclass
class ArtifactRecord:
    artifact_id: str
    app_id: str
    version: str
    source_revision: str
    build_id: str
    digest_sha256: str
    size_bytes: int
    format_type: str  # "wheel", "tarball", "container_image", "binary"
    storage_uri: str
    builder_identity: str
    toolchain_metadata: Dict[str, Any] = field(default_factory=dict)
    dependency_manifest: Dict[str, str] = field(default_factory=dict)
    sbom_digest: Optional[str] = None
    vulnerabilities_summary: Dict[str, int] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    is_tamper_verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "app_id": self.app_id,
            "version": self.version,
            "source_revision": self.source_revision,
            "build_id": self.build_id,
            "digest_sha256": self.digest_sha256,
            "size_bytes": self.size_bytes,
            "format_type": self.format_type,
            "storage_uri": self.storage_uri,
            "builder_identity": self.builder_identity,
            "toolchain_metadata": self.toolchain_metadata,
            "dependency_manifest": self.dependency_manifest,
            "sbom_digest": self.sbom_digest,
            "vulnerabilities_summary": self.vulnerabilities_summary,
            "created_at": self.created_at,
            "is_tamper_verified": self.is_tamper_verified,
        }


@dataclass
class QualificationGateResult:
    gate_name: str
    status: QualificationGateStatus
    required: bool
    details: str
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "status": self.status.value,
            "required": self.required,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ReleaseRecord:
    release_id: str
    app_id: str
    version: str
    source_revision: str
    state: ReleaseState = ReleaseState.DRAFT
    artifact_id: Optional[str] = None
    target_environment: str = "PRODUCTION"
    created_by: str = "system"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    description: str = ""
    migration_safety: MigrationSafetyClass = MigrationSafetyClass.FORWARD_COMPATIBLE
    approval_request_id: Optional[str] = None
    approval_token: Optional[str] = None
    qualification_results: List[Dict[str, Any]] = field(default_factory=list)
    state_history: List[Dict[str, Any]] = field(default_factory=list)
    active_deployment_id: Optional[str] = None

    def transition_to(self, new_state: ReleaseState, actor: str = "system", reason: str = "") -> None:
        valid_transitions = {
            ReleaseState.DRAFT: [ReleaseState.PREPARING, ReleaseState.CANCELLED],
            ReleaseState.PREPARING: [ReleaseState.BUILDING, ReleaseState.BUILD_FAILED, ReleaseState.CANCELLED],
            ReleaseState.BUILDING: [ReleaseState.ARTIFACT_READY, ReleaseState.BUILD_FAILED, ReleaseState.CANCELLED],
            ReleaseState.BUILD_FAILED: [ReleaseState.PREPARING, ReleaseState.CANCELLED],
            ReleaseState.ARTIFACT_READY: [ReleaseState.QUALIFYING, ReleaseState.CANCELLED],
            ReleaseState.QUALIFYING: [ReleaseState.AWAITING_APPROVAL, ReleaseState.APPROVED, ReleaseState.QUALIFICATION_FAILED, ReleaseState.CANCELLED],
            ReleaseState.QUALIFICATION_FAILED: [ReleaseState.QUALIFYING, ReleaseState.CANCELLED],
            ReleaseState.AWAITING_APPROVAL: [ReleaseState.APPROVED, ReleaseState.CANCELLED],
            ReleaseState.APPROVED: [ReleaseState.DEPLOYMENT_QUEUED, ReleaseState.CANCELLED],
            ReleaseState.DEPLOYMENT_QUEUED: [ReleaseState.DEPLOYING, ReleaseState.CANCELLED],
            ReleaseState.DEPLOYING: [ReleaseState.CANARY, ReleaseState.PROGRESSIVE_ROLLOUT, ReleaseState.VERIFYING, ReleaseState.FAILED, ReleaseState.DEGRADED],
            ReleaseState.CANARY: [ReleaseState.PROGRESSIVE_ROLLOUT, ReleaseState.VERIFYING, ReleaseState.ROLLBACK_PENDING, ReleaseState.FAILED],
            ReleaseState.PROGRESSIVE_ROLLOUT: [ReleaseState.VERIFYING, ReleaseState.ROLLBACK_PENDING, ReleaseState.FAILED],
            ReleaseState.VERIFYING: [ReleaseState.DEPLOYED, ReleaseState.ROLLBACK_PENDING, ReleaseState.FAILED, ReleaseState.DEGRADED],
            ReleaseState.DEPLOYED: [ReleaseState.DEGRADED, ReleaseState.ROLLBACK_PENDING],
            ReleaseState.DEGRADED: [ReleaseState.ROLLBACK_PENDING, ReleaseState.REQUIRES_INTERVENTION],
            ReleaseState.ROLLBACK_PENDING: [ReleaseState.ROLLING_BACK, ReleaseState.REQUIRES_INTERVENTION],
            ReleaseState.ROLLING_BACK: [ReleaseState.ROLLED_BACK, ReleaseState.FAILED, ReleaseState.REQUIRES_INTERVENTION],
            ReleaseState.ROLLED_BACK: [],
            ReleaseState.CANCELLED: [],
            ReleaseState.FAILED: [ReleaseState.ROLLBACK_PENDING, ReleaseState.REQUIRES_INTERVENTION],
            ReleaseState.REQUIRES_INTERVENTION: [ReleaseState.ROLLBACK_PENDING, ReleaseState.ROLLING_BACK, ReleaseState.CANCELLED],
        }

        allowed = valid_transitions.get(self.state, [])
        if new_state not in allowed:
            raise ValueError(f"Illegal release state transition from {self.state.value} to {new_state.value}")

        prev = self.state.value
        self.state = new_state
        self.updated_at = time.time()
        self.state_history.append({
            "from_state": prev,
            "to_state": new_state.value,
            "actor": actor,
            "reason": reason,
            "timestamp": self.updated_at,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "release_id": self.release_id,
            "app_id": self.app_id,
            "version": self.version,
            "source_revision": self.source_revision,
            "state": self.state.value,
            "artifact_id": self.artifact_id,
            "target_environment": self.target_environment,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "description": self.description,
            "migration_safety": self.migration_safety.value,
            "approval_request_id": self.approval_request_id,
            "approval_token": self.approval_token,
            "qualification_results": self.qualification_results,
            "state_history": self.state_history,
            "active_deployment_id": self.active_deployment_id,
        }


@dataclass
class EnvironmentRecord:
    environment_id: str
    environment_type: EnvironmentType
    app_id: str
    provider_type: str  # "local_process", "container", "kubernetes", "cloud_run"
    current_release_id: Optional[str] = None
    current_artifact_digest: Optional[str] = None
    desired_release_id: Optional[str] = None
    configuration_revision: str = "rev-1"
    health_status: str = "HEALTHY"
    requires_approval: bool = True
    in_maintenance: bool = False
    last_verified_at: Optional[float] = None
    target_endpoint: str = "http://127.0.0.1:8080"
    cluster_lease_node: Optional[str] = None
    lease_expires_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "environment_type": self.environment_type.value,
            "app_id": self.app_id,
            "provider_type": self.provider_type,
            "current_release_id": self.current_release_id,
            "current_artifact_digest": self.current_artifact_digest,
            "desired_release_id": self.desired_release_id,
            "configuration_revision": self.configuration_revision,
            "health_status": self.health_status,
            "requires_approval": self.requires_approval,
            "in_maintenance": self.in_maintenance,
            "last_verified_at": self.last_verified_at,
            "target_endpoint": self.target_endpoint,
            "cluster_lease_node": self.cluster_lease_node,
            "lease_expires_at": self.lease_expires_at,
        }


@dataclass
class RolloutStage:
    stage_index: int
    traffic_percentage: float
    observation_window_seconds: float
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    error_rate_threshold: float = 0.02
    latency_threshold_ms: float = 500.0
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_index": self.stage_index,
            "traffic_percentage": self.traffic_percentage,
            "observation_window_seconds": self.observation_window_seconds,
            "status": self.status,
            "error_rate_threshold": self.error_rate_threshold,
            "latency_threshold_ms": self.latency_threshold_ms,
            "completed_at": self.completed_at,
        }


@dataclass
class DeploymentRecord:
    deployment_id: str
    release_id: str
    artifact_id: str
    environment_id: str
    strategy: DeploymentStrategy
    status: str = "INITIALIZED"  # INITIALIZED, IN_PROGRESS, VERIFYING, SUCCEEDED, FAILED, ROLLED_BACK
    current_traffic_pct: float = 0.0
    current_stage_index: int = 0
    stages: List[Dict[str, Any]] = field(default_factory=list)
    verification_evidence: Optional[str] = None
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    executed_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "release_id": self.release_id,
            "artifact_id": self.artifact_id,
            "environment_id": self.environment_id,
            "strategy": self.strategy.value,
            "status": self.status,
            "current_traffic_pct": self.current_traffic_pct,
            "current_stage_index": self.current_stage_index,
            "stages": self.stages,
            "verification_evidence": self.verification_evidence,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "executed_by": self.executed_by,
        }


@dataclass
class RollbackRecord:
    rollback_id: str
    failed_release_id: str
    restored_release_id: str
    environment_id: str
    reason: str
    migration_safety: MigrationSafetyClass
    status: str = "PENDING"  # PENDING, IN_PROGRESS, SUCCEEDED, FAILED, REQUIRES_INTERVENTION
    approval_token: Optional[str] = None
    verification_evidence: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "failed_release_id": self.failed_release_id,
            "restored_release_id": self.restored_release_id,
            "environment_id": self.environment_id,
            "reason": self.reason,
            "migration_safety": self.migration_safety.value,
            "status": self.status,
            "approval_token": self.approval_token,
            "verification_evidence": self.verification_evidence,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }
