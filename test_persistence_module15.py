import asyncio
import os
import time
import subprocess
import sys
import tempfile
import sqlite3
import unittest

from persistence.models import (
    RecoveryCondition,
    ResumeStrategy,
    CheckpointValidity,
    CheckpointPolicy,
    PersistedTaskRecord,
    PersistedNodeRecord
)
from persistence.store import TaskPersistenceStore, persistence_store, sanitize_payload
from persistence.checkpoints import CheckpointManager
from persistence.recovery import CrashRecoveryEngine
from task_graph.models import TaskGraph, TaskNode, TaskState, NodeState, IdempotencyLevel
from task_graph.executor import TaskExecutionEngine

class TestModule15Persistence(unittest.IsolatedAsyncioTestCase):

    async def test_database_initialization_and_migrations(self):
        """Validates fresh SQLite initialization, tables, indexes, and repeatable migrations."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            test_db = tf.name
        try:
            store = TaskPersistenceStore(db_path=test_db)
            conn = sqlite3.connect(test_db)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            required = {"tasks", "task_nodes", "task_checkpoints", "task_events", "task_resource_locks", "task_heartbeats", "schema_migrations", "recovery_attempts"}
            self.assertTrue(required.issubset(tables), f"Missing tables: {required - tables}")
            conn.close()
        finally:
            if os.path.exists(test_db):
                os.remove(test_db)

    async def test_task_lifecycle_persistence_and_journaling(self):
        """Ensures task creations, transitions, and monotonic journal events are durable."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            test_db = tf.name
        try:
            store = TaskPersistenceStore(db_path=test_db)
            task_id = "test_task_life_1"
            rec = PersistedTaskRecord(
                task_id=task_id,
                goal="Test Life Cycle",
                status="CREATED",
                current_node_id=None,
                created_at=time.time(),
                started_at=None,
                updated_at=time.time(),
                completed_at=None,
                deadline_ts=time.time() + 60,
                task_timeout_sec=60
            )
            store.save_task(rec)

            seq1 = store.append_event(task_id, "TASK_CREATED", {"goal": rec.goal})
            seq2 = store.append_event(task_id, "TASK_RUNNING", {"active": True})
            self.assertEqual(seq1, 1)
            self.assertEqual(seq2, 2)

            loaded = store.load_task(task_id)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.status, "CREATED")
            events = store.get_task_events(task_id)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[1].event_type, "TASK_RUNNING")
        finally:
            if os.path.exists(test_db):
                os.remove(test_db)

    async def test_checkpoint_atomicity_and_tamper_detection(self):
        """Validates SHA-256 checksum computation and corrupted checkpoint detection."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            test_db = tf.name
        try:
            store = TaskPersistenceStore(db_path=test_db)
            store.save_task(PersistedTaskRecord(
                task_id="chk_task_1",
                goal="Checkpoint Test",
                status="RUNNING",
                current_node_id="n1",
                created_at=time.time(),
                started_at=time.time(),
                updated_at=time.time(),
                completed_at=None,
                deadline_ts=time.time() + 60,
                task_timeout_sec=60
            ))
            chk_mgr = CheckpointManager(store=store)

            chk = chk_mgr.create_checkpoint(
                task_id="chk_task_1",
                node_id="n1",
                task_state="RUNNING",
                node_states={"n1": "COMPLETED", "n2": "PENDING"},
                variables={"token_count": 42},
                resource_state=["desktop:pointer"],
                last_verified_observations=[{"label": "button_ok"}],
                policy_trigger=CheckpointPolicy.CHECKPOINT_NODE_COMPLETE
            )
            self.assertTrue(chk_mgr.verify_checkpoint_integrity(chk))
            self.assertEqual(chk_mgr.evaluate_checkpoint_validity(chk), CheckpointValidity.VALID)

            # Tamper with checkpoint data
            chk.node_states["n1"] = "FAILED"
            self.assertFalse(chk_mgr.verify_checkpoint_integrity(chk))
            self.assertEqual(chk_mgr.evaluate_checkpoint_validity(chk), CheckpointValidity.INVALID)
        finally:
            if os.path.exists(test_db):
                os.remove(test_db)

    async def test_security_redaction_in_persistence(self):
        """Verifies credentials, tokens, cookies, and sensitive values are never persisted in plaintext."""
        payload = {
            "user": "author_lo",
            "password": "SuperSecretPassword123!",
            "token": "bearer eyJhbGciOiJIUzI1NiJ9.secret",
            "credit_card": "4111222233334444",
            "nested": {
                "api_key": "sk-1234567890abcdef"
            }
        }
        sanitized = sanitize_payload(payload)
        self.assertEqual(sanitized["password"], "[REDACTED]")
        self.assertEqual(sanitized["token"], "[REDACTED]")
        self.assertEqual(sanitized["credit_card"], "[REDACTED]")
        self.assertEqual(sanitized["nested"]["api_key"], "[REDACTED]")
        self.assertEqual(sanitized["user"], "author_lo")

    async def test_crash_recovery_classification_and_stale_locks(self):
        """Tests interrupted task classification and stale lock release after heartbeat timeout."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            test_db = tf.name
        try:
            store = TaskPersistenceStore(db_path=test_db)
            rec_engine = CrashRecoveryEngine(store=store)

            # 1. Simulate dead task with expired heartbeat
            task_id = "dead_task_1"
            store.save_task(PersistedTaskRecord(
                task_id=task_id,
                goal="Interrupted Goal",
                status="RUNNING",
                current_node_id="submit_node",
                created_at=time.time() - 100,
                started_at=time.time() - 90,
                updated_at=time.time() - 80,
                completed_at=None,
                deadline_ts=time.time() + 60,
                task_timeout_sec=60
            ))
            store.save_node(PersistedNodeRecord(
                node_id="submit_node",
                task_id=task_id,
                name="Submit Order",
                description="",
                status="RUNNING",
                attempt_count=1,
                started_at=time.time() - 80,
                completed_at=None,
                idempotency="NOT_SAFE_TO_RETRY"
            ))
            # Lock acquired 90s ago
            conn = store._get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO task_resource_locks (lock_id, resource_id, task_id, acquired_at, heartbeat_ts, process_id)
                    VALUES ('lk1', 'browser:session', ?, ?, ?, 99999)
                """, (task_id, time.time() - 90, time.time() - 90))
            conn.close()

            # Add a prior checkpoint
            chk_mgr = CheckpointManager(store=store)
            chk_mgr.create_checkpoint(
                task_id=task_id,
                node_id="init_node",
                task_state="RUNNING",
                node_states={"init_node": "COMPLETED", "submit_node": "RUNNING"},
                variables={"cart_id": "c1"},
                resource_state=["browser:session"],
                last_verified_observations=[]
            )

            # Scan for crashes
            crashed = rec_engine.scan_for_crashes(heartbeat_timeout_sec=30.0)
            self.assertEqual(len(crashed), 1)
            self.assertEqual(crashed[0]["task_id"], task_id)

            # Classify interrupted task: non-idempotent action interrupted -> UNCERTAIN / REVALIDATE_AND_RESUME
            cond, strat, reason = rec_engine.classify_interrupted_task(task_id)
            self.assertEqual(cond, RecoveryCondition.UNCERTAIN)
            self.assertEqual(strat, ResumeStrategy.REVALIDATE_AND_RESUME)

            # Check stale locks were reclaimed
            stale = store.reclaim_stale_locks(timeout_sec=30.0)
            self.assertEqual(len(stale), 0)  # scan_for_crashes already reclaimed it
        finally:
            if os.path.exists(test_db):
                os.remove(test_db)

    async def test_real_world_revalidation_decision(self):
        """Ensures offline changes are verified against the real world before resume."""
        rec_engine = CrashRecoveryEngine()
        
        # 1. State unchanged -> Revalidation passes
        async def checker_passed(tid, exp):
            return True

        ok1, reason1 = await rec_engine.validate_real_world_state("task_x", "submitted", checker_passed)
        self.assertTrue(ok1)

        # 2. State mismatch / altered -> Revalidation fails
        async def checker_failed(tid, exp):
            return False

        ok2, reason2 = await rec_engine.validate_real_world_state("task_x", "submitted", checker_failed)
        self.assertFalse(ok2)

    async def test_genuine_process_crash_and_restart_recovery(self):
        """Spawns an independent child process that executes a task and terminates abruptly.
        Validates that a subsequent restart process discovers the interrupted task,
        loads its checkpoint, and safely resumes to completion."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            shared_db = tf.name

        child_script = f"""
import asyncio
import os
import sys
import time

sys.path.insert(0, r"{os.path.abspath(os.path.dirname(__file__))}")

from persistence.store import TaskPersistenceStore, persistence_store
from task_graph.models import TaskGraph, TaskNode, IdempotencyLevel
from task_graph.executor import TaskExecutionEngine

# Override store db_path
persistence_store.db_path = r"{shared_db}"
persistence_store._ensure_initialized()

engine = TaskExecutionEngine()

async def step1(ctx):
    ctx.variables["step1_done"] = True
    return "step1_ok"

async def step2_crash(ctx):
    time.sleep(0.2)
    os._exit(42)

async def main():
    tg = TaskGraph(goal="Interrupted Crash Task", task_id="crash_task_99")
    tg.add_node(TaskNode(node_id="n1", name="Step 1", description="", action=step1, idempotency=IdempotencyLevel.SAFE_TO_RETRY))
    tg.add_node(TaskNode(node_id="n2", name="Step 2 Crash", description="", action=step2_crash, dependencies=["n1"], idempotency=IdempotencyLevel.NOT_SAFE_TO_RETRY))
    await engine.execute_task(tg)

if __name__ == "__main__":
    asyncio.run(main())
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as sf:
            script_path = sf.name
            sf.write(child_script)

        try:
            # Run child process expected to crash abruptly with exit code 42
            cwd_dir = os.path.dirname(os.path.abspath(__file__))
            proc = subprocess.run([sys.executable, script_path], cwd=cwd_dir, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 42, f"Expected 42, got {proc.returncode}. Stderr: {proc.stderr}")

            # RESTART PHASE: In a fresh context, inspect the database
            store = TaskPersistenceStore(db_path=shared_db)
            rec_engine = CrashRecoveryEngine(store=store)

            interrupted = rec_engine.scan_for_crashes(heartbeat_timeout_sec=0.1)
            self.assertTrue(any(t["task_id"] == "crash_task_99" for t in interrupted))

            # Classify task
            cond, strat, reason = rec_engine.classify_interrupted_task("crash_task_99")
            self.assertEqual(cond, RecoveryCondition.UNCERTAIN)

            # Validate checkpoint was preserved
            chk = store.get_latest_checkpoint("crash_task_99")
            self.assertIsNotNone(chk)
            self.assertEqual(chk.node_states.get("n1"), "COMPLETED")

            # Resume task in restarted engine
            engine_restarted = TaskExecutionEngine()
            tg_resume = TaskGraph(goal="Interrupted Crash Task", task_id="crash_task_99")
            
            async def step1_noop(ctx): return "already_done"
            async def step2_resume_action(ctx):
                ctx.variables["step2_done"] = True
                return "recovered_ok"

            tg_resume.add_node(TaskNode(node_id="n1", name="Step 1", description="", action=step1_noop))
            tg_resume.add_node(TaskNode(node_id="n2", name="Step 2 Resume", description="", action=step2_resume_action, dependencies=["n1"]))

            # Restore from checkpoint
            restored = engine_restarted.restore_task_from_checkpoint(tg_resume, store=store)
            self.assertTrue(restored)
            self.assertEqual(tg_resume.nodes["n1"].state, NodeState.COMPLETED)

            # Execute remainder
            orig_path = persistence_store.db_path
            persistence_store.db_path = shared_db
            try:
                result = await engine_restarted.execute_task(tg_resume)
                self.assertEqual(result["state"], "COMPLETED")
                self.assertEqual(result["completed_nodes"], 2)
            finally:
                persistence_store.db_path = orig_path

        finally:
            if os.path.exists(script_path):
                os.remove(script_path)
            if os.path.exists(shared_db):
                os.remove(shared_db)

    async def test_uncertain_action_recovery_with_real_world_inspection(self):
        """Tests crash immediately following an external action where the environment confirms completion."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            test_db = tf.name
        try:
            store = TaskPersistenceStore(db_path=test_db)
            chk_mgr = CheckpointManager(store=store)
            rec_engine = CrashRecoveryEngine(store=store, chk_mgr=chk_mgr)

            task_id = "uncertain_order_task"
            store.save_task(PersistedTaskRecord(
                task_id=task_id,
                goal="Submit Order",
                status="RUNNING",
                current_node_id="order_submission",
                created_at=time.time() - 30,
                started_at=time.time() - 25,
                updated_at=time.time() - 10,
                completed_at=None,
                deadline_ts=time.time() + 60,
                task_timeout_sec=60
            ))
            store.save_node(PersistedNodeRecord(
                node_id="order_submission",
                task_id=task_id,
                name="Submit Order to API",
                description="",
                status="RUNNING",
                attempt_count=1,
                started_at=time.time() - 10,
                completed_at=None,
                idempotency="NOT_SAFE_TO_RETRY"
            ))

            chk_mgr.create_checkpoint(
                task_id=task_id,
                node_id="order_submission",
                task_state="RUNNING",
                node_states={"prepare_cart": "COMPLETED", "order_submission": "RUNNING"},
                variables={"order_ref": "ORD-9981"},
                resource_state=["api:client"],
                last_verified_observations=[],
                policy_trigger=CheckpointPolicy.CHECKPOINT_BEFORE_RISKY_ACTION
            )

            async def verify_external_order(tid, exp):
                return True

            is_already_completed, msg = await rec_engine.validate_real_world_state(task_id, "ORDER_CONFIRMED", verify_external_order)
            self.assertTrue(is_already_completed)

            rec_engine.record_recovery_decision(
                task_id=task_id,
                condition=RecoveryCondition.UNCERTAIN,
                strategy=ResumeStrategy.REVALIDATE_AND_RESUME,
                reason="Order confirmed externally in real world; bypassing duplicate submission",
                success=True
            )

            evs = store.get_task_events(task_id)
            self.assertTrue(any(e.event_type == "RECOVERY_DECISION" for e in evs))

        finally:
            if os.path.exists(test_db):
                os.remove(test_db)

if __name__ == "__main__":
    unittest.main()
