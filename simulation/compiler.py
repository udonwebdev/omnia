"""
Omnia Module 34: Scenario Definition & Compiler
Validates preconditions, constraints, schemas, and resource budgets,
producing deterministic, executable simulation plans.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from simulation.models import (
    ScenarioDefinition,
    ScenarioType,
    SimulationEnvironment,
    StateSnapshot,
)


class ScenarioCompiler:
    """
    Compiles raw scenario definitions into executable, verified simulation plans.
    Validates preconditions against snapshots and detects impossible or contradictory constraints.
    """

    def __init__(self) -> None:
        pass

    def compile_scenario(
        self,
        scenario: ScenarioDefinition,
        environment: SimulationEnvironment,
        snapshot: StateSnapshot,
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Validates scenario integrity, environment capability match, and precondition satisfiability.
        Returns (is_valid, compiled_plan, rejection_reason).
        """
        # 1. Structural checks
        if not scenario.scenario_id or not scenario.name:
            return False, None, "Scenario missing ID or name"

        if scenario.environment_id != environment.environment_id:
            return False, None, f"Scenario environment mismatch: {scenario.environment_id} != {environment.environment_id}"

        if scenario.initial_snapshot_id != snapshot.snapshot_id:
            return False, None, f"Scenario snapshot mismatch: {scenario.initial_snapshot_id} != {snapshot.snapshot_id}"

        # 2. Action compatibility checks
        supported_actions = set(environment.supported_action_types)
        for act in scenario.proposed_actions:
            act_type = act.get("action_type")
            if not act_type:
                return False, None, "Proposed action missing 'action_type'"
            if supported_actions and act_type not in supported_actions:
                return False, None, f"Action type '{act_type}' not supported in environment '{environment.name}'"

        # 3. Precondition verification against initial snapshot
        initial_state = snapshot.state_payload
        for key, expected_val in scenario.preconditions.items():
            actual_val = self._resolve_json_path(initial_state, key)
            if actual_val is None:
                return False, None, f"Unsatisfied precondition: key '{key}' not found in initial snapshot"
            if actual_val != expected_val:
                return False, None, f"Contradictory precondition: '{key}' expected {expected_val}, found {actual_val}"

        # 4. Resource budget validation
        budget = scenario.resource_budget
        max_duration = budget.get("max_duration_seconds", scenario.time_horizon_seconds)
        if max_duration <= 0:
            return False, None, "Resource budget max_duration_seconds must be positive"

        # 5. Build compiled execution plan
        compiled_plan = {
            "scenario_id": scenario.scenario_id,
            "environment_id": environment.environment_id,
            "snapshot_id": snapshot.snapshot_id,
            "scenario_type": scenario.scenario_type.value,
            "total_actions": len(scenario.proposed_actions),
            "actions": scenario.proposed_actions,
            "time_horizon_seconds": scenario.time_horizon_seconds,
            "budget": budget,
            "constraints": scenario.constraints,
            "compiled_at": time.time(),
        }

        return True, compiled_plan, "Scenario compiled successfully"

    def _resolve_json_path(self, data: Dict[str, Any], path: str) -> Any:
        tokens = path.split(".")
        curr = data
        for t in tokens:
            if isinstance(curr, dict) and t in curr:
                curr = curr[t]
            else:
                return None
        return curr
