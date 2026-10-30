"""
Omnia Module 34: Action Simulation & State Transitions
Simulates domain actions (workflow task completion, failover, resource locks, mock network/APIs)
strictly without ever touching real production adapters.
"""

from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Optional, Tuple


class ActionSimulator:
    """
    Executes simulated actions on isolated state dictionaries.
    CRITICAL INVARIANT: Never falls through to real execution.
    If an action cannot be simulated, returns UNSUPPORTED_SIMULATION_ACTION.
    """

    def __init__(self) -> None:
        pass

    def simulate_action(
        self,
        current_state: Dict[str, Any],
        action: Dict[str, Any],
        step_index: int,
        active_faults: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, Dict[str, Any], Dict[str, Any], str]:
        """
        Applies a simulated action to current_state.
        Returns (success, new_state, transition_metadata, reason_or_error).
        """
        action_type = action.get("action_type", "")
        new_state = copy.deepcopy(current_state)
        faults = active_faults or []

        # Check for fault injection targeting this action
        for f in faults:
            target = f.get("target_component", "")
            f_type = f.get("fault_type", "")
            if target in (action.get("target", ""), action_type, "*"):
                if f_type in ("WORKER_CRASH", "API_TIMEOUT", "NETWORK_PARTITION", "DATABASE_UNAVAILABLE"):
                    return (
                        False,
                        new_state,
                        {"action_type": action_type, "fault_triggered": f_type, "step": step_index},
                        f"Action halted by injected fault: {f_type} on {target}",
                    )

        # Dispatch action simulator
        handler_name = f"_sim_{action_type.lower().replace('.', '_')}"
        handler = getattr(self, handler_name, None)

        if handler is None:
            # Strict boundary: Fail closed
            return (
                False,
                current_state,
                {"action_type": action_type, "unsupported": True},
                f"UNSUPPORTED_SIMULATION_ACTION: No simulator implemented for action type '{action_type}'",
            )

        try:
            success, mutated_state, meta, msg = handler(new_state, action, step_index)
            return success, mutated_state, meta, msg
        except Exception as e:
            return False, current_state, {"error": str(e)}, f"Simulation error: {e}"

    # -------------------------------------------------------------
    # DOMAIN ACTION SIMULATORS
    # -------------------------------------------------------------
    def _sim_task_complete(
        self, state: Dict[str, Any], action: Dict[str, Any], step: int
    ) -> Tuple[bool, Dict[str, Any], Dict[str, Any], str]:
        task_id = action.get("task_id", f"task_{step}")
        tasks = state.setdefault("tasks", {})
        tasks[task_id] = {
            "status": "COMPLETED",
            "completed_at": time.time(),
            "output": action.get("output", {"status": "ok"}),
        }
        meta = {"task_id": task_id, "status": "COMPLETED", "duration_sec": action.get("duration", 1.0)}
        return True, state, meta, f"Simulated task '{task_id}' completion"

    def _sim_task_fail(
        self, state: Dict[str, Any], action: Dict[str, Any], step: int
    ) -> Tuple[bool, Dict[str, Any], Dict[str, Any], str]:
        task_id = action.get("task_id", f"task_{step}")
        tasks = state.setdefault("tasks", {})
        tasks[task_id] = {
            "status": "FAILED",
            "failed_at": time.time(),
            "error": action.get("error", "Simulated failure"),
        }
        meta = {"task_id": task_id, "status": "FAILED"}
        return True, state, meta, f"Simulated task '{task_id}' failure"

    def _sim_node_failover(
        self, state: Dict[str, Any], action: Dict[str, Any], step: int
    ) -> Tuple[bool, Dict[str, Any], Dict[str, Any], str]:
        failed_node = action.get("failed_node", "node_1")
        target_node = action.get("target_node", "node_2")
        nodes = state.setdefault("nodes", {})
        if failed_node in nodes:
            nodes[failed_node]["status"] = "OFFLINE"
        if target_node in nodes:
            nodes[target_node]["status"] = "LEADER"
        meta = {"failed_node": failed_node, "target_node": target_node, "action": "FAILOVER"}
        return True, state, meta, f"Simulated failover from {failed_node} to {target_node}"

    def _sim_resource_allocate(
        self, state: Dict[str, Any], action: Dict[str, Any], step: int
    ) -> Tuple[bool, Dict[str, Any], Dict[str, Any], str]:
        res_name = action.get("resource", "cpu")
        amount = float(action.get("amount", 1.0))
        resources = state.setdefault("resources", {})
        curr = float(resources.get(res_name, 0.0))
        limit = float(state.get("resource_limits", {}).get(res_name, 1000.0))

        if curr + amount > limit:
            return False, state, {"resource": res_name, "requested": amount, "available": limit - curr}, f"Resource limit exceeded for {res_name}"

        resources[res_name] = curr + amount
        meta = {"resource": res_name, "allocated": amount, "total": resources[res_name]}
        return True, state, meta, f"Simulated allocation of {amount} {res_name}"

    def _sim_api_request(
        self, state: Dict[str, Any], action: Dict[str, Any], step: int
    ) -> Tuple[bool, Dict[str, Any], Dict[str, Any], str]:
        endpoint = action.get("endpoint", "/api/test")
        simulated_response = action.get("mock_response", {"status": 200, "data": "simulated"})
        api_log = state.setdefault("api_log", [])
        api_log.append({"endpoint": endpoint, "step": step, "response": simulated_response})
        meta = {"endpoint": endpoint, "status_code": simulated_response.get("status", 200)}
        return True, state, meta, f"Simulated API call to {endpoint}"
