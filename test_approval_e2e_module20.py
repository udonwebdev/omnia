import unittest
import asyncio
import os
import time
import tempfile
import shutil

from approval.models import (
    ApprovalStatus,
    ApprovalType,
    ApprovalDecisionType,
    ApprovalScope
)
from approval.gateway import ApprovalGateway
from approval.persistence import ApprovalPersistenceManager
from persistence.store import TaskPersistenceStore
from task_graph import (
    TaskGraph,
    TaskNode,
    TaskState,
    NodeState,
    task_executor
)
from omnia_tools import (
    request_human_approval,
    submit_human_approval_decision,
    list_pending_human_approvals,
    get_approval_details
)
from approval import approval_gateway

class TestApprovalE2EModule20(unittest.IsolatedAsyncioTestCase):
    """End-to-End integration test suite for Module 20: Human Approval Gateway."""

    async def asyncSetUp(self):
        self.gateway = approval_gateway

    async def asyncTearDown(self):
        pass

    async def test_01_end_to_end_approval_gated_task_execution(self):
        """Verifies full execution pipeline where a node requires human approval release."""
        # 1. Create approval request
        action_name = "clean_temporary_storage"
        action_params = {"days_old": 30}
        req = await self.gateway.create_request(
            requested_action=action_name,
            action_params=action_params,
            title="Clean Temp Storage",
            summary="Clean older files",
            reason="Disk maintenance",
            risk_level="HIGH",
            task_id="e2e_task_1",
            task_node_id="n_clean",
            plan_version=1
        )
        self.assertEqual(req.status, ApprovalStatus.PENDING)

        # 2. User approves and gets release token
        ok, release, msg = await self.gateway.submit_decision(
            approval_id=req.approval_id,
            decision_type=ApprovalDecisionType.APPROVE,
            decided_by="operator"
        )
        self.assertTrue(ok)
        self.assertIsNotNone(release)

        # 3. Build Task Graph with node protected by approval token
        tg = TaskGraph(task_id="e2e_task_1", goal="Storage Cleanup")
        executed = False

        async def cleanup_action(ctx):
            nonlocal executed
            executed = True
            return "CLEANUP_SUCCESS"

        async def verify_cleanup(ctx, res):
            return res == "CLEANUP_SUCCESS"

        node = TaskNode(
            node_id="n_clean",
            name="clean_temporary_storage",
            description="Clean temp directory",
            action=cleanup_action,
            verifier=verify_cleanup,
            metadata={
                "requires_approval": True,
                "approval_release_token": release.release_token,
                "action_name": action_name,
                "action_params": action_params,
                "plan_version": 1
            }
        )
        tg.add_node(node)

        # 4. Execute Task Graph through Task Executor
        exec_res = await task_executor.execute_task(tg)
        self.assertEqual(exec_res["state"], "COMPLETED")
        self.assertTrue(executed)
        self.assertEqual(node.state, NodeState.COMPLETED)

    async def test_02_e2e_failure_injection_unapproved_node_blocks_task(self):
        """Failure injection: A task node requiring approval without a valid release token blocks task execution."""
        tg = TaskGraph(task_id="e2e_task_blocked", goal="Sensitive Action")
        node_executed = False

        async def sensitive_action(ctx):
            nonlocal node_executed
            node_executed = True
            return "EXECUTED"

        node = TaskNode(
            node_id="n_sensitive",
            name="wipe_credentials",
            description="Delete saved credentials",
            action=sensitive_action,
            metadata={
                "requires_approval": True
                # Missing approval_release_token!
            }
        )
        tg.add_node(node)

        exec_res = await task_executor.execute_task(tg)
        # Execution loop stops in WAITING state waiting for approval
        self.assertEqual(exec_res["state"], "WAITING")
        self.assertFalse(node_executed)

if __name__ == "__main__":
    unittest.main()
