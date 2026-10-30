"""
Omnia Module 34: Simulation Execution Engine
Orchestrates step-by-step and full-scenario deterministic simulations,
managing state transitions, fault triggers, checkpoints, and resource tracking.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Optional, Tuple

from simulation.actions import ActionSimulator
from simulation.faults import FaultInjector
from simulation.models import (
    FaultInjectionSpec,
    ScenarioDefinition,
    SimulationExecutionRecord,
    SimulationStatus,
    StateFidelity,
    StateSnapshot,
)


class SimulationEngine:
    """
    Deterministic runtime engine for simulated scenarios.
    Strictly isolated: never falls through to live production adapters.
    """

    def __init__(self) -> None:
        self.action_simulator = ActionSimulator()
        self.fault_injector = FaultInjector()

    def run_simulation(
        self,
        simulation_id: str,
        scenario: ScenarioDefinition,
        snapshot: StateSnapshot,
        twin_id: Optional[str] = None,
        fault_specs: Optional[List[FaultInjectionSpec]] = None,
    ) -> SimulationExecutionRecord:
        """
        Executes a compiled scenario from an immutable initial snapshot.
        """
        now = time.time()
        record = SimulationExecutionRecord(
            simulation_id=simulation_id,
            scenario_id=scenario.scenario_id,
            environment_id=scenario.environment_id,
            snapshot_id=snapshot.snapshot_id,
            twin_id=twin_id,
            status=SimulationStatus.RUNNING,
            current_step=0,
            total_steps=len(scenario.proposed_actions),
            action_history=[],
            state_transitions=[],
            events_generated=[],
            resource_consumption={"cpu_seconds": 0.0, "steps_executed": 0},
            result_summary={},
            fidelity_classification=StateFidelity.MODERATE,
            started_at=now,
            created_at=now,
        )

        current_state = copy.deepcopy(snapshot.state_payload)
        faults = fault_specs or []

        for step_idx, action in enumerate(scenario.proposed_actions):
            record.current_step = step_idx + 1

            # Determine active faults
            active_faults = self.fault_injector.get_active_faults_for_step(faults, step_idx + 1)

            # Simulate action transition
            success, next_state, transition_meta, reason = self.action_simulator.simulate_action(
                current_state=current_state,
                action=action,
                step_index=step_idx + 1,
                active_faults=active_faults,
            )

            record.action_history.append({
                "step": step_idx + 1,
                "action": action,
                "success": success,
                "reason": reason,
            })

            record.state_transitions.append({
                "step": step_idx + 1,
                "transition_meta": transition_meta,
                "state_hash_delta": len(next_state),
            })

            record.resource_consumption["steps_executed"] += 1
            record.resource_consumption["cpu_seconds"] = round(record.resource_consumption["cpu_seconds"] + 0.01, 3)

            if not success:
                # Execution halted (fault or failure)
                record.status = SimulationStatus.FAILED
                record.error_message = reason
                record.completed_at = time.time()
                record.result_summary = {
                    "final_status": "FAILED",
                    "failed_step": step_idx + 1,
                    "failure_reason": reason,
                    "final_state": next_state,
                }
                return record

            # Transition state
            current_state = next_state

        # Completed successfully
        record.status = SimulationStatus.COMPLETED
        record.completed_at = time.time()
        record.result_summary = {
            "final_status": "COMPLETED",
            "total_steps_executed": len(scenario.proposed_actions),
            "final_state": current_state,
        }
        return record
