from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Awaitable, Set
import time
import uuid

class TaskState(Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"

class NodeState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RECOVERING = "RECOVERING"

class FailureCategory(Enum):
    TRANSIENT = "TRANSIENT"
    TIMEOUT = "TIMEOUT"
    DEVICE_UNAVAILABLE = "DEVICE_UNAVAILABLE"
    BROWSER_FAILURE = "BROWSER_FAILURE"
    VISION_FAILURE = "VISION_FAILURE"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    POLICY_BLOCK = "POLICY_BLOCK"
    INVALID_ACTION = "INVALID_ACTION"
    UNEXPECTED_STATE = "UNEXPECTED_STATE"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"

class RecoveryStrategy(Enum):
    RETRY = "RETRY"
    REFRESH = "REFRESH"
    RECONNECT = "RECONNECT"
    RECAPTURE = "RECAPTURE"
    RELOCATE = "RELOCATE"
    REOPEN = "REOPEN"
    RESET_STEP = "RESET_STEP"
    SKIP_OPTIONAL = "SKIP_OPTIONAL"
    ROLLBACK = "ROLLBACK"
    REPLAN = "REPLAN"
    ABORT = "ABORT"

class IdempotencyLevel(Enum):
    SAFE_TO_RETRY = "SAFE_TO_RETRY"                     # Reads, navigations, inspections
    CONDITIONALLY_RETRYABLE = "CONDITIONALLY_RETRYABLE" # Refresh, re-focus
    NOT_SAFE_TO_RETRY = "NOT_SAFE_TO_RETRY"             # Form submits, payments, deletes

class ObservationSource(Enum):
    VISION = "VISION"
    BROWSER_DOM = "BROWSER_DOM"
    ACCESSIBILITY_TREE = "ACCESSIBILITY_TREE"
    ADB_DEVICE_STATE = "ADB_DEVICE_STATE"
    TOOL_RESULT = "TOOL_RESULT"
    SYSTEM_STATE = "SYSTEM_STATE"
    MEMORY = "MEMORY"

@dataclass
class Observation:
    """Unified observation representation across multimodal senses."""
    source: ObservationSource
    timestamp: float = field(default_factory=time.time)
    state: str = ""
    evidence: Any = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class TaskFailure:
    """Structured failure representation with root category and retryability."""
    failure_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str = ""
    node_id: str = ""
    category: FailureCategory = FailureCategory.UNKNOWN
    message: str = ""
    timestamp: float = field(default_factory=time.time)
    evidence: Any = None
    retryable: bool = False
    suggested_recovery: RecoveryStrategy = RecoveryStrategy.ABORT

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay_sec: float = 1.0
    max_delay_sec: float = 10.0
    exponential_backoff: bool = True
    jitter: bool = True
    retryable_categories: Set[FailureCategory] = field(default_factory=lambda: {
        FailureCategory.TRANSIENT,
        FailureCategory.TIMEOUT,
        FailureCategory.NETWORK_FAILURE,
        FailureCategory.UNEXPECTED_STATE
    })

@dataclass
class TaskNode:
    """A single atomic step or checkpoint in the task graph."""
    node_id: str
    name: str
    description: str
    action: Callable[['ExecutionContext'], Awaitable[Any]]
    expected_state: Optional[str] = None
    verifier: Optional[Callable[['ExecutionContext', Any], Awaitable[bool]]] = None
    timeout_sec: float = 30.0
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    idempotency: IdempotencyLevel = IdempotencyLevel.SAFE_TO_RETRY
    required_resources: List[str] = field(default_factory=list)
    state: NodeState = NodeState.PENDING
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    result: Any = None
    error: Optional[TaskFailure] = None

@dataclass
class ExecutionContext:
    """Persistent state and evidence container across task steps."""
    task_id: str
    variables: Dict[str, Any] = field(default_factory=dict)
    observations: List[Observation] = field(default_factory=list)
    tool_results: Dict[str, Any] = field(default_factory=dict)
    failures: List[TaskFailure] = field(default_factory=list)
    resource_locks: List[str] = field(default_factory=list)
    max_observations: int = 50

    def add_observation(self, obs: Observation):
        self.observations.append(obs)
        if len(self.observations) > self.max_observations:
            self.observations.pop(0)

@dataclass
class TaskGraph:
    """Directed acyclic task graph representing nodes, dependencies, and flow."""
    goal: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    nodes: Dict[str, TaskNode] = field(default_factory=dict)
    state: TaskState = TaskState.CREATED
    current_node_id: Optional[str] = None
    deadline_ts: float = 0.0
    task_timeout_sec: float = 300.0
    created_ts: float = field(default_factory=time.time)
    replan_count: int = 0
    max_replans: int = 3
    history: List[Dict[str, Any]] = field(default_factory=list)

    def add_node(self, node: TaskNode):
        self.nodes[node.node_id] = node

    def get_ready_nodes(self) -> List[TaskNode]:
        ready = []
        for n in self.nodes.values():
            if n.state == NodeState.PENDING:
                deps_satisfied = all(
                    self.nodes[d].state == NodeState.COMPLETED
                    for d in n.dependencies if d in self.nodes
                )
                if deps_satisfied:
                    ready.append(n)
        return ready

    def is_complete(self) -> bool:
        return all(n.state == NodeState.COMPLETED or n.state == NodeState.SKIPPED for n in self.nodes.values())

    def has_unrecoverable_failure(self) -> bool:
        return any(n.state == NodeState.FAILED for n in self.nodes.values())

    def log_event(self, event_type: str, details: Dict[str, Any]):
        entry = {
            "timestamp": time.time(),
            "task_id": self.task_id,
            "current_node": self.current_node_id,
            "event": event_type,
            **details
        }
        self.history.append(entry)
