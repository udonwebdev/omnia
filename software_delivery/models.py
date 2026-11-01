"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Domain Models, Enums, and Value Objects - models.py
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class RepositoryType(str, enum.Enum):
    GIT_LOCAL = "GIT_LOCAL"
    GITHUB = "GITHUB"
    GITLAB = "GITLAB"
    BITBUCKET = "BITBUCKET"
    SIMULATED_VCS = "SIMULATED_VCS"


class ChangeCategory(str, enum.Enum):
    CODE = "CODE"
    CONFIGURATION = "CONFIGURATION"
    DEPENDENCY = "DEPENDENCY"
    DATABASE_MIGRATION = "DATABASE_MIGRATION"
    TEST = "TEST"
    DOCUMENTATION = "DOCUMENTATION"
    SECURITY_CRITICAL = "SECURITY_CRITICAL"


class PipelineStageType(str, enum.Enum):
    SOURCE_VALIDATION = "SOURCE_VALIDATION"
    CHANGE_ANALYSIS = "CHANGE_ANALYSIS"
    DEPENDENCY_CHECK = "DEPENDENCY_CHECK"
    LINT_AND_FORMAT = "LINT_AND_FORMAT"
    BUILD_COMPILE = "BUILD_COMPILE"
    UNIT_TEST = "UNIT_TEST"
    INTEGRATION_TEST = "INTEGRATION_TEST"
    SECURITY_SCAN = "SECURITY_SCAN"
    ARTIFACT_PACKAGING = "ARTIFACT_PACKAGING"
    PROVENANCE_ATTESTATION = "PROVENANCE_ATTESTATION"
    QUALITY_GATE = "QUALITY_GATE"
    DEPLOYMENT_HANDOFF = "DEPLOYMENT_HANDOFF"


class PipelineStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class BuildStatus(str, enum.Enum):
    PENDING = "PENDING"
    BUILDING = "BUILDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class TestStatus(str, enum.Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class GateStatus(str, enum.Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    WARNING = "WARNING"
    WAIVED = "WAIVED"


class FindingSeverity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ReleaseStage(str, enum.Enum):
    CANDIDATE = "CANDIDATE"
    QUALIFIED = "QUALIFIED"
    PROMOTED = "PROMOTED"
    DEPLOYED = "DEPLOYED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"


class HandoffStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DEPLOYING = "DEPLOYING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------

@dataclass
class SourceRepository:
    repository_id: str
    name: str
    provider_type: RepositoryType
    clone_url: str
    default_branch: str = "main"
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SourceRevision:
    revision_id: str
    repository_id: str
    commit_hash: str
    branch: str
    author: str
    commit_message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    parent_commits: List[str] = field(default_factory=list)


@dataclass
class ChangeImpactReport:
    report_id: str
    revision_id: str
    repository_id: str
    changed_files: List[str] = field(default_factory=list)
    change_categories: List[ChangeCategory] = field(default_factory=list)
    impacted_modules: List[str] = field(default_factory=list)
    relevant_test_suites: List[str] = field(default_factory=list)
    migration_detected: bool = False
    security_sensitive: bool = False
    confidence_score: float = 1.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PipelineDefinition:
    pipeline_id: str
    name: str
    repository_id: str
    stages: List[PipelineStageType] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    environment_variables: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 1800
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PipelineStageExecution:
    stage_id: str
    pipeline_execution_id: str
    stage_type: PipelineStageType
    status: PipelineStatus
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    exit_code: int = 0
    logs: str = ""
    error_message: Optional[str] = None


@dataclass
class PipelineExecution:
    execution_id: str
    pipeline_id: str
    revision_id: str
    status: PipelineStatus = PipelineStatus.PLANNED
    stages_executed: List[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    total_duration_seconds: float = 0.0
    error_summary: Optional[str] = None


@dataclass
class BuildExecutionRecord:
    build_id: str
    pipeline_execution_id: str
    command: str
    status: BuildStatus = BuildStatus.PENDING
    artifact_paths: List[str] = field(default_factory=list)
    logs: str = ""
    duration_seconds: float = 0.0
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TestExecutionRecord:
    test_run_id: str
    pipeline_execution_id: str
    suite_name: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    duration_seconds: float = 0.0
    coverage_pct: Optional[float] = None
    status: TestStatus = TestStatus.PASSED
    failure_details: List[Dict[str, Any]] = field(default_factory=list)
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class QualityGateResult:
    gate_id: str
    pipeline_execution_id: str
    status: GateStatus = GateStatus.PASSED
    score: float = 1.0
    metrics: Dict[str, Any] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DependencyAssessment:
    assessment_id: str
    revision_id: str
    direct_dependency_count: int = 0
    transitive_dependency_count: int = 0
    vulnerabilities_detected: int = 0
    deprecated_dependencies: List[str] = field(default_factory=list)
    outdated_dependencies: List[str] = field(default_factory=list)
    findings: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityAssessment:
    assessment_id: str
    revision_id: str
    secrets_found_count: int = 0
    sast_violations_count: int = 0
    highest_severity: FindingSeverity = FindingSeverity.INFO
    findings: List[Dict[str, Any]] = field(default_factory=list)
    is_passing: bool = True
    scanned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class BuildArtifactRecord:
    artifact_id: str
    pipeline_execution_id: str
    name: str
    artifact_type: str  # TAR, WHEEL, CONTAINER_IMAGE, BINARY
    storage_uri: str
    checksum_sha256: str
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ArtifactAttestation:
    attestation_id: str
    artifact_id: str
    predicate_type: str = "https://slsa.dev/provenance/v1"
    builder_id: str = "omnia-builder-v1"
    source_repository: str = ""
    source_commit: str = ""
    build_config: Dict[str, Any] = field(default_factory=dict)
    is_signed: bool = False
    signature_ref: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RegressionFinding:
    regression_id: str
    pipeline_execution_id: str
    component_name: str
    metric_name: str
    baseline_value: float
    current_value: float
    delta_pct: float
    severity: FindingSeverity = FindingSeverity.MEDIUM
    description: str = ""
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RepairAttemptRecord:
    repair_id: str
    pipeline_execution_id: str
    failure_type: str
    proposed_patch: str
    applied: bool = False
    retest_success: bool = False
    retry_count: int = 1
    max_retries_allowed: int = 3
    approval_token: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ReleaseCandidateRecord:
    candidate_id: str
    version: str
    artifact_id: str
    source_revision_id: str
    stage: ReleaseStage = ReleaseStage.CANDIDATE
    release_notes: str = ""
    approval_token: Optional[str] = None
    approver: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DeploymentHandoffRecord:
    handoff_id: str
    release_candidate_id: str
    target_environment_id: str
    deployment_strategy: str = "DIRECT"
    status: HandoffStatus = HandoffStatus.PENDING
    module43_deployment_id: Optional[str] = None
    verification_evidence: Dict[str, Any] = field(default_factory=dict)
    requested_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
