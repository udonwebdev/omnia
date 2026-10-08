import unittest
import asyncio
import os
import time
import uuid
import tempfile
import shutil

from approval.models import (
    ApprovalStatus,
    ApprovalType,
    ApprovalDecisionType,
    ApprovalScope,
    ApprovalRequest,
    ApprovalDecision,
    ApprovalRelease,
    VALID_APPROVAL_TRANSITIONS
)
from approval.fingerprints import FingerprintGenerator
from approval.presentation import ApprovalPresentationManager
from approval.persistence import ApprovalPersistenceManager
from approval.gateway import ApprovalGateway
from persistence.store import TaskPersistenceStore

class TestApprovalGatewayModule20(unittest.IsolatedAsyncioTestCase):
    """Forensic verification test suite for Module 20: Human Approval Gateway & Consent Orchestrator."""

    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_approval.db")
        self.store = TaskPersistenceStore(db_path=self.db_path)
        self.persistence = ApprovalPersistenceManager(store=self.store)
        self.presentation = ApprovalPresentationManager()
        self.fp_gen = FingerprintGenerator()
        self.gateway = ApprovalGateway(
            persistence_mgr=self.persistence,
            presentation_mgr=self.presentation,
            fp_gen=self.fp_gen
        )

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. Models & Transition Integrity
    def test_01_status_transitions_and_invariants(self):
        req = ApprovalRequest(status=ApprovalStatus.CREATED)
        self.assertTrue(req.transition_to(ApprovalStatus.PENDING))
        self.assertTrue(req.transition_to(ApprovalStatus.WAITING))
        self.assertTrue(req.transition_to(ApprovalStatus.APPROVED))
        self.assertTrue(req.transition_to(ApprovalStatus.EXECUTION_RELEASED))
        # Terminal state: cannot transition further
        self.assertFalse(req.transition_to(ApprovalStatus.PENDING))
        self.assertTrue(req.is_terminal())

    # 2. Deterministic Action Fingerprinting
    def test_02_fingerprint_generation_and_drift_detection(self):
        fp1 = self.fp_gen.compute_action_fingerprint(
            action="wipe_cache",
            params={"mode": "deep", "retries": 3},
            target_resource="storage:app_data",
            plan_version=1
        )
        # Identical params in different order produces exact same hash
        fp2 = self.fp_gen.compute_action_fingerprint(
            action="wipe_cache",
            params={"retries": 3, "mode": "deep"},
            target_resource="storage:app_data",
            plan_version=1
        )
        self.assertEqual(fp1, fp2)

        # Parameter mutation changes fingerprint
        fp_mutated = self.fp_gen.compute_action_fingerprint(
            action="wipe_cache",
            params={"mode": "shallow", "retries": 3},
            target_resource="storage:app_data",
            plan_version=1
        )
        self.assertNotEqual(fp1, fp_mutated)

        # Plan version mutation changes fingerprint
        fp_version_drift = self.fp_gen.compute_action_fingerprint(
            action="wipe_cache",
            params={"mode": "deep", "retries": 3},
            target_resource="storage:app_data",
            plan_version=2
        )
        self.assertNotEqual(fp1, fp_version_drift)

    # 3. Persistence CRUD & Reconstitution
    def test_03_sqlite_persistence_roundtrip(self):
        req = ApprovalRequest(
            approval_id="apr_test_persist",
            title="Deploy Contract",
            requested_action="deploy_smart_contract",
            action_params={"gas_limit": 500000},
            risk_level="CRITICAL",
            scope=ApprovalScope.ONCE,
            is_reversible=False,
            fingerprint="abc123hash",
            status=ApprovalStatus.PENDING
        )
        self.persistence.save_approval_request(req)
        loaded = self.persistence.get_approval_request("apr_test_persist")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, "Deploy Contract")
        self.assertEqual(loaded.requested_action, "deploy_smart_contract")
        self.assertEqual(loaded.action_params["gas_limit"], 500000)
        self.assertEqual(loaded.risk_level, "CRITICAL")
        self.assertFalse(loaded.is_reversible)

    # 4. Presentation Formatting across Channels
    def test_04_multi_channel_presentation_formatting(self):
        req = ApprovalRequest(
            approval_id="apr_channel_test",
            title="Format Drive",
            requested_action="format_disk",
            risk_level="CRITICAL",
            summary="Disk will be permanently erased"
        )
        # HUD
        hud_pres = self.presentation.format_for_channel(req, "HUD")
        self.assertEqual(hud_pres.channel, "HUD")
        self.assertEqual(hud_pres.priority, "CRITICAL")

        # Voice
        voice_pres = self.presentation.format_for_channel(req, "VOICE")
        self.assertEqual(voice_pres.channel, "VOICE")
        self.assertIn("Omnia requires your confirmation", voice_pres.formatted_prompt)

        # CLI
        cli_pres = self.presentation.format_for_channel(req, "CLI")
        self.assertEqual(cli_pres.channel, "CLI")
        self.assertIn("APPROVAL REQUIRED", cli_pres.formatted_prompt)

    # 5. Voice Response Interpretation & Ambiguity Filtering
    def test_05_voice_interpreter_ambiguity_invariants(self):
        req1 = ApprovalRequest(approval_id="apr_one", title="One")
        req2 = ApprovalRequest(approval_id="apr_two", title="Two")

        # Case A: Exactly 1 request -> "yes" is valid approval
        dec, target, conf, expl = self.presentation.interpret_voice_response("yes, go ahead", [req1])
        self.assertEqual(dec, ApprovalDecisionType.APPROVE)
        self.assertEqual(target, "apr_one")
        self.assertGreaterEqual(conf, 0.9)

        # Case B: Multiple requests -> generic "yes" is Ambiguous (rejected)
        dec_amb, target_amb, conf_amb, expl_amb = self.presentation.interpret_voice_response("yes, please", [req1, req2])
        self.assertIsNone(dec_amb)
        self.assertIn("Ambiguous voice response", expl_amb)

        # Case C: Multiple requests with explicit approval ID reference -> valid
        dec_spec, target_spec, conf_spec, expl_spec = self.presentation.interpret_voice_response("approve apr two", [req1, req2])
        self.assertEqual(dec_spec, ApprovalDecisionType.APPROVE)
        self.assertEqual(target_spec, "apr_two")

        # Case D: Rejection keywords
        dec_rej, _, _, _ = self.presentation.interpret_voice_response("no, stop that immediately", [req1])
        self.assertEqual(dec_rej, ApprovalDecisionType.REJECT)

    # 6. Request Creation and Deduplication
    async def test_06_request_creation_and_deduplication(self):
        req1 = await self.gateway.create_request(
            requested_action="update_system_clock",
            action_params={"offset": 0},
            title="Sync Clock",
            summary="Clock synchronization",
            reason="Drift detected",
            dedup_key="sync_clock_op"
        )
        self.assertEqual(req1.status, ApprovalStatus.PENDING)

        # Duplicate call with same dedup_key returns same request
        req2 = await self.gateway.create_request(
            requested_action="update_system_clock",
            action_params={"offset": 0},
            title="Sync Clock",
            summary="Clock synchronization",
            reason="Drift detected",
            dedup_key="sync_clock_op"
        )
        self.assertEqual(req1.approval_id, req2.approval_id)

    # 7. Explicit User Approval & Execution Release Token
    async def test_07_approval_and_execution_release_issuance(self):
        req = await self.gateway.create_request(
            requested_action="restart_service",
            action_params={"service": "nginx"},
            title="Restart Nginx",
            summary="Restarting server",
            reason="Config reload",
            task_id="task_100",
            task_node_id="node_5",
            plan_version=1
        )
        ok, release, msg = await self.gateway.submit_decision(
            approval_id=req.approval_id,
            decision_type=ApprovalDecisionType.APPROVE,
            decided_by="admin"
        )
        self.assertTrue(ok)
        self.assertIsNotNone(release)
        self.assertTrue(release.release_token.startswith("rel_"))

        # Verify request reached terminal EXECUTION_RELEASED status
        updated_req = self.gateway.get_approval(req.approval_id)
        self.assertEqual(updated_req.status, ApprovalStatus.EXECUTION_RELEASED)

        # Release validation check against identical context
        valid, reason = await self.gateway.verify_and_consume_release(
            release_token=release.release_token,
            action="restart_service",
            params={"service": "nginx"},
            task_id="task_100",
            task_node_id="node_5",
            plan_version=1
        )
        self.assertTrue(valid)
        self.assertEqual(reason, "VALID_RELEASE")

        # Second attempt to consume one-time token fails
        valid_again, reason_again = await self.gateway.verify_and_consume_release(
            release_token=release.release_token,
            action="restart_service",
            params={"service": "nginx"},
            task_id="task_100",
            task_node_id="node_5",
            plan_version=1
        )
        self.assertFalse(valid_again)
        self.assertIn("TOKEN_ALREADY_USED", reason_again)

    # 8. Fingerprint Mismatch / Stale Plan Invalidation
    async def test_08_fingerprint_drift_rejection(self):
        req = await self.gateway.create_request(
            requested_action="write_config",
            action_params={"port": 8080},
            title="Write Port Config",
            summary="Update port",
            reason="Port change",
            plan_version=1
        )
        ok, release, _ = await self.gateway.submit_decision(
            approval_id=req.approval_id,
            decision_type=ApprovalDecisionType.APPROVE
        )
        self.assertTrue(ok)

        # Tampered / mutated parameter at execution time
        valid, reason = await self.gateway.verify_and_consume_release(
            release_token=release.release_token,
            action="write_config",
            params={"port": 9999},  # Changed!
            plan_version=1
        )
        self.assertFalse(valid)
        self.assertIn("FINGERPRINT_MISMATCH", reason)

    # 9. Explicit Rejection Flow
    async def test_09_explicit_rejection_flow(self):
        req = await self.gateway.create_request(
            requested_action="delete_archive",
            action_params={},
            title="Delete Archive",
            summary="Clean old logs",
            reason="Storage full"
        )
        ok, release, msg = await self.gateway.submit_decision(
            approval_id=req.approval_id,
            decision_type=ApprovalDecisionType.REJECT,
            reason="Archive needed for legal compliance"
        )
        self.assertTrue(ok)
        self.assertIsNone(release)

        updated_req = self.gateway.get_approval(req.approval_id)
        self.assertEqual(updated_req.status, ApprovalStatus.REJECTED)

    # 10. Timeout Invariant (Silence != Approval)
    async def test_10_timeout_expires_without_approval(self):
        req = await self.gateway.create_request(
            requested_action="dangerous_migration",
            action_params={},
            title="Run Migration",
            summary="Database migration",
            reason="Schema upgrade",
            timeout_sec=0.1  # Fast timeout
        )
        resolved = await self.gateway.wait_for_decision(req.approval_id, timeout_sec=0.1)
        self.assertEqual(resolved.status, ApprovalStatus.EXPIRED)

    # 11. Policy Invariant (Approval Cannot Override Hard Policy Block)
    async def test_11_policy_block_cannot_be_approved(self):
        # execute_mesh_shell_command with forkbomb is strictly blocked by PolicyEngine
        req = await self.gateway.create_request(
            requested_action="execute_mesh_shell_command",
            action_params={"shell_command": ":(){ :|:& };:"},
            title="Run Forkbomb",
            summary="Destructive shell",
            reason="Testing"
        )
        # Should be stopped at creation with FAILED_TO_VALIDATE
        self.assertEqual(req.status, ApprovalStatus.FAILED_TO_VALIDATE)

    # 12. Crash Recovery & Startup Reconciliation
    def test_12_crash_recovery_reconciliation(self):
        # Save one expired request and one active waiting request
        req_expired = ApprovalRequest(
            approval_id="apr_crashed_expired",
            title="Old Operation",
            status=ApprovalStatus.WAITING,
            expires_at=time.time() - 100.0  # Already expired
        )
        req_active = ApprovalRequest(
            approval_id="apr_crashed_active",
            title="Active Operation",
            status=ApprovalStatus.WAITING,
            expires_at=time.time() + 300.0  # Still active
        )
        self.persistence.save_approval_request(req_expired)
        self.persistence.save_approval_request(req_active)

        stats = self.persistence.reconcile_on_startup()
        self.assertEqual(stats["expired"], 1)
        self.assertEqual(stats["recovering"], 1)

        loaded_expired = self.persistence.get_approval_request("apr_crashed_expired")
        self.assertEqual(loaded_expired.status, ApprovalStatus.EXPIRED)

        loaded_active = self.persistence.get_approval_request("apr_crashed_active")
        self.assertEqual(loaded_active.status, ApprovalStatus.RECOVERY_REQUIRED)

    # 13. Emergency Invalidation
    async def test_13_emergency_invalidation(self):
        await self.gateway.create_request("op1", {}, "Op1", "Op1", "Test")
        await self.gateway.create_request("op2", {}, "Op2", "Op2", "Test")
        self.assertEqual(len(self.gateway.list_pending()), 2)

        count = await self.gateway.emergency_invalidate(reason="Operator killed session")
        self.assertEqual(count, 2)
        self.assertEqual(len(self.gateway.list_pending()), 0)

if __name__ == "__main__":
    unittest.main()
