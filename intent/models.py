import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

class AmbiguityState(Enum):
    CLEAR = "CLEAR"
    LOW_AMBIGUITY = "LOW_AMBIGUITY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSAFE_TO_INFER = "UNSAFE_TO_INFER"

class PlanRiskLevel(Enum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    MODERATE_RISK = "MODERATE_RISK"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"

class ValidationStatus(Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    REQUIRES_CLARIFICATION = "REQUIRES_CLARIFICATION"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    UNSAFE = "UNSAFE"

@dataclass
class AmbiguityDetail:
    state: AmbiguityState = AmbiguityState.CLEAR
    ambiguity_type: str = ""
    missing_information: List[str] = field(default_factory=list)
    candidate_interpretations: List[str] = field(default_factory=list)
    confidence: float = 1.0
    clarification_question: Optional[str] = None

@dataclass
class UserIntent:
    intent_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    raw_text: str = ""
    normalized_text: str = ""
    primary_objective: str = ""
    desired_outcome: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    target_devices: List[str] = field(default_factory=list)
    target_applications: List[str] = field(default_factory=list)
    target_websites: List[str] = field(default_factory=list)
    temporal_constraints: List[str] = field(default_factory=list)
    safety_constraints: List[str] = field(default_factory=list)
    deadline_ts: Optional[float] = None
    priority: int = 1
    requires_confirmation: bool = False
    ambiguity: AmbiguityDetail = field(default_factory=AmbiguityDetail)
    created_at: float = field(default_factory=time.time)

@dataclass
class CapabilityMetadata:
    name: str
    description: str
    supported_environments: List[str]
    required_resources: List[str]
    risk_level: PlanRiskLevel
    idempotent: bool
    reversibility: bool
    verification_mechanism: str
    timeout_sec: float = 30.0
    input_keys: List[str] = field(default_factory=list)
    output_keys: List[str] = field(default_factory=list)

@dataclass
class PlannedStep:
    step_id: str
    purpose: str
    capability_name: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    verification_strategy: str = "DEFAULT"
    expected_state: Optional[str] = None
    risk_level: PlanRiskLevel = PlanRiskLevel.LOW_RISK
    requires_confirmation: bool = False
    timeout_sec: float = 30.0
    idempotency: str = "SAFE_TO_RETRY"

@dataclass
class PlanScore:
    completeness: float = 1.0
    capability_coverage: float = 1.0
    safety: float = 1.0
    reliability: float = 1.0
    verification_coverage: float = 1.0
    confidence: float = 1.0
    overall: float = 1.0

@dataclass
class ValidationReport:
    status: ValidationStatus
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PlanVersion:
    plan_id: str
    version: int
    parent_version: Optional[int]
    created_at: float
    reason_for_change: str
    changed_nodes: List[str]
    compiler_version: str = "1.0.0"

@dataclass
class CompiledPlan:
    plan_id: str
    intent: UserIntent
    steps: List[PlannedStep]
    validation: ValidationReport
    score: PlanScore
    version: PlanVersion
    created_at: float = field(default_factory=time.time)
