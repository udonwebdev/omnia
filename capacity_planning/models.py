"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Domain Models, Enums, and Value Objects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class ResourceDimension(str, enum.Enum):
    COMPUTE = "COMPUTE"
    STORAGE = "STORAGE"
    NETWORKING = "NETWORKING"
    APPLICATION = "APPLICATION"


class MetricUnit(str, enum.Enum):
    PERCENT = "PERCENT"
    CORES = "CORES"
    MEGABYTES = "MEGABYTES"
    GIGABYTES = "GIGABYTES"
    TERABYTES = "TERABYTES"
    IOPS = "IOPS"
    MEGABITS_PER_SEC = "MEGABITS_PER_SEC"
    MILLISECONDS = "MILLISECONDS"
    COUNT = "COUNT"
    REQUESTS_PER_SEC = "REQUESTS_PER_SEC"
    CONNECTIONS = "CONNECTIONS"
    DOLLARS_PER_HOUR = "DOLLARS_PER_HOUR"


class WorkloadCategory(str, enum.Enum):
    INTERACTIVE = "INTERACTIVE"
    BACKGROUND = "BACKGROUND"
    SCHEDULED = "SCHEDULED"
    HIGH_PRIORITY_MISSION = "HIGH_PRIORITY_MISSION"
    RESOURCE_INTENSIVE = "RESOURCE_INTENSIVE"
    TIME_SENSITIVE = "TIME_SENSITIVE"
    BATCH_PROCESSING = "BATCH_PROCESSING"
    DISTRIBUTED_EXECUTION = "DISTRIBUTED_EXECUTION"
    EXTERNAL_API_DEPENDENT = "EXTERNAL_API_DEPENDENT"


class ForecastHorizon(str, enum.Enum):
    ONE_HOUR = "1H"
    TWENTY_FOUR_HOURS = "24H"
    SEVEN_DAYS = "7D"
    THIRTY_DAYS = "30D"


class SaturationRiskSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ScalingStrategyType(str, enum.Enum):
    HORIZONTAL_SCALE_OUT = "HORIZONTAL_SCALE_OUT"
    HORIZONTAL_SCALE_IN = "HORIZONTAL_SCALE_IN"
    VERTICAL_SCALE_UP = "VERTICAL_SCALE_UP"
    VERTICAL_SCALE_DOWN = "VERTICAL_SCALE_DOWN"
    WORKER_POOL_EXPANSION = "WORKER_POOL_EXPANSION"
    WORKER_POOL_REDUCTION = "WORKER_POOL_REDUCTION"
    RESOURCE_REDISTRIBUTION = "RESOURCE_REDISTRIBUTION"
    CAPACITY_RESERVATION = "CAPACITY_RESERVATION"
    WORKLOAD_THROTTLING = "WORKLOAD_THROTTLING"


class ScalingGovernanceMode(str, enum.Enum):
    ADVISORY = "ADVISORY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    POLICY_AUTHORIZED = "POLICY_AUTHORIZED"


class ScalingProposalStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class ResourceInventoryItem:
    resource_id: str
    resource_name: str
    dimension: ResourceDimension
    resource_type: str  # e.g., "CPU_CORES", "MEMORY_RAM", "DATABASE_CONNECTIONS"
    source: str         # e.g., "LOCAL_HOST", "GCP_DATAPROC", "WORKER_MESH"
    total_capacity: float
    unit: MetricUnit
    associated_service: str = "omnia-core"
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ResourceMeasurementRecord:
    measurement_id: str
    resource_id: str
    timestamp: str
    current_value: float
    configured_capacity: float
    available_headroom: float
    utilization_pct: float
    unit: MetricUnit
    collection_status: str = "VALID"  # VALID, STALE, DEGRADED, UNAVAILABLE
    data_confidence: float = 1.0     # 0.0 to 1.0


@dataclass
class WorkloadDemandProfile:
    profile_id: str
    category: WorkloadCategory
    workload_name: str
    avg_cpu_consumption: float
    avg_memory_mb: float
    avg_duration_sec: float
    request_rate_per_sec: float = 0.0
    burstiness_index: float = 1.0  # peak / average
    concurrency_requirement: int = 1
    sample_count: int = 1
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CapacityForecastRecord:
    forecast_id: str
    resource_id: str
    horizon: ForecastHorizon
    forecasted_demand: float
    current_capacity: float
    projected_headroom: float
    projected_utilization_pct: float
    estimated_saturation_hours: Optional[float]
    confidence_lower_bound: float
    confidence_upper_bound: float
    confidence_score: float
    model_method: str = "LINEAR_TREND_EXPONENTIAL_SMOOTHING"
    data_quality: str = "HIGH"  # HIGH, MEDIUM, LOW_DATA
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SaturationRiskFinding:
    risk_id: str
    resource_id: str
    severity: SaturationRiskSeverity
    observed_utilization_pct: float
    estimated_time_to_saturation_hours: Optional[float]
    likely_cause: str
    expected_operational_impact: str
    recommended_mitigation: str
    confidence_level: float
    is_resolved: bool = False
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ScalingStrategyEvaluation:
    evaluation_id: str
    resource_id: str
    strategy_type: ScalingStrategyType
    proposed_capacity_change: float
    expected_headroom_increase: float
    expected_performance_gain_pct: float
    estimated_cost_delta_per_hr: float
    operational_complexity: str  # LOW, MEDIUM, HIGH
    reversibility: bool = True
    policy_compatible: bool = True
    risk_score: float = 0.1      # 0.0 (safe) to 1.0 (dangerous)


@dataclass
class InfrastructureCostProjection:
    projection_id: str
    current_hourly_cost: float
    projected_monthly_cost: float
    cost_by_dimension: Dict[str, float] = field(default_factory=dict)
    potential_savings_monthly: float = 0.0
    pricing_status: str = "CONFIGURED_ESTIMATE"  # CONFIGURED_ESTIMATE, EXACT_PROVIDER, UNKNOWN
    currency: str = "USD"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CapacityScenarioDefinition:
    scenario_id: str
    scenario_name: str
    workload_multiplier: float  # e.g., 2.0, 5.0, 10.0
    unavailable_resources: List[str] = field(default_factory=list)
    quota_reduction_pct: float = 0.0
    description: str = ""


@dataclass
class CapacitySimulationResult:
    simulation_id: str
    scenario_id: str
    max_projected_utilization_pct: float
    bottleneck_resources: List[str] = field(default_factory=list)
    throughput_degradation_pct: float = 0.0
    latency_increase_factor: float = 1.0
    estimated_additional_cost_hr: float = 0.0
    recommended_scaling_action: str = ""
    is_resilient: bool = True
    simulated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CapacityPlanRecord:
    plan_id: str
    title: str
    horizon: ForecastHorizon
    current_health_posture: str
    identified_gaps: List[str] = field(default_factory=list)
    recommended_strategies: List[Dict[str, Any]] = field(default_factory=list)
    estimated_total_cost_delta: float = 0.0
    required_governance_mode: ScalingGovernanceMode = ScalingGovernanceMode.APPROVAL_REQUIRED
    approval_token: Optional[str] = None
    status: str = "PROPOSED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ScalingProposalRecord:
    proposal_id: str
    plan_id: str
    resource_id: str
    strategy_type: ScalingStrategyType
    from_capacity: float
    to_capacity: float
    cost_impact_per_hr: float
    status: ScalingProposalStatus = ScalingProposalStatus.PROPOSED
    approval_token: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ScalingExecutionRecord:
    execution_id: str
    proposal_id: str
    resource_id: str
    applied_capacity: float
    previous_capacity: float
    status: str = "SUCCESS"
    executed_by: str = "autonomous_governor"
    execution_notes: str = ""
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ForecastAccuracyEvaluation:
    evaluation_id: str
    forecast_id: str
    resource_id: str
    predicted_demand: float
    actual_demand: float
    absolute_error: float
    percentage_error: float
    within_confidence_bounds: bool
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
