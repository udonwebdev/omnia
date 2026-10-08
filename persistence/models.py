import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

class RecoveryCondition(Enum):
    RECOVERABLE = "RECOVERABLE"
    UNCERTAIN = "UNCERTAIN"
    STALE = "STALE"
    CORRUPTED = "CORRUPTED"
    UNSAFE_TO_RESUME = "UNSAFE_TO_RESUME"

class CheckpointValidity(Enum):
    VALID = "VALID"
    STALE = "STALE"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"

class ResumeStrategy(Enum):
    RESUME_FROM_CHECKPOINT = "RESUME_FROM_CHECKPOINT"
    REVALIDATE_AND_RESUME = "REVALIDATE_AND_RESUME"
    ROLLBACK_TO_CHECKPOINT = "ROLLBACK_TO_CHECKPOINT"
    REPLAN_FROM_CURRENT_STATE = "REPLAN_FROM_CURRENT_STATE"
    ABORT_TASK = "ABORT_TASK"

class CheckpointPolicy(Enum):
    CHECKPOINT_TASK_START = "CHECKPOINT_TASK_START"
    CHECKPOINT_NODE_COMPLETE = "CHECKPOINT_NODE_COMPLETE"
    CHECKPOINT_STATE_CHANGE = "CHECKPOINT_STATE_CHANGE"
    CHECKPOINT_BEFORE_RISKY_ACTION = "CHECKPOINT_BEFORE_RISKY_ACTION"
    CHECKPOINT_AFTER_VERIFICATION = "CHECKPOINT_AFTER_VERIFICATION"
    CHECKPOINT_PERIODIC = "CHECKPOINT_PERIODIC"
    CHECKPOINT_TASK_COMPLETE = "CHECKPOINT_TASK_COMPLETE"

@dataclass
class PersistedTaskRecord:
    task_id: str
    goal: str
    status: str
    current_node_id: Optional[str]
    created_at: float
    started_at: Optional[float]
    updated_at: float
    completed_at: Optional[float]
    deadline_ts: float
    task_timeout_sec: float
    attempt_count: int = 1
    replan_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PersistedNodeRecord:
    node_id: str
    task_id: str
    name: str
    description: str
    status: str
    attempt_count: int
    started_at: Optional[float]
    completed_at: Optional[float]
    expected_state: Optional[str] = None
    idempotency: str = "SAFE_TO_RETRY"
    required_resources: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    last_error_category: Optional[str] = None
    last_error_message: Optional[str] = None
    last_verification_status: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PersistedCheckpoint:
    checkpoint_id: str
    task_id: str
    node_id: Optional[str]
    timestamp: float
    task_state: str
    node_states: Dict[str, str]
    variables: Dict[str, Any]
    resource_state: List[str]
    last_verified_observations: List[Dict[str, Any]]
    policy_trigger: str
    browser_state_ref: Optional[str] = None
    device_state_ref: Optional[str] = None
    vision_frame_ref: Optional[str] = None
    checksum: str = ""

@dataclass
class PersistedJournalEvent:
    event_id: str
    task_id: str
    sequence_number: int
    timestamp: float
    event_type: str
    payload: Dict[str, Any]

@dataclass
class PersistedResourceLock:
    lock_id: str
    resource_id: str
    task_id: str
    acquired_at: float
    heartbeat_ts: float
    process_id: int

@dataclass
class TaskHeartbeat:
    task_id: str
    heartbeat_ts: float
    current_node_id: Optional[str]
    process_id: int
