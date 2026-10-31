"""
OMNIA Module 37: Decision Support, Strategic Options & Trade-off Analysis Models
Provides typed contracts for decision cases, strategic options, criteria,
multi-criteria assessments, risk/trade-off matrices, sensitivity analyses,
value of information evaluations, recommendations, and outcome monitoring.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class DecisionLifecycleState(str, Enum):
    DRAFT = "DRAFT"
    EVIDENCE_GATHERING = "EVIDENCE_GATHERING"
    OPTIONS_READY = "OPTIONS_READY"
    ANALYSIS = "ANALYSIS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    DECIDED = "DECIDED"
    MONITORING = "MONITORING"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    CANCELLED = "CANCELLED"


class CriterionDirection(str, Enum):
    MAXIMIZE = "MAXIMIZE"
    MINIMIZE = "MINIMIZE"


class RecommendationOutcome(str, Enum):
    RECOMMENDED = "RECOMMENDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DISPUTED_EVIDENCE = "DISPUTED_EVIDENCE"
    TIED_OPTIONS = "TIED_OPTIONS"


class InformationAction(str, Enum):
    DECIDE_NOW = "DECIDE_NOW"
    GATHER_SPECIFIC_EVIDENCE = "GATHER_SPECIFIC_EVIDENCE"
    RUN_SIMULATION = "RUN_SIMULATION"
    CONDUCT_RESEARCH = "CONDUCT_RESEARCH"
    EXPERT_REVIEW = "EXPERT_REVIEW"


@dataclass
class DecisionCaseRecord:
    case_id: str
    title: str
    description: str
    owner_id: str
    category: str
    deadline_ts: Optional[float]
    context: Dict[str, Any]
    desired_outcomes: List[str]
    constraints: List[str]
    available_resources: Dict[str, Any]
    stakeholders: List[str]
    risk_tolerance: str  # "LOW", "MEDIUM", "HIGH"
    version: int = 1
    state: DecisionLifecycleState = DecisionLifecycleState.DRAFT
    selected_option_id: Optional[str] = None
    decided_by: Optional[str] = None
    approval_token: Optional[str] = None
    review_date_ts: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "description": self.description,
            "owner_id": self.owner_id,
            "category": self.category,
            "deadline_ts": self.deadline_ts,
            "context": self.context,
            "desired_outcomes": self.desired_outcomes,
            "constraints": self.constraints,
            "available_resources": self.available_resources,
            "stakeholders": self.stakeholders,
            "risk_tolerance": self.risk_tolerance,
            "version": self.version,
            "state": self.state.value,
            "selected_option_id": self.selected_option_id,
            "decided_by": self.decided_by,
            "approval_token": self.approval_token,
            "review_date_ts": self.review_date_ts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class StrategicOptionRecord:
    option_id: str
    case_id: str
    title: str
    description: str
    is_baseline: bool  # Status quo option
    expected_outcome: str
    estimated_cost: float
    implementation_complexity: str  # "LOW", "MEDIUM", "HIGH", "EXTREME"
    reversibility_score: float  # 0.0 (irreversible) to 1.0 (fully reversible)
    time_horizon_days: int
    dependencies: List[str]
    benefits: List[str]
    disadvantages: List[str]
    critical_assumptions: List[str]
    known_limitations: List[str]
    origin: str = "GENERATED"  # "HUMAN_PROPOSAL", "RESEARCH", "SIMULATION", "GENERATED"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "option_id": self.option_id,
            "case_id": self.case_id,
            "title": self.title,
            "description": self.description,
            "is_baseline": self.is_baseline,
            "expected_outcome": self.expected_outcome,
            "estimated_cost": self.estimated_cost,
            "implementation_complexity": self.implementation_complexity,
            "reversibility_score": self.reversibility_score,
            "time_horizon_days": self.time_horizon_days,
            "dependencies": self.dependencies,
            "benefits": self.benefits,
            "disadvantages": self.disadvantages,
            "critical_assumptions": self.critical_assumptions,
            "known_limitations": self.known_limitations,
            "origin": self.origin,
            "created_at": self.created_at,
        }


@dataclass
class DecisionCriterion:
    criterion_id: str
    case_id: str
    name: str
    weight: float  # Normalized weight (0.0 to 1.0)
    direction: CriterionDirection  # MAXIMIZE or MINIMIZE
    is_mandatory: bool = False
    minimum_threshold: Optional[float] = None
    acceptable_range: Optional[List[float]] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "case_id": self.case_id,
            "name": self.name,
            "weight": self.weight,
            "direction": self.direction.value,
            "is_mandatory": self.is_mandatory,
            "minimum_threshold": self.minimum_threshold,
            "acceptable_range": self.acceptable_range,
            "description": self.description,
        }


@dataclass
class OptionAssessment:
    assessment_id: str
    case_id: str
    option_id: str
    criterion_scores: Dict[str, float]  # criterion_id -> raw score
    normalized_score: float  # Overall weighted score (0.0 to 100.0)
    is_pareto_dominated: bool = False
    violates_mandatory_constraint: bool = False
    constraint_violations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "case_id": self.case_id,
            "option_id": self.option_id,
            "criterion_scores": self.criterion_scores,
            "normalized_score": self.normalized_score,
            "is_pareto_dominated": self.is_pareto_dominated,
            "violates_mandatory_constraint": self.violates_mandatory_constraint,
            "constraint_violations": self.constraint_violations,
        }


@dataclass
class RiskTradeoffAssessment:
    assessment_id: str
    case_id: str
    option_id: str
    probability_of_failure: float  # 0.0 to 1.0
    severity_of_failure: float  # 0.0 to 1.0
    financial_exposure: float
    operational_disruption: str  # "NONE", "MINOR", "MAJOR", "CATASTROPHIC"
    security_risk: str  # "LOW", "MEDIUM", "HIGH"
    opportunity_cost_notes: str
    mitigation_strategy: str
    residual_risk_score: float  # 0.0 to 1.0
    is_acceptable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "case_id": self.case_id,
            "option_id": self.option_id,
            "probability_of_failure": self.probability_of_failure,
            "severity_of_failure": self.severity_of_failure,
            "financial_exposure": self.financial_exposure,
            "operational_disruption": self.operational_disruption,
            "security_risk": self.security_risk,
            "opportunity_cost_notes": self.opportunity_cost_notes,
            "mitigation_strategy": self.mitigation_strategy,
            "residual_risk_score": self.residual_risk_score,
            "is_acceptable": self.is_acceptable,
        }


@dataclass
class SensitivityResult:
    case_id: str
    dominant_option_id: str
    stability_score: float  # 0.0 (fragile) to 1.0 (hyper-robust)
    threshold_break_evens: Dict[str, float]  # parameter -> break-even shift percentage
    critical_assumptions: List[str]
    pareto_frontier_options: List[str]
    sensitivity_narrative: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "dominant_option_id": self.dominant_option_id,
            "stability_score": self.stability_score,
            "threshold_break_evens": self.threshold_break_evens,
            "critical_assumptions": self.critical_assumptions,
            "pareto_frontier_options": self.pareto_frontier_options,
            "sensitivity_narrative": self.sensitivity_narrative,
        }


@dataclass
class ValueInformationAssessment:
    case_id: str
    recommended_action: InformationAction
    information_gaps: List[str]
    expected_uncertainty_reduction_pct: float
    cost_of_delay_assessment: str
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "recommended_action": self.recommended_action.value,
            "information_gaps": self.information_gaps,
            "expected_uncertainty_reduction_pct": self.expected_uncertainty_reduction_pct,
            "cost_of_delay_assessment": self.cost_of_delay_assessment,
            "explanation": self.explanation,
        }


@dataclass
class StrategicRecommendation:
    recommendation_id: str
    case_id: str
    outcome: RecommendationOutcome
    recommended_option_id: Optional[str]
    primary_justification: str
    key_tradeoffs: List[str]
    major_risks: List[str]
    critical_assumptions: List[str]
    conditions_for_invalidation: List[str]
    confidence_level: str  # "HIGH", "MEDIUM", "LOW"
    suggested_review_date_ts: float
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "case_id": self.case_id,
            "outcome": self.outcome.value,
            "recommended_option_id": self.recommended_option_id,
            "primary_justification": self.primary_justification,
            "key_tradeoffs": self.key_tradeoffs,
            "major_risks": self.major_risks,
            "critical_assumptions": self.critical_assumptions,
            "conditions_for_invalidation": self.conditions_for_invalidation,
            "confidence_level": self.confidence_level,
            "suggested_review_date_ts": self.suggested_review_date_ts,
            "created_at": self.created_at,
        }


@dataclass
class DecisionOutcomeMonitoring:
    monitoring_id: str
    case_id: str
    selected_option_id: str
    actual_cost: Optional[float] = None
    expected_vs_actual_variance_pct: float = 0.0
    assumptions_still_valid: bool = True
    invalidated_assumptions: List[str] = field(default_factory=list)
    reassessment_triggered: bool = False
    reassessment_reason: Optional[str] = None
    observed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "monitoring_id": self.monitoring_id,
            "case_id": self.case_id,
            "selected_option_id": self.selected_option_id,
            "actual_cost": self.actual_cost,
            "expected_vs_actual_variance_pct": self.expected_vs_actual_variance_pct,
            "assumptions_still_valid": self.assumptions_still_valid,
            "invalidated_assumptions": self.invalidated_assumptions,
            "reassessment_triggered": self.reassessment_triggered,
            "reassessment_reason": self.reassessment_reason,
            "observed_at": self.observed_at,
        }
