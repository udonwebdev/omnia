"""
Omnia Module 32: Forecast Calibration & Evaluation Metrics
Computes verifiable calibration metrics including Brier score, Expected
Calibration Error (ECE), MAE, RMSE, and prediction interval coverage rates.
"""

from typing import List, Dict, Any, Optional, Tuple
import math
import statistics
import time
import uuid

from prediction.models import (
    Forecast,
    ForecastOutcome,
    ForecastEvaluation,
    CalibrationRecord,
)


class CalibrationEngine:
    """Evaluates forecast accuracy against observed outcomes and maintains calibration records."""

    @staticmethod
    def evaluate_single_forecast(
        forecast: Forecast,
        outcome: ForecastOutcome,
    ) -> ForecastEvaluation:
        """
        Evaluates a single forecast against its validated outcome without mutating the forecast.
        """
        eid = f"fev-{uuid.uuid4().hex[:10]}"
        now = time.time()
        metric_name = "ERROR"
        error_val = 0.0
        is_accurate = False

        if forecast.predicted_value is not None and outcome.observed_value is not None:
            # Continuous numerical forecast
            error_val = round(abs(forecast.predicted_value - outcome.observed_value), 4)
            metric_name = "ABSOLUTE_ERROR"
            # Accurate if error is within interval or within 10%
            if forecast.interval:
                is_accurate = (forecast.interval.lower_bound <= outcome.observed_value <= forecast.interval.upper_bound)
            else:
                margin = max(1.0, abs(forecast.predicted_value) * 0.10)
                is_accurate = error_val <= margin

        elif forecast.predicted_class is not None and outcome.observed_class is not None:
            # Categorical classification forecast
            is_accurate = (forecast.predicted_class == outcome.observed_class)
            metric_name = "ZERO_ONE_LOSS"
            error_val = 0.0 if is_accurate else 1.0

            # If probability was predicted, calculate Brier score component
            if forecast.probability is not None:
                actual_binary = 1.0 if is_accurate else 0.0
                error_val = round((forecast.probability - actual_binary) ** 2, 4)
                metric_name = "BRIER_COMPONENT"

        return ForecastEvaluation(
            evaluation_id=eid,
            forecast_id=forecast.forecast_id,
            outcome_id=outcome.outcome_id,
            metric_name=metric_name,
            error_value=error_val,
            is_accurate=is_accurate,
            evaluated_at=now,
            evaluation_notes=f"Evaluated with metric {metric_name}: error {error_val}, accurate={is_accurate}",
        )

    @staticmethod
    def compute_calibration_record(
        model_name: str,
        target_type: str,
        evaluations: List[Tuple[Forecast, ForecastOutcome]],
    ) -> Optional[CalibrationRecord]:
        """
        Aggregates multiple forecast-outcome evaluations to produce a calibrated performance record.
        """
        if not evaluations:
            return None

        cid = f"calib-{uuid.uuid4().hex[:10]}"
        sample_count = len(evaluations)
        now = time.time()
        timestamps = [fc.created_at for fc, _ in evaluations]
        t_start = min(timestamps) if timestamps else now
        t_end = max(timestamps) if timestamps else now

        # Compute regression metrics if applicable
        num_errors = []
        covered_count = 0
        interval_eval_count = 0

        # Probabilistic classification metrics
        brier_components = []
        prob_acc_bins: Dict[int, List[Tuple[float, float]]] = {i: [] for i in range(5)}  # 5 bins (0-0.2, 0.2-0.4, etc)

        for fc, out in evaluations:
            if fc.predicted_value is not None and out.observed_value is not None:
                diff = abs(fc.predicted_value - out.observed_value)
                num_errors.append(diff)
                if fc.interval:
                    interval_eval_count += 1
                    if fc.interval.lower_bound <= out.observed_value <= fc.interval.upper_bound:
                        covered_count += 1

            if fc.probability is not None and out.observed_class is not None:
                actual_val = 1.0 if (fc.predicted_class == out.observed_class) else 0.0
                p = max(0.0, min(1.0, fc.probability))
                brier_components.append((p - actual_val) ** 2)

                # Bin for ECE
                bin_idx = min(4, int(p * 5))
                prob_acc_bins[bin_idx].append((p, actual_val))

        mae = round(statistics.mean(num_errors), 4) if num_errors else None
        rmse = round(math.sqrt(statistics.mean([e ** 2 for e in num_errors])), 4) if num_errors else None
        coverage_rate = round(covered_count / interval_eval_count, 4) if interval_eval_count > 0 else None
        brier_score = round(statistics.mean(brier_components), 4) if brier_components else None

        # Expected Calibration Error (ECE) across 5 bins
        ece = None
        if brier_components:
            total_binned = sum(len(pairs) for pairs in prob_acc_bins.values())
            if total_binned > 0:
                ece_sum = 0.0
                for pairs in prob_acc_bins.values():
                    if pairs:
                        avg_conf = statistics.mean([p for p, _ in pairs])
                        avg_acc = statistics.mean([a for _, a in pairs])
                        ece_sum += (len(pairs) / total_binned) * abs(avg_conf - avg_acc)
                ece = round(ece_sum, 4)

        return CalibrationRecord(
            calibration_id=cid,
            model_name=model_name,
            target_type=target_type,
            sample_count=sample_count,
            brier_score=brier_score,
            ece=ece,
            mae=mae,
            rmse=rmse,
            coverage_rate=coverage_rate,
            time_window_start=t_start,
            time_window_end=t_end,
            is_valid=True,
            notes=f"Aggregated calibration over {sample_count} evaluation pairs.",
            updated_at=now,
        )
