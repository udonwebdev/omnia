"""
Omnia Module 33: Adaptive Learning & Model Lifecycle Governance Models
Strongly typed domain models, enums, dataclasses, and lifecycle states.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class SignalType(str, Enum):
    TASK_COMPLETION = "TASK_COMPLETION"
    TASK_FAILURE = "TASK_FAILURE"
    TASK_RECOVERY = "TASK_RECOVERY"
    FORECAST_EVALUATION = "FORECAST_EVALUATION"
    OPERATOR_FEEDBACK = "OPERATOR_FEEDBACK"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    SECURITY_BLOCK = "SECURITY_BLOCK"
    DRIFT_ALERT = "DRIFT_ALERT"


class SignalQualityStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class AttributionConfidence(str, Enum):
    DIRECTLY_OBSERVED = "DIRECTLY_OBSERVED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"
    USER_REPORTED = "USER_REPORTED"
    MODEL_INFERRED = "MODEL_INFERRED"
    CORRELATED = "CORRELATED"
    UNKNOWN = "UNKNOWN"


class DatasetPurpose(str, Enum):
    TRAINING = "TRAINING"
    VALIDATION = "VALIDATION"
    OFFLINE_EVALUATION = "OFFLINE_EVALUATION"
    SHADOW_EVALUATION = "SHADOW_EVALUATION"
    DRIFT_MONITORING = "DRIFT_MONITORING"
    BENCHMARK_TESTING = "BENCHMARK_TESTING"


class ModelLifecycleStatus(str, Enum):
    DRAFT = "DRAFT"
    EVALUATING = "EVALUATING"
    REJECTED = "REJECTED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    STAGING = "STAGING"
    SHADOW = "SHADOW"
    CANARY = "CANARY"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"
    REVOKED = "REVOKED"


class ExperimentType(str, Enum):
    OFFLINE_BENCHMARK = "OFFLINE_BENCHMARK"
    DETERMINISTIC_SIMULATION = "DETERMINISTIC_SIMULATION"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    SHADOW_MODE = "SHADOW_MODE"
    CONTROLLED_PARAMETER = "CONTROLLED_PARAMETER"
    CANARY_ROLLOUT = "CANARY_ROLLOUT"


class ExperimentStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class RolloutStage(str, Enum):
    OFFLINE = "OFFLINE"
    SHADOW = "SHADOW"
    STAGING = "STAGING"
    CANARY = "CANARY"
    PRODUCTION = "PRODUCTION"


class RolloutStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    HALTED = "HALTED"
    ROLLED_BACK = "ROLLED_BACK"


class DriftType(str, Enum):
    FEATURE_DRIFT = "FEATURE_DRIFT"
    CONCEPT_DRIFT = "CONCEPT_DRIFT"
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"
    CALIBRATION_DEGRADATION = "CALIBRATION_DEGRADATION"
    DATA_QUALITY_DEGRADATION = "DATA_QUALITY_DEGRADATION"


class DriftSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class LearningSignal:
    signal_id: str
    signal_type: SignalType
    source_module: str
    source_record_id: str
    event_time: float
    observation_time: float
    outcome_status: str  # e.g. "SUCCESS", "FAILED", "ACCURATE", "DRIFT"
    metrics: Dict[str, float] = field(default_factory=dict)
    schema_version: str = "1.0.0"
    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    experiment_id: Optional[str] = None
    correlation_id: Optional[str] = None
    model_version: Optional[str] = None
    strategy_id: Optional[str] = None
    is_verified: bool = False
    verification_method: Optional[str] = None
    quality_status: SignalQualityStatus = SignalQualityStatus.ACCEPTED
    exclusion_reason: Optional[str] = None
    is_eligible_for_eval: bool = True
    is_eligible_for_training: bool = True
    provenance_hash: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value if isinstance(self.signal_type, SignalType) else str(self.signal_type),
            "source_module": self.source_module,
            "source_record_id": self.source_record_id,
            "event_time": self.event_time,
            "observation_time": self.observation_time,
            "outcome_status": self.outcome_status,
            "metrics": self.metrics,
            "schema_version": self.schema_version,
            "mission_id": self.mission_id,
            "task_id": self.task_id,
            "experiment_id": self.experiment_id,
            "correlation_id": self.correlation_id,
            "model_version": self.model_version,
            "strategy_id": self.strategy_id,
            "is_verified": self.is_verified,
            "verification_method": self.verification_method,
            "quality_status": self.quality_status.value if isinstance(self.quality_status, SignalQualityStatus) else str(self.quality_status),
            "exclusion_reason": self.exclusion_reason,
            "is_eligible_for_eval": self.is_eligible_for_eval,
            "is_eligible_for_training": self.is_eligible_for_training,
            "provenance_hash": self.provenance_hash,
            "created_at": self.created_at,
        }


@dataclass
class LearningDataset:
    dataset_id: str
    version: str
    purpose: DatasetPurpose
    time_window_start: float
    time_window_end: float
    sample_count: int
    content_digest: str
    schema_version: str = "1.0.0"
    manifest: Dict[str, Any] = field(default_factory=dict)
    inclusion_rules: List[str] = field(default_factory=list)
    features_schema: Dict[str, Any] = field(default_factory=dict)
    known_limitations: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "purpose": self.purpose.value if isinstance(self.purpose, DatasetPurpose) else str(self.purpose),
            "time_window_start": self.time_window_start,
            "time_window_end": self.time_window_end,
            "sample_count": self.sample_count,
            "content_digest": self.content_digest,
            "schema_version": self.schema_version,
            "manifest": self.manifest,
            "inclusion_rules": self.inclusion_rules,
            "features_schema": self.features_schema,
            "known_limitations": self.known_limitations,
            "created_at": self.created_at,
        }


@dataclass
class ModelVersion:
    model_id: str
    version_id: str
    model_family: str
    artifact_ref: str
    artifact_digest: str
    feature_schema_version: str = "1.0.0"
    risk_level: str = "LOW"
    status: ModelLifecycleStatus = ModelLifecycleStatus.DRAFT
    evaluation_summary: Dict[str, Any] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    created_by: str = "system"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version_id": self.version_id,
            "model_family": self.model_family,
            "artifact_ref": self.artifact_ref,
            "artifact_digest": self.artifact_digest,
            "feature_schema_version": self.feature_schema_version,
            "risk_level": self.risk_level,
            "status": self.status.value if isinstance(self.status, ModelLifecycleStatus) else str(self.status),
            "evaluation_summary": self.evaluation_summary,
            "limitations": self.limitations,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ExperimentConfig:
    experiment_id: str
    name: str
    hypothesis: str
    experiment_type: ExperimentType
    baseline_version: str
    candidate_version: str
    dataset_id: str
    primary_metric: str
    min_sample_size: int = 20
    success_threshold: float = 0.05
    max_regression_threshold: float = 0.02
    protocol: Dict[str, Any] = field(default_factory=dict)
    budget: Dict[str, Any] = field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.CREATED
    results: Dict[str, Any] = field(default_factory=dict)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "hypothesis": self.hypothesis,
            "experiment_type": self.experiment_type.value if isinstance(self.experiment_type, ExperimentType) else str(self.experiment_type),
            "baseline_version": self.baseline_version,
            "candidate_version": self.candidate_version,
            "dataset_id": self.dataset_id,
            "primary_metric": self.primary_metric,
            "min_sample_size": self.min_sample_size,
            "success_threshold": self.success_threshold,
            "max_regression_threshold": self.max_regression_threshold,
            "protocol": self.protocol,
            "budget": self.budget,
            "status": self.status.value if isinstance(self.status, ExperimentStatus) else str(self.status),
            "results": self.results,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
        }


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    score: float
    threshold: float
    reason: str
    is_mandatory: bool = True
    evaluated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "passed": self.passed,
            "score": self.score,
            "threshold": self.threshold,
            "reason": self.reason,
            "is_mandatory": self.is_mandatory,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class PromotionRequest:
    request_id: str
    candidate_id: str
    candidate_version: str
    baseline_version: str
    risk_level: str = "LOW"
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    experiment_id: Optional[str] = None
    gate_results: List[GateResult] = field(default_factory=list)
    approval_request_id: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[float] = None
    rejection_reason: Optional[str] = None
    target_rollout_stage: RolloutStage = RolloutStage.CANARY
    current_rollout_stage: RolloutStage = RolloutStage.OFFLINE
    rollback_target_version: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def is_eligible_for_promotion(self) -> bool:
        if not self.gate_results:
            return False
        return all(g.passed for g in self.gate_results if g.is_mandatory)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "candidate_id": self.candidate_id,
            "candidate_version": self.candidate_version,
            "baseline_version": self.baseline_version,
            "risk_level": self.risk_level,
            "status": self.status,
            "experiment_id": self.experiment_id,
            "gate_results": [g.to_dict() for g in self.gate_results],
            "approval_request_id": self.approval_request_id,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "rejection_reason": self.rejection_reason,
            "target_rollout_stage": self.target_rollout_stage.value if isinstance(self.target_rollout_stage, RolloutStage) else str(self.target_rollout_stage),
            "current_rollout_stage": self.current_rollout_stage.value if isinstance(self.current_rollout_stage, RolloutStage) else str(self.current_rollout_stage),
            "rollback_target_version": self.rollback_target_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class RolloutRecord:
    rollout_id: str
    request_id: str
    candidate_version: str
    baseline_version: str
    current_stage: RolloutStage
    canary_traffic_pct: float = 0.0
    status: RolloutStatus = RolloutStatus.IN_PROGRESS
    metrics_summary: Dict[str, float] = field(default_factory=dict)
    halt_reason: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rollout_id": self.rollout_id,
            "request_id": self.request_id,
            "candidate_version": self.candidate_version,
            "baseline_version": self.baseline_version,
            "current_stage": self.current_stage.value if isinstance(self.current_stage, RolloutStage) else str(self.current_stage),
            "canary_traffic_pct": self.canary_traffic_pct,
            "status": self.status.value if isinstance(self.status, RolloutStatus) else str(self.status),
            "metrics_summary": self.metrics_summary,
            "halt_reason": self.halt_reason,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
        }


@dataclass
class DriftRecord:
    record_id: str
    model_id: str
    version_id: str
    drift_type: DriftType
    feature_or_metric: str
    baseline_value: float
    observed_value: float
    drift_metric_value: float
    threshold: float
    severity: DriftSeverity = DriftSeverity.LOW
    recommendation: str = "CONTINUE_MONITORING"
    assessed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "model_id": self.model_id,
            "version_id": self.version_id,
            "drift_type": self.drift_type.value if isinstance(self.drift_type, DriftType) else str(self.drift_type),
            "feature_or_metric": self.feature_or_metric,
            "baseline_value": self.baseline_value,
            "observed_value": self.observed_value,
            "drift_metric_value": self.drift_metric_value,
            "threshold": self.threshold,
            "severity": self.severity.value if isinstance(self.severity, DriftSeverity) else str(self.severity),
            "recommendation": self.recommendation,
            "assessed_at": self.assessed_at,
        }


@dataclass
class ParameterRecommendation:
    recommendation_id: str
    parameter_key: str
    current_value: Any
    proposed_value: Any
    supporting_evidence: str
    baseline_comparison: str
    expected_benefit: float
    uncertainty: float
    potential_regressions: List[str]
    required_authorization: str
    expires_at: float
    status: str = "PROPOSED"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "parameter_key": self.parameter_key,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "supporting_evidence": self.supporting_evidence,
            "baseline_comparison": self.baseline_comparison,
            "expected_benefit": self.expected_benefit,
            "uncertainty": self.uncertainty,
            "potential_regressions": self.potential_regressions,
            "required_authorization": self.required_authorization,
            "expires_at": self.expires_at,
            "status": self.status,
            "created_at": self.created_at,
        }
