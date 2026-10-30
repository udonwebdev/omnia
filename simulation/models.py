"""
Omnia Module 34: Simulation & Digital Twin Domain Models
Strongly typed enums, dataclasses, and lifecycle states for digital twins,
sandboxed simulation environments, snapshots, scenarios, and executions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EnvironmentType(str, Enum):
    DETERMINISTIC_STATE = "DETERMINISTIC_STATE"
    DISCRETE_EVENT = "DISCRETE_EVENT"
    WORKFLOW = "WORKFLOW"
    RESOURCE_CAPACITY = "RESOURCE_CAPACITY"
    DISTRIBUTED_SYSTEM = "DISTRIBUTED_SYSTEM"
    BROWSER_INTERACTION = "BROWSER_INTERACTION"
    DEVICE_OPERATION = "DEVICE_OPERATION"
    NETWORK_TOPOLOGY = "NETWORK_TOPOLOGY"
    FORECAST_SCENARIO = "FORECAST_SCENARIO"
    CUSTOM_DOMAIN = "CUSTOM_DOMAIN"


class EnvironmentClassification(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"
    STAGING = "STAGING"
    PRODUCTION_MIRROR = "PRODUCTION_MIRROR"


class TwinStatus(str, Enum):
    INITIALIZED = "INITIALIZED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    ARCHIVED = "ARCHIVED"


class TwinSyncMode(str, Enum):
    STATIC = "STATIC"
    DYNAMIC = "DYNAMIC"


class StateFidelity(str, Enum):
    UNVALIDATED = "UNVALIDATED"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VALIDATED_FOR_SCOPE = "VALIDATED_FOR_SCOPE"


class ScenarioType(str, Enum):
    NORMAL_OPERATION = "NORMAL_OPERATION"
    FAILURE_INJECTION = "FAILURE_INJECTION"
    CAPACITY_STRESS = "CAPACITY_STRESS"
    RESOURCE_CONTENTION = "RESOURCE_CONTENTION"
    NETWORK_INTERRUPTION = "NETWORK_INTERRUPTION"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    DELAYED_RESPONSE = "DELAYED_RESPONSE"
    INVALID_INPUT = "INVALID_INPUT"
    PARTIAL_COMPLETION = "PARTIAL_COMPLETION"
    RECOVERY_AND_RETRY = "RECOVERY_AND_RETRY"
    ALTERNATIVE_PATHS = "ALTERNATIVE_PATHS"
    SECURITY_BOUNDARY = "SECURITY_BOUNDARY"
    CONFIGURATION_CHANGE = "CONFIGURATION_CHANGE"
    DISTRIBUTED_COORDINATION = "DISTRIBUTED_COORDINATION"


class SimulationStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FaultType(str, Enum):
    WORKER_CRASH = "WORKER_CRASH"
    NETWORK_PARTITION = "NETWORK_PARTITION"
    API_TIMEOUT = "API_TIMEOUT"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    EVENT_DELAY = "EVENT_DELAY"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    STALE_OWNERSHIP = "STALE_OWNERSHIP"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    PARTIAL_WRITE = "PARTIAL_WRITE"
    PROCESS_RESTART = "PROCESS_RESTART"
    CORRUPT_INPUT = "CORRUPT_INPUT"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"


class AlternativeSearchStrategy(str, Enum):
    BREADTH_FIRST = "BREADTH_FIRST"
    DEPTH_FIRST = "DEPTH_FIRST"
    COST_OPTIMIZED = "COST_OPTIMIZED"
    RELIABILITY_OPTIMIZED = "RELIABILITY_OPTIMIZED"


# -------------------------------------------------------------------------
# DOMAIN ENTITIES
# -------------------------------------------------------------------------

@dataclass
class SimulationEnvironment:
    environment_id: str
    name: str
    env_type: EnvironmentType
    classification: EnvironmentClassification = EnvironmentClassification.TEST
    version: str = "1.0.0"
    owner: str = "system"
    model_references: List[str] = field(default_factory=list)
    supported_capabilities: List[str] = field(default_factory=list)
    state_schema: Dict[str, Any] = field(default_factory=dict)
    supported_action_types: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    isolation_level: str = "PROCESS_ISOLATED"
    fidelity_classification: StateFidelity = StateFidelity.UNVALIDATED
    data_classification: str = "INTERNAL"
    status: str = "ACTIVE"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "name": self.name,
            "env_type": self.env_type.value if isinstance(self.env_type, EnvironmentType) else str(self.env_type),
            "classification": self.classification.value if isinstance(self.classification, EnvironmentClassification) else str(self.classification),
            "version": self.version,
            "owner": self.owner,
            "model_references": self.model_references,
            "supported_capabilities": self.supported_capabilities,
            "state_schema": self.state_schema,
            "supported_action_types": self.supported_action_types,
            "constraints": self.constraints,
            "resource_limits": self.resource_limits,
            "isolation_level": self.isolation_level,
            "fidelity_classification": self.fidelity_classification.value if isinstance(self.fidelity_classification, StateFidelity) else str(self.fidelity_classification),
            "data_classification": self.data_classification,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class DigitalTwin:
    twin_id: str
    source_system_id: str
    source_system_type: str
    version: str = "1.0.0"
    sync_mode: TwinSyncMode = TwinSyncMode.STATIC
    state_schema_version: str = "1.0.0"
    observed_state: Dict[str, Any] = field(default_factory=dict)
    inferred_state: Dict[str, Any] = field(default_factory=dict)
    simulated_state: Dict[str, Any] = field(default_factory=dict)
    capability_model: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    known_omissions: List[str] = field(default_factory=list)
    last_sync_time: float = field(default_factory=time.time)
    freshness_seconds: float = 0.0
    fidelity_status: StateFidelity = StateFidelity.UNVALIDATED
    provenance_hash: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "twin_id": self.twin_id,
            "source_system_id": self.source_system_id,
            "source_system_type": self.source_system_type,
            "version": self.version,
            "sync_mode": self.sync_mode.value if isinstance(self.sync_mode, TwinSyncMode) else str(self.sync_mode),
            "state_schema_version": self.state_schema_version,
            "observed_state": self.observed_state,
            "inferred_state": self.inferred_state,
            "simulated_state": self.simulated_state,
            "capability_model": self.capability_model,
            "constraints": self.constraints,
            "dependencies": self.dependencies,
            "known_omissions": self.known_omissions,
            "last_sync_time": self.last_sync_time,
            "freshness_seconds": self.freshness_seconds,
            "fidelity_status": self.fidelity_status.value if isinstance(self.fidelity_status, StateFidelity) else str(self.fidelity_status),
            "provenance_hash": self.provenance_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class StateSnapshot:
    snapshot_id: str
    environment_id: str
    source_version: str
    captured_at: float
    state_payload: Dict[str, Any]
    integrity_digest: str
    state_schema_version: str = "1.0.0"
    included_components: List[str] = field(default_factory=list)
    excluded_components: List[str] = field(default_factory=list)
    consistency_status: str = "CONSISTENT"
    data_classification: str = "INTERNAL"
    known_limitations: List[str] = field(default_factory=list)
    created_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "environment_id": self.environment_id,
            "source_version": self.source_version,
            "captured_at": self.captured_at,
            "state_schema_version": self.state_schema_version,
            "state_payload": self.state_payload,
            "included_components": self.included_components,
            "excluded_components": self.excluded_components,
            "integrity_digest": self.integrity_digest,
            "consistency_status": self.consistency_status,
            "data_classification": self.data_classification,
            "known_limitations": self.known_limitations,
            "created_by": self.created_by,
        }


@dataclass
class ScenarioDefinition:
    scenario_id: str
    name: str
    scenario_type: ScenarioType
    environment_id: str
    initial_snapshot_id: str
    proposed_actions: List[Dict[str, Any]] = field(default_factory=list)
    preconditions: Dict[str, Any] = field(default_factory=dict)
    constraints: Dict[str, Any] = field(default_factory=dict)
    expected_observations: Dict[str, Any] = field(default_factory=dict)
    time_horizon_seconds: float = 60.0
    resource_budget: Dict[str, Any] = field(default_factory=dict)
    uncertainty_assumptions: Dict[str, Any] = field(default_factory=dict)
    evaluation_metrics: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    created_by: str = "system"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "scenario_type": self.scenario_type.value if isinstance(self.scenario_type, ScenarioType) else str(self.scenario_type),
            "environment_id": self.environment_id,
            "initial_snapshot_id": self.initial_snapshot_id,
            "proposed_actions": self.proposed_actions,
            "preconditions": self.preconditions,
            "constraints": self.constraints,
            "expected_observations": self.expected_observations,
            "time_horizon_seconds": self.time_horizon_seconds,
            "resource_budget": self.resource_budget,
            "uncertainty_assumptions": self.uncertainty_assumptions,
            "evaluation_metrics": self.evaluation_metrics,
            "created_at": self.created_at,
            "created_by": self.created_by,
        }


@dataclass
class SimulationExecutionRecord:
    simulation_id: str
    scenario_id: str
    environment_id: str
    snapshot_id: str
    twin_id: Optional[str] = None
    status: SimulationStatus = SimulationStatus.CREATED
    current_step: int = 0
    total_steps: int = 0
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    state_transitions: List[Dict[str, Any]] = field(default_factory=list)
    events_generated: List[Dict[str, Any]] = field(default_factory=list)
    resource_consumption: Dict[str, float] = field(default_factory=dict)
    result_summary: Dict[str, Any] = field(default_factory=dict)
    fidelity_classification: StateFidelity = StateFidelity.UNVALIDATED
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario_id": self.scenario_id,
            "environment_id": self.environment_id,
            "twin_id": self.twin_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status.value if isinstance(self.status, SimulationStatus) else str(self.status),
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "action_history": self.action_history,
            "state_transitions": self.state_transitions,
            "events_generated": self.events_generated,
            "resource_consumption": self.resource_consumption,
            "result_summary": self.result_summary,
            "fidelity_classification": self.fidelity_classification.value if isinstance(self.fidelity_classification, StateFidelity) else str(self.fidelity_classification),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "created_at": self.created_at,
        }


@dataclass
class FaultInjectionSpec:
    fault_id: str
    simulation_id: str
    fault_type: FaultType
    target_component: str
    activation_step: int = 0
    duration_steps: int = 1
    severity: str = "HIGH"
    injected_at: float = field(default_factory=time.time)
    recovery_observed: bool = False
    recovery_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fault_id": self.fault_id,
            "simulation_id": self.simulation_id,
            "fault_type": self.fault_type.value if isinstance(self.fault_type, FaultType) else str(self.fault_type),
            "target_component": self.target_component,
            "activation_step": self.activation_step,
            "duration_steps": self.duration_steps,
            "severity": self.severity,
            "injected_at": self.injected_at,
            "recovery_observed": self.recovery_observed,
            "recovery_details": self.recovery_details,
        }


@dataclass
class FidelityAssessment:
    record_id: str
    simulation_id: str
    twin_id: Optional[str]
    fidelity_level: StateFidelity
    reality_observation_id: Optional[str] = None
    deviation_metrics: Dict[str, float] = field(default_factory=dict)
    failed_assumptions: List[str] = field(default_factory=list)
    unexplained_deviations: List[str] = field(default_factory=list)
    assessed_at: float = field(default_factory=time.time)
    recommended_learning_signal: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "simulation_id": self.simulation_id,
            "twin_id": self.twin_id,
            "fidelity_level": self.fidelity_level.value if isinstance(self.fidelity_level, StateFidelity) else str(self.fidelity_level),
            "reality_observation_id": self.reality_observation_id,
            "deviation_metrics": self.deviation_metrics,
            "failed_assumptions": self.failed_assumptions,
            "unexplained_deviations": self.unexplained_deviations,
            "assessed_at": self.assessed_at,
            "recommended_learning_signal": self.recommended_learning_signal,
        }
