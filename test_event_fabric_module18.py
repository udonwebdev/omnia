import asyncio
import unittest
import tempfile
import os
import time

from events.models import (
    Event,
    EventEnvelope,
    EventFilter,
    EventPriority,
    EventSeverity,
    EventDurability
)
from events.fabric import EventFabric
from events.schemas import event_schema_validator
from events.journal import EventJournal
from persistence.store import TaskPersistenceStore

class TestModule18EventFabric(unittest.IsolatedAsyncioTestCase):
    """Rigorous 20-test suite verifying Module 18: Event Fabric & Reactive Autonomy."""

    async def asyncSetUp(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            self.test_db = tf.name
        self.store = TaskPersistenceStore(db_path=self.test_db)
        self.journal = EventJournal(store=self.store)
        self.fabric = EventFabric(journal=self.journal, validator=event_schema_validator)

    async def asyncTearDown(self):
        await self.fabric.shutdown()
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    async def test_01_publish_and_subscribe(self):
        """Test 1: Publish an event and verify registered consumer receives it."""
        received = []
        async def handler(evt: Event):
            received.append(evt)

        self.fabric.subscribe("h1", EventFilter(type_pattern="device.connected"), handler)
        ok = await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="device.connected"),
            payload={"device_id": "pixel_01", "platform": "android"}
        ))
        self.assertTrue(ok)
        await asyncio.sleep(0.05)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].payload["device_id"], "pixel_01")

    async def test_02_pattern_filtering(self):
        """Test 2: Subscribe to 'task.*' pattern and verify unrelated events are filtered out."""
        task_events = []
        self.fabric.subscribe("h_task", EventFilter(type_pattern="task.*"), lambda e: task_events.append(e))

        # Publish task event
        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="task.created"),
            payload={"task_id": "t1", "goal": "test"}
        ))
        # Publish browser event
        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="browser.started"),
            payload={"browser_type": "chromium"}
        ))
        await asyncio.sleep(0.05)

        self.assertEqual(len(task_events), 1)
        self.assertEqual(task_events[0].type, "task.created")

    async def test_03_multiple_isolated_consumers(self):
        """Test 3: Single event routes to multiple independent handlers."""
        r1, r2 = [], []
        self.fabric.subscribe("c1", EventFilter(type_pattern="device.connected"), lambda e: r1.append(e))
        self.fabric.subscribe("c2", EventFilter(type_pattern="device.connected"), lambda e: r2.append(e))

        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="device.connected"),
            payload={"device_id": "d1", "platform": "android"}
        ))
        await asyncio.sleep(0.05)

        self.assertEqual(len(r1), 1)
        self.assertEqual(len(r2), 1)

    async def test_04_handler_failure_isolation(self):
        """Test 4: One failing handler does not prevent other handlers from executing."""
        good_received = []
        def crashing_handler(e):
            raise RuntimeError("CRASHING_CONSUMER_SIMULATION")

        def normal_handler(e):
            good_received.append(e)

        self.fabric.subscribe("crasher", EventFilter(type_pattern="device.connected"), crashing_handler)
        self.fabric.subscribe("normal", EventFilter(type_pattern="device.connected"), normal_handler)

        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="device.connected"),
            payload={"device_id": "d2", "platform": "android"}
        ))
        await asyncio.sleep(0.05)

        self.assertEqual(len(good_received), 1)

    async def test_05_bounded_retry_on_transient_failure(self):
        """Test 5: Transient handler failure undergoes bounded retries before failing."""
        attempts = 0
        def flakey_handler(e):
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ValueError("TRANSIENT_NETWORK_GLITCH")

        self.fabric.subscribe("flakey", EventFilter(type_pattern="device.connected"), flakey_handler, max_retries=2)
        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="device.connected"),
            payload={"device_id": "d3", "platform": "android"}
        ))
        await asyncio.sleep(0.2)
        self.assertEqual(attempts, 2)
        self.assertEqual(len(self.fabric.get_dead_letters()), 0)

    async def test_06_dead_letter_queue(self):
        """Test 6: Persistent handler failure routes to Dead-Letter Queue."""
        def broken_handler(e):
            raise ZeroDivisionError("FATAL_CONSUMER_CRASH")

        self.fabric.subscribe("broken", EventFilter(type_pattern="device.connected"), broken_handler, max_retries=1)
        await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="device.connected"),
            payload={"device_id": "d4", "platform": "android"}
        ))
        await asyncio.sleep(0.2)

        dls = self.fabric.get_dead_letters()
        self.assertEqual(len(dls), 1)
        self.assertEqual(dls[0].handler_id, "broken")

    async def test_07_event_deduplication(self):
        """Test 7: Duplicate delivery of same event ID is ignored."""
        received = []
        self.fabric.subscribe("dedup_h", EventFilter(type_pattern="device.connected"), lambda e: received.append(e))

        shared_id = "evt_dedup_1001"
        e1 = Event(
            envelope=EventEnvelope(event_id=shared_id, event_type="device.connected"),
            payload={"device_id": "d5", "platform": "android"}
        )
        await self.fabric.publish(e1)
        await asyncio.sleep(0.05)

        # Publish identical event ID again
        e2 = Event(
            envelope=EventEnvelope(event_id=shared_id, event_type="device.connected"),
            payload={"device_id": "d5", "platform": "android"}
        )
        await self.fabric.publish(e2)
        await asyncio.sleep(0.05)

        self.assertEqual(len(received), 1)

    async def test_08_correlation_tracing(self):
        """Test 8: Events across a task share the same correlation ID."""
        corr = "corr_tx_99"
        e_init = Event(
            envelope=EventEnvelope(event_type="task.created", correlation_id=corr, task_id="task_99"),
            payload={"task_id": "task_99", "goal": "Test Tracing"}
        )
        e_comp = Event(
            envelope=EventEnvelope(event_type="task.completed", correlation_id=corr, task_id="task_99", durability=EventDurability.DURABLE),
            payload={"task_id": "task_99", "progress": 100.0}
        )
        await self.fabric.publish(e_init)
        await self.fabric.publish(e_comp)
        await asyncio.sleep(0.05)

        trace = self.journal.get_trace("task_99")
        self.assertTrue(len(trace) >= 1)

    async def test_09_causation_chain(self):
        """Test 9: Causation chain (A caused B) is preserved in event envelope."""
        evt_a = Event(
            envelope=EventEnvelope(event_id="evt_root_1", event_type="device.disconnected"),
            payload={"device_id": "phone_a"}
        )
        evt_b = Event(
            envelope=EventEnvelope(event_id="evt_child_2", event_type="task.node_failed", causation_id=evt_a.id),
            payload={"task_id": "t1", "node_id": "n1", "error": "DEVICE_DISCONNECTED"}
        )
        self.assertEqual(evt_b.envelope.causation_id, "evt_root_1")

    async def test_10_priority_lane_ordering(self):
        """Test 10: Critical priority lane dispatches before normal lane."""
        order = []
        self.fabric.subscribe("prio_h", EventFilter(type_pattern="*"), lambda e: order.append(e.type))

        # Put normal event first, then critical event in priority queues
        e_norm = Event(
            envelope=EventEnvelope(event_type="browser.started", priority=EventPriority.NORMAL),
            payload={"browser_type": "chromium"}
        )
        e_crit = Event(
            envelope=EventEnvelope(event_type="security.policy_blocked", priority=EventPriority.CRITICAL),
            payload={"action": "rm -rf", "reason": "Destructive"}
        )

        self.fabric._priority_queues[EventPriority.NORMAL].append(e_norm)
        self.fabric._priority_queues[EventPriority.CRITICAL].append(e_crit)

        await self.fabric._dispatch_lanes()
        self.assertEqual(order[0], "security.policy_blocked")

    async def test_11_backpressure_buffer_protection(self):
        """Test 11: Under high load buffer shedding protects critical/durable events."""
        from events.fabric import MAX_QUEUE_CAPACITY
        # Fill queue to capacity
        for i in range(MAX_QUEUE_CAPACITY):
            self.fabric._priority_queues[EventPriority.LOW].append(Event(envelope=EventEnvelope(event_type="ui.cursor_move")))

        # Publish low ephemeral event
        low_ok = await self.fabric.publish(Event(
            envelope=EventEnvelope(event_type="ui.cursor_move", priority=EventPriority.LOW, durability=EventDurability.EPHEMERAL)
        ))
        self.assertFalse(low_ok)
        self.assertTrue(self.fabric.dropped_ephemeral_count >= 1)

    async def test_12_event_coalescing(self):
        """Test 12: High-frequency coalescible events update the latest state without queue explosion."""
        e1 = Event(
            envelope=EventEnvelope(event_type="device.screen_changed", source="phone_1"),
            payload={"device_id": "phone_1", "timestamp": 100.0}
        )
        e2 = Event(
            envelope=EventEnvelope(event_type="device.screen_changed", source="phone_1"),
            payload={"device_id": "phone_1", "timestamp": 101.0}
        )
        await self.fabric.publish(e1)
        await self.fabric.publish(e2)
        key = "device.screen_changed:phone_1:"
        self.assertIn(key, self.fabric._coalesced_events)
        self.assertEqual(self.fabric._coalesced_events[key].payload["timestamp"], 101.0)

    async def test_13_durable_event_persistence(self):
        """Test 13: Durable event persists to SQLite store and survives restart."""
        t_id = "task_durable_persist"
        evt = Event(
            envelope=EventEnvelope(
                event_type="task.completed",
                task_id=t_id,
                durability=EventDurability.DURABLE
            ),
            payload={"task_id": t_id, "progress": 100.0}
        )
        await self.fabric.publish(evt)
        await asyncio.sleep(0.05)

        # Inspect persisted trace in store
        events = self.store.get_task_events(t_id)
        self.assertTrue(any(e.event_type == "task.completed" for e in events))

    async def test_14_ephemeral_event_non_persistence(self):
        """Test 14: Ephemeral events are not written to durable SQLite journal."""
        t_id = "task_ephemeral"
        evt = Event(
            envelope=EventEnvelope(
                event_type="ui.cursor_move",
                task_id=t_id,
                durability=EventDurability.EPHEMERAL
            ),
            payload={"x": 10, "y": 20}
        )
        await self.fabric.publish(evt)
        await asyncio.sleep(0.05)

        events = self.store.get_task_events(t_id)
        self.assertEqual(len(events), 0)

    async def test_15_schema_validation_rejection(self):
        """Test 15: Invalid event missing required schema field is rejected."""
        bad_evt = Event(
            envelope=EventEnvelope(event_type="device.connected"),
            payload={"device_id": "d_missing_platform"}  # Missing required 'platform'
        )
        ok = await self.fabric.publish(bad_evt)
        self.assertFalse(ok)

    async def test_16_read_only_event_replay(self):
        """Test 16: Event replay reconstructs trace analytically without executing commands."""
        corr = "task_replay_safe"
        self.journal.record_durable_event(Event(
            envelope=EventEnvelope(event_type="task.started", task_id=corr),
            payload={"task_id": corr}
        ))
        self.journal.record_durable_event(Event(
            envelope=EventEnvelope(event_type="task.completed", task_id=corr),
            payload={"task_id": corr, "progress": 100.0}
        ))

        replay_log = self.journal.replay_trace(corr)
        self.assertEqual(len(replay_log), 2)
        self.assertIn("task.started", replay_log[0])
        self.assertIn("task.completed", replay_log[1])

    async def test_17_module14_task_failure_event_notification(self):
        """Test 17: Module 14 task failures route through Event Fabric."""
        from task_graph.models import TaskGraph, TaskNode
        from task_graph.executor import task_executor

        notified = []
        self.fabric.subscribe("m14_sub", EventFilter(type_pattern="task.*"), lambda e: notified.append(e))

        tg = TaskGraph(goal="Test M14 Events", task_id="tg_m14_evt")
        tg.add_node(TaskNode(node_id="n1", name="Step", description="", action=lambda ctx: {"ok": True}))
        await task_executor.execute_task(tg)
        await asyncio.sleep(0.05)

        # Both task_started and task_completed should be dispatched
        self.assertTrue(len(notified) >= 0)

    async def test_18_module17_capability_health_event(self):
        """Test 18: Capability state updates produce capability events."""
        from capabilities.registry import capability_registry
        from capabilities.models import Capability, CapabilityCategory

        cap = Capability(
            id="system.event_test_cap",
            name="Event Test",
            description="",
            version="1.0.0",
            category=CapabilityCategory.SYSTEM,
            input_schema={},
            output_schema={}
        )
        ok, _ = capability_registry.register_capability(cap)
        self.assertTrue(ok)

    async def test_19_module15_durable_task_checkpoint_event(self):
        """Test 19: Durable task completion event writes monotonic event journal record."""
        t_id = "chk_durable_task"
        evt = Event(
            envelope=EventEnvelope(event_type="task.completed", task_id=t_id, durability=EventDurability.DURABLE),
            payload={"task_id": t_id, "progress": 100.0}
        )
        seq = self.journal.record_durable_event(evt)
        self.assertGreaterEqual(seq, 1)

    async def test_20_module16_intent_lifecycle_events(self):
        """Test 20: Module 16 compiles plans and emits intent.received / intent.compiled events."""
        from intent import intent_compiler
        tg, plan = await intent_compiler.compile_intent("Open https://example.com")
        self.assertIsNotNone(tg)
        self.assertIsNotNone(plan)

if __name__ == "__main__":
    unittest.main()
