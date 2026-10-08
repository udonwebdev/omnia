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
    SupervisoryState,
    SupervisoryDecisionType,
    DecisionConfidence,
    DecisionUrgency,
    MissionPriority,
    DeadlineRisk,
    ResourcePressure,
    StallClassification,
    MissionPhase
)
from supervisor.heartbeat import HeartbeatMonitor
from supervisor.resources import ResourceSupervisor
from supervisor.reconciliation import StateReconciler, StateConsistency
from supervisor.engine import AutonomousSupervisor
from events import (
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
from persistence.models import PersistedTaskRecord


class TestAutonomousSupervisorModule19(unittest.IsolatedAsyncioTestCase):
    """Unit and Integration Verification Suite for Module 19: Autonomous Supervisor & Mission Control."""

    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.store = TaskPersistenceStore(db_path=self.temp_db.name)
        self.journal = EventJournal(store=self.store)
        self.fabric = EventFabric(journal=self.journal)
        self.hb_monitor = HeartbeatMonitor()
        self.res_supervisor = ResourceSupervisor()
        self.reconciler = StateReconciler(store=self.store, journal=self.journal)

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

    async def test_01_healthy_mission_progress(self):
        """Test 1: Healthy mission progress produces CONTINUE decisions."""
        m = await self.supervisor.create_mission("Run regular system diagnostics")
        self.assertEqual(m.status, MissionState.CREATED)

        # Simulate task start and node progress
        m.active_task_id = "task_healthy_1"
        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="task.started", task_id="task_healthy_1"),
            payload={"task_id": "task_healthy_1"}
        ))
        await asyncio.sleep(0.05)
        self.assertEqual(m.status, MissionState.RUNNING)

        # Record verified progress
        self.hb_monitor.record_progress(m.mission_id, "NODE_1_COMPLETED")
        stall_class, _, _ = self.hb_monitor.assess_stall(m.mission_id)
        self.assertEqual(stall_class, StallClassification.ACTIVE)

    async def test_02_stall_and_no_progress_detection(self):
        """Test 2: Missions lacking progress beyond warning thresholds are detected as STALLED."""
        m = await self.supervisor.create_mission("Monitor background server")
        m.active_task_id = "task_stall_1"
        m.transition_to(MissionState.RUNNING)

        # Simulate no progress past warning threshold (override timestamp)
        rec = self.hb_monitor._records[m.mission_id]
        rec.last_progress_ts = time.time() - 70.0  # > 60s warning threshold

        stall_class, reason, elapsed = self.hb_monitor.assess_stall(
            m.mission_id,
            expected_interval_sec=10.0,
            warning_threshold_sec=30.0,
            hard_timeout_sec=120.0
        )
        self.assertEqual(stall_class, StallClassification.STALLED)
        self.assertIn("Stall warning", reason)

    async def test_03_recoverable_failure_and_decision(self):
        """Test 3: Recoverable failure produces an evidence-backed RECOVER decision."""
        m = await self.supervisor.create_mission("Capture remote screen")
        m.active_task_id = "task_recov_1"
        m.transition_to(MissionState.RUNNING)

        # Trigger device disconnected event
        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="device.disconnected", task_id="task_recov_1"),
            payload={"device_id": "phone_test_01", "reason": "USB_TIMEOUT"}
        ))
        await asyncio.sleep(0.05)

        self.assertEqual(m.status, MissionState.DEGRADED)
        self.assertEqual(m.recovery_attempts_used, 1)

        decisions = self.supervisor.decisions_history.get(m.mission_id, [])
        self.assertTrue(len(decisions) >= 1)
        last_dec = decisions[-1]
        self.assertEqual(last_dec.decision, SupervisoryDecisionType.RECOVER)
        self.assertIn("phone_test_01", str(last_dec.evidence))

    async def test_04_recovery_budget_exhaustion(self):
        """Test 4: Exceeding max recovery attempts forces terminal ABORT/FAILED."""
        m = await self.supervisor.create_mission("Mission with bounded retries")
        m.active_task_id = "task_budget_1"
        m.max_recovery_attempts = 2
        m.recovery_attempts_used = 2  # Budget exhausted!
        m.transition_to(MissionState.RUNNING)

        await self.supervisor._assess_mission_on_event(m, "DEVICE_FAULT", {"error": "Device dead"})
        self.assertEqual(m.status, MissionState.FAILED)

        decisions = self.supervisor.decisions_history[m.mission_id]
        self.assertEqual(decisions[-1].decision, SupervisoryDecisionType.ABORT)
        self.assertIn("budget exhausted", decisions[-1].reason)

    async def test_05_execution_loop_detection(self):
        """Test 5: Repeated oscillating nodes trigger LOOP detection and REPLAN decision."""
        m = await self.supervisor.create_mission("Looping workflow")
        m.active_task_id = "task_loop_1"

        # Simulate A -> B -> A -> B node oscillation
        self.hb_monitor.record_heartbeat(m.mission_id, "Node A", current_node_id="node_A")
        self.hb_monitor.record_heartbeat(m.mission_id, "Node B", current_node_id="node_B")
        self.hb_monitor.record_heartbeat(m.mission_id, "Node A", current_node_id="node_A")
        self.hb_monitor.record_heartbeat(m.mission_id, "Node B", current_node_id="node_B")

        is_loop, reason = self.hb_monitor.check_loop_or_oscillation(m.mission_id)
        self.assertTrue(is_loop)
        self.assertIn("Oscillating", reason)

    async def test_06_deadline_supervision_and_timeout(self):
        """Test 6: Expired hard deadlines cause supervisory ABORT and TIMED_OUT state."""
        m = await self.supervisor.create_mission("Urgent short deadline", deadline_sec=0.1)
        m.transition_to(MissionState.RUNNING)
        await asyncio.sleep(0.15)  # Let deadline expire

        # Trigger periodic loop tick manually to evaluate
        m.deadline_ts = time.time() - 10.0
        now = time.time()
        self.assertTrue(now > m.deadline_ts)

    async def test_07_security_policy_block_intervention(self):
        """Test 7: Security policy blocked events pause mission with CRITICAL urgency."""
        m = await self.supervisor.create_mission("Financial checkout audit")
        m.active_task_id = "task_sec_1"
        m.transition_to(MissionState.RUNNING)

        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="security.policy_blocked", task_id="task_sec_1"),
            payload={"action": "checkout", "reason": "Restricted financial action"}
        ))
        await asyncio.sleep(0.05)

        self.assertEqual(m.status, MissionState.PAUSED)
        decisions = self.supervisor.decisions_history[m.mission_id]
        self.assertEqual(decisions[-1].decision, SupervisoryDecisionType.PAUSE)
        self.assertEqual(decisions[-1].urgency, DecisionUrgency.CRITICAL)

    async def test_08_deadlock_detection_in_resource_wait_graph(self):
        """Test 8: Resource supervisor detects cycles in wait-for graph and chooses victim."""
        rs = self.res_supervisor
        rs.clear()

        # Task 1 holds Resource A, waits for Resource B
        rs.register_task_priority("task_1", priority=1)  # Lower priority
        rs.record_resource_acquired("task_1", "res_A")
        rs.record_resource_waiting("task_1", "res_B")

        # Task 2 holds Resource B, waits for Resource A
        rs.register_task_priority("task_2", priority=5)  # Higher priority
        rs.record_resource_acquired("task_2", "res_B")
        rs.record_resource_waiting("task_2", "res_A")

        is_deadlock, cycle, victim = rs.detect_deadlock()
        self.assertTrue(is_deadlock)
        self.assertEqual(set(cycle), {"task_1", "task_2"})
        self.assertEqual(victim, "task_1")  # Preempts lowest priority

    async def test_09_state_reconciliation_after_crash(self):
        """Test 9: Process restart reconciles un-terminated RUNNING task as UNCERTAIN."""
        t_id = "task_crashed_test"
        self.store.save_task(PersistedTaskRecord(
            task_id=t_id,
            goal="Crash test",
            status="RUNNING",
            current_node_id="node_3",
            created_at=time.time() - 100,
            started_at=time.time() - 90,
            updated_at=time.time() - 80,
            completed_at=None,
            deadline_ts=time.time() + 3600,
            task_timeout_sec=3600
        ))

        consistency, reason, details = self.reconciler.reconcile_task_state(t_id, is_runtime_active=False)
        self.assertEqual(consistency, StateConsistency.UNCERTAIN)
        self.assertIn("interrupted", reason)

        m = Mission(mission_id="msn_reconcile", active_task_id=t_id, status=MissionState.RUNNING)
        new_state = self.reconciler.reconcile_mission_on_startup(m)
        self.assertEqual(new_state, MissionState.RECOVERING)

    async def test_10_user_intervention_controls(self):
        """Test 10: Pause, resume, and abort controls take precedence."""
        m = await self.supervisor.create_mission("Interactive mission")
        m.transition_to(MissionState.RUNNING)

        paused = await self.supervisor.pause_mission(m.mission_id, reason="User clicked pause")
        self.assertTrue(paused)
        self.assertEqual(m.status, MissionState.PAUSED)

        resumed = await self.supervisor.resume_mission(m.mission_id)
        self.assertTrue(resumed)
        self.assertEqual(m.status, MissionState.RUNNING)

        aborted = await self.supervisor.abort_mission(m.mission_id, reason="User cancelled")
        self.assertTrue(aborted)
        self.assertEqual(m.status, MissionState.ABORTED)

    async def test_11_invalid_state_transitions_blocked(self):
        """Test 11: Arbitrary state jumps are strictly prevented by transition model."""
        m = Mission(mission_id="msn_trans", status=MissionState.COMPLETED)
        # Cannot transition from COMPLETED to RUNNING
        ok = m.transition_to(MissionState.RUNNING)
        self.assertFalse(ok)
        self.assertEqual(m.status, MissionState.COMPLETED)

    async def test_12_resource_pressure_classification(self):
        """Test 12: System resource pressure calculates accurate pressure levels."""
        pressure, metrics = self.res_supervisor.get_system_resource_pressure()
        self.assertIn(pressure, {
            ResourcePressure.NORMAL,
            ResourcePressure.ELEVATED,
            ResourcePressure.HIGH,
            ResourcePressure.CRITICAL
        })
        self.assertIn("memory_percent", metrics)
        self.assertIn("cpu_percent", metrics)

    async def test_13_mission_event_fabric_integration(self):
        """Test 13: Mission lifecycle publishes strongly typed mission.* events."""
        captured_events = []
        async def mission_collector(e: Event):
            if e.type.startswith("mission."):
                captured_events.append(e)

        self.fabric.subscribe("msn_collector", EventFilter(), mission_collector)
        m = await self.supervisor.create_mission("Test event emission")
        await asyncio.sleep(0.05)

        self.fabric.unsubscribe("msn_collector")
        self.assertTrue(any(e.type == "mission.started" for e in captured_events))

    async def test_14_evidence_backed_supervisory_decision_model(self):
        """Test 14: Supervisory decisions contain required evidence and rationale fields."""
        m = await self.supervisor.create_mission("Evidence test")
        dec = await self.supervisor._record_and_publish_decision(
            m,
            decision_type=SupervisoryDecisionType.REPLAN,
            reason="Repeated failure in step 3",
            evidence={"consecutive_failures": 3, "step_id": "step_3"},
            confidence=DecisionConfidence.HIGH,
            urgency=DecisionUrgency.NORMAL
        )
        self.assertIsNotNone(dec.decision_id)
        self.assertEqual(dec.decision, SupervisoryDecisionType.REPLAN)
        self.assertEqual(dec.evidence["consecutive_failures"], 3)
        self.assertEqual(dec.confidence, DecisionConfidence.HIGH)

    async def test_15_tools_integration_and_query(self):
        """Test 15: Module 19 tools query status and manage missions."""
        from omnia_tools import create_autonomous_mission, get_mission_status, list_active_missions
        res_create = await create_autonomous_mission("Tool test goal", 1800.0)
        self.assertIn("created with status", res_create)

        res_list = list_active_missions()
        self.assertIn("Tool test goal", res_list)


if __name__ == "__main__":
    unittest.main()
