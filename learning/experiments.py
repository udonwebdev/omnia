"""
Omnia Module 33: Learning Experiments & Evaluation Protocol Runner
Orchestrates offline benchmark, shadow, A/B test, and replay experiments
with pre-registered hypotheses and bounded execution budgets.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from learning.models import ExperimentConfig, ExperimentStatus, ExperimentType


class ExperimentEngine:
    """
    Manages experiment lifecycle, tracking hypothesis validation,
    enforcing resource budgets, and computing statistical outcomes.
    """

    def __init__(self) -> None:
        pass

    def start_experiment(self, experiment: ExperimentConfig) -> ExperimentConfig:
        """
        Validates experiment preconditions and transitions it to RUNNING.
        """
        if experiment.status != ExperimentStatus.CREATED:
            raise ValueError(f"Cannot start experiment in status: {experiment.status.value}")

        if not experiment.baseline_version_id or not experiment.candidate_version_id:
            raise ValueError("Experiment requires both baseline and candidate version IDs")

        if experiment.baseline_version_id == experiment.candidate_version_id:
            raise ValueError("Baseline and candidate version IDs cannot be identical")

        if not experiment.primary_metric:
            raise ValueError("Experiment requires a defined primary_metric")

        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now(timezone.utc)
        return experiment

    def record_observation(
        self,
        experiment: ExperimentConfig,
        is_candidate: bool,
        metrics: Dict[str, float],
    ) -> bool:
        """
        Records an evaluation sample under the experiment budget.
        Returns True if budget allows, False if budget exceeded.
        """
        if experiment.status != ExperimentStatus.RUNNING:
            return False

        # Budget checking
        max_samples = experiment.max_samples
        if experiment.current_samples >= max_samples:
            return False

        experiment.current_samples += 1
        target_dict = experiment.candidate_metrics if is_candidate else experiment.baseline_metrics

        for k, v in metrics.items():
            prev = target_dict.get(k, 0.0)
            # Incremental average update
            count = experiment.current_samples if not is_candidate else experiment.current_samples // 2 or 1
            target_dict[k] = round((prev * (count - 1) + v) / count, 4)

        return True

    def conclude_experiment(
        self,
        experiment: ExperimentConfig,
        force_stop_reason: Optional[str] = None,
    ) -> Tuple[ExperimentConfig, Dict[str, Any]]:
        """
        Concludes experiment, evaluates hypothesis against significance thresholds,
        and returns results summary.
        """
        if experiment.status not in (ExperimentStatus.RUNNING, ExperimentStatus.CREATED):
            return experiment, {"status": experiment.status.value, "error": "Already concluded"}

        experiment.ended_at = datetime.now(timezone.utc)

        if force_stop_reason:
            experiment.status = ExperimentStatus.FAILED
            experiment.metadata["stop_reason"] = force_stop_reason
            return experiment, {"status": "FAILED", "reason": force_stop_reason}

        # Check sample count sufficiency
        if experiment.current_samples < experiment.min_sample_size:
            experiment.status = ExperimentStatus.INCONCLUSIVE
            experiment.metadata["conclude_reason"] = f"Insufficient samples: {experiment.current_samples} < {experiment.min_sample_size}"
            return experiment, {
                "status": "INCONCLUSIVE",
                "samples": experiment.current_samples,
                "required": experiment.min_sample_size,
            }

        # Evaluate primary metric delta
        base_val = experiment.baseline_metrics.get(experiment.primary_metric, 0.0)
        cand_val = experiment.candidate_metrics.get(experiment.primary_metric, 0.0)

        # Assuming higher is better unless metric has 'error', 'latency', 'loss', or 'cost'
        lower_is_better = any(term in experiment.primary_metric.lower() for term in ("error", "latency", "loss", "cost", "failure"))
        
        if lower_is_better:
            rel_improvement = (base_val - cand_val) / (base_val if base_val != 0 else 1.0)
        else:
            rel_improvement = (cand_val - base_val) / (base_val if base_val != 0 else 1.0)

        passed_threshold = rel_improvement >= experiment.significance_threshold

        experiment.status = ExperimentStatus.COMPLETED
        experiment.metadata["relative_improvement"] = round(rel_improvement, 4)
        experiment.metadata["hypothesis_verified"] = passed_threshold

        results = {
            "experiment_id": experiment.experiment_id,
            "status": experiment.status.value,
            "samples": experiment.current_samples,
            "primary_metric": experiment.primary_metric,
            "baseline_value": base_val,
            "candidate_value": cand_val,
            "relative_improvement": round(rel_improvement, 4),
            "threshold_required": experiment.significance_threshold,
            "hypothesis_verified": passed_threshold,
        }

        return experiment, results
