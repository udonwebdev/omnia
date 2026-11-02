"""
privacy/models.py
Data models and Enums for OMNIA Module 51:
Autonomous Privacy Engineering, Data Governance & Information Protection Intelligence.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time
import uuid


class SensitivityTier(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"
    HIGHLY_RESTRICTED = "HIGHLY_RESTRICTED"

    @classmethod
    def rank(cls, tier: "SensitivityTier") -> int:
        order = {
            cls.PUBLIC: 1,
            cls.INTERNAL: 2,
            cls.CONFIDENTIAL: 3,
            cls.RESTRICTED: 4,
            cls.HIGHLY_RESTRICTED: 5,
        }
        return order.get(tier, 1)


class DataCategory(str, Enum):
    PII = "PII"
    FINANCIAL = "FINANCIAL"
    CREDENTIALS = "CREDENTIALS"
    GOV_ID = "GOV_ID"
    HEALTH = "HEALTH"
    BIOMETRIC = "BIOMETRIC"
    LOCATION = "LOCATION"
    BEHAVIORAL = "BEHAVIORAL"
    CONFIDENTIAL_BIZ = "CONFIDENTIAL_BIZ"
    SECURITY_SENSITIVE = "SECURITY_SENSITIVE"


class AssetType(str, Enum):
    DATABASE = "DATABASE"
    TABLE = "TABLE"
    FILE = "FILE"
    STREAM = "STREAM"
    CACHE = "CACHE"
    AI_MODEL = "AI_MODEL"
    BACKUP = "BACKUP"
    LOG = "LOG"


class DSRType(str, Enum):
    ACCESS = "ACCESS"
    CORRECTION = "CORRECTION"
    DELETION = "DELETION"
    PORTABILITY = "PORTABILITY"
    RESTRICTION = "RESTRICTION"


class DSRStatus(str, Enum):
    RECEIVED = "RECEIVED"
    VERIFIED = "VERIFIED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    FULFILLED = "FULFILLED"
    REJECTED = "REJECTED"
    BLOCKED_LEGAL_HOLD = "BLOCKED_LEGAL_HOLD"


class DeletionStatus(str, Enum):
    REQUESTED = "REQUESTED"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    APPROVED = "APPROVED"
    BLOCKED_LEGAL_HOLD = "BLOCKED_LEGAL_HOLD"
    EXECUTING = "EXECUTING"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ConsentStatus(str, Enum):
    GRANTED = "GRANTED"
    WITHDRAWN = "WITHDRAWN"


class PIAStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PIAType(str, Enum):
    PIA = "PIA"
    DPIA = "DPIA"


class LawfulBasis(str, Enum):
    CONSENT = "CONSENT"
    CONTRACT = "CONTRACT"
    LEGAL_OBLIGATION = "LEGAL_OBLIGATION"
    VITAL_INTERESTS = "VITAL_INTERESTS"
    PUBLIC_TASK = "PUBLIC_TASK"
    LEGITIMATE_INTERESTS = "LEGITIMATE_INTERESTS"


class TransferMechanism(str, Enum):
    ADEQUACY_DECISION = "ADEQUACY_DECISION"
    STANDARD_CONTRACTUAL_CLAUSES = "STANDARD_CONTRACTUAL_CLAUSES"
    BINDING_CORPORATE_RULES = "BINDING_CORPORATE_RULES"
    DEROGATION = "DEROGATION"
    EXEMPT = "EXEMPT"


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ContainmentStatus(str, Enum):
    DETECTED = "DETECTED"
    CONTAINING = "CONTAINING"
    CONTAINED = "CONTAINED"
    REMEDIATED = "REMEDIATED"
    CLOSED = "CLOSED"


@dataclass
class DataAsset:
    asset_id: str
    name: str
    asset_type: AssetType
    storage_location: str
    owner: str
    residency_country: str
    sensitivity_tier: SensitivityTier
    is_active: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataClassification:
    class_id: str
    asset_id: str
    field_name: str
    category: DataCategory
    sensitivity_tier: SensitivityTier
    confidence: float
    rule_matched: str
    classified_at: float = field(default_factory=time.time)


@dataclass
class DiscoveryScan:
    scan_id: str
    target_scope: str
    scanner_identity: str
    findings_count: int = 0
    sensitive_fields: List[Dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    status: str = "IN_PROGRESS"


@dataclass
class LineageRecord:
    lineage_id: str
    source_asset_id: str
    dest_asset_id: str
    operation_type: str
    purpose: str
    transformation_type: str
    actor: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ProcessingActivity:
    activity_id: str
    name: str
    purpose: str
    lawful_basis: LawfulBasis
    owner: str
    data_categories: List[DataCategory] = field(default_factory=list)
    retention_schedule: str = "P3Y"
    is_approved: bool = False
    review_date: float = field(default_factory=lambda: time.time() + 31536000.0)


@dataclass
class ConsentRecord:
    consent_id: str
    subject_id: str
    purpose: str
    status: ConsentStatus
    granted_at: float = field(default_factory=time.time)
    withdrawn_at: Optional[float] = None
    policy_version: str = "1.0"


@dataclass
class RetentionPolicy:
    policy_id: str
    purpose: str
    max_retention_days: int
    legal_basis: str
    legal_hold_exempt: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class DeletionRequest:
    request_id: str
    asset_id: str
    target_selector: str
    reason: str
    requested_by: str
    approval_token: Optional[str] = None
    status: DeletionStatus = DeletionStatus.REQUESTED
    verified: bool = False
    requested_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    verification_proof: Optional[str] = None


@dataclass
class DSRRequest:
    dsr_id: str
    subject_id: str
    request_type: DSRType
    status: DSRStatus = DSRStatus.RECEIVED
    verification_token: Optional[str] = None
    requester_email: str = ""
    deadline: float = field(default_factory=lambda: time.time() + 2592000.0)  # 30 days
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    result_summary: Optional[str] = None


@dataclass
class PrivacyAssessment:
    assessment_id: str
    activity_id: str
    assessment_type: PIAType
    risk_score: float
    findings: List[Dict[str, Any]] = field(default_factory=list)
    safeguards: List[Dict[str, Any]] = field(default_factory=list)
    approval_status: PIAStatus = PIAStatus.DRAFT
    assessed_at: float = field(default_factory=time.time)


@dataclass
class AccessDisclosureLog:
    log_id: str
    actor_id: str
    asset_id: str
    purpose: str
    action: str
    authorized: bool
    justification: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class VendorProcessor:
    vendor_id: str
    name: str
    service_type: str
    dpa_status: str  # SIGNED, PENDING, EXPIRED, NONE
    residency: str
    subprocessors: List[str] = field(default_factory=list)
    assessment_status: str = "ASSESSED"
    updated_at: float = field(default_factory=time.time)


@dataclass
class CrossBorderTransfer:
    transfer_id: str
    source_country: str
    dest_country: str
    recipient: str
    purpose: str
    transfer_mechanism: TransferMechanism
    is_approved: bool = False
    reviewed_at: float = field(default_factory=time.time)


@dataclass
class PrivacyIncident:
    incident_id: str
    incident_type: str
    affected_assets: List[str] = field(default_factory=list)
    affected_categories: List[DataCategory] = field(default_factory=list)
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    containment_status: ContainmentStatus = ContainmentStatus.DETECTED
    reportable: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class AIGovernanceConfig:
    ai_gov_id: str
    model_id: str
    provider: str
    inference_logging_allowed: bool = False
    training_permitted: bool = False
    prompt_redaction_enabled: bool = True
    retention_policy: str = "ZERO_DAY"


@dataclass
class PrivacyAuditLog:
    audit_id: str
    event_type: str
    actor: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class PrivacyPostureReport:
    report_id: str
    timestamp: float
    total_assets: int
    total_classifications: int
    active_holds_count: int
    pending_dsrs_count: int
    high_risk_vendors_count: int
    overall_posture_score: float
    cryptographic_seal: str
    summary_facts: List[str] = field(default_factory=list)
    estimates: List[str] = field(default_factory=list)
