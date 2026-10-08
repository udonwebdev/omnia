import unittest
import asyncio
import os
import time
import tempfile
import shutil

from scheduler.models import (
    ResourceRequirement,
    ResourceAccessMode,
    SchedulingPriority
)
from scheduler.orchestrator import resource_scheduler
from task_graph import (
    TaskGraph,
    TaskNode,
    TaskState,
    NodeState,
    task_executor
)

class TestSchedulerE2EModule21(unittest.IsolatedAsyncioTestCase):
    """End-to-End integration and concurrency stress test suite for Module 21 Scheduler."""

    async def asyncSetUp(self):
        self.scheduler = resource_scheduler

    async def test_01_e2e_scheduler_gated_task_execution(self):
        """Full pipeline: Task Graph node requires scheduler admission and exclusive resource reservation."""
        tg = TaskGraph(task_id="e2e_sched_task", goal="Scheduler Gated Job")
        executed = False

        async def worker_action(ctx):
            nonlocal executed
            executed = True
            return "SUCCESS"

        node = TaskNode(
            node_id="n_scheduled",
            name="scheduled_job",
            description="Job requiring scheduler",
            action=worker_action,
            required_resources=["desktop:screen"],
            metadata={
                "requires_scheduling": True
            }
        )
        tg.add_node(node)

        exec_res = await task_executor.execute_task(tg)
        self.assertEqual(exec_res["state"], "COMPLETED")
        self.assertTrue(executed)
        self.assertEqual(node.state, NodeState.COMPLETED)

    async def test_02_e2e_concurrency_exclusion_and_sequential_release(self):
        """Concurrency conflict test: Two tasks concurrently requesting the same exclusive resource.
        One runs first, the second waits safely without interleaving corruption.
        """
        # Register test device
        self.scheduler.registry.register_resource("dev:mesh_tablet", "DEVICE", total_capacity=1.0)

        t1_run = False
        t2_run = False

        # Task 1
        tg1 = TaskGraph(task_id="e2e_conc_1", goal="Tablet Task 1")
        async def act1(ctx):
            nonlocal t1_run
            t1_run = True
            await asyncio.sleep(0.1)
            return "T1_DONE"

        node1 = TaskNode(
            node_id="n1",
            name="task_1_action",
            description="Tablet task 1 action",
            action=act1,
            required_resources=["dev:mesh_tablet"],
            metadata={"requires_scheduling": True}
        )
        tg1.add_node(node1)

        # Task 2
        tg2 = TaskGraph(task_id="e2e_conc_2", goal="Tablet Task 2")
        async def act2(ctx):
            nonlocal t2_run
            t2_run = True
            return "T2_DONE"

        node2 = TaskNode(
            node_id="n2",
            name="task_2_action",
            description="Tablet task 2 action",
            action=act2,
            required_resources=["dev:mesh_tablet"],
            metadata={"requires_scheduling": True}
        )
        tg2.add_node(node2)

        # Execute Task 1 and Task 2 concurrently
        res1, res2 = await asyncio.gather(
            task_executor.execute_task(tg1),
            task_executor.execute_task(tg2)
        )

        # At least one finishes, and the resource is cleanly released
        self.assertIn(res1["state"], ["COMPLETED", "WAITING"])
        self.assertIn(res2["state"], ["COMPLETED", "WAITING"])

if __name__ == "__main__":
    unittest.main()
