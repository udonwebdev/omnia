"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Domain Models, Enums, and Value Objects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ServiceCriticality(str, enum.Enum):
    MISSION_CRITICAL = "MISSION_CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SystemHealthState(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"
    MAINTENANCE = "MAINTENANCE"


class IncidentSeverity(str, enum.Enum):
    SEV_1_CRITICAL = "SEV_1_CRITICAL"
    SEV_2_HIGH = "SEV_2_HIGH"
    SEV_3_MODERATE = "SEV_3_MODERATE"
    SEV_4_LOW = "SEV_4_LOW"
    INFORMATIONAL = "INFORMATIONAL"


class IncidentLifecycleState(str, enum.Enum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    MITIGATING = "MITIGATING"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"
    REVIEWED = "REVIEWED"
    CLOSED = "CLOSED"


class RecoveryActionStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    VERIFIED = "VERIFIED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class ServiceRecord:
    service_id: str
    service_name: str
    description: str
    version: str
    environment: str
    owner: str
    criticality: ServiceCriticality
    health_endpoint: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    current_state: SystemHealthState = SystemHealthState.UNKNOWN
    last_observed_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class HealthObservationRecord:
    observation_id: str
    service_id: str
    health_state: SystemHealthState
    latency_ms: float
    error_rate: float
    status_message: str
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_stale: bool = False


@dataclass
class MetricRecord:
    metric_id: str
    service_id: str
    metric_name: str
    value: float
    unit: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LogRecord:
    log_id: str
    service_id: str
    level: str  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message: str
    error_category: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TraceSpanRecord:
    span_id: str
    trace_id: str
    service_id: str
    operation_name: str
    duration_ms: float
    status_code: int = 200
    parent_span_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SLORecord:
    slo_id: str
    service_id: str
    name: str
    target_pct: float
    current_sli_pct: float
    error_budget_remaining_pct: float
    burn_rate: float
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class IncidentAlertRecord:
    alert_id: str
    service_id: str
    alert_name: str
    severity: IncidentSeverity
    symptom_description: str
    supporting_metric_value: float
    correlated_incident_id: Optional[str] = None
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class IncidentRecord:
    incident_id: str
    title: str
    severity: IncidentSeverity
    state: IncidentLifecycleState
    primary_service_id: str
    affected_services: List[str] = field(default_factory=list)
    correlated_alert_ids: List[str] = field(default_factory=list)
    assigned_to: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None


@dataclass
class RootCauseFinding:
    finding_id: str
    incident_id: str
    candidate_cause: str
    confidence: float
    supporting_evidence: List[str] = field(default_factory=list)
    contradictory_evidence: List[str] = field(default_factory=list)
    investigated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ImpactAssessmentRecord:
    assessment_id: str
    incident_id: str
    blast_radius_score: float  # 0.0 - 1.0
    affected_workflows: List[str] = field(default_factory=list)
    data_integrity_risk: str = "LOW"
    operational_disruption: str = "LOW"
    financial_exposure_estimate: float = 0.0
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RecoveryProposalRecord:
    proposal_id: str
    incident_id: str
    target_service_id: str
    action_name: str
    rationale: str
    expected_benefit: str
    risk_level: str
    requires_human_approval: bool = True
    status: RecoveryActionStatus = RecoveryActionStatus.PROPOSED
    approval_token: Optional[str] = None
    approved_by: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PostIncidentReport:
    report_id: str
    incident_id: str
    title: str
    summary: str
    root_cause: str
    timeline_events: List[Dict[str, Any]] = field(default_factory=list)
    what_went_well: List[str] = field(default_factory=list)
    what_failed: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)
    published_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
