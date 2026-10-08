import time
import logging
from typing import Dict, List, Set, Tuple, Optional, Any

from supervisor.models import ResourcePressure, MissionPriority

logger = logging.getLogger("Omnia.Supervisor.Resources")

class ResourceSupervisor:
    """Supervises system resource pressure, concurrency boundaries, and resource deadlocks."""

    def __init__(self):
        # Resource wait graph:
        # task_id -> set of resources the task is waiting for
        self._wait_graph: Dict[str, Set[str]] = {}
        # resource_name -> owning task_id
        self._allocation_graph: Dict[str, str] = {}
        # task priorities for deadlock resolution
        self._task_priorities: Dict[str, int] = {}

    def get_system_resource_pressure(self) -> Tuple[ResourcePressure, Dict[str, float]]:
        """Queries operating system resource pressure with lightweight fallback."""
        mem_pct = 50.0
        cpu_pct = 20.0
        try:
            import psutil
            mem_pct = psutil.virtual_memory().percent
            cpu_pct = psutil.cpu_percent(interval=None)
        except Exception:
            # Fallback if psutil not installed or permissions restricted
            pass

        metrics = {"memory_percent": mem_pct, "cpu_percent": cpu_pct}

        if mem_pct >= 92.0 or cpu_pct >= 95.0:
            return ResourcePressure.CRITICAL, metrics
        if mem_pct >= 85.0 or cpu_pct >= 85.0:
            return ResourcePressure.HIGH, metrics
        if mem_pct >= 75.0 or cpu_pct >= 70.0:
            return ResourcePressure.ELEVATED, metrics
        return ResourcePressure.NORMAL, metrics

    # --- Deadlock & Wait Graph Management ---

    def register_task_priority(self, task_id: str, priority: int):
        self._task_priorities[task_id] = priority

    def record_resource_acquired(self, task_id: str, resource: str):
        """Records that task_id currently holds lock on resource."""
        self._allocation_graph[resource] = task_id
        if task_id in self._wait_graph:
            self._wait_graph[task_id].discard(resource)

    def record_resource_waiting(self, task_id: str, resource: str):
        """Records that task_id is waiting for lock on resource."""
        self._wait_graph.setdefault(task_id, set()).add(resource)

    def record_resource_released(self, task_id: str, resource: Optional[str] = None):
        """Records release of resource(s)."""
        if resource:
            if self._allocation_graph.get(resource) == task_id:
                del self._allocation_graph[resource]
            if task_id in self._wait_graph:
                self._wait_graph[task_id].discard(resource)
        else:
            # Release all resources held by task
            to_remove = [r for r, owner in self._allocation_graph.items() if owner == task_id]
            for r in to_remove:
                del self._allocation_graph[r]
            self._wait_graph.pop(task_id, None)
            self._task_priorities.pop(task_id, None)

    def detect_deadlock(self) -> Tuple[bool, List[str], Optional[str]]:
        """Detects cycles in the task-resource wait-for graph.
        
        Returns:
            (is_deadlock, cycle_task_ids, victim_task_to_preempt)
        """
        # Build direct Task -> Task wait dependencies:
        # Task A waits for Task B if A waits for resource R and R is allocated to B.
        task_deps: Dict[str, Set[str]] = {}
        for waiting_task, requested_res in self._wait_graph.items():
            task_deps[waiting_task] = set()
            for r in requested_res:
                holder = self._allocation_graph.get(r)
                if holder and holder != waiting_task:
                    task_deps[waiting_task].add(holder)

        # Cycle detection using DFS
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycle_nodes: List[str] = []

        def dfs(node: str, path: List[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in task_deps.get(node, set()):
                if neighbor not in visited:
                    if dfs(neighbor, path):
                        return True
                elif neighbor in rec_stack:
                    # Cycle found! Extract cycle path from neighbor to current
                    idx = path.index(neighbor)
                    cycle_nodes.extend(path[idx:])
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        for t in list(task_deps.keys()):
            if t not in visited:
                if dfs(t, []):
                    # Found a cycle: cycle_nodes contains participating tasks
                    # Select victim with lowest priority to preempt/break deadlock
                    victim = min(
                        cycle_nodes,
                        key=lambda tid: self._task_priorities.get(tid, MissionPriority.NORMAL.value)
                    )
                    logger.critical(f"DEADLOCK DETECTED! Cycle: {cycle_nodes}. Chosen victim to pause/replan: {victim}")
                    return True, cycle_nodes, victim

        return False, [], None

    def clear(self):
        self._wait_graph.clear()
        self._allocation_graph.clear()
        self._task_priorities.clear()

resource_supervisor = ResourceSupervisor()
