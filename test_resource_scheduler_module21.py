import unittest
import asyncio
import os
import time
import uuid
import tempfile
import shutil

from scheduler.models import (
    ScheduleState,
    ResourceAccessMode,
    ReservationState,
    SchedulingPriority,
    PreemptionPolicy,
    SchedulingDecisionType,
    ResourceConflictType,
    SchedulerHealth,
    ResourceRequirement,
    ResourceCapacity,
    ResourceReservation,
    ScheduleRequest
)
from scheduler.resources import ResourceRegistry
from scheduler.reservations import ReservationManager
from scheduler.workers import WorkerSlotManager
from scheduler.scoring import PriorityScorer
from scheduler.deadlock import DeadlockDetector
from scheduler.persistence import SchedulerPersistenceManager
from scheduler.orchestrator import ResourceScheduler
from persistence.store import TaskPersistenceStore

class TestResourceSchedulerModule21(unittest.IsolatedAsyncioTestCase):
    """Forensic verification test suite for Module 21: Autonomous Resource Scheduler & Concurrency Orchestrator."""

    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_scheduler.db")
        self.store = TaskPersistenceStore(db_path=self.db_path)
        self.persistence = SchedulerPersistenceManager(store=self.store)
        self.registry = ResourceRegistry()
        self.reservations = ReservationManager(registry=self.registry)
        self.workers = WorkerSlotManager()
        self.scheduler = ResourceScheduler(
            registry=self.registry,
            reservations=self.reservations,
            workers=self.workers,
            persistence=self.persistence
        )

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. Resource Registry & Capacity Check
    def test_01_resource_capacity_and_modes(self):
        # Register test device with capacity 1.0 (exclusive)
        self.registry.register_resource("dev:phone1", "DEVICE", total_capacity=1.0)
        req_ex = ResourceRequirement("dev:phone1", access_mode=ResourceAccessMode.EXCLUSIVE)
        
        # Check availability
        avail, conflict = self.registry.check_availability(req_ex)
        self.assertTrue(avail)
        self.assertIsNone(conflict)

        # Allocate
        ok = self.registry.allocate(req_ex, owner_id="task_A")
        self.assertTrue(ok)

        # Second exclusive request should conflict
        avail2, conflict2 = self.registry.check_availability(req_ex)
        self.assertFalse(avail2)
        self.assertEqual(conflict2, ResourceConflictType.EXCLUSIVE_CONFLICT)

        # Release
        rel = self.registry.release("dev:phone1", owner_id="task_A")
        self.assertTrue(rel)
        avail3, _ = self.registry.check_availability(req_ex)
        self.assertTrue(avail3)

    # 2. Multi-Resource Atomicity & Rollback
    def test_02_multi_resource_atomic_reservation(self):
        self.registry.register_resource("res_A", "GENERIC", total_capacity=1.0)
        self.registry.register_resource("res_B", "GENERIC", total_capacity=1.0)

        # Hold res_B
        self.registry.allocate(ResourceRequirement("res_B"), owner_id="foreign_holder")

        reqs = [
            ResourceRequirement("res_A"),
            ResourceRequirement("res_B")
        ]

        # Attempt to reserve both atomically: Must fail and leave res_A unallocated
        ok, rsvs, conflict, msg = self.reservations.reserve_atomic("sch_1", "task_1", reqs)
        self.assertFalse(ok)
        self.assertEqual(conflict, ResourceConflictType.EXCLUSIVE_CONFLICT)

        # Verify res_A was NOT leaked
        cap_a = self.registry.get_capacity("res_A")
        self.assertIsNone(cap_a.exclusive_owner)
        self.assertEqual(cap_a.available_capacity, 1.0)

    # 3. Deterministic Priority & Aging Scoring
    def test_03_priority_and_aging_scoring(self):
        req_low = ScheduleRequest(
            schedule_id="sch_low",
            priority=SchedulingPriority.LOW,
            ready_at=time.time() - 100.0  # 100 seconds old
        )
        req_crit = ScheduleRequest(
            schedule_id="sch_crit",
            priority=SchedulingPriority.CRITICAL,
            ready_at=time.time()
        )

        score_low = PriorityScorer.compute_priority_score(req_low, {})
        score_crit = PriorityScorer.compute_priority_score(req_crit, {})

        # Low (200 + 50 aging = 250) vs Critical (500)
        self.assertGreater(score_crit, score_low)
        self.assertEqual(req_crit.priority_score, 500.0)

    # 4. Deadlock Detection & Safe Victim Selection
    def test_04_deadlock_detection_and_victim_selection(self):
        # Wait graph: t1 waits for rB, t2 waits for rA
        wait_graph = {"t1": {"rB"}, "t2": {"rA"}}
        # Allocation graph: rA held by t1, rB held by t2
        alloc_graph = {"rA": "t1", "rB": "t2"}

        is_dl, cycle = DeadlockDetector.detect_cycles(wait_graph, alloc_graph)
        self.assertTrue(is_dl)
        self.assertIn("t1", cycle)
        self.assertIn("t2", cycle)

        requests = {
            "t1": ScheduleRequest(schedule_id="t1", priority_score=100.0, preemption_policy=PreemptionPolicy.SAFE_TO_PAUSE),
            "t2": ScheduleRequest(schedule_id="t2", priority_score=500.0, preemption_policy=PreemptionPolicy.NON_PREEMPTIBLE)
        }
        # t2 is non-preemptible, so t1 must be chosen as victim
        victim = DeadlockDetector.select_victim(cycle, requests)
        self.assertEqual(victim, "t1")

    # 5. Lease Expiration & Automatic Reclamation
    def test_05_lease_expiration_and_reclamation(self):
        self.registry.register_resource("res_lease", "GENERIC", total_capacity=1.0)
        reqs = [ResourceRequirement("res_lease")]

        ok, rsvs, _, _ = self.reservations.reserve_atomic("sch_lease", "task_lease", reqs, lease_duration_sec=-1.0)
        self.assertTrue(ok)

        # Lease is expired immediately
        reaped = self.reservations.scan_and_reap_expired_leases()
        self.assertIn("sch_lease", reaped)

        # Resource must now be free
        cap = self.registry.get_capacity("res_lease")
        self.assertIsNone(cap.exclusive_owner)

    # 6. Basic Schedule Admission & Resource Allocation
    async def test_06_schedule_admission_and_completion(self):
        self.registry.register_resource("gpu:0", "ACCELERATOR", total_capacity=1.0)
        req = await self.scheduler.submit_for_scheduling(
            task_id="task_gpu_job",
            required_resources=[ResourceRequirement("gpu:0")],
            priority=SchedulingPriority.HIGH
        )
        self.assertEqual(req.state, ScheduleState.CREATED)

        decisions = await self.scheduler.schedule_next()
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].decision, SchedulingDecisionType.ADMIT)
        self.assertEqual(req.state, ScheduleState.SCHEDULED)
        self.assertIsNotNone(req.assigned_slot_id)

        # Complete schedule
        await self.scheduler.complete_schedule(req.schedule_id, success=True)
        self.assertEqual(req.state, ScheduleState.COMPLETED)
        cap = self.registry.get_capacity("gpu:0")
        self.assertIsNone(cap.exclusive_owner)

    # 7. Contention Queueing (First Runs, Second Waits)
    async def test_07_resource_contention_and_waiting(self):
        self.registry.register_resource("dev:screen", "DISPLAY", total_capacity=1.0)

        req1 = await self.scheduler.submit_for_scheduling(
            task_id="task_1",
            required_resources=[ResourceRequirement("dev:screen")],
            priority=SchedulingPriority.NORMAL
        )
        req2 = await self.scheduler.submit_for_scheduling(
            task_id="task_2",
            required_resources=[ResourceRequirement("dev:screen")],
            priority=SchedulingPriority.NORMAL
        )

        decisions = await self.scheduler.schedule_next()
        self.assertEqual(len(decisions), 2)
        admitted = [d for d in decisions if d.decision == SchedulingDecisionType.ADMIT]
        waiting = [d for d in decisions if d.decision == SchedulingDecisionType.WAIT]
        self.assertEqual(len(admitted), 1)
        self.assertEqual(len(waiting), 1)

        # Release task 1, schedule again -> task 2 gets admitted
        await self.scheduler.complete_schedule(admitted[0].schedule_id, success=True)
        decisions2 = await self.scheduler.schedule_next()
        admitted2 = [d for d in decisions2 if d.decision == SchedulingDecisionType.ADMIT]
        self.assertEqual(len(admitted2), 1)
        self.assertEqual(admitted2[0].schedule_id, waiting[0].schedule_id)

    # 8. Priority Inversion Prevention (Higher Priority Precedes)
    async def test_08_priority_precedence_in_queue(self):
        self.registry.register_resource("exclusive_line", "LINE", total_capacity=1.0)
        # Lock resource initially
        self.registry.allocate(ResourceRequirement("exclusive_line"), owner_id="initial_holder")

        req_low = await self.scheduler.submit_for_scheduling(
            task_id="task_low",
            required_resources=[ResourceRequirement("exclusive_line")],
            priority=SchedulingPriority.LOW
        )
        req_crit = await self.scheduler.submit_for_scheduling(
            task_id="task_crit",
            required_resources=[ResourceRequirement("exclusive_line")],
            priority=SchedulingPriority.CRITICAL
        )

        # First cycle: both wait
        await self.scheduler.schedule_next()
        self.assertEqual(req_low.state, ScheduleState.WAITING_RESOURCE)
        self.assertEqual(req_crit.state, ScheduleState.WAITING_RESOURCE)

        # Release holder
        self.registry.release("exclusive_line", owner_id="initial_holder")

        # Second cycle: Critical MUST be scheduled first
        decisions = await self.scheduler.schedule_next()
        admitted = [d for d in decisions if d.decision == SchedulingDecisionType.ADMIT]
        self.assertEqual(len(admitted), 1)
        self.assertEqual(admitted[0].schedule_id, req_crit.schedule_id)

    # 9. Starvation Detection & Aging
    async def test_09_starvation_detection_and_aging_boost(self):
        req_old = await self.scheduler.submit_for_scheduling(
            task_id="task_starved",
            required_resources=[ResourceRequirement("desktop:mouse")]
        )
        req_old.ready_at = time.time() - 50.0  # Simulated old wait
        req_old.wait_count = 5

        # Run scheduler cycle
        await self.scheduler.schedule_next()
        self.assertGreaterEqual(self.scheduler.starvation_count, 1)
        self.assertGreater(req_old.fairness_debt, 0.0)

    # 10. Persistence & Crash Reconciliation
    def test_10_persistence_and_crash_recovery(self):
        req = ScheduleRequest(
            schedule_id="sch_crash",
            task_id="t_crash",
            state=ScheduleState.RUNNING,
            required_resources=[ResourceRequirement("r_crash")]
        )
        self.persistence.save_schedule_request(req)

        rsv = ResourceReservation(
            reservation_id="rsv_crash",
            schedule_id="sch_crash",
            task_id="t_crash",
            resource_id="r_crash",
            state=ReservationState.ACTIVE,
            expires_at=time.time() - 100.0  # Expired during crash
        )
        self.persistence.save_reservation(rsv)

        stats = self.persistence.reconcile_on_startup()
        self.assertEqual(stats["expired_reservations"], 1)
        self.assertEqual(stats["recovering_schedules"], 1)

        loaded_req = self.persistence.get_schedule_request("sch_crash")
        self.assertEqual(loaded_req.state, ScheduleState.WAITING_RESOURCE)

    # 11. Cooperative Preemption Resolution
    async def test_11_cooperative_preemption(self):
        req = await self.scheduler.submit_for_scheduling(
            task_id="task_preemptible",
            required_resources=[],
            preemption_policy=PreemptionPolicy.SAFE_TO_PAUSE
        )
        await self.scheduler.schedule_next()
        self.assertEqual(req.state, ScheduleState.SCHEDULED)

        ok = await self.scheduler._preempt_schedule(req.schedule_id, reason="HIGH_PRIO_INCOMING")
        self.assertTrue(ok)
        self.assertEqual(req.state, ScheduleState.PREEMPTED)

    # 12. Non-Preemptible Operations Shielded
    async def test_12_non_preemptible_operation_protected(self):
        req = await self.scheduler.submit_for_scheduling(
            task_id="task_critical_trans",
            required_resources=[],
            preemption_policy=PreemptionPolicy.NON_PREEMPTIBLE
        )
        await self.scheduler.schedule_next()
        ok = await self.scheduler._preempt_schedule(req.schedule_id, reason="PREEMPTION_ATTEMPT")
        self.assertFalse(ok)
        self.assertEqual(req.state, ScheduleState.SCHEDULED)

    # 13. Telemetry Snapshot
    async def test_13_telemetry_snapshot(self):
        t = self.scheduler.get_telemetry()
        self.assertEqual(t.health, SchedulerHealth.READY)
        self.assertGreaterEqual(t.total_slots, 1)

if __name__ == "__main__":
    unittest.main()
