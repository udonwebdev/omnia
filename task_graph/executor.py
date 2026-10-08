import asyncio
import time
import logging
from typing import Optional, Dict, Any, List

from task_graph.models import (
    TaskGraph,
    TaskNode,
    TaskState,
    NodeState,
    ExecutionContext,
    Observation,
    ObservationSource,
    FailureCategory,
    RecoveryStrategy
)
from task_graph.resources import resource_manager
from task_graph.recovery import recovery_engine
from audit_logger import audit_logger

logger = logging.getLogger("Omnia.TaskGraph.Executor")

BUS_STATE_URL = "http://127.0.0.1:8000/api/state"

class TaskExecutionEngine:
    """Orchestrates dynamic task graphs with observation-verification loops and self-healing."""

    def __init__(self, max_active_tasks: int = 5):
        self.active_tasks: Dict[str, TaskGraph] = {}
        self.contexts: Dict[str, ExecutionContext] = {}
        self.cancel_flags: Dict[str, bool] = {}
        self.pause_flags: Dict[str, bool] = {}
        self.max_active_tasks = max_active_tasks

    async def _notify_hud(self, state: str, message: str):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=0.5) as client:
                await client.post(BUS_STATE_URL, json={"state": state, "message": message})
        except Exception:
            pass

    async def execute_task(self, graph: TaskGraph) -> Dict[str, Any]:
        """Main lifecycle loop executing a dynamic TaskGraph until completion, abort, or timeout."""
        if len(self.active_tasks) >= self.max_active_tasks:
            raise RuntimeError(f"CONCURRENCY_LIMIT: Maximum active tasks ({self.max_active_tasks}) reached.")

        self.active_tasks[graph.task_id] = graph
        self.cancel_flags[graph.task_id] = False
        self.pause_flags[graph.task_id] = False

        context = ExecutionContext(task_id=graph.task_id)
        self.contexts[graph.task_id] = context

        graph.state = TaskState.RUNNING
        graph.deadline_ts = time.time() + graph.task_timeout_sec
        graph.log_event("TASK_STARTED", {"goal": graph.goal, "total_nodes": len(graph.nodes)})
        await self._notify_hud("TASK_RUNNING", f"Task {graph.task_id[:6]}: {graph.goal[:30]}")

        # Loop detection tracker: (node_id, failure_count)
        consecutive_node_failures: Dict[str, int] = {}

        try:
            while not graph.is_complete():
                # 1. Check Cancellation & Timeouts
                if self.cancel_flags.get(graph.task_id, False):
                    graph.state = TaskState.CANCELLED
                    graph.log_event("TASK_CANCELLED", {})
                    await self._notify_hud("TASK_CANCELLED", f"Task {graph.task_id[:6]} cancelled.")
                    break

                if time.time() > graph.deadline_ts:
                    graph.state = TaskState.TIMED_OUT
                    graph.log_event("TASK_TIMED_OUT", {"deadline": graph.deadline_ts})
                    await self._notify_hud("TASK_TIMED_OUT", f"Task {graph.task_id[:6]} reached deadline.")
                    break

                # 2. Check Paused State
                while self.pause_flags.get(graph.task_id, False):
                    graph.state = TaskState.PAUSED
                    await asyncio.sleep(0.5)
                    if self.cancel_flags.get(graph.task_id, False):
                        break
                if graph.state == TaskState.PAUSED:
                    graph.state = TaskState.RUNNING

                # 3. Find Ready Nodes
                ready_nodes = graph.get_ready_nodes()
                if not ready_nodes:
                    if graph.has_unrecoverable_failure():
                        graph.state = TaskState.FAILED
                    else:
                        # Deadlock / unscheduled nodes remaining
                        graph.state = TaskState.FAILED
                        graph.log_event("DEADLOCK_DETECTED", {"nodes": [n.node_id for n in graph.nodes.values()]})
                    break

                # Pick the first ready node
                node = ready_nodes[0]
                graph.current_node_id = node.node_id
                
                # Check for infinite failure loop on this node (> 4 consecutive failures)
                if consecutive_node_failures.get(node.node_id, 0) >= 4:
                    logger.error(f"LOOP_DETECTED: Node '{node.name}' failed repeatedly with no progress.")
                    graph.state = TaskState.FAILED
                    graph.log_event("LOOP_DETECTED", {"node_id": node.node_id, "failures": consecutive_node_failures[node.node_id]})
                    break

                # 4. Acquire Resource Locks
                acquired = await resource_manager.acquire_locks(graph.task_id, node.required_resources, timeout_sec=5.0)
                if not acquired:
                    logger.warning(f"Resource contention: Waiting for resources {node.required_resources}")
                    await asyncio.sleep(1.0)
                    continue

                try:
                    success = await self._execute_node_with_retry(node, graph, context)
                    if success:
                        consecutive_node_failures[node.node_id] = 0
                    else:
                        consecutive_node_failures[node.node_id] = consecutive_node_failures.get(node.node_id, 0) + 1
                        # If node failed and is not retryable, check if replan can salvage
                        if graph.replan_count < graph.max_replans and node.metadata.get("allow_replan", True):
                            logger.info(f"Triggering dynamic replan (attempt {graph.replan_count + 1}/{graph.max_replans})...")
                            replan_ok = await self._replan_node(node, graph, context)
                            if replan_ok:
                                graph.replan_count += 1
                                continue
                        graph.state = TaskState.FAILED
                        break
                finally:
                    await resource_manager.release_locks(graph.task_id, node.required_resources)

            if graph.is_complete() and graph.state not in [TaskState.CANCELLED, TaskState.TIMED_OUT, TaskState.FAILED]:
                graph.state = TaskState.COMPLETED
                graph.log_event("TASK_COMPLETED", {"progress": 100.0})
                await self._notify_hud("TASK_COMPLETED", f"Task {graph.task_id[:6]} finished successfully.")

        finally:
            # Release all remaining resource locks
            await resource_manager.release_locks(graph.task_id)
            if graph.task_id in self.active_tasks:
                del self.active_tasks[graph.task_id]

        total_nodes = len(graph.nodes)
        completed_nodes = sum(1 for n in graph.nodes.values() if n.state == NodeState.COMPLETED)
        progress_pct = (completed_nodes / total_nodes * 100.0) if total_nodes > 0 else 0.0

        return {
            "task_id": graph.task_id,
            "goal": graph.goal,
            "state": graph.state.value,
            "progress_percentage": round(progress_pct, 1),
            "completed_nodes": completed_nodes,
            "total_nodes": total_nodes,
            "replans": graph.replan_count,
            "history_count": len(graph.history)
        }

    async def _execute_node_with_retry(self, node: TaskNode, graph: TaskGraph, context: ExecutionContext) -> bool:
        """Executes a single node following the Plan -> Act -> Observe -> Verify loop with retries."""
        node.state = NodeState.RUNNING
        policy = node.retry_policy

        while node.attempts < policy.max_attempts:
            node.attempts += 1
            graph.log_event("NODE_ATTEMPT_STARTED", {"node_id": node.node_id, "attempt": node.attempts})

            try:
                # ACT with node timeout
                logger.info(f"Executing node '{node.name}' (Attempt {node.attempts}/{policy.max_attempts})...")
                result = await asyncio.wait_for(node.action(context), timeout=node.timeout_sec)
                node.result = result
                context.tool_results[node.node_id] = result

                # OBSERVE & VERIFY
                node.state = NodeState.VERIFYING
                if node.verifier:
                    verified = await node.verifier(context, result)
                    if not verified:
                        raise RuntimeError(f"VERIFICATION_FAILED: Expected state '{node.expected_state}' not satisfied.")
                
                # Success confirmed!
                node.state = NodeState.COMPLETED
                graph.log_event("NODE_COMPLETED", {"node_id": node.node_id, "attempts": node.attempts})
                return True

            except Exception as ex:
                failure = recovery_engine.classify_exception(ex, node)
                node.error = failure
                context.failures.append(failure)
                graph.log_event("NODE_FAILED", {"node_id": node.node_id, "category": failure.category.value, "msg": failure.message})

                # Check if retry is appropriate
                if node.attempts < policy.max_attempts and failure.retryable:
                    node.state = NodeState.RECOVERING
                    recovered = await recovery_engine.execute_recovery(failure.suggested_recovery, node, context)
                    if recovered:
                        continue
                
                # Unrecoverable or retries exhausted
                node.state = NodeState.FAILED
                return False

        node.state = NodeState.FAILED
        return False

    async def _replan_node(self, failed_node: TaskNode, graph: TaskGraph, context: ExecutionContext) -> bool:
        """Dynamic replanner: if vision/browser action fails, introduces alternative fallback node."""
        logger.info(f"Replanning graph for failed node: {failed_node.name}")
        graph.log_event("REPLAN_INITIATED", {"failed_node": failed_node.node_id, "category": failed_node.error.category.value if failed_node.error else ""})

        # Example: If Playwright DOM click failed, replace with Module 13 Visual Grounding Click
        if "click" in failed_node.name.lower() or "button" in failed_node.name.lower():
            alt_node_id = f"visual_{failed_node.node_id}"
            target_desc = failed_node.metadata.get("target_label", failed_node.name)
            
            async def fallback_visual_action(ctx: ExecutionContext):
                from vision import vision_engine, VisionSource
                res = await vision_engine.observe_act_verify(
                    target_description=target_desc,
                    expected_change=failed_node.expected_state or "Page transition",
                    source=VisionSource.BROWSER
                )
                if not res.get("success"):
                    raise RuntimeError(f"Visual fallback failed: {res.get('reason')}")
                return res

            alt_node = TaskNode(
                node_id=alt_node_id,
                name=f"Fallback Visual Interaction: {target_desc}",
                description="Visual grounding fallback generated by replanner",
                action=fallback_visual_action,
                expected_state=failed_node.expected_state,
                dependencies=failed_node.dependencies,
                required_resources=failed_node.required_resources,
                metadata={"allow_replan": False}
            )
            alt_node.retry_policy.max_attempts = 1

            # Insert replacement node and redirect downstream dependencies
            graph.add_node(alt_node)
            for other in graph.nodes.values():
                if failed_node.node_id in other.dependencies:
                    other.dependencies.remove(failed_node.node_id)
                    other.dependencies.append(alt_node_id)

            failed_node.state = NodeState.SKIPPED
            graph.log_event("REPLAN_SUCCESS", {"alt_node_id": alt_node_id})
            return True

        return False

    def pause_task(self, task_id: str):
        if task_id in self.pause_flags:
            self.pause_flags[task_id] = True
            if task_id in self.active_tasks:
                self.active_tasks[task_id].state = TaskState.PAUSED
                self.active_tasks[task_id].log_event("TASK_PAUSED", {})

    def resume_task(self, task_id: str):
        if task_id in self.pause_flags:
            self.pause_flags[task_id] = False
            if task_id in self.active_tasks:
                self.active_tasks[task_id].state = TaskState.RUNNING
                self.active_tasks[task_id].log_event("TASK_RESUMED", {})

    def cancel_task(self, task_id: str):
        if task_id in self.cancel_flags:
            self.cancel_flags[task_id] = True

task_executor = TaskExecutionEngine()
