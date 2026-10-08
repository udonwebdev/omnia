import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set

class ScheduleState(Enum):
    CREATED = "CREATED"
    ADMITTED = "ADMITTED"
    WAITING_RESOURCE = "WAITING_RESOURCE"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_CAPABILITY = "WAITING_CAPABILITY"
    WAITING_POLICY = "WAITING_POLICY"
    DEFERRED = "DEFERRED"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    PREEMPTED = "PREEMPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class ResourceAccessMode(Enum):
    EXCLUSIVE = "EXCLUSIVE"
    SHARED = "SHARED"
    READ_ONLY = "READ_ONLY"
    WRITE = "WRITE"
    APPEND = "APPEND"
    CONCURRENT_LIMITED = "CONCURRENT_LIMITED"

class ReservationState(Enum):
    REQUESTED = "REQUESTED"
    RESERVED = "RESERVED"
    ACTIVE = "ACTIVE"
    RELEASING = "RELEASING"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    LOST = "LOST"

class SchedulingPriority(Enum):
    CRITICAL = 5
    HIGH = 4
    NORMAL = 3
    LOW = 2
    BACKGROUND = 1

class PreemptionPolicy(Enum):
    NON_PREEMPTIBLE = "NON_PREEMPTIBLE"
    SAFE_TO_PAUSE = "SAFE_TO_PAUSE"
    CHECKPOINT_PREEMPTIBLE = "CHECKPOINT_PREEMPTIBLE"
    CANCEL_AND_RESTART = "CANCEL_AND_RESTART"

class SchedulingDecisionType(Enum):
    ADMIT = "ADMIT"
    DEFER = "DEFER"
    WAIT = "WAIT"
    PREEMPT = "PREEMPT"
    REJECT = "REJECT"
    RESCHEDULE = "RESCHEDULE"

class ResourceConflictType(Enum):
    EXCLUSIVE_CONFLICT = "EXCLUSIVE_CONFLICT"
    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"
    DEVICE_BUSY = "DEVICE_BUSY"
    BROWSER_BUSY = "BROWSER_BUSY"
    PROVIDER_BUSY = "PROVIDER_BUSY"
    DEPENDENCY_BLOCKED = "DEPENDENCY_BLOCKED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    APPROVAL_BLOCKED = "APPROVAL_BLOCKED"
    DEADLINE_CONFLICT = "DEADLINE_CONFLICT"
    PRIORITY_CONFLICT = "PRIORITY_CONFLICT"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"

class SchedulerHealth(Enum):
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    OVERLOADED = "OVERLOADED"
    BLOCKED = "BLOCKED"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"

class SchedulerPressure(Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

@dataclass
class ResourceRequirement:
    """Requirement for a specific hardware, software, or logical resource."""
    resource_id: str
    resource_type: str = "GENERIC"
    access_mode: ResourceAccessMode = ResourceAccessMode.EXCLUSIVE
    amount: float = 1.0
    optional: bool = False

@dataclass
class ResourceCapacity:
    """Capacity descriptor for a physical or logical resource."""
    resource_id: str
    resource_type: str
    total_capacity: float = 1.0
    allocated_capacity: float = 0.0
    reserved_capacity: float = 0.0
    overcommit_ratio: float = 1.0
    exclusive_owner: Optional[str] = None
    shared_owners: Set[str] = field(default_factory=set)

    @property
    def available_capacity(self) -> float:
        return max(0.0, (self.total_capacity * self.overcommit_ratio) - (self.allocated_capacity + self.reserved_capacity))

    def can_accommodate(self, mode: ResourceAccessMode, amount: float = 1.0) -> bool:
        if mode == ResourceAccessMode.EXCLUSIVE:
            return self.exclusive_owner is None and len(self.shared_owners) == 0 and self.available_capacity >= amount
        else:
            return self.exclusive_owner is None and self.available_capacity >= amount

@dataclass
class ResourceReservation:
    """Atomic reservation record for a scheduled execution step."""
    reservation_id: str = field(default_factory=lambda: f"rsv_{uuid.uuid4().hex[:8]}")
    schedule_id: str = ""
    mission_id: Optional[str] = None
    task_id: str = ""
    task_node_id: Optional[str] = None
    resource_id: str = ""
    resource_type: str = "GENERIC"
    access_mode: ResourceAccessMode = ResourceAccessMode.EXCLUSIVE
    amount: float = 1.0
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 60.0)
    state: ReservationState = ReservationState.REQUESTED
    lease_id: Optional[str] = None
    lease_heartbeat: Optional[float] = None
    release_reason: Optional[str] = None

    def is_expired(self, now: Optional[float] = None) -> bool:
        current = now or time.time()
        return current >= self.expires_at

@dataclass
class ExecutionSlot:
    """Execution worker slot managed by the scheduler."""
    slot_id: str
    slot_name: str
    worker_type: str = "LOCAL_WORKER"
    capacity: float = 1.0
    supported_capabilities: List[str] = field(default_factory=list)
    health: str = "HEALTHY"
    current_schedule_id: Optional[str] = None
    current_task_id: Optional[str] = None
    updated_at: float = field(default_factory=time.time)

    @property
    def is_idle(self) -> bool:
        return self.current_schedule_id is None and self.health == "HEALTHY"

@dataclass
class ScheduleRequest:
    """Request submitted to the scheduler for execution admission and resource allocation."""
    schedule_id: str = field(default_factory=lambda: f"sch_{uuid.uuid4().hex[:8]}")
    mission_id: Optional[str] = None
    task_id: str = ""
    task_node_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    ready_at: float = field(default_factory=time.time)
    deadline: Optional[float] = None
    priority: SchedulingPriority = SchedulingPriority.NORMAL
    urgency: str = "NORMAL"
    risk_level: str = "LOW"
    estimated_duration_sec: float = 10.0
    preemption_policy: PreemptionPolicy = PreemptionPolicy.SAFE_TO_PAUSE
    parallelizable: bool = True

    required_resources: List[ResourceRequirement] = field(default_factory=list)
    required_capabilities: List[str] = field(default_factory=list)
    required_devices: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

    state: ScheduleState = ScheduleState.CREATED
    assigned_slot_id: Optional[str] = None
    priority_score: float = 0.0
    wait_count: int = 0
    fairness_debt: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.state in {
            ScheduleState.COMPLETED,
            ScheduleState.FAILED,
            ScheduleState.REJECTED,
            ScheduleState.CANCELLED
        }

@dataclass
class SchedulingDecision:
    """Formal, explainable decision produced by the scheduler."""
    decision_id: str = field(default_factory=lambda: f"sd_{uuid.uuid4().hex[:8]}")
    schedule_id: str = ""
    decision: SchedulingDecisionType = SchedulingDecisionType.WAIT
    reason: str = ""
    priority_score: float = 0.0
    resource_score: float = 0.0
    deadline_score: float = 0.0
    fairness_score: float = 0.0
    selected_slot_id: Optional[str] = None
    selected_resources: List[str] = field(default_factory=list)
    conflicts: List[ResourceConflictType] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

@dataclass
class SchedulerTelemetry:
    """Structured telemetry snapshot from the scheduler."""
    health: SchedulerHealth = SchedulerHealth.READY
    pressure: SchedulerPressure = SchedulerPressure.NORMAL
    ready_queue_depth: int = 0
    waiting_queue_depth: int = 0
    active_schedules: int = 0
    total_slots: int = 0
    idle_slots: int = 0
    active_reservations: int = 0
    deadlock_count: int = 0
    starvation_count: int = 0
    preemption_count: int = 0
    average_wait_time_sec: float = 0.0
