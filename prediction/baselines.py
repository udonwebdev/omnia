"""
Omnia Module 32: Baseline Forecasting Methods
Implements foundational, deterministic, transparent forecasting baselines
including Last-Observation, Moving Average, Trend Extrapolation,
Frequency Classification, Duration Estimation, and Rule-Based Risk.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import math
import statistics
import time
import uuid

from prediction.models import (
    Forecast,
    ForecastRequest,
    ForecastInput,
    ForecastType,
    ForecastStatus,
    ForecastInterval,
    ForecastAssumption,
    PredictionExplanation,
    RiskAssessment,
    RiskLevel,
    RiskFactor,
)


class BaseForecaster(ABC):
    """Abstract interface for forecasting methods."""

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version

    @abstractmethod
    def forecast(
        self,
        request: ForecastRequest,
        inputs: List[ForecastInput],
        features: Dict[str, Any],
    ) -> Forecast:
        pass


class LastObservationBaseline(BaseForecaster):
    """
    Naive persistence baseline: forecasts that the next value or state
    will match the most recently observed value.
    """

    def __init__(self):
        super().__init__(name="LastObservationBaseline", version="1.0.0")

    def forecast(
        self,
        request: ForecastRequest,
        inputs: List[ForecastInput],
        features: Dict[str, Any],
    ) -> Forecast:
        recent_val = features.get("recent_value")
        fid = f"fc-{uuid.uuid4().hex[:12]}"
        now = time.time()

        if recent_val is None:
            return Forecast(
                forecast_id=fid,
                request_id=request.request_id,
                target=request.target,
                horizon=request.horizon,
                forecast_type=request.target.target_type,
                method_name=self.name,
                model_version=self.version,
                status=ForecastStatus.INSUFFICIENT_DATA,
                limitations=["No valid observations available for baseline forecast."],
                created_at=now,
                expires_at=request.horizon.end_time,
            )

        is_numeric = isinstance(recent_val, (int, float))
        pred_val = float(recent_val) if is_numeric else None
        pred_class = str(recent_val) if not is_numeric else None

        # Build interval heuristic from historical std if available
        interval = None
        if is_numeric and features.get("historical_std") is not None:
            std_val = features["historical_std"]
            interval = ForecastInterval(
                lower_bound=pred_val - 1.96 * std_val,
                upper_bound=pred_val + 1.96 * std_val,
                confidence_level=0.95,
                is_calibrated=False,
                coverage_guarantee="HEURISTIC_HISTORICAL_VARIANCE_NO_GUARANTEE",
            )

        explanation = PredictionExplanation(
            summary=f"Projected next outcome using naive persistence of last observed value: {recent_val}.",
            key_factors=[f"Most recent observation at t={features.get('time_since_last_observation', 0):.1f}s ago"],
            baseline_comparison="Identity baseline (zero-lag projection)",
            data_uncertainty="LOW" if features.get("sample_count", 0) > 5 else "HIGH",
            model_uncertainty="HIGH",  # Naive baseline carries high structural uncertainty
            known_assumptions=["System state remains stationary over forecast horizon."],
            limitations=["Assumes future will exactly match the immediate past."],
        )

        return Forecast(
            forecast_id=fid,
            request_id=request.request_id,
            target=request.target,
            horizon=request.horizon,
            forecast_type=request.target.target_type,
            predicted_value=pred_val,
            predicted_class=pred_class,
            probability=None,  # Naive baseline does not produce defensible probability
            is_calibrated_probability=False,
            interval=interval,
            method_name=self.name,
            model_version=self.version,
            sample_count=features.get("sample_count", 0),
            assumptions=[ForecastAssumption(assumption_id="asm_stat_1", description="Stationary system state")],
            limitations=["Naive baseline: no trend or cyclical adjustments."],
            explanation=explanation,
            status=ForecastStatus.COMPLETED,
            created_at=now,
            expires_at=request.horizon.end_time,
        )


class MovingAverageForecaster(BaseForecaster):
    """
    Moving Average Forecaster: predicts the mean of the most recent k observations.
    Computes an uncalibrated prediction interval based on sample variance.
    """

    def __init__(self, window_size: int = 5):
        super().__init__(name="MovingAverageForecaster", version="1.0.0")
        self.window_size = window_size

    def forecast(
        self,
        request: ForecastRequest,
        inputs: List[ForecastInput],
        features: Dict[str, Any],
    ) -> Forecast:
        fid = f"fc-{uuid.uuid4().hex[:12]}"
        now = time.time()

        sorted_inputs = sorted(
            [inp for inp in inputs if inp.timestamp <= request.as_of_time and isinstance(inp.value, (int, float))],
            key=lambda x: x.timestamp
        )

        if not sorted_inputs:
            return Forecast(
                forecast_id=fid,
                request_id=request.request_id,
                target=request.target,
                horizon=request.horizon,
                forecast_type=ForecastType.REGRESSION,
                method_name=self.name,
                model_version=self.version,
                status=ForecastStatus.INSUFFICIENT_DATA,
                limitations=["No numeric observations available for moving average."],
                created_at=now,
                expires_at=request.horizon.end_time,
            )

        window = sorted_inputs[-self.window_size:]
        vals = [float(inp.value) for inp in window]
        pred_val = round(statistics.mean(vals), 4)

        # Standard error of the mean
        sample_std = statistics.stdev(vals) if len(vals) > 1 else 0.0
        interval = ForecastInterval(
            lower_bound=round(pred_val - 1.96 * sample_std, 4),
            upper_bound=round(pred_val + 1.96 * sample_std, 4),
            confidence_level=0.95,
            is_calibrated=False,
            coverage_guarantee="EMPIRICAL_WINDOW_VARIANCE_NO_GUARANTEE",
        )

        explanation = PredictionExplanation(
            summary=f"Computed rolling mean across window of {len(window)} observations: {pred_val}.",
            key_factors=[f"Window size: {len(window)}", f"Window standard deviation: {sample_std:.4f}"],
            baseline_comparison=f"Last observation was {sorted_inputs[-1].value}; rolling average is {pred_val}",
            data_uncertainty="MEDIUM" if len(window) < self.window_size else "LOW",
            model_uncertainty="MEDIUM",
            known_assumptions=["Underlying mean is locally constant across the window."],
            limitations=["Smooths short-term fluctuations; lags behind sudden shocks."],
        )

        return Forecast(
            forecast_id=fid,
            request_id=request.request_id,
            target=request.target,
            horizon=request.horizon,
            forecast_type=ForecastType.REGRESSION,
            predicted_value=pred_val,
            probability=None,
            is_calibrated_probability=False,
            interval=interval,
            method_name=self.name,
            model_version=self.version,
            sample_count=len(sorted_inputs),
            assumptions=[ForecastAssumption(assumption_id="asm_ma_1", description="Stationary local mean")],
            limitations=["Moving average exhibits lag during rapid monotonic trends."],
            explanation=explanation,
            status=ForecastStatus.COMPLETED,
            created_at=now,
            expires_at=request.horizon.end_time,
        )


class TrendForecaster(BaseForecaster):
    """
    Trend Forecaster: fits a deterministic linear trend and extrapolates
    to the target horizon midpoint or endpoint.
    """

    def __init__(self):
        super().__init__(name="TrendForecaster", version="1.0.0")

    def forecast(
        self,
        request: ForecastRequest,
        inputs: List[ForecastInput],
        features: Dict[str, Any],
    ) -> Forecast:
        fid = f"fc-{uuid.uuid4().hex[:12]}"
        now = time.time()

        slope = features.get("trend_slope", 0.0)
        recent_val = features.get("recent_value")

        if recent_val is None or not isinstance(recent_val, (int, float)):
            return Forecast(
                forecast_id=fid,
                request_id=request.request_id,
                target=request.target,
                horizon=request.horizon,
                forecast_type=ForecastType.REGRESSION,
                method_name=self.name,
                model_version=self.version,
                status=ForecastStatus.INSUFFICIENT_DATA,
                limitations=["No numeric observations available for linear trend extrapolation."],
                created_at=now,
                expires_at=request.horizon.end_time,
            )

        duration = max(0.0, request.horizon.duration_sec)
        # Project midpoint of horizon
        delta = slope * (duration / 2.0)
        pred_val = round(float(recent_val) + delta, 4)

        # Interval expands with horizon duration
        std_val = features.get("historical_std", 1.0) or 1.0
        expansion_factor = math.sqrt(1.0 + (duration / 3600.0))
        interval_margin = 1.96 * std_val * expansion_factor

        interval = ForecastInterval(
            lower_bound=round(pred_val - interval_margin, 4),
            upper_bound=round(pred_val + interval_margin, 4),
            confidence_level=0.95,
            is_calibrated=False,
            coverage_guarantee="EXTRAPOLATED_TREND_VARIANCE_NO_GUARANTEE",
        )

        explanation = PredictionExplanation(
            summary=f"Extrapolated linear trend with slope {slope:.6f} over horizon duration {duration:.0f}s to predicted value {pred_val}.",
            key_factors=[f"Estimated trend slope: {slope:.6f} units/sec", f"Recent baseline: {recent_val}"],
            baseline_comparison=f"Compared to static baseline {recent_val}, trend projects shift of {delta:+.4f}",
            data_uncertainty="LOW" if features.get("sample_count", 0) > 10 else "MEDIUM",
            model_uncertainty="MEDIUM",
            horizon_uncertainty="HIGH" if duration > 7200 else "MEDIUM",
            known_assumptions=["Linear trend remains constant across forecast horizon."],
            limitations=["Unbounded extrapolation risk if trend flattens or reverses."],
        )

        return Forecast(
            forecast_id=fid,
            request_id=request.request_id,
            target=request.target,
            horizon=request.horizon,
            forecast_type=ForecastType.TIME_SERIES,
            predicted_value=pred_val,
            probability=None,
            is_calibrated_probability=False,
            interval=interval,
            method_name=self.name,
            model_version=self.version,
            sample_count=features.get("sample_count", 0),
            assumptions=[ForecastAssumption(assumption_id="asm_tr_1", description="Persistent linear slope")],
            limitations=["Linear projection does not capture saturation or boundary effects."],
            explanation=explanation,
            status=ForecastStatus.COMPLETED,
            created_at=now,
            expires_at=request.horizon.end_time,
        )


class FrequencyClassificationForecaster(BaseForecaster):
    """
    Frequency-Based Classification: predicts the most frequent category.
    Empirical frequency is explicitly marked as uncalibrated score, not calibrated probability.
    """

    def __init__(self):
        super().__init__(name="FrequencyClassificationForecaster", version="1.0.0")

    def forecast(
        self,
        request: ForecastRequest,
        inputs: List[ForecastInput],
        features: Dict[str, Any],
    ) -> Forecast:
        fid = f"fc-{uuid.uuid4().hex[:12]}"
        now = time.time()

        freqs = features.get("category_frequencies", {})
        if not freqs:
            # Fallback if values are strings in inputs
            vals = [str(inp.value) for inp in inputs if inp.timestamp <= request.as_of_time and inp.value is not None]
            if not vals:
                return Forecast(
                    forecast_id=fid,
                    request_id=request.request_id,
                    target=request.target,
                    horizon=request.horizon,
                    forecast_type=ForecastType.CLASSIFICATION,
                    method_name=self.name,
                    model_version=self.version,
                    status=ForecastStatus.INSUFFICIENT_DATA,
                    limitations=["No categorical observations available."],
                    created_at=now,
                    expires_at=request.horizon.end_time,
                )
            counts: Dict[str, int] = {}
            for v in vals:
                counts[v] = counts.get(v, 0) + 1
            n = len(vals)
            freqs = {k: v / n for k, v in counts.items()}

        top_class = max(freqs.keys(), key=lambda k: freqs[k])
        uncalibrated_score = round(freqs[top_class], 4)

        explanation = PredictionExplanation(
            summary=f"Projected class '{top_class}' based on historical empirical frequency of {uncalibrated_score*100:.1f}%.",
            key_factors=[f"Class frequency: {uncalibrated_score:.4f}", f"Classes observed: {list(freqs.keys())}"],
            baseline_comparison=f"Top category '{top_class}' leads runner-up classes",
            data_uncertainty="LOW" if len(inputs) >= 20 else "MEDIUM",
            model_uncertainty="MEDIUM",
            known_assumptions=["Categorical class base-rate remains stationary."],
            limitations=["Raw empirical frequency is not a calibrated posterior probability."],
        )

        return Forecast(
            forecast_id=fid,
            request_id=request.request_id,
            target=request.target,
            horizon=request.horizon,
            forecast_type=ForecastType.CLASSIFICATION,
            predicted_class=top_class,
            probability=uncalibrated_score,
            is_calibrated_probability=False,  # STRICT PROBABILITY INTEGRITY RULE
            method_name=self.name,
            model_version=self.version,
            sample_count=len(inputs),
            assumptions=[ForecastAssumption(assumption_id="asm_freq_1", description="Stationary base-rates")],
            limitations=["Uncalibrated frequency score; does not condition on transient exogenous factors."],
            explanation=explanation,
            status=ForecastStatus.COMPLETED,
            created_at=now,
            expires_at=request.horizon.end_time,
        )


class DurationForecaster(BaseForecaster):
    """
    Duration Estimation Forecaster: estimates task or mission duration
    based on historical execution duration percentiles and mean.
    """

    def __init__(self):
        super().__init__(name="DurationForecaster", version="1.0.0")

    def forecast(
        self,
        request: ForecastRequest,
        inputs: List[ForecastInput],
        features: Dict[str, Any],
    ) -> Forecast:
        fid = f"fc-{uuid.uuid4().hex[:12]}"
        now = time.time()

        durations = [
            float(inp.value)
            for inp in inputs
            if inp.timestamp <= request.as_of_time and isinstance(inp.value, (int, float)) and float(inp.value) > 0
        ]

        if not durations:
            return Forecast(
                forecast_id=fid,
                request_id=request.request_id,
                target=request.target,
                horizon=request.horizon,
                forecast_type=ForecastType.DURATION_ESTIMATION,
                method_name=self.name,
                model_version=self.version,
                status=ForecastStatus.INSUFFICIENT_DATA,
                limitations=["No positive duration records found."],
                created_at=now,
                expires_at=request.horizon.end_time,
            )

        durations.sort()
        n = len(durations)
        median_dur = round(statistics.median(durations), 2)
        mean_dur = round(statistics.mean(durations), 2)

        # Percentile boundaries (P10 and P90)
        p10 = durations[max(0, int(0.10 * n))]
        p90 = durations[min(n - 1, int(0.90 * n))]

        interval = ForecastInterval(
            lower_bound=round(p10, 2),
            upper_bound=round(p90, 2),
            confidence_level=0.80,
            is_calibrated=False,
            coverage_guarantee="EMPIRICAL_PERCENTILE_RANGE_NO_GUARANTEE",
        )

        explanation = PredictionExplanation(
            summary=f"Estimated duration: median {median_dur:.2f}s (mean {mean_dur:.2f}s) with 80% empirical range [{p10:.2f}s, {p90:.2f}s].",
            key_factors=[f"Sample size: {n} tasks", f"P10-P90 range: {p10:.2f}s - {p90:.2f}s"],
            baseline_comparison=f"Median duration {median_dur:.2f}s",
            data_uncertainty="LOW" if n >= 10 else "HIGH",
            model_uncertainty="LOW",
            known_assumptions=["Task resource profile and complexity are homogeneous."],
            limitations=["Outlier workloads or host starvation can exceed P90 bound."],
        )

        return Forecast(
            forecast_id=fid,
            request_id=request.request_id,
            target=request.target,
            horizon=request.horizon,
            forecast_type=ForecastType.DURATION_ESTIMATION,
            predicted_value=median_dur,
            probability=None,
            is_calibrated_probability=False,
            interval=interval,
            method_name=self.name,
            model_version=self.version,
            sample_count=n,
            assumptions=[ForecastAssumption(assumption_id="asm_dur_1", description="Homogeneous workload distribution")],
            limitations=["Queueing delays are not accounted for in execution duration."],
            explanation=explanation,
            status=ForecastStatus.COMPLETED,
            created_at=now,
            expires_at=request.horizon.end_time,
        )


class RuleBasedRiskForecaster(BaseForecaster):
    """
    Deterministic Rule-Based Risk Forecaster:
    Evaluates observed system indicators against configured thresholds.
    Strictly separates likelihood score from impact severity.
    """

    def __init__(self):
        super().__init__(name="RuleBasedRiskForecaster", version="1.0.0")

    def forecast(
        self,
        request: ForecastRequest,
        inputs: List[ForecastInput],
        features: Dict[str, Any],
    ) -> Forecast:
        fid = f"fc-{uuid.uuid4().hex[:12]}"
        now = time.time()

        recent_val = features.get("recent_value")
        trend = features.get("trend_slope", 0.0)
        variance = features.get("historical_variance", 0.0)

        risk_factors: List[RiskFactor] = []
        likelihood_score = 0.1  # Baseline baseline probability score
        impact_score = float(request.parameters.get("configured_impact", 3.0))

        # Factor 1: High recent value threshold (e.g. latency > 500 or error > 0)
        if isinstance(recent_val, (int, float)):
            thresh = float(request.parameters.get("critical_threshold", 80.0))
            if recent_val >= thresh:
                likelihood_score += 0.4
                risk_factors.append(RiskFactor(
                    factor_id="rf_threshold_breach",
                    name="Threshold Breach",
                    description=f"Recent value {recent_val} exceeds warning threshold {thresh}",
                    weight=1.5,
                ))

        # Factor 2: Deteriorating monotonic trend
        if trend > 0.01:
            likelihood_score += 0.25
            risk_factors.append(RiskFactor(
                factor_id="rf_deteriorating_trend",
                name="Deteriorating Trend",
                description=f"Positive trend slope ({trend:.4f} units/s) indicates continuous degradation",
                weight=1.2,
            ))

        # Factor 3: High volatility / variance
        if variance > 50.0:
            likelihood_score += 0.15
            risk_factors.append(RiskFactor(
                factor_id="rf_high_volatility",
                name="High Volatility",
                description=f"Variance of {variance:.2f} indicates system instability",
                weight=1.0,
            ))

        likelihood_score = min(1.0, round(likelihood_score, 4))

        # Map to RiskLevel
        risk_level = RiskLevel.INFORMATIONAL
        if likelihood_score >= 0.8:
            risk_level = RiskLevel.CRITICAL if impact_score >= 4.0 else RiskLevel.HIGH
        elif likelihood_score >= 0.5:
            risk_level = RiskLevel.HIGH if impact_score >= 4.0 else RiskLevel.MODERATE
        elif likelihood_score >= 0.3:
            risk_level = RiskLevel.MODERATE if impact_score >= 4.0 else RiskLevel.LOW
        else:
            risk_level = RiskLevel.LOW

        risk_assessment = RiskAssessment(
            risk_id=f"risk-{uuid.uuid4().hex[:10]}",
            target_id=request.target.target_id,
            risk_level=risk_level,
            likelihood_score=likelihood_score,
            is_calibrated_likelihood=False,  # Uncalibrated score
            impact_score=impact_score,
            risk_factors=risk_factors,
            mitigations=request.parameters.get("mitigations", ["Enable rate limiting", "Trigger circuit breaker"]),
            evaluated_at=now,
            expires_at=request.horizon.end_time,
        )

        explanation = PredictionExplanation(
            summary=f"Assessed risk level as {risk_level.value} (likelihood score {likelihood_score:.2f}, impact {impact_score:.1f}).",
            key_factors=[f"{f.name}: {f.description}" for f in risk_factors],
            baseline_comparison=f"Baseline likelihood 0.10 shifted to {likelihood_score:.2f}",
            data_uncertainty="LOW" if features.get("sample_count", 0) >= 5 else "HIGH",
            model_uncertainty="LOW",  # Deterministic rule evaluation
            known_assumptions=["Configured thresholds represent genuine operational boundaries."],
            limitations=["Likelihood score is a heuristic index, not an actuarial probability."],
        )

        return Forecast(
            forecast_id=fid,
            request_id=request.request_id,
            target=request.target,
            horizon=request.horizon,
            forecast_type=ForecastType.ANOMALY_RISK,
            predicted_value=likelihood_score,
            predicted_class=risk_level.value,
            probability=likelihood_score,
            is_calibrated_probability=False,
            method_name=self.name,
            model_version=self.version,
            sample_count=features.get("sample_count", 0),
            risk_assessment=risk_assessment,
            assumptions=[ForecastAssumption(assumption_id="asm_risk_1", description="Threshold validity")],
            limitations=["Heuristic scoring; correlation does not imply causality."],
            explanation=explanation,
            status=ForecastStatus.COMPLETED,
            created_at=now,
            expires_at=request.horizon.end_time,
        )
