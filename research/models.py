"""
OMNIA Module 35: Autonomous Research, Scientific Discovery & Hypothesis Testing Models
Provides typed contracts for research requests, plans, knowledge gaps, hypotheses,
experiment designs, statistical tests, conclusions, reproducibility manifests, and reports.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class ResearchState(str, Enum):
    INITIALIZED = "INITIALIZED"
    PLANNING = "PLANNING"
    EVIDENCE_GATHERING = "EVIDENCE_GATHERING"
    GAP_ANALYSIS = "GAP_ANALYSIS"
    HYPOTHESIS_FORMULATION = "HYPOTHESIS_FORMULATION"
    EXPERIMENT_DESIGN = "EXPERIMENT_DESIGN"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXPERIMENT_EXECUTING = "EXPERIMENT_EXECUTING"
    TESTING_HYPOTHESES = "TESTING_HYPOTHESES"
    CONCLUDED = "CONCLUDED"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class HypothesisType(str, Enum):
    NULL = "NULL"
    ALTERNATIVE = "ALTERNATIVE"
    COMPARATIVE = "COMPARATIVE"
    MECHANISTIC = "MECHANISTIC"
    OPERATIONAL = "OPERATIONAL"
    STATISTICAL = "STATISTICAL"
    EXPLORATORY = "EXPLORATORY"


class HypothesisState(str, Enum):
    PROPOSED = "PROPOSED"
    UNDER_REVIEW = "UNDER_REVIEW"
    READY_FOR_TESTING = "READY_FOR_TESTING"
    TESTING = "TESTING"
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    SUPERSEDED = "SUPERSEDED"


class MethodologyCategory(str, Enum):
    LITERATURE_REVIEW = "LITERATURE_REVIEW"
    STRUCTURED_DATA_ANALYSIS = "STRUCTURED_DATA_ANALYSIS"
    COMPARATIVE_ANALYSIS = "COMPARATIVE_ANALYSIS"
    STATISTICAL_ANALYSIS = "STATISTICAL_ANALYSIS"
    TIME_SERIES_INVESTIGATION = "TIME_SERIES_INVESTIGATION"
    CONTROLLED_EXPERIMENT = "CONTROLLED_EXPERIMENT"
    SIMULATION_BASED = "SIMULATION_BASED"
    BENCHMARK_EVALUATION = "BENCHMARK_EVALUATION"
    ABLATION_STUDY = "ABLATION_STUDY"


class ExperimentType(str, Enum):
    SINGLE_VARIABLE = "SINGLE_VARIABLE"
    MULTI_VARIABLE = "MULTI_VARIABLE"
    A_B_TEST = "A_B_TEST"
    BENCHMARK = "BENCHMARK"
    SIMULATION = "SIMULATION"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"


class ConclusionState(str, Enum):
    SUPPORTED_WITHIN_SCOPE = "SUPPORTED_WITHIN_SCOPE"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class KnowledgeGapRecord:
    gap_id: str
    research_id: str
    description: str
    why_it_matters: str
    evidence_required: str
    possible_acquisition_method: str
    priority: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW
    resolution_status: str = "OPEN"  # OPEN, IN_PROGRESS, RESOLVED, UNRESOLVABLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "research_id": self.research_id,
            "description": self.description,
            "why_it_matters": self.why_it_matters,
            "evidence_required": self.evidence_required,
            "possible_acquisition_method": self.possible_acquisition_method,
            "priority": self.priority,
            "resolution_status": self.resolution_status,
        }


@dataclass
class HypothesisRecord:
    hypothesis_id: str
    research_id: str
    statement: str
    hypothesis_type: HypothesisType
    scope: str
    assumptions: List[str] = field(default_factory=list)
    supporting_evidence: List[str] = field(default_factory=list)
    contradictory_evidence: List[str] = field(default_factory=list)
    expected_observations: List[str] = field(default_factory=list)
    falsification_conditions: List[str] = field(default_factory=list)
    state: HypothesisState = HypothesisState.PROPOSED
    confidence_score: float = 0.5
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "research_id": self.research_id,
            "statement": self.statement,
            "hypothesis_type": self.hypothesis_type.value,
            "scope": self.scope,
            "assumptions": self.assumptions,
            "supporting_evidence": self.supporting_evidence,
            "contradictory_evidence": self.contradictory_evidence,
            "expected_observations": self.expected_observations,
            "falsification_conditions": self.falsification_conditions,
            "state": self.state.value,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ExperimentDefinition:
    experiment_id: str
    research_id: str
    hypothesis_id: str
    title: str
    objective: str
    experiment_type: ExperimentType
    independent_variables: List[str]
    dependent_variables: List[str]
    controlled_variables: List[str]
    sampling_strategy: str
    sample_size: int
    baseline_condition: str
    treatment_condition: str
    measurement_protocol: str
    stopping_conditions: str
    success_criteria: str
    failure_criteria: str
    requires_approval: bool = False
    approval_token: Optional[str] = None
    isolation_environment: str = "SIMULATION"  # SIMULATION or ISOLATED_SANDBOX
    status: str = "PLANNED"  # PLANNED, APPROVED, RUNNING, COMPLETED, FAILED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "research_id": self.research_id,
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "objective": self.objective,
            "experiment_type": self.experiment_type.value,
            "independent_variables": self.independent_variables,
            "dependent_variables": self.dependent_variables,
            "controlled_variables": self.controlled_variables,
            "sampling_strategy": self.sampling_strategy,
            "sample_size": self.sample_size,
            "baseline_condition": self.baseline_condition,
            "treatment_condition": self.treatment_condition,
            "measurement_protocol": self.measurement_protocol,
            "stopping_conditions": self.stopping_conditions,
            "success_criteria": self.success_criteria,
            "failure_criteria": self.failure_criteria,
            "requires_approval": self.requires_approval,
            "approval_token": self.approval_token,
            "isolation_environment": self.isolation_environment,
            "status": self.status,
        }


@dataclass
class ExperimentExecutionResult:
    experiment_id: str
    execution_id: str
    measurements: List[Dict[str, Any]]
    raw_observations: List[str]
    baseline_metric: float
    treatment_metric: float
    effect_size: float
    duration_ms: float
    status: str = "COMPLETED"
    error_message: Optional[str] = None
    executed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "execution_id": self.execution_id,
            "measurements": self.measurements,
            "raw_observations": self.raw_observations,
            "baseline_metric": self.baseline_metric,
            "treatment_metric": self.treatment_metric,
            "effect_size": self.effect_size,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error_message": self.error_message,
            "executed_at": self.executed_at,
        }


@dataclass
class HypothesisTestResult:
    test_id: str
    hypothesis_id: str
    method: str
    sample_size: int
    test_statistic: Optional[float]
    p_value: Optional[float]
    effect_size: float
    confidence_interval: Optional[List[float]]
    evaluated_state: HypothesisState
    reasoning: str
    limitations: List[str] = field(default_factory=list)
    tested_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "hypothesis_id": self.hypothesis_id,
            "method": self.method,
            "sample_size": self.sample_size,
            "test_statistic": self.test_statistic,
            "p_value": self.p_value,
            "effect_size": self.effect_size,
            "confidence_interval": self.confidence_interval,
            "evaluated_state": self.evaluated_state.value,
            "reasoning": self.reasoning,
            "limitations": self.limitations,
            "tested_at": self.tested_at,
        }


@dataclass
class ResearchConclusion:
    conclusion_id: str
    research_id: str
    state: ConclusionState
    summary: str
    direct_observations: List[str]
    supported_claims: List[str]
    rejected_hypotheses: List[str]
    unresolved_uncertainties: List[str]
    scope_limitations: List[str]
    evidence_trail: List[str]
    concluded_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conclusion_id": self.conclusion_id,
            "research_id": self.research_id,
            "state": self.state.value,
            "summary": self.summary,
            "direct_observations": self.direct_observations,
            "supported_claims": self.supported_claims,
            "rejected_hypotheses": self.rejected_hypotheses,
            "unresolved_uncertainties": self.unresolved_uncertainties,
            "scope_limitations": self.scope_limitations,
            "evidence_trail": self.evidence_trail,
            "concluded_at": self.concluded_at,
        }


@dataclass
class ReproducibilityManifest:
    manifest_id: str
    research_id: str
    dataset_digest_sha256: str
    methodology_version: str
    code_digest_sha256: str
    random_seed: Optional[int]
    environment_metadata: Dict[str, Any]
    replay_instructions: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "research_id": self.research_id,
            "dataset_digest_sha256": self.dataset_digest_sha256,
            "methodology_version": self.methodology_version,
            "code_digest_sha256": self.code_digest_sha256,
            "random_seed": self.random_seed,
            "environment_metadata": self.environment_metadata,
            "replay_instructions": self.replay_instructions,
            "created_at": self.created_at,
        }


@dataclass
class ResearchRequest:
    research_id: str
    original_question: str
    normalized_objective: str
    domain: str
    scope: str
    state: ResearchState = ResearchState.INITIALIZED
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH
    requires_approval: bool = False
    created_by: str = "researcher"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def transition_to(self, new_state: ResearchState) -> None:
        self.state = new_state
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "research_id": self.research_id,
            "original_question": self.original_question,
            "normalized_objective": self.normalized_objective,
            "domain": self.domain,
            "scope": self.scope,
            "state": self.state.value,
            "risk_level": self.risk_level,
            "requires_approval": self.requires_approval,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
