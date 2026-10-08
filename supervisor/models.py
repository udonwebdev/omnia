import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set

class MissionState(Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    REPLANNING = "REPLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"

class SupervisoryState(Enum):
    IDLE = "IDLE"
    SUPERVISING = "SUPERVISING"
    ASSESSING = "ASSESSING"
    DECIDING = "DECIDING"

class SupervisoryDecisionType(Enum):
    CONTINUE = "CONTINUE"
    WAIT = "WAIT"
    PAUSE = "PAUSE"
    RECOVER = "RECOVER"
    REPLAN = "REPLAN"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    ABORT = "ABORT"
    ESCALATE = "ESCALATE"

class DecisionConfidence(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"

class DecisionUrgency(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"

class MissionPriority(Enum):
    CRITICAL = 5
    HIGH = 4
    NORMAL = 3
    LOW = 2
    BACKGROUND = 1

class DeadlineRisk(Enum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    LIKELY_TO_MISS = "LIKELY_TO_MISS"
    MISSED = "MISSED"

class ResourcePressure(Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class StallClassification(Enum):
    ALIVE = "ALIVE"
    ACTIVE = "ACTIVE"
    STALLED = "STALLED"
    NO_PROGRESS = "NO_PROGRESS"
    LOOP = "LOOP"
    OSCILLATION = "OSCILLATION"
    DEGRADED = "DEGRADED"

class MissionPhase(Enum):
    DISCOVERY = "DISCOVERY"
    PLANNING = "PLANNING"
    PREPARATION = "PREPARATION"
    EXECUTION = "EXECUTION"
    VERIFICATION = "VERIFICATION"
    RECOVERY = "RECOVERY"
    COMPLETION = "COMPLETION"

class SupervisorFailureCategory(Enum):
    TRANSIENT = "TRANSIENT"
    RESOURCE = "RESOURCE"
    CAPABILITY = "CAPABILITY"
    DEVICE = "DEVICE"
    NETWORK = "NETWORK"
    BROWSER = "BROWSER"
    VISION = "VISION"
    POLICY = "POLICY"
    SECURITY = "SECURITY"
    LOGIC = "LOGIC"
    DATA = "DATA"
    TIMEOUT = "TIMEOUT"
    STALL = "STALL"
    DEADLOCK = "DEADLOCK"
    UNKNOWN = "UNKNOWN"

VALID_MISSION_TRANSITIONS: Dict[MissionState, Set[MissionState]] = {
    MissionState.CREATED: {MissionState.PLANNING, MissionState.READY, MissionState.RUNNING, MissionState.PAUSED, MissionState.CANCELLED, MissionState.UNKNOWN},
    MissionState.PLANNING: {MissionState.READY, MissionState.RUNNING, MissionState.FAILED, MissionState.AWAITING_APPROVAL, MissionState.CANCELLED},
    MissionState.READY: {MissionState.RUNNING, MissionState.PAUSED, MissionState.CANCELLED},
    MissionState.RUNNING: {
        MissionState.WAITING, MissionState.PAUSED, MissionState.DEGRADED, MissionState.RECOVERING,
        MissionState.REPLANNING, MissionState.AWAITING_APPROVAL, MissionState.COMPLETED,
        MissionState.FAILED, MissionState.ABORTING, MissionState.ABORTED, MissionState.TIMED_OUT, MissionState.CANCELLED
    },
    MissionState.WAITING: {MissionState.RUNNING, MissionState.DEGRADED, MissionState.PAUSED, MissionState.TIMED_OUT, MissionState.CANCELLED},
    MissionState.PAUSED: {MissionState.RUNNING, MissionState.ABORTING, MissionState.ABORTED, MissionState.CANCELLED},
    MissionState.DEGRADED: {MissionState.RECOVERING, MissionState.REPLANNING, MissionState.RUNNING, MissionState.FAILED, MissionState.ABORTING, MissionState.ABORTED, MissionState.CANCELLED},
    MissionState.RECOVERING: {MissionState.RUNNING, MissionState.DEGRADED, MissionState.REPLANNING, MissionState.FAILED, MissionState.ABORTING, MissionState.ABORTED},
    MissionState.REPLANNING: {MissionState.RUNNING, MissionState.READY, MissionState.AWAITING_APPROVAL, MissionState.FAILED, MissionState.ABORTING, MissionState.ABORTED},
    MissionState.AWAITING_APPROVAL: {MissionState.RUNNING, MissionState.PLANNING, MissionState.PAUSED, MissionState.ABORTING, MissionState.ABORTED, MissionState.CANCELLED},
    MissionState.COMPLETED: set(),
    MissionState.FAILED: set(),
    MissionState.ABORTING: {MissionState.ABORTED, MissionState.FAILED},
    MissionState.ABORTED: set(),
    MissionState.TIMED_OUT: set(),
    MissionState.CANCELLED: set(),
    MissionState.UNKNOWN: {MissionState.READY, MissionState.RUNNING, MissionState.PAUSED, MissionState.FAILED, MissionState.ABORTED}
}

@dataclass
class SupervisoryDecision:
    """A structured, evidence-backed decision produced by the Autonomous Supervisor."""
    decision_id: str = field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:8]}")
    mission_id: str = ""
    task_id: Optional[str] = None
    decision: SupervisoryDecisionType = SupervisoryDecisionType.CONTINUE
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: DecisionConfidence = DecisionConfidence.HIGH
    urgency: DecisionUrgency = DecisionUrgency.NORMAL
    recommended_action: str = ""
    policy_reference: Optional[str] = None
    created_at: float = field(default_factory=time.time)

@dataclass
class MissionTelemetry:
    """Supervisory performance and progress metrics for a mission."""
    mission_id: str
    start_time: float = field(default_factory=time.time)
    elapsed_sec: float = 0.0
    progress_percentage: float = 0.0
    completed_nodes: int = 0
    total_nodes: int = 0
    recovery_count: int = 0
    replan_count: int = 0
    stall_count: int = 0
    anomalies_detected: int = 0
    deadline_status: DeadlineRisk = DeadlineRisk.ON_TRACK
    resource_pressure: ResourcePressure = ResourcePressure.NORMAL
    active_tasks: List[str] = field(default_factory=list)

@dataclass
class Mission:
    """Authoritative high-level mission model representing long-running autonomous objectives."""
    mission_id: str = field(default_factory=lambda: f"msn_{uuid.uuid4().hex[:8]}")
    objective: str = ""
    status: MissionState = MissionState.CREATED
    task_ids: List[str] = field(default_factory=list)
    active_task_id: Optional[str] = None
    plan_version: int = 1
    priority: MissionPriority = MissionPriority.NORMAL
    deadline_ts: float = field(default_factory=lambda: time.time() + 3600.0)
    constraints: List[str] = field(default_factory=list)
    risk_profile: str = "NORMAL"
    health: str = "HEALTHY"
    progress: float = 0.0
    phase: MissionPhase = MissionPhase.DISCOVERY
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # Recovery & Supervision Budget
    retries_used: int = 0
    max_retries: int = 5
    recovery_attempts_used: int = 0
    max_recovery_attempts: int = 3
    replans_used: int = 0
    max_replans: int = 3
    consecutive_failures: int = 0
    max_consecutive_failures: int = 3
    recovery_time_spent_sec: float = 0.0
    max_recovery_time_sec: float = 180.0

    # Timing and windows
    expected_progress_interval_sec: float = 30.0
    warning_threshold_sec: float = 60.0
    hard_timeout_sec: float = 300.0

    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_transition_to(self, new_state: MissionState) -> bool:
        """Validates if transition from current status to new_state is allowed."""
        if self.status == new_state:
            return True
        allowed = VALID_MISSION_TRANSITIONS.get(self.status, set())
        return new_state in allowed

    def transition_to(self, new_state: MissionState, reason: str = "") -> bool:
        """Applies state transition if valid, updating timestamp."""
        if not self.can_transition_to(new_state):
            return False
        self.status = new_state
        self.updated_at = time.time()
        return True

    def is_terminal(self) -> bool:
        """Returns True if the mission has reached a terminal state."""
        return self.status in {
            MissionState.COMPLETED,
            MissionState.FAILED,
            MissionState.ABORTED,
            MissionState.TIMED_OUT,
            MissionState.CANCELLED
        }

    def has_recovery_budget(self) -> bool:
        """Checks if mission has remaining autonomous recovery budget."""
        if self.recovery_attempts_used >= self.max_recovery_attempts:
            return False
        if self.replans_used >= self.max_replans:
            return False
        if self.consecutive_failures >= self.max_consecutive_failures:
            return False
        if self.recovery_time_spent_sec >= self.max_recovery_time_sec:
            return False
        return True
