"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Domain Models, Enums, and Value Objects - models.py
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class EventCategory(str, enum.Enum):
    IDENTITY = "IDENTITY"
    API = "API"
    WORKLOAD = "WORKLOAD"
    NETWORK = "NETWORK"
    CONFIG = "CONFIG"
    CLOUD = "CLOUD"


class EventResult(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class SecuritySeverity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BaselineStatus(str, enum.Enum):
    COLD_START = "COLD_START"
    LEARNING = "LEARNING"
    ESTABLISHED = "ESTABLISHED"
    EXPIRED = "EXPIRED"


class RuleType(str, enum.Enum):
    DETERMINISTIC = "DETERMINISTIC"
    ANOMALY = "ANOMALY"
    MODEL_ASSISTED = "MODEL_ASSISTED"


class AlertStatus(str, enum.Enum):
    NEW = "NEW"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    RESOLVED = "RESOLVED"


class IncidentStatus(str, enum.Enum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    RESPONSE_PENDING = "RESPONSE_PENDING"
    CONTAINMENT_IN_PROGRESS = "CONTAINMENT_IN_PROGRESS"
    CONTAINED = "CONTAINED"
    RECOVERY = "RECOVERY"
    RESOLVED = "RESOLVED"
    POST_INCIDENT_REVIEW = "POST_INCIDENT_REVIEW"


class IncidentPriority(str, enum.Enum):
    P0_IMMEDIATE = "P0_IMMEDIATE"
    P1_URGENT = "P1_URGENT"
    P2_STANDARD = "P2_STANDARD"
    P3_LOW = "P3_LOW"


class IndicatorType(str, enum.Enum):
    IP = "IP"
    DOMAIN = "DOMAIN"
    HASH = "HASH"
    CVE = "CVE"


class ResponseActionType(str, enum.Enum):
    REVOKE_SESSION = "REVOKE_SESSION"
    DISABLE_ACCOUNT = "DISABLE_ACCOUNT"
    BLOCK_INDICATOR = "BLOCK_INDICATOR"
    ISOLATE_ENDPOINT = "ISOLATE_ENDPOINT"
    ROLLBACK_CONFIG = "ROLLBACK_CONFIG"


class OperationalRisk(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------

@dataclass
class TelemetrySource:
    source_id: str
    provider: str
    environment: str
    collection_method: str
    auth_method: str
    asset_scope: List[str] = field(default_factory=list)
    event_types_supported: List[str] = field(default_factory=list)
    last_successful_ingestion: Optional[str] = None
    health_status: str = "HEALTHY"
    retention_days: int = 90
    coverage_limitations: List[str] = field(default_factory=list)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityEvent:
    event_id: str
    source_id: str
    provider: str
    event_type: str
    event_category: EventCategory
    event_timestamp: str
    action: str
    result: EventResult
    raw_payload_hash: str
    ingestion_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    environment: str = "PRODUCTION"
    asset_id: Optional[str] = None
    actor_id: Optional[str] = None
    target_id: Optional[str] = None
    source_address: Optional[str] = None
    destination_address: Optional[str] = None
    severity: SecuritySeverity = SecuritySeverity.INFO
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    correlation_ids: List[str] = field(default_factory=list)
    quarantine_reason: Optional[str] = None
    is_quarantined: bool = False


@dataclass
class BehavioralBaseline:
    baseline_id: str
    entity_id: str
    entity_type: str  # USER, SERVICE_ACCOUNT, API_CLIENT, WORKLOAD, ASSET
    metric_name: str
    rolling_mean: float = 0.0
    rolling_stddev: float = 0.0
    sample_count: int = 0
    confidence_level: float = 0.1
    status: BaselineStatus = BaselineStatus.COLD_START
    seasonality_model: Dict[str, Any] = field(default_factory=dict)
    first_seen_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DetectionRule:
    rule_id: str
    name: str
    description: str
    rule_type: RuleType
    required_telemetry_sources: List[str] = field(default_factory=list)
    severity: SecuritySeverity = SecuritySeverity.MEDIUM
    confidence_score: float = 0.8
    threshold_params: Dict[str, Any] = field(default_factory=dict)
    suppression_conditions: List[str] = field(default_factory=list)
    mitre_attack_technique: Optional[str] = None
    version: int = 1
    is_enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityAlert:
    alert_id: str
    rule_id: str
    title: str
    description: str
    dedup_key: str
    severity: SecuritySeverity = SecuritySeverity.MEDIUM
    confidence: float = 0.8
    asset_id: Optional[str] = None
    actor_id: Optional[str] = None
    status: AlertStatus = AlertStatus.NEW
    contributing_event_ids: List[str] = field(default_factory=list)
    explanation: Dict[str, Any] = field(default_factory=dict)
    suppression_expires_at: Optional[str] = None
    assigned_to: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CorrelationGraph:
    correlation_id: str
    correlation_title: str
    affected_entities: List[str] = field(default_factory=list)
    participating_alert_ids: List[str] = field(default_factory=list)
    participating_event_ids: List[str] = field(default_factory=list)
    attack_chain_sequence: List[Dict[str, Any]] = field(default_factory=list)
    correlation_confidence: float = 0.7
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ThreatIntelIndicator:
    indicator_id: str
    indicator_type: IndicatorType
    indicator_value: str
    source_provider: str
    published_at: str
    threat_actor: Optional[str] = None
    campaign: Optional[str] = None
    confidence: float = 0.8
    mitre_techniques: List[str] = field(default_factory=list)
    expires_at: Optional[str] = None
    is_active: bool = True


@dataclass
class SecurityInvestigation:
    investigation_id: str
    title: str
    assigned_analyst: str
    primary_hypothesis: str
    status: str = "OPEN"
    competing_hypotheses: List[str] = field(default_factory=list)
    supporting_event_ids: List[str] = field(default_factory=list)
    contradictory_evidence: List[str] = field(default_factory=list)
    affected_assets: List[str] = field(default_factory=list)
    affected_identities: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    findings_summary: Optional[str] = None
    confidence: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityIncident:
    incident_id: str
    title: str
    description: str
    severity: SecuritySeverity = SecuritySeverity.MEDIUM
    priority: IncidentPriority = IncidentPriority.P2_STANDARD
    status: IncidentStatus = IncidentStatus.DETECTED
    affected_assets: List[str] = field(default_factory=list)
    affected_identities: List[str] = field(default_factory=list)
    related_alert_ids: List[str] = field(default_factory=list)
    investigation_id: Optional[str] = None
    assigned_owner: Optional[str] = None
    resolution_summary: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class IncidentTimelineEntry:
    timeline_entry_id: str
    incident_id: str
    entry_timestamp: str
    entry_type: str  # ALERT, EVENT, ANALYST_NOTE, CONTAINMENT, APPROVAL, RECOVERY
    description: str
    actor: str
    evidence_reference: Optional[str] = None


@dataclass
class DefensiveResponsePlan:
    plan_id: str
    incident_id: str
    recommended_action: ResponseActionType
    target_identifier: str
    justification: str
    operational_risk: OperationalRisk = OperationalRisk.LOW
    requires_approval: bool = True
    approval_token_ref: Optional[str] = None
    status: str = "PROPOSED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ContainmentActionRecord:
    action_id: str
    plan_id: str
    incident_id: str
    action_type: str
    target: str
    status: str = "EXECUTED"
    approval_token: Optional[str] = None
    execution_result: Dict[str, Any] = field(default_factory=dict)
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verified_at: Optional[str] = None


@dataclass
class EvidencePackage:
    package_id: str
    incident_id: str
    package_digest_sha256: str
    evidence_manifest: Dict[str, Any]
    sealed_by: str
    investigation_id: Optional[str] = None
    sealed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DetectionEvaluation:
    eval_id: str
    dataset_name: str
    total_samples: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision_score: float
    recall_score: float
    f1_score: float
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
