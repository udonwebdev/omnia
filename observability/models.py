"""
OMNIA Module 36: Autonomous Observability, Diagnostics & Self-Healing Models
Provides typed data contracts for metrics, traces, health contracts, failure taxonomy,
diagnostic hypotheses, remediation actions, and recovery verification.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class ComponentHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    RECOVERING = "RECOVERING"
    MAINTENANCE = "MAINTENANCE"


class HealthCheckType(str, Enum):
    LIVENESS = "LIVENESS"
    READINESS = "READINESS"
    FUNCTIONAL = "FUNCTIONAL"
    DEEP_DIAGNOSTIC = "DEEP_DIAGNOSTIC"
    RECOVERY_VERIFICATION = "RECOVERY_VERIFICATION"


class DependencyType(str, Enum):
    HARD = "HARD"         # Failure in dependency causes total failure
    SOFT = "SOFT"         # Failure in dependency causes degradation
    OPTIONAL = "OPTIONAL" # Failure in dependency causes minor feature loss


class FailureCategory(str, Enum):
    PROCESS_FAILURE = "PROCESS_FAILURE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    DATABASE_FAILURE = "DATABASE_FAILURE"
    EVENT_PIPELINE_FAILURE = "EVENT_PIPELINE_FAILURE"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    EXTERNAL_PROVIDER_FAILURE = "EXTERNAL_PROVIDER_FAILURE"
    DATA_INTEGRITY_FAILURE = "DATA_INTEGRITY_FAILURE"
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"
    DISTRIBUTED_COORDINATION_FAILURE = "DISTRIBUTED_COORDINATION_FAILURE"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


class RemediationAutonomyLevel(int, Enum):
    LEVEL_0_OBSERVE = 0
    LEVEL_1_DIAGNOSE = 1
    LEVEL_2_RECOMMEND = 2
    LEVEL_3_LOW_RISK_AUTO = 3
    LEVEL_4_APPROVAL_REQUIRED = 4
    LEVEL_5_EMERGENCY_POLICY = 5


class RecoveryVerificationStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    VERIFIED_RECOVERED = "VERIFIED_RECOVERED"
    PARTIALLY_RECOVERED = "PARTIALLY_RECOVERED"
    FAILED = "FAILED"
    ESCALATION_REQUIRED = "ESCALATION_REQUIRED"


@dataclass
class OperationalMetric:
    metric_id: str
    component_id: str
    metric_name: str
    value: float
    unit: str
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "component_id": self.component_id,
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp,
            "labels": self.labels,
        }


@dataclass
class TraceSpan:
    trace_id: str
    span_id: str
    operation_name: str
    component_id: str
    parent_span_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: float = 0.0
    status: str = "OK"  # "OK" or "ERROR"
    tags: Dict[str, str] = field(default_factory=dict)
    error_message: Optional[str] = None

    def finish(self, status: str = "OK", error: Optional[str] = None) -> None:
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000.0, 2)
        self.status = status
        self.error_message = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "operation_name": self.operation_name,
            "component_id": self.component_id,
            "parent_span_id": self.parent_span_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "tags": self.tags,
            "error_message": self.error_message,
        }


@dataclass
class ComponentHealthRecord:
    component_id: str
    component_name: str
    module_ownership: str
    version: str = "1.0.0"
    current_status: ComponentHealthStatus = ComponentHealthStatus.UNKNOWN
    status_message: str = "Initialized"
    critical_dependencies: List[str] = field(default_factory=list)
    last_check_timestamp: Optional[float] = None
    last_healthy_timestamp: Optional[float] = None
    last_failure_timestamp: Optional[float] = None
    consecutive_failures: int = 0
    liveness_ok: bool = False
    readiness_ok: bool = False
    functional_ok: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_name": self.component_name,
            "module_ownership": self.module_ownership,
            "version": self.version,
            "current_status": self.current_status.value if isinstance(self.current_status, ComponentHealthStatus) else str(self.current_status),
            "status_message": self.status_message,
            "critical_dependencies": self.critical_dependencies,
            "last_check_timestamp": self.last_check_timestamp,
            "last_healthy_timestamp": self.last_healthy_timestamp,
            "last_failure_timestamp": self.last_failure_timestamp,
            "consecutive_failures": self.consecutive_failures,
            "liveness_ok": self.liveness_ok,
            "readiness_ok": self.readiness_ok,
            "functional_ok": self.functional_ok,
        }


@dataclass
class HealthCheckDefinition:
    check_id: str
    target_component_id: str
    name: str
    check_type: HealthCheckType
    interval_seconds: float = 30.0
    timeout_seconds: float = 5.0
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "target_component_id": self.target_component_id,
            "name": self.name,
            "check_type": self.check_type.value if isinstance(self.check_type, HealthCheckType) else str(self.check_type),
            "interval_seconds": self.interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


@dataclass
class InfrastructureDependencyEdge:
    edge_id: str
    source_component_id: str
    target_component_id: str  # source depends on target
    dependency_type: DependencyType
    criticality: float = 1.0  # 0.0 to 1.0
    failure_propagation_probability: float = 0.85

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_component_id": self.source_component_id,
            "target_component_id": self.target_component_id,
            "dependency_type": self.dependency_type.value if isinstance(self.dependency_type, DependencyType) else str(self.dependency_type),
            "criticality": self.criticality,
            "failure_propagation_probability": self.failure_propagation_probability,
        }


@dataclass
class DiagnosticHypothesis:
    hypothesis_id: str
    suspected_component_id: str
    failure_category: FailureCategory
    confidence: float  # 0.0 to 1.0
    explanation: str
    supporting_evidence: List[str]
    contradicting_evidence: List[str] = field(default_factory=list)
    cascading_impact_components: List[str] = field(default_factory=list)
    recommended_remediation_action: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "suspected_component_id": self.suspected_component_id,
            "failure_category": self.failure_category.value if isinstance(self.failure_category, FailureCategory) else str(self.failure_category),
            "confidence": self.confidence,
            "explanation": self.explanation,
            "supporting_evidence": self.supporting_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "cascading_impact_components": self.cascading_impact_components,
            "recommended_remediation_action": self.recommended_remediation_action,
            "timestamp": self.timestamp,
        }


@dataclass
class InfrastructureRemediationAction:
    action_id: str
    target_component_id: str
    proposed_action: str  # e.g., "reconnect_service", "clear_cache", "restart_worker", "rebuild_index"
    failure_category: FailureCategory
    reason: str
    autonomy_level: RemediationAutonomyLevel
    status: RecoveryVerificationStatus = RecoveryVerificationStatus.NOT_STARTED
    is_reversible: bool = True
    approval_request_id: Optional[str] = None
    approval_token: Optional[str] = None
    retry_budget: int = 2
    retry_count: int = 0
    verification_window_seconds: float = 10.0
    created_at: float = field(default_factory=time.time)
    executed_at: Optional[float] = None
    verified_at: Optional[float] = None
    verification_evidence: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "target_component_id": self.target_component_id,
            "proposed_action": self.proposed_action,
            "failure_category": self.failure_category.value if isinstance(self.failure_category, FailureCategory) else str(self.failure_category),
            "reason": self.reason,
            "autonomy_level": int(self.autonomy_level),
            "status": self.status.value if isinstance(self.status, RecoveryVerificationStatus) else str(self.status),
            "is_reversible": self.is_reversible,
            "approval_request_id": self.approval_request_id,
            "approval_token": self.approval_token,
            "retry_budget": self.retry_budget,
            "retry_count": self.retry_count,
            "verification_window_seconds": self.verification_window_seconds,
            "created_at": self.created_at,
            "executed_at": self.executed_at,
            "verified_at": self.verified_at,
            "verification_evidence": self.verification_evidence,
            "error_message": self.error_message,
        }
