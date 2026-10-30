"""
OMNIA Module 35: Autonomous Cybersecurity, Threat Intelligence & Runtime Defense Models
Provides typed data contracts, state machines, severity models, and response levels.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class SecuritySeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IndicatorType(str, Enum):
    IP_ADDRESS = "IP_ADDRESS"
    DOMAIN = "DOMAIN"
    URL = "URL"
    FILE_HASH = "FILE_HASH"
    MALWARE_SIGNATURE = "MALWARE_SIGNATURE"
    VULNERABILITY_ID = "VULNERABILITY_ID"
    ATTACK_PATTERN = "ATTACK_PATTERN"
    COMPROMISED_CREDENTIAL = "COMPROMISED_CREDENTIAL"


class IndicatorValidationStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ThreatClassification(str, Enum):
    UNAUTHORIZED_ACCESS = "UNAUTHORIZED_ACCESS"
    CREDENTIAL_EXPOSURE = "CREDENTIAL_EXPOSURE"
    CAPABILITY_ABUSE = "CAPABILITY_ABUSE"
    INJECTION_ATTACK = "INJECTION_ATTACK"
    DISTRIBUTED_SPLIT_BRAIN = "DISTRIBUTED_SPLIT_BRAIN"
    ANOMALOUS_BEHAVIOR = "ANOMALOUS_BEHAVIOR"
    DATA_EXFILTRATION = "DATA_EXFILTRATION"
    INTEGRITY_TAMPERING = "INTEGRITY_TAMPERING"
    DENIAL_OF_SERVICE = "DENIAL_OF_SERVICE"


class SecurityPostureState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    AT_RISK = "AT_RISK"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    CONTAINMENT_PENDING = "CONTAINMENT_PENDING"
    CONTAINED = "CONTAINED"
    REMEDIATION_PENDING = "REMEDIATION_PENDING"
    REMEDIATING = "REMEDIATING"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"


# Allowed state transitions for the Incident lifecycle
VALID_INCIDENT_TRANSITIONS = {
    IncidentStatus.DETECTED: {IncidentStatus.TRIAGED, IncidentStatus.CONTAINMENT_PENDING, IncidentStatus.CLOSED},
    IncidentStatus.TRIAGED: {IncidentStatus.INVESTIGATING, IncidentStatus.CONTAINMENT_PENDING, IncidentStatus.CLOSED},
    IncidentStatus.INVESTIGATING: {IncidentStatus.CONTAINMENT_PENDING, IncidentStatus.REMEDIATION_PENDING, IncidentStatus.RESOLVED, IncidentStatus.CLOSED},
    IncidentStatus.CONTAINMENT_PENDING: {IncidentStatus.CONTAINED, IncidentStatus.INVESTIGATING},
    IncidentStatus.CONTAINED: {IncidentStatus.REMEDIATION_PENDING, IncidentStatus.INVESTIGATING},
    IncidentStatus.REMEDIATION_PENDING: {IncidentStatus.REMEDIATING, IncidentStatus.CONTAINED},
    IncidentStatus.REMEDIATING: {IncidentStatus.RECOVERY_PENDING, IncidentStatus.INVESTIGATING},
    IncidentStatus.RECOVERY_PENDING: {IncidentStatus.RECOVERING, IncidentStatus.REMEDIATING},
    IncidentStatus.RECOVERING: {IncidentStatus.RESOLVED, IncidentStatus.RECOVERY_PENDING},
    IncidentStatus.RESOLVED: {IncidentStatus.CLOSED, IncidentStatus.REOPENED},
    IncidentStatus.CLOSED: {IncidentStatus.REOPENED},
    IncidentStatus.REOPENED: {IncidentStatus.INVESTIGATING, IncidentStatus.CONTAINMENT_PENDING},
}


class ResponseAutonomyLevel(int, Enum):
    LEVEL_0_OBSERVE = 0
    LEVEL_1_RECOMMEND = 1
    LEVEL_2_LOW_RISK_AUTO = 2
    LEVEL_3_APPROVAL_REQUIRED = 3
    LEVEL_4_EMERGENCY_POLICY = 4


class ContainmentStatus(str, Enum):
    REQUESTED = "REQUESTED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    VERIFIED_ACTIVE = "VERIFIED_ACTIVE"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class SecurityTelemetryEvent:
    event_id: str
    event_type: str
    source_component: str
    action_category: str
    outcome: str
    severity: SecuritySeverity = SecuritySeverity.INFO
    timestamp: float = field(default_factory=time.time)
    schema_version: int = 1
    source_identity: Optional[str] = None
    node_identity: Optional[str] = None
    correlation_id: Optional[str] = None
    resource_reference: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    data_classification: str = "INTERNAL"
    signature: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source_component": self.source_component,
            "action_category": self.action_category,
            "outcome": self.outcome,
            "severity": self.severity.value if isinstance(self.severity, SecuritySeverity) else str(self.severity),
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
            "source_identity": self.source_identity,
            "node_identity": self.node_identity,
            "correlation_id": self.correlation_id,
            "resource_reference": self.resource_reference,
            "details": self.details,
            "data_classification": self.data_classification,
            "signature": self.signature,
        }


@dataclass
class ThreatIndicator:
    indicator_id: str
    indicator_type: IndicatorType
    indicator_value: str
    source: str
    source_reliability: float = 0.5  # 0.0 to 1.0
    confidence: float = 0.5          # 0.0 to 1.0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    context: Dict[str, Any] = field(default_factory=dict)
    threat_classification: ThreatClassification = ThreatClassification.ANOMALOUS_BEHAVIOR
    validation_status: IndicatorValidationStatus = IndicatorValidationStatus.PENDING
    applicable_scope: str = "GLOBAL"

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        now = current_time or time.time()
        if self.expires_at is not None and now > self.expires_at:
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicator_id": self.indicator_id,
            "indicator_type": self.indicator_type.value if isinstance(self.indicator_type, IndicatorType) else str(self.indicator_type),
            "indicator_value": self.indicator_value,
            "source": self.source,
            "source_reliability": self.source_reliability,
            "confidence": self.confidence,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "expires_at": self.expires_at,
            "context": self.context,
            "threat_classification": self.threat_classification.value if isinstance(self.threat_classification, ThreatClassification) else str(self.threat_classification),
            "validation_status": self.validation_status.value if isinstance(self.validation_status, IndicatorValidationStatus) else str(self.validation_status),
            "applicable_scope": self.applicable_scope,
        }


@dataclass
class SecurityDetectionRule:
    rule_id: str
    name: str
    description: str
    threat_classification: ThreatClassification
    severity: SecuritySeverity
    required_telemetry_types: List[str]
    matching_criteria: Dict[str, Any]
    confidence: float = 0.8
    version: int = 1
    is_active: bool = True
    suppression_window_sec: float = 60.0
    expected_response_level: ResponseAutonomyLevel = ResponseAutonomyLevel.LEVEL_1_RECOMMEND

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "threat_classification": self.threat_classification.value if isinstance(self.threat_classification, ThreatClassification) else str(self.threat_classification),
            "severity": self.severity.value if isinstance(self.severity, SecuritySeverity) else str(self.severity),
            "required_telemetry_types": self.required_telemetry_types,
            "matching_criteria": self.matching_criteria,
            "confidence": self.confidence,
            "version": self.version,
            "is_active": self.is_active,
            "suppression_window_sec": self.suppression_window_sec,
            "expected_response_level": int(self.expected_response_level),
        }


@dataclass
class ThreatAlert:
    alert_id: str
    rule_id: str
    title: str
    threat_classification: ThreatClassification
    severity: SecuritySeverity
    confidence: float
    trigger_event_ids: List[str]
    affected_resources: List[str]
    explanation: str
    timestamp: float = field(default_factory=time.time)
    source_identity: Optional[str] = None
    node_identity: Optional[str] = None
    suggested_response_level: ResponseAutonomyLevel = ResponseAutonomyLevel.LEVEL_1_RECOMMEND

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "title": self.title,
            "threat_classification": self.threat_classification.value if isinstance(self.threat_classification, ThreatClassification) else str(self.threat_classification),
            "severity": self.severity.value if isinstance(self.severity, SecuritySeverity) else str(self.severity),
            "confidence": self.confidence,
            "trigger_event_ids": self.trigger_event_ids,
            "affected_resources": self.affected_resources,
            "explanation": self.explanation,
            "timestamp": self.timestamp,
            "source_identity": self.source_identity,
            "node_identity": self.node_identity,
            "suggested_response_level": int(self.suggested_response_level),
        }


@dataclass
class SecurityIncident:
    incident_id: str
    title: str
    threat_classification: ThreatClassification
    severity: SecuritySeverity
    confidence: float
    detection_source: str
    affected_assets: List[str]
    related_event_ids: List[str]
    evidence_ids: List[str] = field(default_factory=list)
    status: IncidentStatus = IncidentStatus.DETECTED
    assigned_owner: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    containment_action_ids: List[str] = field(default_factory=list)
    resolution_summary: Optional[str] = None
    audit_history: List[Dict[str, Any]] = field(default_factory=list)

    def transition_to(self, new_status: IncidentStatus, actor: str, reason: str) -> None:
        allowed = VALID_INCIDENT_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid incident state transition from '{self.status.value}' to '{new_status.value}'. "
                f"Allowed transitions: {[s.value for s in allowed]}"
            )
        old_status = self.status
        self.status = new_status
        self.updated_at = time.time()
        self.audit_history.append({
            "from_status": old_status.value,
            "to_status": new_status.value,
            "actor": actor,
            "reason": reason,
            "timestamp": self.updated_at,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "threat_classification": self.threat_classification.value if isinstance(self.threat_classification, ThreatClassification) else str(self.threat_classification),
            "severity": self.severity.value if isinstance(self.severity, SecuritySeverity) else str(self.severity),
            "confidence": self.confidence,
            "detection_source": self.detection_source,
            "affected_assets": self.affected_assets,
            "related_event_ids": self.related_event_ids,
            "evidence_ids": self.evidence_ids,
            "status": self.status.value if isinstance(self.status, IncidentStatus) else str(self.status),
            "assigned_owner": self.assigned_owner,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "containment_action_ids": self.containment_action_ids,
            "resolution_summary": self.resolution_summary,
            "audit_history": self.audit_history,
        }


@dataclass
class ContainmentAction:
    action_id: str
    incident_id: str
    action_type: str  # e.g., "suspend_worker", "revoke_session", "isolate_node", "quarantine_artifact"
    target_resource: str
    scope: str
    reason: str
    response_level: ResponseAutonomyLevel
    status: ContainmentStatus = ContainmentStatus.REQUESTED
    is_reversible: bool = True
    approval_request_id: Optional[str] = None
    approval_token: Optional[str] = None
    requested_at: float = field(default_factory=time.time)
    executed_at: Optional[float] = None
    verified_at: Optional[float] = None
    verification_evidence: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "incident_id": self.incident_id,
            "action_type": self.action_type,
            "target_resource": self.target_resource,
            "scope": self.scope,
            "reason": self.reason,
            "response_level": int(self.response_level),
            "status": self.status.value if isinstance(self.status, ContainmentStatus) else str(self.status),
            "is_reversible": self.is_reversible,
            "approval_request_id": self.approval_request_id,
            "approval_token": self.approval_token,
            "requested_at": self.requested_at,
            "executed_at": self.executed_at,
            "verified_at": self.verified_at,
            "verification_evidence": self.verification_evidence,
            "error_message": self.error_message,
        }


@dataclass
class ForensicEvidenceRecord:
    evidence_id: str
    incident_id: str
    artifact_type: str  # e.g., "security_event", "config_snapshot", "audit_log", "traffic_metadata"
    source_identifier: str
    collector_identity: str
    integrity_digest: str  # SHA-256
    raw_payload_redacted: str
    collected_at: float = field(default_factory=time.time)
    data_classification: str = "CONFIDENTIAL"
    chain_of_custody: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "incident_id": self.incident_id,
            "artifact_type": self.artifact_type,
            "source_identifier": self.source_identifier,
            "collector_identity": self.collector_identity,
            "integrity_digest": self.integrity_digest,
            "raw_payload_redacted": self.raw_payload_redacted,
            "collected_at": self.collected_at,
            "data_classification": self.data_classification,
            "chain_of_custody": self.chain_of_custody,
        }


@dataclass
class SecurityPostureAssessment:
    assessment_id: str
    overall_state: SecurityPostureState
    score: float  # 0.0 to 100.0
    active_incidents_count: int
    critical_alerts_count: int
    monitored_sources_count: int
    missing_sources: List[str]
    component_posture: Dict[str, SecurityPostureState]
    recommended_remediations: List[str]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "overall_state": self.overall_state.value if isinstance(self.overall_state, SecurityPostureState) else str(self.overall_state),
            "score": self.score,
            "active_incidents_count": self.active_incidents_count,
            "critical_alerts_count": self.critical_alerts_count,
            "monitored_sources_count": self.monitored_sources_count,
            "missing_sources": self.missing_sources,
            "component_posture": {k: (v.value if isinstance(v, SecurityPostureState) else str(v)) for k, v in self.component_posture.items()},
            "recommended_remediations": self.recommended_remediations,
            "timestamp": self.timestamp,
        }
