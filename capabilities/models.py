import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set, Union

class CapabilityCategory(Enum):
    DEVICE = "DEVICE"
    BROWSER = "BROWSER"
    VISION = "VISION"
    VOICE = "VOICE"
    TELEPHONY = "TELEPHONY"
    MESH = "MESH"
    SYSTEM = "SYSTEM"
    MEMORY = "MEMORY"
    ORCHESTRATION = "ORCHESTRATION"

class CapabilityHealth(Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    INITIALIZING = "INITIALIZING"
    FAILED = "FAILED"

class CapabilityLifecycle(Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    REGISTERED = "REGISTERED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"
    REMOVED = "REMOVED"

class SideEffectType(Enum):
    NONE = "NONE"
    READ = "READ"
    WRITE = "WRITE"
    DEVICE_CONTROL = "DEVICE_CONTROL"
    NETWORK = "NETWORK"
    EXTERNAL_COMMUNICATION = "EXTERNAL_COMMUNICATION"
    FINANCIAL = "FINANCIAL"
    DESTRUCTIVE = "DESTRUCTIVE"
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"

class IdempotencyType(Enum):
    IDEMPOTENT = "IDEMPOTENT"
    CONDITIONALLY_IDEMPOTENT = "CONDITIONALLY_IDEMPOTENT"
    NON_IDEMPOTENT = "NON_IDEMPOTENT"
    UNKNOWN = "UNKNOWN"

class ReversibilityType(Enum):
    REVERSIBLE = "REVERSIBLE"
    CONDITIONALLY_REVERSIBLE = "CONDITIONALLY_REVERSIBLE"
    POTENTIALLY_IRREVERSIBLE = "POTENTIALLY_IRREVERSIBLE"
    IRREVERSIBLE = "IRREVERSIBLE"

class RiskLevel(Enum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    MODERATE_RISK = "MODERATE_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"

@dataclass
class VerificationContract:
    mechanism: str  # e.g., "DOM_URL_MATCH", "OCR_TEXT_MATCH", "PROCESS_EXIT_ZERO", "VISUAL_STATE_CHANGE"
    target_expression: Optional[str] = None
    expected_state: Optional[str] = None
    timeout_sec: float = 10.0
    fallback_mechanism: Optional[str] = None

@dataclass
class CapabilityProvider:
    provider_id: str
    capability_id: str
    implementation_ref: str  # module/class or callable name or remote host
    version: str = "1.0.0"
    priority: int = 100  # lower number = higher priority
    health: CapabilityHealth = CapabilityHealth.UNKNOWN
    latency_ms: float = 0.0
    cost: float = 0.0
    environment: str = "local"  # "local", "mesh", "device", "browser", "cloud"
    constraints: Dict[str, Any] = field(default_factory=dict)
    last_check_ts: float = field(default_factory=time.time)
    error_message: Optional[str] = None

@dataclass
class Capability:
    id: str  # Canonical stable identity e.g. "browser.navigate", "vision.find_element"
    name: str
    description: str
    version: str = "1.0.0"
    category: CapabilityCategory = CapabilityCategory.SYSTEM
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    environment: str = "local"  # "local", "desktop", "android", "browser", "mesh"
    platforms: List[str] = field(default_factory=lambda: ["windows", "linux", "macos"])
    required_resources: List[str] = field(default_factory=list)
    required_permissions: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW_RISK
    side_effects: List[SideEffectType] = field(default_factory=lambda: [SideEffectType.READ])
    reversible: ReversibilityType = ReversibilityType.REVERSIBLE
    idempotent: IdempotencyType = IdempotencyType.IDEMPOTENT
    verification_contract: Optional[VerificationContract] = None
    default_timeout_sec: float = 30.0
    health: CapabilityHealth = CapabilityHealth.UNKNOWN
    dependencies: List[str] = field(default_factory=list)
    providers: Dict[str, CapabilityProvider] = field(default_factory=dict)
    lifecycle: CapabilityLifecycle = CapabilityLifecycle.DISCOVERED
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

@dataclass
class CapabilityMatchQuery:
    intent_category: Optional[CapabilityCategory] = None
    capability_id: Optional[str] = None
    required_platforms: List[str] = field(default_factory=list)
    environment: Optional[str] = None
    max_risk_level: Optional[RiskLevel] = None
    available_permissions: List[str] = field(default_factory=list)
    max_latency_ms: Optional[float] = None
    max_cost: Optional[float] = None
    required_resources: List[str] = field(default_factory=list)

@dataclass
class CapabilityLease:
    lease_id: str = field(default_factory=lambda: f"lease_{str(uuid.uuid4())[:8]}")
    capability_id: str = ""
    provider_id: str = ""
    task_id: str = ""
    acquired_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    status: str = "ACTIVE"
    metadata: Dict[str, Any] = field(default_factory=dict)
