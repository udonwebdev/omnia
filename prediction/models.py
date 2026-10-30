"""
Omnia Module 32: Predictive Intelligence & Risk Forecasting Engine Models
Defines typed domain models for forecast requests, targets, horizons, forecasts,
probability distributions, intervals, uncertainty, risk assessments, scenarios,
outcomes, evaluations, calibration, and drift tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time
import uuid


class ForecastType(str, Enum):
    CLASSIFICATION = "CLASSIFICATION"
    REGRESSION = "REGRESSION"
    TIME_SERIES = "TIME_SERIES"
    ANOMALY_RISK = "ANOMALY_RISK"
    DURATION_ESTIMATION = "DURATION_ESTIMATION"
    SCENARIO_COMPARISON = "SCENARIO_COMPARISON"


class ForecastStatus(str, Enum):
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    GATHERING_EVIDENCE = "GATHERING_EVIDENCE"
    READY = "READY"
    FORECASTING = "FORECASTING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class RiskLevel(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class ForecastHorizon:
    start_time: float
    end_time: float
    duration_sec: float
    is_relative: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_sec": self.duration_sec,
            "is_relative": self.is_relative,
        }

    @classmethod
    def from_duration(cls, duration_sec: float, start_time: Optional[float] = None) -> "ForecastHorizon":
        st = start_time if start_time is not None else time.time()
        return cls(
            start_time=st,
            end_time=st + duration_sec,
            duration_sec=duration_sec,
            is_relative=True
        )


@dataclass
class ForecastTarget:
    target_id: str
    target_description: str
    target_type: ForecastType
    observation_unit: str
    outcome_definition: str
    evaluation_method: str = "EXACT_OR_ERROR"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_description": self.target_description,
            "target_type": self.target_type.value if isinstance(self.target_type, ForecastType) else str(self.target_type),
            "observation_unit": self.observation_unit,
            "outcome_definition": self.outcome_definition,
            "evaluation_method": self.evaluation_method,
        }


@dataclass
class ForecastRequest:
    request_id: str
    target: ForecastTarget
    horizon: ForecastHorizon
    parameters: Dict[str, Any] = field(default_factory=dict)
    as_of_time: float = field(default_factory=time.time)
    status: ForecastStatus = ForecastStatus.REQUESTED
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "target": self.target.to_dict(),
            "horizon": self.horizon.to_dict(),
            "parameters": self.parameters,
            "as_of_time": self.as_of_time,
            "status": self.status.value if isinstance(self.status, ForecastStatus) else str(self.status),
            "created_at": self.created_at,
        }


@dataclass
class ForecastInput:
    input_id: str
    timestamp: float
    value: Any
    source: str
    provenance_hash: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_id": self.input_id,
            "timestamp": self.timestamp,
            "value": self.value,
            "source": self.source,
            "provenance_hash": self.provenance_hash,
            "metadata": self.metadata,
        }


@dataclass
class ForecastInterval:
    lower_bound: float
    upper_bound: float
    confidence_level: float = 0.95
    is_calibrated: bool = False
    coverage_guarantee: str = "EMPIRICAL_HEURISTIC_NO_GUARANTEE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "confidence_level": self.confidence_level,
            "is_calibrated": self.is_calibrated,
            "coverage_guarantee": self.coverage_guarantee,
        }


@dataclass
class ForecastAssumption:
    assumption_id: str
    description: str
    sensitivity: str = "MEDIUM"
    source: str = "MODEL_DEFAULT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "description": self.description,
            "sensitivity": self.sensitivity,
            "source": self.source,
        }


@dataclass
class ForecastScenario:
    scenario_id: str
    name: str
    description: str
    modified_variables: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[ForecastAssumption] = field(default_factory=list)
    is_hypothetical: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "modified_variables": self.modified_variables,
            "assumptions": [a.to_dict() for a in self.assumptions],
            "is_hypothetical": self.is_hypothetical,
        }


@dataclass
class RiskFactor:
    factor_id: str
    name: str
    description: str
    weight: float = 1.0
    correlation_type: str = "STATISTICAL_ASSOCIATION"  # NOT CAUSAL PROOF
    evidence_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "correlation_type": self.correlation_type,
            "evidence_ids": self.evidence_ids,
        }


@dataclass
class RiskAssessment:
    risk_id: str
    target_id: str
    risk_level: RiskLevel
    likelihood_score: float  # Raw model score (0.0 to 1.0)
    is_calibrated_likelihood: bool = False
    impact_score: float = 1.0  # Scale 1.0 to 5.0
    risk_factors: List[RiskFactor] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    counterevidence_ids: List[str] = field(default_factory=list)
    evaluated_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 3600.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "target_id": self.target_id,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, RiskLevel) else str(self.risk_level),
            "likelihood_score": self.likelihood_score,
            "is_calibrated_likelihood": self.is_calibrated_likelihood,
            "impact_score": self.impact_score,
            "risk_factors": [f.to_dict() for f in self.risk_factors],
            "mitigations": self.mitigations,
            "evidence_ids": self.evidence_ids,
            "counterevidence_ids": self.counterevidence_ids,
            "evaluated_at": self.evaluated_at,
            "expires_at": self.expires_at,
        }


@dataclass
class PredictionExplanation:
    summary: str
    key_factors: List[str] = field(default_factory=list)
    baseline_comparison: Optional[str] = None
    data_uncertainty: str = "LOW"
    model_uncertainty: str = "LOW"
    horizon_uncertainty: str = "LOW"
    known_assumptions: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "key_factors": self.key_factors,
            "baseline_comparison": self.baseline_comparison,
            "data_uncertainty": self.data_uncertainty,
            "model_uncertainty": self.model_uncertainty,
            "horizon_uncertainty": self.horizon_uncertainty,
            "known_assumptions": self.known_assumptions,
            "limitations": self.limitations,
        }


@dataclass
class Forecast:
    forecast_id: str
    request_id: str
    target: ForecastTarget
    horizon: ForecastHorizon
    forecast_type: ForecastType
    predicted_value: Optional[float] = None
    predicted_class: Optional[str] = None
    probability: Optional[float] = None
    is_calibrated_probability: bool = False
    interval: Optional[ForecastInterval] = None
    method_name: str = "BASELINE"
    model_version: str = "1.0.0"
    inputs_hash: str = ""
    sample_count: int = 0
    assumptions: List[ForecastAssumption] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    explanation: Optional[PredictionExplanation] = None
    risk_assessment: Optional[RiskAssessment] = None
    scenario: Optional[ForecastScenario] = None
    status: ForecastStatus = ForecastStatus.COMPLETED
    superseded_by: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 1800.0)

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        ct = current_time if current_time is not None else time.time()
        return ct >= self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "forecast_id": self.forecast_id,
            "request_id": self.request_id,
            "target": self.target.to_dict(),
            "horizon": self.horizon.to_dict(),
            "forecast_type": self.forecast_type.value if isinstance(self.forecast_type, ForecastType) else str(self.forecast_type),
            "predicted_value": self.predicted_value,
            "predicted_class": self.predicted_class,
            "probability": self.probability,
            "is_calibrated_probability": self.is_calibrated_probability,
            "interval": self.interval.to_dict() if self.interval else None,
            "method_name": self.method_name,
            "model_version": self.model_version,
            "inputs_hash": self.inputs_hash,
            "sample_count": self.sample_count,
            "assumptions": [a.to_dict() for a in self.assumptions],
            "limitations": self.limitations,
            "explanation": self.explanation.to_dict() if self.explanation else None,
            "risk_assessment": self.risk_assessment.to_dict() if self.risk_assessment else None,
            "scenario": self.scenario.to_dict() if self.scenario else None,
            "status": self.status.value if isinstance(self.status, ForecastStatus) else str(self.status),
            "superseded_by": self.superseded_by,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


@dataclass
class ForecastOutcome:
    outcome_id: str
    forecast_id: str
    target_id: str
    observed_value: Optional[float] = None
    observed_class: Optional[str] = None
    observed_at: float = field(default_factory=time.time)
    source: str = "system"
    is_verified: bool = True
    notes: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "forecast_id": self.forecast_id,
            "target_id": self.target_id,
            "observed_value": self.observed_value,
            "observed_class": self.observed_class,
            "observed_at": self.observed_at,
            "source": self.source,
            "is_verified": self.is_verified,
            "notes": self.notes,
            "created_at": self.created_at,
        }


@dataclass
class ForecastEvaluation:
    evaluation_id: str
    forecast_id: str
    outcome_id: str
    metric_name: str
    error_value: float
    is_accurate: bool
    evaluated_at: float = field(default_factory=time.time)
    evaluation_notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "forecast_id": self.forecast_id,
            "outcome_id": self.outcome_id,
            "metric_name": self.metric_name,
            "error_value": self.error_value,
            "is_accurate": self.is_accurate,
            "evaluated_at": self.evaluated_at,
            "evaluation_notes": self.evaluation_notes,
        }


@dataclass
class CalibrationRecord:
    calibration_id: str
    model_name: str
    target_type: str
    sample_count: int
    brier_score: Optional[float] = None
    ece: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    coverage_rate: Optional[float] = None
    time_window_start: float = 0.0
    time_window_end: float = 0.0
    is_valid: bool = True
    notes: Optional[str] = None
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "calibration_id": self.calibration_id,
            "model_name": self.model_name,
            "target_type": self.target_type,
            "sample_count": self.sample_count,
            "brier_score": self.brier_score,
            "ece": self.ece,
            "mae": self.mae,
            "rmse": self.rmse,
            "coverage_rate": self.coverage_rate,
            "time_window_start": self.time_window_start,
            "time_window_end": self.time_window_end,
            "is_valid": self.is_valid,
            "notes": self.notes,
            "updated_at": self.updated_at,
        }


@dataclass
class DriftAssessment:
    drift_id: str
    model_name: str
    target_id: str
    detected: bool
    drift_type: str
    p_value: Optional[float] = None
    metric_shift: float = 0.0
    sample_count: int = 0
    recommendation: str = "CONTINUE_MONITORING"
    detected_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_id": self.drift_id,
            "model_name": self.model_name,
            "target_id": self.target_id,
            "detected": self.detected,
            "drift_type": self.drift_type,
            "p_value": self.p_value,
            "metric_shift": self.metric_shift,
            "sample_count": self.sample_count,
            "recommendation": self.recommendation,
            "detected_at": self.detected_at,
        }
