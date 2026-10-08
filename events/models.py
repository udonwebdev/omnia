import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Union, Callable

class EventPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

class EventSeverity(Enum):
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class EventDurability(Enum):
    EPHEMERAL = "EPHEMERAL"       # UI ticks, mouse moves, transient updates - discarded on restart
    OPERATIONAL = "OPERATIONAL"   # Short-term diagnostic & monitoring events
    DURABLE = "DURABLE"           # Checkpoint triggers, security blocks, task outcomes - persisted

@dataclass
class EventEnvelope:
    """Carries routing, causal tracing, and policy metadata decoupled from payload."""
    event_id: str = field(default_factory=lambda: f"evt_{str(uuid.uuid4())[:12]}")
    event_type: str = ""
    event_version: str = "1.0.0"
    occurred_at: float = field(default_factory=time.time)
    published_at: float = field(default_factory=time.time)
    source: str = "omnia.system"
    subject: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: f"corr_{str(uuid.uuid4())[:8]}")
    causation_id: Optional[str] = None
    task_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    priority: EventPriority = EventPriority.NORMAL
    severity: EventSeverity = EventSeverity.INFO
    durability: EventDurability = EventDurability.OPERATIONAL
    schema_version: str = "1.0.0"

@dataclass
class Event:
    """First-class typed event representing a factual occurrence in Omnia."""
    envelope: EventEnvelope
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    security_context: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.envelope.event_id

    @property
    def type(self) -> str:
        return self.envelope.event_type

    @property
    def correlation_id(self) -> str:
        return self.envelope.correlation_id

    @property
    def task_id(self) -> Optional[str]:
        return self.envelope.task_id

    @property
    def priority(self) -> EventPriority:
        return self.envelope.priority

    @property
    def severity(self) -> EventSeverity:
        return self.envelope.severity

    @property
    def durability(self) -> EventDurability:
        return self.envelope.durability

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.envelope.event_id,
            "event_type": self.envelope.event_type,
            "event_version": self.envelope.event_version,
            "occurred_at": self.envelope.occurred_at,
            "published_at": self.envelope.published_at,
            "source": self.envelope.source,
            "subject": self.envelope.subject,
            "correlation_id": self.envelope.correlation_id,
            "causation_id": self.envelope.causation_id,
            "task_id": self.envelope.task_id,
            "parent_event_id": self.envelope.parent_event_id,
            "priority": self.envelope.priority.name,
            "severity": self.envelope.severity.value,
            "durability": self.envelope.durability.value,
            "payload": self.payload,
            "metadata": self.metadata,
            "security_context": self.security_context
        }

@dataclass
class EventFilter:
    """Criteria for filtering subscribed events efficiently."""
    type_pattern: Optional[str] = None  # Exact type or glob pattern (e.g. 'task.*', 'device.disconnected')
    source: Optional[str] = None
    task_id: Optional[str] = None
    correlation_id: Optional[str] = None
    min_priority: Optional[EventPriority] = None
    min_severity: Optional[EventSeverity] = None

    def matches(self, event: Event) -> bool:
        if self.type_pattern:
            if self.type_pattern.endswith(".*"):
                prefix = self.type_pattern[:-2]
                if not (event.type == prefix or event.type.startswith(prefix + ".")):
                    return False
            elif self.type_pattern != "*" and event.type != self.type_pattern:
                return False

        if self.source and event.envelope.source != self.source:
            return False

        if self.task_id and event.envelope.task_id != self.task_id:
            return False

        if self.correlation_id and event.envelope.correlation_id != self.correlation_id:
            return False

        if self.min_priority and event.priority.value < self.min_priority.value:
            return False

        return True

@dataclass
class DeadLetterRecord:
    event_id: str
    event_type: str
    handler_id: str
    failure_reason: str
    attempts: int
    first_attempt_ts: float
    last_attempt_ts: float
    event_payload: Dict[str, Any]
