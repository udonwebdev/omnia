"""
Omnia Module 32: Model & Concept Drift Detection
Monitors error growth, distribution shifts, and calibration degradation,
emitting actionable recommendations without automated risky policy modifications.
"""

from typing import List, Dict, Any, Optional
import math
import statistics
import time
import uuid

from prediction.models import (
    DriftAssessment,
    ForecastEvaluation,
)


class DriftDetector:
    """Detects concept and performance drift by comparing recent errors against baseline."""

    @staticmethod
    def assess_drift(
        model_name: str,
        target_id: str,
        evaluations: List[ForecastEvaluation],
        baseline_error: Optional[float] = None,
        drift_threshold_multiplier: float = 1.75,
        min_evals_required: int = 6,
    ) -> DriftAssessment:
        did = f"drift-{uuid.uuid4().hex[:10]}"
        now = time.time()

        if len(evaluations) < min_evals_required:
            return DriftAssessment(
                drift_id=did,
                model_name=model_name,
                target_id=target_id,
                detected=False,
                drift_type="INSUFFICIENT_EVALUATIONS",
                sample_count=len(evaluations),
                metric_shift=0.0,
                recommendation="CONTINUE_MONITORING: Need more evaluation samples to evaluate drift.",
                detected_at=now,
            )

        # Split into historical baseline (first half) and recent window (second half)
        # if baseline_error not provided
        split_idx = len(evaluations) // 2
        historical_evals = evaluations[:split_idx]
        recent_evals = evaluations[split_idx:]

        hist_errs = [e.error_value for e in historical_evals]
        rec_errs = [e.error_value for e in recent_evals]

        base_mean = baseline_error if baseline_error is not None else (statistics.mean(hist_errs) if hist_errs else 0.0)
        recent_mean = statistics.mean(rec_errs) if rec_errs else 0.0

        shift = round(recent_mean - base_mean, 4)
        relative_shift = (shift / base_mean) if base_mean > 0 else 0.0

        detected = False
        drift_type = "NO_DRIFT"
        recommendation = "CONTINUE_MONITORING"

        # Check if recent error exceeded baseline by drift_threshold_multiplier
        if base_mean > 0 and recent_mean >= base_mean * drift_threshold_multiplier:
            detected = True
            drift_type = "INCREASING_PREDICTION_ERROR"
            recommendation = (
                f"RECOMMEND_RECALIBRATION: Recent error ({recent_mean:.3f}) exceeded baseline "
                f"({base_mean:.3f}) by {relative_shift*100:.1f}%. Consider fallback to safer baseline."
            )
        elif recent_mean > base_mean + 2.0:
            detected = True
            drift_type = "ABSOLUTE_ERROR_SHIFT"
            recommendation = "RECOMMEND_RECALIBRATION: Absolute prediction error has grown significantly."

        return DriftAssessment(
            drift_id=did,
            model_name=model_name,
            target_id=target_id,
            detected=detected,
            drift_type=drift_type,
            metric_shift=shift,
            sample_count=len(evaluations),
            recommendation=recommendation,
            detected_at=now,
        )
