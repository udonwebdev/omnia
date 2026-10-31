"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Domain Models, Enums, and Value Objects.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class GoalType(str, enum.Enum):
    STRATEGIC = "STRATEGIC"
    OPERATIONAL = "OPERATIONAL"
    FINANCIAL = "FINANCIAL"
    RESEARCH = "RESEARCH"
    LEARNING = "LEARNING"
    TECHNICAL = "TECHNICAL"
    MAINTENANCE = "MAINTENANCE"
    PERSONAL = "PERSONAL"


class GoalLifecycleState(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class GoalPriority(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class MetricType(str, enum.Enum):
    INCREASING = "INCREASING"      # Higher is better
    DECREASING = "DECREASING"      # Lower is better
    THRESHOLD = "THRESHOLD"        # Step satisfaction
    BINARY = "BINARY"              # 0 or 1
    MILESTONE = "MILESTONE"        # Stage completion
    QUALITATIVE = "QUALITATIVE"    # Verified evidence against criteria
    COMPOSITE = "COMPOSITE"        # Weighted collection


class VerificationTier(str, enum.Enum):
    SELF_REPORTED = "SELF_REPORTED"
    SYSTEM_OBSERVED = "SYSTEM_OBSERVED"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
    INDEPENDENTLY_AUDITED = "INDEPENDENTLY_AUDITED"


class GoalHealthState(str, enum.Enum):
    HEALTHY = "HEALTHY"
    AT_RISK = "AT_RISK"
    BLOCKED = "BLOCKED"
    STALLED = "STALLED"
    OFF_TRACK = "OFF_TRACK"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNKNOWN = "UNKNOWN"


class CorrectiveActionType(str, enum.Enum):
    REPRIORITIZE_INITIATIVE = "REPRIORITIZE_INITIATIVE"
    RESOLVE_BLOCKING_DEPENDENCY = "RESOLVE_BLOCKING_DEPENDENCY"
    REALLOCATE_RESOURCES = "REALLOCATE_RESOURCES"
    REDUCE_SCOPE = "REDUCE_SCOPE"
    REVISE_DEADLINE = "REVISE_DEADLINE"
    GATHER_MISSING_EVIDENCE = "GATHER_MISSING_EVIDENCE"
    RUN_SIMULATION = "RUN_SIMULATION"
    REQUEST_HUMAN_INTERVENTION = "REQUEST_HUMAN_INTERVENTION"
    RECONSIDER_OBJECTIVE = "RECONSIDER_OBJECTIVE"


class AlignmentStatus(str, enum.Enum):
    ALIGNED = "ALIGNED"
    PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
    CONFLICTING = "CONFLICTING"
    ORPHAN = "ORPHAN"
    DUPLICATE = "DUPLICATE"
    UNMEASURED = "UNMEASURED"


@dataclass
class GoalDefinition:
    goal_id: str
    title: str
    description: str
    purpose: str
    owner: str
    goal_type: GoalType
    priority: GoalPriority
    state: GoalLifecycleState = GoalLifecycleState.DRAFT
    version: int = 1
    parent_goal_id: Optional[str] = None
    start_date: Optional[str] = None
    target_date: Optional[str] = None
    success_criteria: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    review_schedule: str = "WEEKLY"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class GoalVersionSnapshot:
    snapshot_id: str
    goal_id: str
    version: int
    title: str
    description: str
    state: str
    target_date: Optional[str]
    success_criteria: List[str]
    constraints: List[str]
    changed_by: str
    change_reason: str
    snapshot_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class KeyResultDefinition:
    key_result_id: str
    goal_id: str
    metric_name: str
    description: str
    unit: str
    metric_type: MetricType
    baseline_value: float
    target_value: float
    current_reported_value: float
    current_verified_value: float
    measurement_frequency: str = "DAILY"
    calculation_method: str = "DIRECT"
    required_verification_tier: VerificationTier = VerificationTier.SYSTEM_OBSERVED
    confidence: float = 1.0
    is_satisfied: bool = False
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class OutcomeEvidenceRecord:
    evidence_id: str
    key_result_id: str
    goal_id: str
    verification_tier: VerificationTier
    data_source: str
    observed_value: float
    evidence_summary: str
    evidence_payload: Dict[str, Any] = field(default_factory=dict)
    evidence_hash: str = ""
    verified_by: str = "system"
    approval_token: Optional[str] = None
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_valid: bool = True


@dataclass
class InitiativeRecord:
    initiative_id: str
    goal_id: str
    title: str
    scope: str
    expected_outcome: str
    owner: str
    required_capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    estimated_resources: Dict[str, Any] = field(default_factory=dict)
    target_date: Optional[str] = None
    status: str = "PLANNED"  # PLANNED, IN_PROGRESS, COMPLETED, CANCELLED
    task_graph_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class MilestoneRecord:
    milestone_id: str
    initiative_id: str
    goal_id: str
    title: str
    description: str
    target_date: str
    status: str = "PENDING"  # PENDING, IN_PROGRESS, ACHIEVED, MISSED
    completed_at: Optional[str] = None
    verification_evidence_id: Optional[str] = None


@dataclass
class GoalProgressAssessment:
    assessment_id: str
    goal_id: str
    reported_task_progress: float    # 0.0 - 1.0 based on tasks/milestones
    verified_outcome_progress: float # 0.0 - 1.0 based strictly on verified key results
    activity_to_outcome_variance: float # reported - verified (detects busywork vs achievement)
    schedule_variance_days: float
    budget_variance_ratio: float
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class GoalHealthRecord:
    health_id: str
    goal_id: str
    health_state: GoalHealthState
    primary_reason: str
    progress_trajectory: str  # IMPROVING, STABLE, DECLINING
    risk_factors: List[str] = field(default_factory=list)
    stale_metric_count: int = 0
    blocked_dependency_count: int = 0
    confidence_score: float = 1.0
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CorrectiveActionProposal:
    proposal_id: str
    goal_id: str
    action_type: CorrectiveActionType
    title: str
    rationale: str
    expected_benefit: str
    potential_cost: str
    risk_level: str
    dependencies: List[str] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    requires_human_approval: bool = True
    status: str = "PROPOSED"  # PROPOSED, APPROVED, REJECTED, EXECUTED
    approval_token: Optional[str] = None
    approved_by: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class GoalChangeAuditRecord:
    audit_id: str
    goal_id: str
    change_type: str  # CREATED, TARGET_REVISED, DEADLINE_EXTENDED, SCOPE_CHANGED, STATUS_CHANGED
    field_name: str
    old_value: Any
    new_value: Any
    author: str
    rationale: str
    approval_token: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
