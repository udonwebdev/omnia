"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Domain Models, Enums, and Value Objects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ComponentReliabilityCriticality(str, enum.Enum):
    MISSION_CRITICAL = "MISSION_CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FailureDomain(str, enum.Enum):
    PROCESS = "PROCESS"
    HOST = "HOST"
    ZONE = "ZONE"
    REGION = "REGION"
    NETWORK = "NETWORK"
    STORAGE = "STORAGE"
    DEPENDENCY = "DEPENDENCY"


class ResilienceObjectiveType(str, enum.Enum):
    RTO = "RTO"  # Recovery Time Objective (seconds)
    RPO = "RPO"  # Recovery Point Objective (seconds)
    MAX_DOWNTIME = "MAX_DOWNTIME"
    AVAILABILITY_PCT = "AVAILABILITY_PCT"
    FAILOVER_LATENCY = "FAILOVER_LATENCY"
    DATA_LOSS_TOLERANCE = "DATA_LOSS_TOLERANCE"


class ExperimentLifecycleState(str, enum.Enum):
    DEFINED = "DEFINED"
    APPROVED = "APPROVED"
    RUNNING = "RUNNING"
    ABORTED = "ABORTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BackupType(str, enum.Enum):
    FULL = "FULL"
    INCREMENTAL = "INCREMENTAL"
    DIFFERENTIAL = "DIFFERENTIAL"
    SNAPSHOT = "SNAPSHOT"
    CHECKPOINT = "CHECKPOINT"
    STATE_DELTA = "STATE_DELTA"


class ValidationStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    CORRUPTED = "CORRUPTED"
    DEPRECATED = "DEPRECATED"


class RecoveryStrategy(str, enum.Enum):
    RESTART = "RESTART"
    REBUILD = "REBUILD"
    RESTORE_FROM_BACKUP = "RESTORE_FROM_BACKUP"
    FAILOVER = "FAILOVER"
    REPLICA_PROMOTION = "REPLICA_PROMOTION"
    STATE_RECONCILIATION = "STATE_RECONCILIATION"
    ISOLATION = "ISOLATION"


class FailoverReadinessState(str, enum.Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    NOT_READY = "NOT_READY"
    UNKNOWN = "UNKNOWN"


@dataclass
class ReliabilityComponent:
    component_id: str
    component_name: str
    criticality: ComponentReliabilityCriticality
    owner: str
    failure_domain: FailureDomain
    data_ownership: str
    dependencies: List[str] = field(default_factory=list)
    recovery_procedure: str = "DEFAULT_RESTART"
    backup_strategy: BackupType = BackupType.SNAPSHOT
    redundancy_config: str = "N+1"
    failover_readiness: FailoverReadinessState = FailoverReadinessState.READY
    last_assessment_at: Optional[str] = None
    last_recovery_drill_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class FailureModeRecord:
    mode_id: str
    component_id: str
    failure_mode_name: str
    potential_causes: List[str] = field(default_factory=list)
    local_impact: str = "Component Degraded"
    downstream_impact: str = "None"
    detectability_score: int = 5  # 1 (easily detected) to 10 (hidden)
    severity_score: int = 5       # 1 (minor) to 10 (catastrophic)
    probability_score: int = 5    # 1 (rare) to 10 (frequent)
    risk_priority_number: int = 125 # detectability * severity * probability
    is_spof: bool = False
    existing_controls: List[str] = field(default_factory=list)
    recommended_mitigation: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ResilienceObjectiveRecord:
    objective_id: str
    component_id: str
    objective_type: ResilienceObjectiveType
    target_value: float
    unit: str
    demonstrated_value: Optional[float] = None
    is_demonstrated: bool = False
    verification_evidence: Optional[str] = None
    last_verified_at: Optional[str] = None


@dataclass
class FailureScenarioRecord:
    scenario_id: str
    title: str
    category: str  # APPLICATION, INFRASTRUCTURE, DISTRIBUTED, DATA, DEPENDENCY
    target_environment: str  # MUST NOT BE PRODUCTION WITHOUT APPROVAL
    affected_components: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    injection_method: str = "SIMULATION"
    safety_constraints: List[str] = field(default_factory=list)
    expected_behavior: str = ""
    abort_conditions: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class FaultInjectionExperiment:
    experiment_id: str
    scenario_id: str
    hypothesis: str
    target_environment: str
    lifecycle_state: ExperimentLifecycleState = ExperimentLifecycleState.DEFINED
    max_duration_sec: float = 300.0
    actual_duration_sec: float = 0.0
    containment_successful: bool = False
    cascading_failure_detected: bool = False
    approval_token: Optional[str] = None
    approved_by: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    observations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BackupRecord:
    backup_id: str
    data_source: str
    backup_type: BackupType
    version: str
    storage_reference: str
    checksum_sha256: str
    is_encrypted: bool = True
    retention_days: int = 30
    record_count: int = 0
    size_bytes: int = 0
    validation_status: ValidationStatus = ValidationStatus.PENDING
    last_validated_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class BackupValidationRecord:
    validation_id: str
    backup_id: str
    status: ValidationStatus
    checksum_verified: bool
    schema_compatible: bool
    isolated_restore_tested: bool
    record_count_matches: bool
    validation_notes: str = ""
    validated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DisasterRecoveryPlanRecord:
    plan_id: str
    title: str
    disaster_scenario: str
    version: int
    affected_services: List[str] = field(default_factory=list)
    recovery_priority: int = 1  # 1 = highest
    strategy: RecoveryStrategy = RecoveryStrategy.RESTORE_FROM_BACKUP
    dependency_order: List[str] = field(default_factory=list)
    target_rto_sec: float = 300.0
    target_rpo_sec: float = 60.0
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RecoveryExecutionRecord:
    execution_id: str
    plan_id: str
    target_environment: str
    status: str = "IN_PROGRESS"
    approval_token: Optional[str] = None
    approved_by: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_sec: float = 0.0
    steps_executed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class RecoveryVerificationRecord:
    verification_id: str
    execution_id: str
    component_id: str
    service_responsive: bool
    data_integrity_verified: bool
    distributed_state_reconciled: bool
    actual_rto_sec: float
    actual_rpo_sec: float
    rto_compliant: bool
    rpo_compliant: bool
    findings: List[str] = field(default_factory=list)
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class StateIntegrityFinding:
    finding_id: str
    subsystem: str
    divergence_type: str  # MISSING_RECORD, SPLIT_BRAIN, STALE_REPLICA, CORRUPTED_OFFSET
    severity: str = "HIGH"
    details: str = ""
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ResilienceRegressionRecord:
    regression_id: str
    component_id: str
    metric_name: str
    baseline_value: float
    current_value: float
    degradation_pct: float
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
