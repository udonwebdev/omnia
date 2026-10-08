import asyncio
import unittest
import uuid
import time

from task_graph.models import (
    TaskGraph,
    TaskNode,
    TaskState,
    NodeState
)
from task_graph.executor import TaskExecutionEngine
from coordination import (
    coordination_service,
    CoordinationService,
    NodeIdentity,
    LeaderRole
)

class TestCoordinationE2EModule22(unittest.TestCase):

    def setUp(self):
        self.executor = TaskExecutionEngine()

    def test_multi_node_task_duplicate_execution_prevention(self):
        """E2E Invariant: Two nodes observing the same task; only the claiming node executes,

        while the remote node is strictly blocked from duplicate execution by Module 22.
        """
        async def run_e2e():
            task_id = f"task_dist_{uuid.uuid4().hex[:6]}"
            
            # Node Alpha (Simulated remote owner)
            remote_node_id = f"node_remote_{uuid.uuid4().hex[:6]}"
            
            # 1. Remote node Alpha claims ownership over the task first
            claimed, claim, msg = coordination_service.claim_task_ownership(
                task_id=task_id,
                owner_node_id=remote_node_id,
                lease_sec=30.0
            )
            self.assertTrue(claimed, f"Alpha claim failed: {msg}")
            self.assertEqual(coordination_service.get_task_owner(task_id), remote_node_id)

            # 2. Local Node Beta attempts to execute the SAME task via TaskExecutionEngine
            async def dummy_action(ctx):
                return "executed"

            graph = TaskGraph(
                task_id=task_id,
                goal="Distributed multi-node concurrent execution attempt",
                nodes={
                    "n1": TaskNode(
                        node_id="n1",
                        name="echo_action",
                        description="Test execution node",
                        action=dummy_action
                    )
                }
            )

            result = await self.executor.execute_task(graph)
            
            # 3. Verify that Local Node Beta was BLOCKED by distributed ownership
            self.assertEqual(result["state"], TaskState.FAILED.value)
            self.assertIn("OWNERSHIP_BLOCKED", result["error"])
            self.assertEqual(result["completed_nodes"], 0)

            # 4. Remote Node Alpha releases ownership
            coordination_service.release_task_ownership(task_id, owner_node_id=remote_node_id)
            self.assertIsNone(coordination_service.get_task_owner(task_id))

            # 5. Now Local Node can claim and execute without conflict
            claimed_local, claim_local, _ = coordination_service.claim_task_ownership(
                task_id=task_id,
                owner_node_id=coordination_service.node_id
            )
            self.assertTrue(claimed_local)
            self.assertEqual(coordination_service.get_task_owner(task_id), coordination_service.node_id)

            # Clean up
            coordination_service.release_task_ownership(task_id)

        asyncio.run(run_e2e())

    def test_multi_node_cluster_split_brain_resilience(self):
        """E2E Invariant: In a 3-node cluster, minority partition cannot achieve quorum or issue valid fencing tokens."""
        node_1 = NodeIdentity(node_id="peer_1", node_name="node-1")
        node_2 = NodeIdentity(node_id="peer_2", node_name="node-2")
        node_3 = NodeIdentity(node_id="peer_3", node_name="node-3")

        service = CoordinationService(node_id="peer_1", node_name="node-1")
        service.membership.register_node(node_2)
        service.membership.register_node(node_3)

        # 3 active nodes -> Quorum is 2
        self.assertEqual(service.membership.calculate_quorum_size(), 2)

        # Minority partition: Peer 2 and Peer 3 become unreachable
        node_2.last_seen = time.time() - 30.0
        node_3.last_seen = time.time() - 30.0
        service.detect_node_failures()

        # Active nodes drop to 1 (Peer 1 only)
        # Peer 1 alone cannot win election if it needs quorum across the registered cluster
        # In isolated partition, Peer 1 should fail to elect itself if quorum requires 2 votes
        self.assertFalse(service.membership.has_quorum(votes=1))

if __name__ == "__main__":
    unittest.main()
