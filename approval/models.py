import time
import uuid
import hashlib
import json
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set

class ApprovalStatus(Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    PENDING = "PENDING"
    PRESENTING = "PRESENTING"
    DELIVERED = "DELIVERED"
    WAITING = "WAITING"
    APPROVED = "APPROVED"
    EXECUTION_RELEASED = "EXECUTION_RELEASED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"
    WITHDRAWN = "WITHDRAWN"
    FAILED_TO_DELIVER = "FAILED_TO_DELIVER"
    FAILED_TO_VALIDATE = "FAILED_TO_VALIDATE"
    UNKNOWN = "UNKNOWN"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

class ApprovalType(Enum):
    HIGH_RISK_ACTION = "HIGH_RISK_ACTION"
    CRITICAL_ACTION = "CRITICAL_ACTION"
    EXTERNAL_SIDE_EFFECT = "EXTERNAL_SIDE_EFFECT"
    FINANCIAL_ACTION = "FINANCIAL_ACTION"
    ACCOUNT_CHANGE = "ACCOUNT_CHANGE"
    DATA_DELETION = "DATA_DELETION"
    CREDENTIAL_USE = "CREDENTIAL_USE"
    PRIVILEGED_OPERATION = "PRIVILEGED_OPERATION"
    IRREVERSIBLE_ACTION = "IRREVERSIBLE_ACTION"
    AMBIGUOUS_INTENT = "AMBIGUOUS_INTENT"
    PLAN_EXCEPTION = "PLAN_EXCEPTION"
    POLICY_REQUIRED = "POLICY_REQUIRED"
    RESOURCE_ESCALATION = "RESOURCE_ESCALATION"
    NEW_CAPABILITY = "NEW_CAPABILITY"
    UNTRUSTED_CAPABILITY = "UNTRUSTED_CAPABILITY"
    SECURITY_EXCEPTION = "SECURITY_EXCEPTION"
    MISSION_ESCALATION = "MISSION_ESCALATION"
    USER_REQUESTED_CONFIRMATION = "USER_REQUESTED_CONFIRMATION"

class ApprovalDecisionType(Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CANCEL = "CANCEL"
    DEFER = "DEFER"

class ApprovalScope(Enum):
    ONCE = "ONCE"
    TASK = "TASK"
    TASK_NODE = "TASK_NODE"
    MISSION = "MISSION"
    SESSION = "SESSION"
    RESOURCE = "RESOURCE"
    CAPABILITY = "CAPABILITY"
    ACTION_CLASS = "ACTION_CLASS"

VALID_APPROVAL_TRANSITIONS: Dict[ApprovalStatus, Set[ApprovalStatus]] = {
    ApprovalStatus.CREATED: {ApprovalStatus.VALIDATING, ApprovalStatus.PENDING, ApprovalStatus.CANCELLED, ApprovalStatus.INVALIDATED},
    ApprovalStatus.VALIDATING: {ApprovalStatus.PENDING, ApprovalStatus.FAILED_TO_VALIDATE, ApprovalStatus.CANCELLED, ApprovalStatus.INVALIDATED},
    ApprovalStatus.PENDING: {ApprovalStatus.PRESENTING, ApprovalStatus.DELIVERED, ApprovalStatus.WAITING, ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.DEFERRED, ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED, ApprovalStatus.INVALIDATED, ApprovalStatus.RECOVERY_REQUIRED},
    ApprovalStatus.PRESENTING: {ApprovalStatus.DELIVERED, ApprovalStatus.WAITING, ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.DEFERRED, ApprovalStatus.FAILED_TO_DELIVER, ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED, ApprovalStatus.INVALIDATED, ApprovalStatus.RECOVERY_REQUIRED},
    ApprovalStatus.DELIVERED: {ApprovalStatus.WAITING, ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.DEFERRED, ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED, ApprovalStatus.INVALIDATED, ApprovalStatus.RECOVERY_REQUIRED},
    ApprovalStatus.WAITING: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.DEFERRED, ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED, ApprovalStatus.INVALIDATED, ApprovalStatus.RECOVERY_REQUIRED},
    ApprovalStatus.APPROVED: {ApprovalStatus.EXECUTION_RELEASED, ApprovalStatus.EXPIRED, ApprovalStatus.INVALIDATED, ApprovalStatus.SUPERSEDED, ApprovalStatus.CANCELLED},
    ApprovalStatus.EXECUTION_RELEASED: set(),
    ApprovalStatus.REJECTED: set(),
    ApprovalStatus.DEFERRED: {ApprovalStatus.WAITING, ApprovalStatus.CANCELLED, ApprovalStatus.EXPIRED, ApprovalStatus.INVALIDATED},
    ApprovalStatus.EXPIRED: set(),
    ApprovalStatus.CANCELLED: set(),
    ApprovalStatus.SUPERSEDED: set(),
    ApprovalStatus.INVALIDATED: set(),
    ApprovalStatus.WITHDRAWN: set(),
    ApprovalStatus.FAILED_TO_DELIVER: {ApprovalStatus.PENDING, ApprovalStatus.CANCELLED, ApprovalStatus.INVALIDATED},
    ApprovalStatus.FAILED_TO_VALIDATE: set(),
    ApprovalStatus.UNKNOWN: {ApprovalStatus.INVALIDATED, ApprovalStatus.CANCELLED, ApprovalStatus.RECOVERY_REQUIRED},
    ApprovalStatus.RECOVERY_REQUIRED: {ApprovalStatus.WAITING, ApprovalStatus.INVALIDATED, ApprovalStatus.CANCELLED, ApprovalStatus.APPROVED, ApprovalStatus.REJECTED}
}

@dataclass
class ApprovalRequest:
    """Strongly typed approval request representing an action awaiting human consent."""
    approval_id: str = field(default_factory=lambda: f"apr_{uuid.uuid4().hex[:8]}")
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    request_type: ApprovalType = ApprovalType.POLICY_REQUIRED
    title: str = ""
    summary: str = ""
    reason: str = ""

    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    task_node_id: Optional[str] = None
    plan_version: int = 1
    capability_id: Optional[str] = None
    provider_id: Optional[str] = None

    risk_level: str = "HIGH"
    policy_reference: Optional[str] = None

    requested_action: str = ""
    action_params: Dict[str, Any] = field(default_factory=dict)
    target_resource: Optional[str] = None
    target_device: Optional[str] = None
    target_application: Optional[str] = None

    expected_effect: str = ""
    potential_side_effects: str = ""
    is_reversible: bool = False

    expires_at: float = field(default_factory=lambda: time.time() + 120.0)
    scope: ApprovalScope = ApprovalScope.ONCE
    fingerprint: str = ""

    status: ApprovalStatus = ApprovalStatus.CREATED
    created_by: str = "omnia.system"
    correlation_id: str = ""
    causation_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_transition_to(self, target_status: ApprovalStatus) -> bool:
        if self.status == target_status:
            return True
        allowed = VALID_APPROVAL_TRANSITIONS.get(self.status, set())
        return target_status in allowed

    def transition_to(self, target_status: ApprovalStatus) -> bool:
        if not self.can_transition_to(target_status):
            return False
        self.status = target_status
        self.updated_at = time.time()
        return True

    def is_terminal(self) -> bool:
        return self.status in {
            ApprovalStatus.EXECUTION_RELEASED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
            ApprovalStatus.SUPERSEDED,
            ApprovalStatus.INVALIDATED,
            ApprovalStatus.WITHDRAWN,
            ApprovalStatus.FAILED_TO_VALIDATE
        }

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time or time.time()
        return now >= self.expires_at

@dataclass
class ApprovalDecision:
    """User decision record capturing human consent or rejection."""
    decision_id: str = field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:8]}")
    approval_id: str = ""
    decision: ApprovalDecisionType = ApprovalDecisionType.REJECT
    decided_at: float = field(default_factory=time.time)
    decided_by: str = "user.primary"
    decision_source: str = "HUD"  # HUD, VOICE, CLI, DESKTOP
    device_id: Optional[str] = None
    session_id: Optional[str] = None
    reason: str = ""
    approval_version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ApprovalPresentation:
    """Normalized payload delivered to presentation channels (HUD, Voice, CLI)."""
    approval_id: str
    channel: str
    priority: str
    title: str
    summary: str
    risk_level: str
    target_resource: Optional[str]
    is_reversible: bool
    expires_in_sec: float
    context: Dict[str, Any]
    formatted_prompt: str

@dataclass
class ApprovalRelease:
    """Cryptographically verifiable execution authorization consumed by Module 14."""
    release_token: str
    approval_id: str
    task_id: Optional[str]
    task_node_id: Optional[str]
    mission_id: Optional[str]
    authorized_action: str
    authorization_scope: ApprovalScope
    fingerprint: str
    authorized_at: float
    expires_at: float
    policy_reference: Optional[str]
