"""
OMNIA Module 35: Experiment Design & Safety Validator
Defines formal experimental protocols (variables, sample sizes, controls, stopping rules)
and enforces fail-closed human approval gating (Module 20) for live interventions.
"""

import uuid
import logging
from typing import Dict, Any, List, Optional
from research.models import (
    ExperimentDefinition,
    ExperimentType,
)
from research.persistence import ResearchRepository

logger = logging.getLogger("Omnia.Research.Experiments")


class ExperimentDesigner:
    """Designs controlled experimental protocols and validates execution safety."""

    def __init__(self, repo: ResearchRepository):
        self.repo = repo

    def design_experiment(
        self,
        research_id: str,
        hypothesis_id: str,
        title: str,
        objective: str,
        experiment_type: ExperimentType,
        independent_variables: List[str],
        dependent_variables: List[str],
        controlled_variables: List[str],
        baseline_condition: str,
        treatment_condition: str,
        sample_size: int = 30,
        sampling_strategy: str = "RANDOM_UNIFORM",
        measurement_protocol: str = "RECORD_EXECUTION_LATENCY_AND_THROUGHPUT",
        stopping_conditions: str = "COMPLETE_SAMPLE_OR_ERROR_THRESHOLD_EXCEEDED",
        success_criteria: str = "TREATMENT_OUTPERFORMS_BASELINE_STATISTICALLY",
        failure_criteria: str = "NO_SIGNIFICANT_EFFECT_OR_CONTRADICTORY_EVIDENCE",
        requires_approval: bool = False,
        isolation_environment: str = "SIMULATION",
    ) -> ExperimentDefinition:
        """Constructs an empirical experiment definition with strict control variables."""
        if not independent_variables or not dependent_variables:
            raise ValueError("Experiments must define at least one independent and one dependent variable")
        if sample_size < 1:
            raise ValueError("Sample size must be greater than zero")

        exp_id = f"exp-{uuid.uuid4().hex[:8]}"
        exp = ExperimentDefinition(
            experiment_id=exp_id,
            research_id=research_id,
            hypothesis_id=hypothesis_id,
            title=title,
            objective=objective,
            experiment_type=experiment_type,
            independent_variables=independent_variables,
            dependent_variables=dependent_variables,
            controlled_variables=controlled_variables,
            sampling_strategy=sampling_strategy,
            sample_size=sample_size,
            baseline_condition=baseline_condition,
            treatment_condition=treatment_condition,
            measurement_protocol=measurement_protocol,
            stopping_conditions=stopping_conditions,
            success_criteria=success_criteria,
            failure_criteria=failure_criteria,
            requires_approval=requires_approval,
            approval_token=None,
            isolation_environment=isolation_environment,
            status="PLANNED",
        )
        self.repo.save_experiment(exp)
        logger.info(f"Designed experiment '{exp_id}': {title} (Type: {experiment_type.value})")
        return exp

    def authorize_experiment(self, experiment_id: str, approval_token: str) -> bool:
        """Attaches a Module 20 human approval token to an approval-gated experiment."""
        exp = self.repo.get_experiment(experiment_id)
        if not exp:
            return False
        if not approval_token or len(approval_token) < 8:
            logger.warning(f"Invalid approval token provided for experiment {experiment_id}")
            return False

        exp.approval_token = approval_token
        exp.status = "APPROVED"
        self.repo.save_experiment(exp)
        logger.info(f"Experiment {experiment_id} authorized with token {approval_token[:8]}...")
        return True
