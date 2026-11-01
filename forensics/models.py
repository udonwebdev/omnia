"""
forensics/models.py
Core domain models and enums for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    SCOPED = "SCOPED"
    ACQUIRING_EVIDENCE = "ACQUIRING_EVIDENCE"
    ANALYSIS = "ANALYSIS"
    REVIEW = "REVIEW"
    REPORTING = "REPORTING"
    CLOSED = "CLOSED"


class ArtifactType(str, Enum):
    IDENTITY_AUDIT = "IDENTITY_AUDIT"
    ENDPOINT_PROCESS = "ENDPOINT_PROCESS"
    ENDPOINT_FILESYSTEM = "ENDPOINT_FILESYSTEM"
    CLOUD_AUDIT_LOG = "CLOUD_AUDIT_LOG"
    NETWORK_CONNECTION_LOG = "NETWORK_CONNECTION_LOG"
    SYSTEM_EVENT_LOG = "SYSTEM_EVENT_LOG"
    CONFIG_SNAPSHOT = "CONFIG_SNAPSHOT"
    MEMORY_METADATA = "MEMORY_METADATA"


class CustodyOperation(str, Enum):
    ACQUISITION = "ACQUISITION"
    TRANSFER = "TRANSFER"
    HASH_VERIFICATION = "HASH_VERIFICATION"
    ANALYSIS_READ = "ANALYSIS_READ"
    LEGAL_HOLD_APPLIED = "LEGAL_HOLD_APPLIED"
    LEGAL_HOLD_RELEASED = "LEGAL_HOLD_RELEASED"
    EXPORT = "EXPORT"


class HypothesisStatus(str, Enum):
    PROPOSED = "PROPOSED"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class StatementCategory(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


class EvidenceReliabilityTier(str, Enum):
    CONFIRMED = "CONFIRMED"      # Cryptographically signed / immutable cloud audit log
    HIGH = "HIGH"                # Authoritative endpoint or directory event with hash match
    MODERATE = "MODERATE"        # Secondary telemetry or aggregated syslog
    LOW = "LOW"                  # Inferred or unverified correlation
    DISPUTED = "DISPUTED"        # Inconsistent timestamp or missing checksum


@dataclass
class ForensicCase:
    case_id: str
    title: str
    description: str
    incident_id: Optional[str]
    scope_definition: Dict[str, Any]
    status: CaseStatus = CaseStatus.OPEN
    lead_investigator: str = "omnia_forensic_agent"
    retention_days: int = 365
    legal_hold_active: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None


@dataclass
class EvidenceArtifact:
    artifact_id: str
    case_id: str
    source_type: ArtifactType
    source_identifier: str
    artifact_name: str
    classification: str
    sha256_hash: str
    size_bytes: int
    storage_uri: str
    parser_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    acquired_at: float = field(default_factory=time.time)
    acquired_by: str = "omnia_forensic_agent"
    integrity_status: str = "VERIFIED"


@dataclass
class ChainOfCustodyRecord:
    custody_id: str
    artifact_id: str
    case_id: str
    operation: CustodyOperation
    actor: str
    reason: str
    sha256_verified: str
    integrity_ok: bool = True
    approval_token: Optional[str] = None
    recorded_at: float = field(default_factory=time.time)


@dataclass
class AcquisitionJob:
    job_id: str
    case_id: str
    target_source: str
    source_type: ArtifactType
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"
    artifacts_collected: int = 0
    error_message: Optional[str] = None
    approval_token: Optional[str] = None
    initiated_by: str = "omnia_forensic_agent"
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


@dataclass
class TimelineEvent:
    event_id: str
    case_id: str
    artifact_id: Optional[str]
    timestamp_utc: float
    raw_timestamp: str
    clock_drift_seconds: float = 0.0
    event_category: str = "SYSTEM"
    action: str = ""
    actor: Optional[str] = None
    source_entity: Optional[str] = None
    target_entity: Optional[str] = None
    summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    reliability_tier: EvidenceReliabilityTier = EvidenceReliabilityTier.CONFIRMED


@dataclass
class EvidenceCorrelation:
    correlation_id: str
    case_id: str
    source_artifact_id: str
    target_artifact_id: str
    correlation_type: str
    correlation_key: str
    confidence_score: float
    notes: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class ForensicHypothesis:
    hypothesis_id: str
    case_id: str
    title: str
    theory_description: str
    competing_with_id: Optional[str] = None
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    support_score: float = 0.0
    refutation_score: float = 0.0
    supporting_evidence: List[str] = field(default_factory=list)
    contradictory_evidence: List[str] = field(default_factory=list)
    verdict_rationale: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class StatementItem:
    category: StatementCategory
    statement: str
    evidence_refs: List[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class ForensicReport:
    report_id: str
    case_id: str
    title: str
    executive_summary: str
    facts: List[StatementItem] = field(default_factory=list)
    inferences: List[StatementItem] = field(default_factory=list)
    hypotheses: List[StatementItem] = field(default_factory=list)
    unknowns: List[StatementItem] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    sign_off_investigator: str = "omnia_forensic_agent"
    cryptographic_seal: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class LegalHold:
    hold_id: str
    case_id: str
    hold_reason: str
    applied_by: str
    approval_token: str
    is_active: bool = True
    applied_at: float = field(default_factory=time.time)
    released_at: Optional[float] = None
    released_by: Optional[str] = None
