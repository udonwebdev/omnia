"""
Omnia Module 32: Predictive Intelligence & Risk Forecasting Service
Authoritative orchestrator for forecasting, risk estimation, scenario analysis,
outcome tracking, accuracy evaluation, calibration, and drift detection.
"""

from typing import List, Dict, Any, Optional, Tuple
import uuid
import time
import logging
import asyncio

from prediction.models import (
    Forecast,
    ForecastRequest,
    ForecastTarget,
    ForecastHorizon,
    ForecastInput,
    ForecastScenario,
    ForecastOutcome,
    ForecastEvaluation,
    CalibrationRecord,
    DriftAssessment,
    RiskAssessment,
    ForecastType,
    ForecastStatus,
    RiskLevel,
)
from prediction.validation import validate_input_dataset, DataQualityReport
from prediction.features import FeaturePipeline
from prediction.baselines import BaseForecaster
from prediction.methods import forecaster_registry, ForecasterRegistry
from prediction.scenarios import ScenarioAnalyzer, ScenarioComparisonResult
from prediction.calibration import CalibrationEngine
from prediction.drift import DriftDetector
from prediction.persistence import PredictionPersistence

# Integrations
from events.fabric import event_fabric, EventFabric
from events.models import Event, EventEnvelope
from capabilities.registry import capability_registry, CapabilityRegistry

logger = logging.getLogger("Omnia.Prediction.Service")


class PredictiveIntelligenceService:
    """Core service managing the predictive intelligence and risk forecasting lifecycle."""

    def __init__(
        self,
        persistence: Optional[PredictionPersistence] = None,
        event_bus: Optional[EventFabric] = None,
        registry: Optional[CapabilityRegistry] = None,
        forecasters: Optional[ForecasterRegistry] = None,
    ):
        self.persistence = persistence or PredictionPersistence()
        self.event_bus = event_bus or event_fabric
        self.registry = registry or capability_registry
        self.forecasters = forecasters or forecaster_registry

        self._register_capabilities()

    def _register_capabilities(self) -> None:
        try:
            from capabilities.models import (
                Capability, CapabilityCategory, CapabilityProvider,
                CapabilityHealth, RiskLevel as CapRiskLevel, SideEffectType, IdempotencyType
            )
            cap = Capability(
                capability_id="prediction.forecast_operations",
                name="Predictive Intelligence & Risk Forecasting Engine",
                category=CapabilityCategory.ANALYTICS,
                provider=CapabilityProvider(
                    provider_id="provider.prediction.local",
                    name="Predictive Intelligence Engine",
                    node_id="local",
                    is_local=True
                ),
                version="1.0.0",
                health=CapabilityHealth.HEALTHY,
                risk_level=CapRiskLevel.LOW,
                side_effect_type=SideEffectType.READ,
                idempotency=IdempotencyType.STRICTLY_IDEMPOTENT
            )
            self.registry.register_capability(cap)
            logger.info("Registered prediction.forecast_operations capability into registry.")
        except Exception as e:
            logger.debug(f"Prediction capability registration bypassed: {e}")

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_bus:
            try:
                envelope = EventEnvelope(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    event_type=event_type,
                    source="predictive_intelligence_service"
                )
                ev = Event(envelope=envelope, payload=payload)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.event_bus.publish(ev))
                    else:
                        loop.run_until_complete(self.event_bus.publish(ev))
                except RuntimeError:
                    asyncio.run(self.event_bus.publish(ev))
            except Exception as e:
                logger.debug(f"Prediction event emission bypassed: {e}")

    # --- FORECAST GENERATION ---

    def generate_forecast(
        self,
        request: ForecastRequest,
        inputs: Optional[List[ForecastInput]] = None,
        method_name: Optional[str] = None,
    ) -> Forecast:
        """
        Executes the predictive lifecycle:
        Validate -> Extract Features -> Select Forecaster -> Generate Forecast -> Check Supersession -> Persist.
        """
        self._emit("prediction.requested", {"request_id": request.request_id, "target_id": request.target.target_id})

        input_data = inputs or []
        # If no inputs provided directly, attempt to fetch from Module 31 temporal states if possible
        if not input_data:
            input_data = self._fetch_temporal_inputs(request.target.target_id, request.as_of_time)

        # 1. Validate data quality and leakage prevention
        is_valid, quality_report = validate_input_dataset(input_data, as_of_time=request.as_of_time)
        if not is_valid:
            status = ForecastStatus.INSUFFICIENT_DATA
            fc = Forecast(
                forecast_id=f"fc-{uuid.uuid4().hex[:12]}",
                request_id=request.request_id,
                target=request.target,
                horizon=request.horizon,
                forecast_type=request.target.target_type,
                method_name=method_name or "ABSTAIN",
                sample_count=len(input_data),
                limitations=quality_report.issues,
                status=status,
                created_at=time.time(),
                expires_at=request.horizon.end_time,
            )
            self.persistence.save_forecast(fc)
            self._emit("prediction.low_confidence", {"forecast_id": fc.forecast_id, "reasons": quality_report.issues})
            return fc

        # 2. Extract features without leakage
        features = FeaturePipeline.extract_features(input_data, request.as_of_time)

        # 3. Select method and forecast
        forecaster = self.forecasters.select_forecaster(request.target.target_type, method_name)
        forecast = forecaster.forecast(request, input_data, features)

        # 4. Check for calibration record to set is_calibrated flags
        calib = self.persistence.get_latest_calibration(
            forecast.method_name,
            request.target.target_type.value if isinstance(request.target.target_type, ForecastType) else str(request.target.target_type)
        )
        if calib and calib.sample_count >= 10:
            if forecast.probability is not None:
                forecast.is_calibrated_probability = True
            if forecast.interval is not None:
                forecast.interval.is_calibrated = True

        # 5. Handle supersession of existing unexpired forecast for same target and forecast_type
        existing = self.persistence.get_forecasts_for_target(request.target.target_id)
        for prev_fc in existing:
            if (
                prev_fc.status == ForecastStatus.COMPLETED
                and prev_fc.forecast_type == forecast.forecast_type
                and not prev_fc.is_expired(request.as_of_time)
            ):
                prev_fc.status = ForecastStatus.SUPERSEDED
                prev_fc.superseded_by = forecast.forecast_id
                self.persistence.save_forecast(prev_fc)
                self._emit("prediction.superseded", {
                    "previous_forecast_id": prev_fc.forecast_id,
                    "superseded_by": forecast.forecast_id,
                })
                break

        # 6. Persist & Emit
        self.persistence.save_forecast(forecast)
        self._emit("prediction.completed", {
            "forecast_id": forecast.forecast_id,
            "target_id": request.target.target_id,
            "predicted_value": forecast.predicted_value,
            "predicted_class": forecast.predicted_class,
        })

        return forecast

    def _fetch_temporal_inputs(self, entity_id: str, as_of_time: float) -> List[ForecastInput]:
        """Queries Module 31 temporal states if available."""
        inputs: List[ForecastInput] = []
        try:
            from temporal.service import temporal_causal_service
            states = temporal_causal_service.persistence.get_states_for_entity(entity_id=entity_id, as_of_transaction_time=as_of_time)
            for s in states:
                # Extract primary metric from payload if available
                val = s.state_payload.get("value") or s.state_payload.get("status") or s.state_payload.get("load")
                if val is not None:
                    inputs.append(ForecastInput(
                        input_id=s.state_id,
                        timestamp=s.valid_from,
                        value=val,
                        source=f"temporal_state:{s.entity_id}",
                    ))
        except Exception as e:
            logger.debug(f"Module 31 temporal input query bypassed: {e}")
        return inputs

    # --- RISK ASSESSMENT ---

    def assess_risk(
        self,
        target_id: str,
        inputs: Optional[List[ForecastInput]] = None,
        critical_threshold: float = 80.0,
        impact_score: float = 3.0,
        horizon_sec: float = 3600.0,
    ) -> RiskAssessment:
        now = time.time()
        req = ForecastRequest(
            request_id=f"req-risk-{uuid.uuid4().hex[:8]}",
            target=ForecastTarget(
                target_id=target_id,
                target_description=f"Risk assessment for {target_id}",
                target_type=ForecastType.ANOMALY_RISK,
                observation_unit="risk_index",
                outcome_definition="Hazard or degradation condition",
            ),
            horizon=ForecastHorizon.from_duration(horizon_sec, now),
            parameters={
                "critical_threshold": critical_threshold,
                "configured_impact": impact_score,
            },
            as_of_time=now,
        )

        fc = self.generate_forecast(req, inputs=inputs, method_name="RuleBasedRiskForecaster")
        if fc.risk_assessment:
            if fc.risk_assessment.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                self._emit("prediction.risk_elevated", {
                    "risk_id": fc.risk_assessment.risk_id,
                    "target_id": target_id,
                    "risk_level": fc.risk_assessment.risk_level.value,
                    "likelihood": fc.risk_assessment.likelihood_score,
                })
            return fc.risk_assessment

        # Fallback if no assessment was formed
        return RiskAssessment(
            risk_id=f"risk-{uuid.uuid4().hex[:10]}",
            target_id=target_id,
            risk_level=RiskLevel.UNKNOWN,
            likelihood_score=0.0,
            impact_score=impact_score,
            mitigations=[],
            evaluated_at=now,
            expires_at=now + horizon_sec,
        )

    # --- SCENARIO COMPARISON ---

    def compare_scenarios(
        self,
        base_request: ForecastRequest,
        scenarios: List[ForecastScenario],
        inputs: Optional[List[ForecastInput]] = None,
        method_name: Optional[str] = None,
    ) -> ScenarioComparisonResult:
        input_data = inputs or []
        if not input_data:
            input_data = self._fetch_temporal_inputs(base_request.target.target_id, base_request.as_of_time)

        return ScenarioAnalyzer.compare_scenarios(
            base_request=base_request,
            base_inputs=input_data,
            scenarios=scenarios,
            method_name=method_name,
        )

    # --- OUTCOMES & EVALUATION ---

    def record_outcome(
        self,
        forecast_id: str,
        observed_value: Optional[float] = None,
        observed_class: Optional[str] = None,
        source: str = "system",
        notes: Optional[str] = None,
    ) -> ForecastOutcome:
        fc = self.persistence.get_forecast(forecast_id)
        target_id = fc.target.target_id if fc else "unknown"

        outcome = ForecastOutcome(
            outcome_id=f"out-{uuid.uuid4().hex[:10]}",
            forecast_id=forecast_id,
            target_id=target_id,
            observed_value=observed_value,
            observed_class=observed_class,
            source=source,
            is_verified=True,
            notes=notes,
            created_at=time.time(),
        )
        self.persistence.save_outcome(outcome)
        return outcome

    def evaluate_forecast(
        self,
        forecast_id: str,
        outcome_id: Optional[str] = None,
    ) -> Optional[ForecastEvaluation]:
        fc = self.persistence.get_forecast(forecast_id)
        if not fc:
            return None

        # Look up outcome
        outcome = None
        if outcome_id:
            outcome = self.persistence.get_outcome(outcome_id)
        else:
            # Query by forecast_id
            conn = self.persistence._get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT outcome_id FROM forecast_outcomes WHERE forecast_id = ? ORDER BY created_at DESC LIMIT 1", (forecast_id,))
                r = cur.fetchone()
                if r:
                    outcome = self.persistence.get_outcome(r["outcome_id"])
            finally:
                conn.close()

        if not outcome:
            return None

        evaluation = CalibrationEngine.evaluate_single_forecast(fc, outcome)
        self.persistence.save_evaluation(evaluation)
        self._emit("prediction.outcome_evaluated", {
            "evaluation_id": evaluation.evaluation_id,
            "forecast_id": forecast_id,
            "is_accurate": evaluation.is_accurate,
            "error_value": evaluation.error_value,
        })
        return evaluation

    # --- CALIBRATION & DRIFT ---

    def calibrate_model(
        self,
        model_name: str,
        target_type: str,
    ) -> Optional[CalibrationRecord]:
        evals = self.persistence.get_evaluations_for_model(model_name)
        pairs: List[Tuple[Forecast, ForecastOutcome]] = []
        for ev in evals:
            fc = self.persistence.get_forecast(ev.forecast_id)
            out = self.persistence.get_outcome(ev.outcome_id)
            if fc and out:
                pairs.append((fc, out))

        calib = CalibrationEngine.compute_calibration_record(model_name, target_type, pairs)
        if calib:
            self.persistence.save_calibration_record(calib)
        return calib

    def detect_drift(
        self,
        model_name: str,
        target_id: str,
        baseline_error: Optional[float] = None,
    ) -> DriftAssessment:
        evals = self.persistence.get_evaluations_for_model(model_name)
        assessment = DriftDetector.assess_drift(
            model_name=model_name,
            target_id=target_id,
            evaluations=evals,
            baseline_error=baseline_error,
        )
        self.persistence.save_drift_assessment(assessment)
        if assessment.detected:
            self._emit("prediction.drift_detected", {
                "drift_id": assessment.drift_id,
                "model_name": model_name,
                "target_id": target_id,
                "shift": assessment.metric_shift,
                "recommendation": assessment.recommendation,
            })
        return assessment

    def get_forecast(self, forecast_id: str) -> Optional[Forecast]:
        return self.persistence.get_forecast(forecast_id)

    def get_forecast_history(self, target_id: str) -> List[Forecast]:
        return self.persistence.get_forecasts_for_target(target_id)


# Default global instance
predictive_service = PredictiveIntelligenceService()
