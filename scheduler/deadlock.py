import logging
from typing import Dict, List, Set, Tuple, Optional

from scheduler.models import ScheduleRequest, PreemptionPolicy

logger = logging.getLogger("Omnia.Scheduler.Deadlock")

class DeadlockDetector:
    """Detects cycles in the task-resource wait-for graph and chooses safe preemption victims."""

    @staticmethod
    def detect_cycles(wait_graph: Dict[str, Set[str]], allocation_graph: Dict[str, str]) -> Tuple[bool, List[str]]:
        """Finds directed cycles: Task A waits for R, which is held by Task B."""
        task_deps: Dict[str, Set[str]] = {}
        for waiting_task, requested_res in wait_graph.items():
            task_deps[waiting_task] = set()
            for r in requested_res:
                holder = allocation_graph.get(r)
                if holder and holder != waiting_task:
                    task_deps[waiting_task].add(holder)

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
                    idx = path.index(neighbor)
                    cycle_nodes.extend(path[idx:])
                    return True

            rec_stack.remove(node)
            path.pop()
            return False

        for t in list(task_deps.keys()):
            if t not in visited:
                if dfs(t, []):
                    return True, cycle_nodes

        return False, []

    @staticmethod
    def select_victim(
        cycle_tasks: List[str],
        schedule_requests: Dict[str, ScheduleRequest]
    ) -> Optional[str]:
        """Chooses the safest victim to preempt or defer.
        
        Selection criteria:
        1. Must not be NON_PREEMPTIBLE.
        2. Lowest priority score.
        3. Lowest progress / newest age.
        """
        candidates = []
        for tid in cycle_tasks:
            req = schedule_requests.get(tid)
            if not req:
                candidates.append((0.0, False, tid))
                continue

            # Invariant 17: Never forcibly kill non-preemptible operations
            is_preemptible = req.preemption_policy != PreemptionPolicy.NON_PREEMPTIBLE
            candidates.append((req.priority_score, is_preemptible, tid))

        # Filter only preemptible candidates
        valid_candidates = [c for c in candidates if c[1]]
        if not valid_candidates:
            logger.critical("DEADLOCK_UNRESOLVABLE: All tasks in cycle are NON_PREEMPTIBLE!")
            return None

        # Sort by priority_score ascending (lowest priority victim chosen)
        valid_candidates.sort(key=lambda x: x[0])
        victim = valid_candidates[0][2]
        logger.warning(f"Deadlock victim selected: '{victim}' (Score={valid_candidates[0][0]})")
        return victim

deadlock_detector = DeadlockDetector()
