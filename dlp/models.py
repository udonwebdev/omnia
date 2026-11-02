"""
dlp/models.py
Data models and Enums for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import time
import uuid


class EnforcementMode(str, Enum):
    OBSERVE = "OBSERVE"
    ALERT = "ALERT"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"
    REDACT = "REDACT"


class DLPChannel(str, Enum):
    ENDPOINT = "ENDPOINT"
    NETWORK = "NETWORK"
    CLOUD = "CLOUD"
    COMMUNICATION = "COMMUNICATION"
    REMOVABLE_MEDIA = "REMOVABLE_MEDIA"
    CLIPBOARD = "CLIPBOARD"


class DLPDecision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    QUARANTINE = "QUARANTINE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    REDACT = "REDACT"


class DLPSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ContainmentState(str, Enum):
    DETECTED = "DETECTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    CONTAINED = "CONTAINED"
    VERIFIED = "VERIFIED"
    RESOLVED = "RESOLVED"


class EndpointStatus(str, Enum):
    ENROLLED = "ENROLLED"
    HEALTHY = "HEALTHY"
    UNREACHABLE = "UNREACHABLE"
    REVOKED = "REVOKED"


class FingerprintAlgorithm(str, Enum):
    SHA256_EXACT = "SHA256_EXACT"
    ROLLING_SHINGLE = "ROLLING_SHINGLE"


class DataCategory(str, Enum):
    PII = "PII"
    FINANCIAL = "FINANCIAL"
    CREDENTIALS = "CREDENTIALS"
    INTELLECTUAL_PROPERTY = "INTELLECTUAL_PROPERTY"
    HEALTHCARE = "HEALTHCARE"
    SOURCE_CODE = "SOURCE_CODE"
    GOV_ID = "GOV_ID"


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


class ActionStatus(str, Enum):
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    SIMULATED = "SIMULATED"
    BYPASSED = "BYPASSED"


class TelemetryOpType(str, Enum):
    FILE_COPY = "FILE_COPY"
    CLIPBOARD = "CLIPBOARD"
    PRINT = "PRINT"
    LOCAL_EXPORT = "LOCAL_EXPORT"


@dataclass
class DLPPolicy:
    policy_id: str
    name: str
    description: str
    category: str
    min_sensitivity_tier: str
    channel: str
    mode: str
    priority: int = 100
    is_active: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    conditions: Dict[str, Any] = field(default_factory=dict)
    actions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "min_sensitivity_tier": self.min_sensitivity_tier,
            "channel": self.channel,
            "mode": self.mode,
            "priority": self.priority,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "conditions": self.conditions,
            "actions": self.actions,
        }


@dataclass
class DLPPolicyVersion:
    version_id: str
    policy_id: str
    version_num: int
    changes_summary: str
    created_at: float
    created_by: str
    snapshot: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "policy_id": self.policy_id,
            "version_num": self.version_num,
            "changes_summary": self.changes_summary,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "snapshot": self.snapshot,
        }


@dataclass
class ProtectedFingerprint:
    fingerprint_id: str
    name: str
    data_category: str
    fingerprint_hash: str
    algorithm: str
    threshold: float = 0.8
    is_active: bool = True
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint_id": self.fingerprint_id,
            "name": self.name,
            "data_category": self.data_category,
            "fingerprint_hash": self.fingerprint_hash,
            "algorithm": self.algorithm,
            "threshold": self.threshold,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class SensitiveFinding:
    finding_id: str
    source_ref: str
    data_category: str
    sensitivity_tier: str
    detection_method: str
    confidence: float
    matched_tokens_count: int
    detected_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "source_ref": self.source_ref,
            "data_category": self.data_category,
            "sensitivity_tier": self.sensitivity_tier,
            "detection_method": self.detection_method,
            "confidence": self.confidence,
            "matched_tokens_count": self.matched_tokens_count,
            "detected_at": self.detected_at,
            "metadata": self.metadata,
        }


@dataclass
class MovementEvent:
    event_id: str
    actor_id: str
    device_id: str
    source_location: str
    destination_location: str
    channel: str
    volume_bytes: int
    timestamp: float = field(default_factory=time.time)
    is_authorized: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "actor_id": self.actor_id,
            "device_id": self.device_id,
            "source_location": self.source_location,
            "destination_location": self.destination_location,
            "channel": self.channel,
            "volume_bytes": self.volume_bytes,
            "timestamp": self.timestamp,
            "is_authorized": self.is_authorized,
            "metadata": self.metadata,
        }


@dataclass
class TransferDecision:
    decision_id: str
    event_id: str
    policy_id: Optional[str]
    decision: str
    reason: str
    evaluated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "event_id": self.event_id,
            "policy_id": self.policy_id,
            "decision": self.decision,
            "reason": self.reason,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class EnforcementAction:
    action_id: str
    decision_id: str
    event_id: str
    adapter_type: str
    action_status: str
    execution_result: str
    verified: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "decision_id": self.decision_id,
            "event_id": self.event_id,
            "adapter_type": self.adapter_type,
            "action_status": self.action_status,
            "execution_result": self.execution_result,
            "verified": self.verified,
            "timestamp": self.timestamp,
        }


@dataclass
class EndpointEnrollment:
    endpoint_id: str
    hostname: str
    os_type: str
    agent_version: str
    status: str
    enrolled_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "hostname": self.hostname,
            "os_type": self.os_type,
            "agent_version": self.agent_version,
            "status": self.status,
            "enrolled_at": self.enrolled_at,
            "last_heartbeat": self.last_heartbeat,
        }


@dataclass
class EndpointTelemetry:
    telemetry_id: str
    endpoint_id: str
    operation_type: str
    file_path: Optional[str]
    process_name: Optional[str]
    volume_bytes: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "telemetry_id": self.telemetry_id,
            "endpoint_id": self.endpoint_id,
            "operation_type": self.operation_type,
            "file_path": self.file_path,
            "process_name": self.process_name,
            "volume_bytes": self.volume_bytes,
            "timestamp": self.timestamp,
        }


@dataclass
class NetworkTelemetry:
    net_telemetry_id: str
    source_ip: str
    dest_ip: str
    dest_domain: Optional[str]
    protocol: str
    bytes_out: int
    bytes_in: int
    is_encrypted: bool = True
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "net_telemetry_id": self.net_telemetry_id,
            "source_ip": self.source_ip,
            "dest_ip": self.dest_ip,
            "dest_domain": self.dest_domain,
            "protocol": self.protocol,
            "bytes_out": self.bytes_out,
            "bytes_in": self.bytes_in,
            "is_encrypted": self.is_encrypted,
            "timestamp": self.timestamp,
        }


@dataclass
class CloudEvent:
    cloud_event_id: str
    service_name: str
    storage_target: str
    action_type: str
    external_recipients: List[str] = field(default_factory=list)
    volume_bytes: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cloud_event_id": self.cloud_event_id,
            "service_name": self.service_name,
            "storage_target": self.storage_target,
            "action_type": self.action_type,
            "external_recipients": self.external_recipients,
            "volume_bytes": self.volume_bytes,
            "timestamp": self.timestamp,
        }


@dataclass
class CommunicationEvent:
    comm_event_id: str
    app_name: str
    sender: str
    recipients: List[str] = field(default_factory=list)
    attachments: List[str] = field(default_factory=list)
    has_external_recipient: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comm_event_id": self.comm_event_id,
            "app_name": self.app_name,
            "sender": self.sender,
            "recipients": self.recipients,
            "attachments": self.attachments,
            "has_external_recipient": self.has_external_recipient,
            "timestamp": self.timestamp,
        }


@dataclass
class RemovableMediaEvent:
    media_event_id: str
    endpoint_id: str
    device_vendor: str
    serial_number: str
    file_name: str
    volume_bytes: int
    is_approved_device: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "media_event_id": self.media_event_id,
            "endpoint_id": self.endpoint_id,
            "device_vendor": self.device_vendor,
            "serial_number": self.serial_number,
            "file_name": self.file_name,
            "volume_bytes": self.volume_bytes,
            "is_approved_device": self.is_approved_device,
            "timestamp": self.timestamp,
        }


@dataclass
class ExfiltrationAlert:
    alert_id: str
    title: str
    severity: str
    risk_score: float
    confidence: float
    anomaly_indicators: List[str] = field(default_factory=list)
    actor_id: str = ""
    destination: str = ""
    status: str = "OPEN"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "severity": self.severity,
            "risk_score": self.risk_score,
            "confidence": self.confidence,
            "anomaly_indicators": self.anomaly_indicators,
            "actor_id": self.actor_id,
            "destination": self.destination,
            "status": self.status,
            "timestamp": self.timestamp,
        }


@dataclass
class DLPIncident:
    incident_id: str
    title: str
    severity: str
    containment_status: str
    affected_assets: List[str] = field(default_factory=list)
    evidence_package: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "severity": self.severity,
            "containment_status": self.containment_status,
            "affected_assets": self.affected_assets,
            "evidence_package": self.evidence_package,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DLPReport:
    report_id: str
    title: str
    findings_count: int
    blocked_transfers_count: int
    active_alerts_count: int
    sha256_seal: str
    generated_at: float = field(default_factory=time.time)
    report_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "findings_count": self.findings_count,
            "blocked_transfers_count": self.blocked_transfers_count,
            "active_alerts_count": self.active_alerts_count,
            "sha256_seal": self.sha256_seal,
            "generated_at": self.generated_at,
            "report_data": self.report_data,
        }
