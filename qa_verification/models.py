"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Domain Models, Enums, and Value Objects - models.py
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class RequirementType(str, enum.Enum):
    FUNCTIONAL = "FUNCTIONAL"
    API_CONTRACT = "API_CONTRACT"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    PERFORMANCE = "PERFORMANCE"
    SECURITY = "SECURITY"
    RELIABILITY = "RELIABILITY"
    UI_UX = "UI_UX"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    DEFECT_DETECTED = "DEFECT_DETECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class TestCategory(str, enum.Enum):
    UNIT = "UNIT"
    INTEGRATION = "INTEGRATION"
    API_CONTRACT = "API_CONTRACT"
    DATABASE_INTEGRITY = "DATABASE_INTEGRITY"
    FRONTEND_UI = "FRONTEND_UI"
    PERFORMANCE_LOAD = "PERFORMANCE_LOAD"
    PROPERTY_FUZZ = "PROPERTY_FUZZ"
    CONCURRENCY = "CONCURRENCY"
    SECURITY_AUDIT = "SECURITY_AUDIT"
    MUTATION = "MUTATION"


class DefectSeverity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    BLOCKER = "BLOCKER"


class DefectCategory(str, enum.Enum):
    FUNCTIONAL = "FUNCTIONAL"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    REGRESSION = "REGRESSION"
    PERFORMANCE_DEGRADATION = "PERFORMANCE_DEGRADATION"
    SECURITY_VULNERABILITY = "SECURITY_VULNERABILITY"
    CONCURRENCY_RACE = "CONCURRENCY_RACE"
    FLAKY_INFRASTRUCTURE = "FLAKY_INFRASTRUCTURE"


class FlakyClassification(str, enum.Enum):
    STABLE_PASSING = "STABLE_PASSING"
    STABLE_FAILING = "STABLE_FAILING"
    INTERMITTENT_FLAKY = "INTERMITTENT_FLAKY"
    ENVIRONMENT_DEPENDENT = "ENVIRONMENT_DEPENDENT"


class QualityTier(str, enum.Enum):
    PRODUCTION_READY = "PRODUCTION_READY"
    CONDITIONALLY_QUALIFIED = "CONDITIONALLY_QUALIFIED"
    DEGRADED = "DEGRADED"
    UNACCEPTABLE = "UNACCEPTABLE"


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------

@dataclass
class VerificationProject:
    project_id: str
    name: str
    repository_ref: str
    framework: str = "python-unittest"
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class VerificationRequirement:
    requirement_id: str
    project_id: str
    title: str
    description: str
    requirement_type: RequirementType = RequirementType.FUNCTIONAL
    source_reference: str = ""
    is_ambiguous: bool = False
    ambiguity_notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AcceptanceCriterion:
    criterion_id: str
    requirement_id: str
    expected_behavior: str
    preconditions: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    expected_outputs: Dict[str, Any] = field(default_factory=dict)
    failure_conditions: List[str] = field(default_factory=list)
    priority: int = 1
    confidence: float = 1.0


@dataclass
class TestStrategy:
    strategy_id: str
    project_id: str
    name: str
    target_categories: List[TestCategory] = field(default_factory=list)
    risk_weighting: Dict[str, float] = field(default_factory=dict)
    allocated_budget_seconds: float = 600.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class GeneratedTestCase:
    test_case_id: str
    criterion_id: str
    name: str
    category: TestCategory
    objective: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    assertions: List[str] = field(default_factory=list)
    is_edge_case: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class VerificationMission:
    mission_id: str
    project_id: str
    strategy_id: str
    status: VerificationStatus = VerificationStatus.PLANNED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None


@dataclass
class VerificationExecution:
    execution_id: str
    mission_id: str
    test_case_id: str
    status: VerificationStatus = VerificationStatus.RUNNING
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class VerificationResult:
    result_id: str
    execution_id: str
    passed: bool
    observed_output: Dict[str, Any] = field(default_factory=dict)
    discrepancies: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class TestEvidence:
    evidence_id: str
    execution_id: str
    evidence_type: str  # LOG, HTTP_PAYLOAD, DB_SNAPSHOT, SCREENSHOT, STACK_TRACE
    payload: str
    checksum_sha256: str
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CoverageRecord:
    coverage_id: str
    mission_id: str
    requirements_total: int
    requirements_covered: int
    coverage_pct: float
    gap_details: List[str] = field(default_factory=list)
    calculated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DefectRecord:
    defect_id: str
    project_id: str
    execution_id: str
    title: str
    category: DefectCategory
    severity: DefectSeverity
    reproduction_steps: List[str] = field(default_factory=list)
    stack_trace: Optional[str] = None
    is_reproduced: bool = True
    is_resolved: bool = False
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RegressionRecord:
    regression_id: str
    project_id: str
    defect_id: str
    component_name: str
    baseline_revision: str
    current_revision: str
    description: str
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class FlakyTestRecord:
    flaky_id: str
    test_case_id: str
    runs_evaluated: int
    passes: int
    failures: int
    variance_score: float
    classification: FlakyClassification
    assessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class MutationTestResult:
    mutation_id: str
    mission_id: str
    mutant_type: str  # OPERATOR_SWAP, INVERTED_LOGIC, RETURN_NULL, BOUNDARY_OFF_BY_ONE
    killed: bool
    surviving_details: Optional[str] = None
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PerformanceAssessment:
    assessment_id: str
    mission_id: str
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_rps: float
    error_rate_pct: float
    cpu_utilization_pct: float
    memory_mb: float
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class QualityAssessment:
    assessment_id: str
    project_id: str
    mission_id: str
    tier: QualityTier
    overall_score: float
    functional_pass_rate: float
    coverage_score: float
    unresolved_defects_count: int
    regressions_count: int
    flaky_tests_count: int
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    summary_notes: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RepairVerification:
    repair_verification_id: str
    defect_id: str
    patch_ref: str
    retest_passed: bool
    regressions_found: int = 0
    verification_evidence: Dict[str, Any] = field(default_factory=dict)
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
