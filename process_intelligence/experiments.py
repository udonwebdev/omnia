"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Improvement Experiment Manager: Controlled Rollout & Guardrail Rollback.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from process_intelligence.models import (
    ExperimentStatus,
    OptimizationExperimentRecord,
)
from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Experiments")


class ImprovementExperimentManager:
    """
    Manages controlled improvement experiments, monitors guardrails (error rate, latency spike),
    and triggers automated rollback if any guardrail threshold is breached.
    """

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def create_experiment(
        self,
        candidate_id: str,
        workflow_id: str,
        baseline_trace_count: int = 10,
        target_trace_count: int = 20,
        max_allowable_error_rate: float = 0.05,
        max_allowable_latency_spike_pct: float = 20.0,
        experiment_id: Optional[str] = None,
    ) -> OptimizationExperimentRecord:
        """Initializes a controlled rollout experiment with protective guardrails."""
        eid = experiment_id or f"exp-{uuid.uuid4().hex[:8]}"
        guardrails = {
            "max_error_rate": max_allowable_error_rate,
            "max_latency_spike_pct": max_allowable_latency_spike_pct,
        }
        exp = OptimizationExperimentRecord(
            experiment_id=eid,
            candidate_id=candidate_id,
            workflow_id=workflow_id,
            baseline_trace_count=baseline_trace_count,
            target_trace_count=target_trace_count,
            guardrail_metrics=guardrails,
            observed_improvement_pct=0.0,
            is_guardrail_breached=False,
            status=ExperimentStatus.RUNNING,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_experiment(exp)
        logger.info(f"Initialized optimization experiment '{eid}' for candidate '{candidate_id}'")
        return exp

    def evaluate_experiment_telemetry(
        self,
        experiment_id: str,
        observed_improvement_pct: float,
        current_error_rate: float,
        latency_spike_pct: float = 0.0,
    ) -> OptimizationExperimentRecord:
        """
        Ingests real-time experiment telemetry, checks guardrails, and triggers rollback if violated.
        """
        exp = self.repo.get_experiment(experiment_id)
        if not exp:
            raise ValueError(f"Experiment '{experiment_id}' not found.")

        max_err = exp.guardrail_metrics.get("max_error_rate", 0.05)
        max_spike = exp.guardrail_metrics.get("max_latency_spike_pct", 20.0)

        # Check breach
        breach = current_error_rate > max_err or latency_spike_pct > max_spike
        now = datetime.now(timezone.utc).isoformat()

        if breach:
            status = ExperimentStatus.ROLLED_BACK
            logger.warning(
                f"GUARDRAIL_BREACH in experiment '{experiment_id}': ErrorRate={current_error_rate:.1%} (max {max_err:.1%}), Spike={latency_spike_pct:.1f}% (max {max_spike:.1f}%). Triggering automated rollback!"
            )
        else:
            status = ExperimentStatus.CONCLUDED
            logger.info(f"Experiment '{experiment_id}' concluded successfully with {observed_improvement_pct:.1f}% improvement.")

        updated_exp = OptimizationExperimentRecord(
            experiment_id=exp.experiment_id,
            candidate_id=exp.candidate_id,
            workflow_id=exp.workflow_id,
            baseline_trace_count=exp.baseline_trace_count,
            target_trace_count=exp.target_trace_count,
            guardrail_metrics=exp.guardrail_metrics,
            observed_improvement_pct=observed_improvement_pct,
            is_guardrail_breached=breach,
            status=status,
            started_at=exp.started_at,
            completed_at=now,
        )
        self.repo.save_experiment(updated_exp)
        return updated_exp
