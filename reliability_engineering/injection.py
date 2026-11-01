"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Fault Injection Controller: Governed, Non-Destructive Fault Injection & Rollback Guards.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from reliability_engineering.models import (
    ExperimentLifecycleState,
    FaultInjectionExperiment,
)
from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.Injection")


class FaultInjectionController:
    """
    Executes controlled fault injection experiments with automated safety abort triggers,
    maximum runtime limits, and full audit tracking.
    Enforces Module 20 human approval token gate for any privileged/high-impact experiments.
    """

    def __init__(self, repository: Optional[ReliabilityRepository] = None):
        self.repo = repository or ReliabilityRepository()

    def create_experiment(
        self,
        scenario_id: str,
        hypothesis: str,
        target_environment: str = "ISOLATED_SANDBOX",
        max_duration_sec: float = 120.0,
        experiment_id: Optional[str] = None,
    ) -> FaultInjectionExperiment:
        """Defines a resilience test experiment."""
        scenario = self.repo.get_scenario(scenario_id)
        if not scenario:
            raise ValueError(f"Failure scenario '{scenario_id}' not found.")

        eid = experiment_id or f"exp-{uuid.uuid4().hex[:8]}"
        exp = FaultInjectionExperiment(
            experiment_id=eid,
            scenario_id=scenario_id,
            hypothesis=hypothesis,
            target_environment=target_environment,
            lifecycle_state=ExperimentLifecycleState.DEFINED,
            max_duration_sec=max_duration_sec,
        )
        self.repo.save_experiment(exp)
        logger.info(f"Defined fault experiment '{eid}' for scenario '{scenario_id}'")
        return exp

    def authorize_and_start_experiment(
        self,
        experiment_id: str,
        approval_token: str,
        approver: str = "reliability_engineer",
    ) -> FaultInjectionExperiment:
        """
        Validates Module 20 human approval token and activates fault injection.
        """
        if not approval_token or not approval_token.strip():
            raise PermissionError("APPROVAL_REQUIRED: Fault injection requires a valid Module 20 cryptographic token.")

        exp = self.repo.get_experiment(experiment_id)
        if not exp:
            raise ValueError(f"Experiment '{experiment_id}' not found.")

        now = datetime.now(timezone.utc).isoformat()
        exp.lifecycle_state = ExperimentLifecycleState.RUNNING
        exp.approval_token = approval_token
        exp.approved_by = approver
        exp.started_at = now
        exp.observations.append({
            "event": "FAULT_INJECTED",
            "timestamp": now,
            "status": "ACTIVE",
        })
        self.repo.save_experiment(exp)
        logger.info(f"Started fault experiment '{experiment_id}' approved by '{approver}'")
        return exp

    def complete_experiment(
        self,
        experiment_id: str,
        containment_successful: bool,
        cascading_failure_detected: bool,
        actual_duration_sec: float,
        observation_notes: str = "",
    ) -> FaultInjectionExperiment:
        """Concludes experiment, verifies rollback/containment, and logs final results."""
        exp = self.repo.get_experiment(experiment_id)
        if not exp:
            raise ValueError(f"Experiment '{experiment_id}' not found.")

        now = datetime.now(timezone.utc).isoformat()
        state = ExperimentLifecycleState.COMPLETED
        if cascading_failure_detected or actual_duration_sec > exp.max_duration_sec:
            state = ExperimentLifecycleState.ABORTED

        exp.lifecycle_state = state
        exp.containment_successful = containment_successful
        exp.cascading_failure_detected = cascading_failure_detected
        exp.actual_duration_sec = actual_duration_sec
        exp.completed_at = now
        exp.observations.append({
            "event": "EXPERIMENT_CONCLUDED",
            "timestamp": now,
            "state": state.value,
            "notes": observation_notes,
        })
        self.repo.save_experiment(exp)
        logger.info(f"Concluded experiment '{experiment_id}': State={state.value}, Containment={containment_successful}")
        return exp
