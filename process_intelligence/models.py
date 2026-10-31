"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Domain Models, Enums, and Value Objects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ProcessEventType(str, enum.Enum):
    TASK_START = "TASK_START"
    TASK_COMPLETE = "TASK_COMPLETE"
    TASK_FAIL = "TASK_FAIL"
    TASK_RETRY = "TASK_RETRY"
    WAIT_ENTER = "WAIT_ENTER"
    WAIT_EXIT = "WAIT_EXIT"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    APPROVAL_GRANT = "APPROVAL_GRANT"
    APPROVAL_REJECT = "APPROVAL_REJECT"
    GATEWAY_BRANCH = "GATEWAY_BRANCH"


class TraceStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class BottleneckType(str, enum.Enum):
    QUEUE_WAITING = "QUEUE_WAITING"
    APPROVAL_DELAY = "APPROVAL_DELAY"
    RESOURCE_CONTENTION = "RESOURCE_CONTENTION"
    SERIALIZED_INDEPENDENT_TASKS = "SERIALIZED_INDEPENDENT_TASKS"
    UNRELIABLE_DEPENDENCY = "UNRELIABLE_DEPENDENCY"
    RETRY_LOOP = "RETRY_LOOP"


class FindingSeverity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DeviationType(str, enum.Enum):
    MISSING_REQUIRED_STEP = "MISSING_REQUIRED_STEP"
    SKIPPED_APPROVAL_GATE = "SKIPPED_APPROVAL_GATE"
    UNAUTHORIZED_PATH = "UNAUTHORIZED_PATH"
    OUT_OF_ORDER_EXECUTION = "OUT_OF_ORDER_EXECUTION"
    POLICY_VIOLATION = "POLICY_VIOLATION"


class OptimizationType(str, enum.Enum):
    PARALLELIZE_INDEPENDENT_TASKS = "PARALLELIZE_INDEPENDENT_TASKS"
    ELIMINATE_REDUNDANT_STEP = "ELIMINATE_REDUNDANT_STEP"
    IMPROVE_RETRY_POLICY = "IMPROVE_RETRY_POLICY"
    OPTIMIZE_TASK_ORDER = "OPTIMIZE_TASK_ORDER"
    SAFE_CACHING = "SAFE_CACHING"
    BATCH_OPERATIONS = "BATCH_OPERATIONS"


class OptimizationStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    SIMULATED = "SIMULATED"
    APPROVED = "APPROVED"
    DEPLOYED = "DEPLOYED"
    ROLLED_BACK = "ROLLED_BACK"


class ExperimentStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    CONCLUDED = "CONCLUDED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class ProcessEventRecord:
    event_id: str
    trace_id: str
    workflow_id: str
    task_id: str
    event_type: ProcessEventType
    timestamp: str
    parent_task_id: Optional[str] = None
    duration_sec: float = 0.0
    waiting_time_sec: float = 0.0
    error_category: Optional[str] = None
    resource_id: Optional[str] = None
    metadata_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionTraceRecord:
    trace_id: str
    workflow_id: str
    execution_id: str
    status: TraceStatus
    started_at: str
    completed_at: Optional[str] = None
    total_duration_sec: float = 0.0
    total_waiting_sec: float = 0.0
    total_active_sec: float = 0.0
    retry_count: int = 0
    failure_count: int = 0
    is_complete: bool = False
    events_count: int = 0


@dataclass
class ProcessGraphNode:
    node_id: str
    task_name: str
    node_type: str  # ACTIVITY, GATEWAY, APPROVAL, WAIT, TERMINAL
    execution_count: int = 0
    total_active_duration_sec: float = 0.0
    total_waiting_duration_sec: float = 0.0
    failure_count: int = 0


@dataclass
class ProcessGraphEdge:
    source_node_id: str
    target_node_id: str
    transition_count: int = 0
    avg_transition_latency_sec: float = 0.0


@dataclass
class ProcessGraphRecord:
    graph_id: str
    workflow_id: str
    version: int
    nodes: Dict[str, ProcessGraphNode] = field(default_factory=dict)
    edges: List[ProcessGraphEdge] = field(default_factory=list)
    common_paths: List[List[str]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class WorkflowPerformanceSnapshot:
    snapshot_id: str
    workflow_id: str
    trace_count: int
    mean_duration_sec: float
    median_duration_sec: float
    p90_duration_sec: float
    p95_duration_sec: float
    p99_duration_sec: float
    mean_waiting_time_sec: float
    active_to_wait_ratio: float
    overall_failure_rate: float
    retry_frequency_per_trace: float
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class BottleneckFinding:
    finding_id: str
    workflow_id: str
    component_id: str
    bottleneck_type: BottleneckType
    severity: FindingSeverity
    estimated_delay_sec: float
    frequency_ratio: float
    confidence: float
    potential_causes: List[str] = field(default_factory=list)
    recommended_action: str = ""
    supporting_trace_ids: List[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProcessDeviationRecord:
    deviation_id: str
    trace_id: str
    workflow_id: str
    deviation_type: DeviationType
    severity: FindingSeverity
    description: str
    policy_rule_violated: Optional[str] = None
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class FailurePatternRecord:
    pattern_id: str
    workflow_id: str
    error_type: str
    affected_tasks: List[str] = field(default_factory=list)
    occurrence_count: int = 0
    total_rework_duration_sec: float = 0.0
    estimated_rework_cost: float = 0.0
    identified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class OptimizationCandidate:
    candidate_id: str
    workflow_id: str
    current_version: int
    optimization_type: OptimizationType
    title: str
    description: str
    current_behavior: str
    proposed_behavior: str
    expected_time_reduction_pct: float
    expected_cost_reduction_pct: float
    reversibility_score: float
    validation_strategy: str
    rollback_strategy: str
    supporting_evidence: List[str] = field(default_factory=list)
    status: OptimizationStatus = OptimizationStatus.PROPOSED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class OptimizationExperimentRecord:
    experiment_id: str
    candidate_id: str
    workflow_id: str
    baseline_trace_count: int
    target_trace_count: int
    guardrail_metrics: Dict[str, float] = field(default_factory=dict)
    observed_improvement_pct: float = 0.0
    is_guardrail_breached: bool = False
    status: ExperimentStatus = ExperimentStatus.RUNNING
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None


@dataclass
class WorkflowChangeGovernanceRecord:
    governance_id: str
    workflow_id: str
    candidate_id: str
    from_version: int
    to_version: int
    approved_by: Optional[str] = None
    approval_token: Optional[str] = None
    change_status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, APPROVED, DEPLOYED, REJECTED, ROLLED_BACK
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
