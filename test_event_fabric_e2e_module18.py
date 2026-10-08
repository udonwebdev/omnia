import asyncio
import unittest
import time
import uuid
import tempfile
import os
from typing import List, Dict, Any

from events import (
    event_fabric,
    event_journal,
    Event,
    EventEnvelope,
    EventPriority,
    EventSeverity,
    EventDurability,
    EventFilter
)
from intent import intent_compiler
from task_graph.models import TaskGraph, TaskNode, TaskState, RetryPolicy
from task_graph.executor import TaskExecutionEngine


class TestModule18ReactiveAutonomyE2E(unittest.IsolatedAsyncioTestCase):
    """End-to-End Reactive Autonomy & Event Fabric Verification.
    
    Verifies full lifecycle:
    Intent (Mod 16) -> Capability Discovery (Mod 17) -> Task Execution (Mod 14) ->
    Asynchronous Failure Event -> Reactive Handler Autonomous Intervention ->
    Self-Healing Recovery -> Verified Task Completion -> Durable Journal & Replay.
    """

    async def asyncSetUp(self):
        self.fabric = event_fabric
        self.journal = event_journal
        self.captured_events: List[Event] = []

    async def test_full_reactive_autonomy_e2e_loop(self):
        """Executes complete reactive loop with an asynchronous external fault event."""
        reactive_interventions: List[str] = []

        # 1. Subscribe wildcard listener to record the narrative stream
        async def event_collector(evt: Event):
            self.captured_events.append(evt)

        self.fabric.subscribe("collector_e2e", EventFilter(), event_collector)

        # 2. Register a reactive policy handler for hardware/device failure events
        # When device fault arrives, reactively inject a recovery flag or trigger self-healing
        async def device_fault_reactor(evt: Event):
            if evt.type == "device.disconnected":
                reactive_interventions.append(
                    f"REACTIVE_INTERVENTION: device {evt.payload.get('device_id')} dropped, activating local fallback"
                )
                # Publish high-priority corrective notification adhering strictly to schema
                recovery_evt = Event(
                    envelope=EventEnvelope(
                        event_type="system.health_changed",
                        correlation_id=evt.correlation_id,
                        task_id=evt.task_id,
                        causation_id=evt.id,
                        priority=EventPriority.HIGH,
                        severity=EventSeverity.WARNING,
                        durability=EventDurability.DURABLE
                    ),
                    payload={
                        "subsystem": "device_mesh",
                        "old_health": "HEALTHY",
                        "new_health": "DEGRADED",
                        "details": f"Recovered via local fallback for {evt.payload.get('device_id')}"
                    }
                )
                await self.fabric.publish(recovery_evt)

        self.fabric.subscribe(
            "fault_reactor_e2e",
            EventFilter(type_pattern="device.disconnected"),
            device_fault_reactor
        )

        # 3. Compile natural language intent (Module 16 -> 17)
        user_prompt = "capture current screen state and click confirm button"
        tg_compiled, plan = await intent_compiler.compile_intent(user_prompt)
        self.assertIsNotNone(tg_compiled)
        self.assertIsNotNone(plan)

        task_id = tg_compiled.task_id
        correlation_id = task_id

        # 4. Construct executable task graph with self-healing recovery node
        recovered_flag = {"recovered": False, "attempts": 0}

        async def action_with_reactive_recovery(ctx):
            recovered_flag["attempts"] += 1
            if recovered_flag["attempts"] == 1:
                # Simulate unexpected hardware fault during execution
                fault_event = Event(
                    envelope=EventEnvelope(
                        event_type="device.disconnected",
                        correlation_id=correlation_id,
                        task_id=task_id,
                        priority=EventPriority.HIGH,
                        severity=EventSeverity.ERROR,
                        durability=EventDurability.DURABLE
                    ),
                    payload={"device_id": "phone_remote_001", "reason": "USB_TIMEOUT"}
                )
                await self.fabric.publish(fault_event)
                # Give reactive listener time to process intervention
                await asyncio.sleep(0.05)
                # Trigger retryable error
                raise RuntimeError("Primary remote device dropped offline")

            # Subsequent attempt: self-heals by using local desktop fallback
            recovered_flag["recovered"] = True
            return {"status": "SUCCESS", "mode": "LOCAL_DESKTOP_FALLBACK"}

        node_primary = TaskNode(
            node_id="step_primary",
            name="Primary Device Capture",
            description="Captures screen with reactive fallback",
            action=action_with_reactive_recovery,
            retry_policy=RetryPolicy(max_attempts=2, base_delay_sec=0.01)
        )

        tg = TaskGraph(task_id=task_id, goal=user_prompt)
        tg.add_node(node_primary)

        executor = TaskExecutionEngine()

        # 5. Execute task through Module 14 TaskExecutionEngine
        result = await executor.execute_task(tg)

        # 6. Verify autonomous self-healing success
        self.assertEqual(result["state"], TaskState.COMPLETED.value)
        self.assertTrue(recovered_flag["recovered"])
        self.assertEqual(len(reactive_interventions), 1)
        self.assertIn("REACTIVE_INTERVENTION", reactive_interventions[0])

        # 7. Settle async tasks and verify Event Fabric recorded narrative
        await asyncio.sleep(0.2)
        event_types = [e.type for e in self.captured_events]
        self.assertIn("task.started", event_types)
        self.assertIn("device.disconnected", event_types)
        self.assertIn("system.health_changed", event_types)
        self.assertIn("task.completed", event_types)

        # 8. Verify Causation Chain: system.health_changed was caused by device.disconnected
        fault_evt = next(e for e in self.captured_events if e.type == "device.disconnected")
        recovery_evts = [e for e in self.captured_events if e.type == "system.health_changed"]
        self.assertTrue(len(recovery_evts) > 0)
        self.assertEqual(recovery_evts[0].envelope.causation_id, fault_evt.id)

        # 9. Verify Durable Journal Persistence
        trace = self.journal.get_trace(task_id)
        self.assertTrue(len(trace) > 0)
        persisted_types = [t["event_type"] for t in trace]
        self.assertIn("task.started", persisted_types)
        self.assertIn("task.completed", persisted_types)

        # 10. Verify Safe Read-Only Analytical Replay
        replay_summary = self.journal.replay_trace(task_id)
        self.assertTrue(len(replay_summary) >= 2)
        self.assertTrue(any("task.started" in line for line in replay_summary))
        self.assertTrue(any("task.completed" in line for line in replay_summary))


if __name__ == "__main__":
    unittest.main()
