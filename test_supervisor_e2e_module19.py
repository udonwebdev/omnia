import asyncio
import unittest
import time
import uuid
import os
import tempfile
from typing import Dict, Any, List

from supervisor.models import (
    Mission,
    MissionState,
    SupervisoryDecisionType,
    DecisionUrgency,
    MissionPhase
)
from supervisor.engine import AutonomousSupervisor
from supervisor.heartbeat import HeartbeatMonitor
from supervisor.resources import ResourceSupervisor
from supervisor.reconciliation import StateReconciler, StateConsistency
from events import (
    event_fabric,
    event_journal,
    EventFabric,
    EventJournal,
    Event,
    EventEnvelope,
    EventPriority,
    EventSeverity,
    EventDurability,
    EventFilter
)
from persistence.store import TaskPersistenceStore
from persistence.checkpoints import CheckpointManager
from persistence.models import PersistedTaskRecord, CheckpointPolicy
from task_graph.models import TaskGraph, TaskNode, TaskState, RetryPolicy
from task_graph.executor import TaskExecutionEngine


class TestSupervisorModule19E2E(unittest.IsolatedAsyncioTestCase):
    """End-to-End Failure-Injection, Self-Healing, and Crash-Recovery Test for Module 19."""

    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.store = TaskPersistenceStore(db_path=self.temp_db.name)
        self.journal = event_journal
        self.fabric = event_fabric
        self.hb_monitor = HeartbeatMonitor()
        self.res_supervisor = ResourceSupervisor()
        self.chk_mgr = CheckpointManager(store=self.store)
        self.reconciler = StateReconciler(store=self.store, chk_mgr=self.chk_mgr, journal=self.journal)

        self.supervisor = AutonomousSupervisor(
            fabric=self.fabric,
            hb_monitor=self.hb_monitor,
            res_supervisor=self.res_supervisor,
            reconciler=self.reconciler
        )
        await self.supervisor.start()

    async def asyncTearDown(self):
        await self.supervisor.stop()
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except Exception:
                pass

    async def test_section_48_failure_injection_and_supervisory_recovery(self):
        """Section 48: Controlled hardware fault event injection -> Supervisory RECOVER decision -> Task self-healing -> Completion."""
        mission_goal = "Supervised device audit with automated recovery"
        mission = await self.supervisor.create_mission(mission_goal)
        task_id = f"task_e2e_{uuid.uuid4().hex[:8]}"
        mission.active_task_id = task_id
        mission.task_ids.append(task_id)
        mission.transition_to(MissionState.RUNNING)

        # 1. Listen for supervisory decisions
        captured_decisions: List[SupervisoryDecisionType] = []

        # 2. Build multi-step executable task graph with transient failure
        execution_trace = {"primary_failed": False, "fallback_succeeded": False, "attempts": 0}

        async def action_with_controlled_fault(ctx):
            execution_trace["attempts"] += 1
            if execution_trace["attempts"] == 1:
                # Real controlled fault injection:
                # Emit device.disconnected into Event Fabric
                fault_evt = Event(
                    envelope=EventEnvelope(
                        event_type="device.disconnected",
                        task_id=task_id,
                        correlation_id=mission.mission_id,
                        priority=EventPriority.HIGH,
                        severity=EventSeverity.ERROR,
                        durability=EventDurability.DURABLE
                    ),
                    payload={"device_id": "phone_simulated_001", "reason": "HARDWARE_DISCONNECT"}
                )
                await self.fabric.publish(fault_evt)
                # Give supervisor event handler brief moment to assess
                await asyncio.sleep(0.05)
                execution_trace["primary_failed"] = True
                raise RuntimeError("Controlled hardware disconnect simulated")

            # Fallback path executes upon recovery/retry
            execution_trace["fallback_succeeded"] = True
            return {"status": "SUCCESS", "mode": "DESKTOP_FALLBACK"}

        node = TaskNode(
            node_id="supervised_step_1",
            name="Supervised Capture Action",
            description="Executes action with automated supervisory monitoring",
            action=action_with_controlled_fault,
            retry_policy=RetryPolicy(max_attempts=2, base_delay_sec=0.01)
        )

        tg = TaskGraph(task_id=task_id, goal=mission_goal)
        tg.add_node(node)

        # 3. Execute via TaskExecutionEngine
        executor = TaskExecutionEngine()
        result = await executor.execute_task(tg)

        # 4. Verify task finished successfully via self-healing
        self.assertEqual(result["state"], TaskState.COMPLETED.value)
        self.assertTrue(execution_trace["primary_failed"])
        self.assertTrue(execution_trace["fallback_succeeded"])

        # 5. Verify Supervisor observed the fault and generated evidence-backed RECOVER decision
        decisions = self.supervisor.decisions_history.get(mission.mission_id, [])
        self.assertTrue(len(decisions) >= 1)
        recover_decision = next((d for d in decisions if d.decision == SupervisoryDecisionType.RECOVER), None)
        self.assertIsNotNone(recover_decision, "Supervisor must produce RECOVER decision upon fault")
        self.assertIn("phone_simulated_001", str(recover_decision.evidence))

        # 6. Verify Mission state and progress
        await asyncio.sleep(0.1)
        self.assertEqual(mission.status, MissionState.COMPLETED)
        self.assertEqual(mission.progress, 100.0)

    async def test_section_49_crash_recovery_reconciliation(self):
        """Section 49: Crashed process does NOT blindly resume as RUNNING; reconciles as RECOVERING."""
        crashed_task_id = f"task_crashed_{uuid.uuid4().hex[:8]}"
        
        # 1. Simulate persisted task that died mid-execution
        self.store.save_task(PersistedTaskRecord(
            task_id=crashed_task_id,
            goal="Long-running data migration",
            status="RUNNING",
            current_node_id="node_step_4",
            created_at=time.time() - 200,
            started_at=time.time() - 190,
            updated_at=time.time() - 100,
            completed_at=None,
            deadline_ts=time.time() + 3600,
            task_timeout_sec=3600
        ))

        # Save valid checkpoint before crash
        chk = self.chk_mgr.create_checkpoint(
            task_id=crashed_task_id,
            node_id="node_step_3",
            task_state="RUNNING",
            node_states={"node_step_1": "COMPLETED", "node_step_2": "COMPLETED", "node_step_3": "COMPLETED"},
            variables={"cursor_offset": 5420},
            resource_state=[],
            last_verified_observations=[],
            policy_trigger=CheckpointPolicy.CHECKPOINT_NODE_COMPLETE
        )

        # 2. Simulate fresh start after process kill
        crashed_mission = Mission(
            mission_id=f"msn_crashed_{uuid.uuid4().hex[:8]}",
            objective="Long-running data migration",
            status=MissionState.RUNNING,
            active_task_id=crashed_task_id,
            task_ids=[crashed_task_id]
        )

        # Reconcile on startup
        reconciled_state = self.reconciler.reconcile_mission_on_startup(crashed_mission)

        # Must NOT assume RUNNING! Must transition to RECOVERING to revalidate reality
        self.assertNotEqual(reconciled_state, MissionState.RUNNING)
        self.assertEqual(reconciled_state, MissionState.RECOVERING)


if __name__ == "__main__":
    unittest.main()
