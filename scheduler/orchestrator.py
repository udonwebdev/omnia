import asyncio
import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple, Set

from scheduler.models import (
    ScheduleRequest,
    ScheduleState,
    SchedulingDecision,
    SchedulingDecisionType,
    ResourceConflictType,
    SchedulingPriority,
    PreemptionPolicy,
    SchedulerHealth,
    SchedulerPressure,
    SchedulerTelemetry,
    ResourceRequirement
)
from scheduler.resources import resource_registry, ResourceRegistry
from scheduler.reservations import reservation_manager, ReservationManager
from scheduler.workers import worker_slot_manager, WorkerSlotManager
from scheduler.scoring import priority_scorer
from scheduler.deadlock import deadlock_detector
from scheduler.persistence import scheduler_persistence_manager, SchedulerPersistenceManager

logger = logging.getLogger("Omnia.Scheduler.Orchestrator")

class ResourceScheduler:
    """Authoritative Autonomous Resource Scheduler & Concurrency Orchestrator for Omnia."""

    def __init__(
        self,
        registry: Optional[ResourceRegistry] = None,
        reservations: Optional[ReservationManager] = None,
        workers: Optional[WorkerSlotManager] = None,
        persistence: Optional[SchedulerPersistenceManager] = None
    ):
        self.registry = registry or resource_registry
        self.reservations = reservations or reservation_manager
        self.workers = workers or worker_slot_manager
        self.persistence = persistence or scheduler_persistence_manager

        self._requests: Dict[str, ScheduleRequest] = {}
        self._fairness_credits: Dict[str, float] = {}  # mission_id -> credit bonus
        self._wait_graph: Dict[str, Set[str]] = {}     # schedule_id -> set of resource_ids waiting for
        self.health = SchedulerHealth.READY
        self.pressure = SchedulerPressure.NORMAL

        # Telemetry counters
        self.deadlock_count = 0
        self.starvation_count = 0
        self.preemption_count = 0

    async def submit_for_scheduling(
        self,
        task_id: str,
        required_resources: List[ResourceRequirement],
        mission_id: Optional[str] = None,
        task_node_id: Optional[str] = None,
        priority: SchedulingPriority = SchedulingPriority.NORMAL,
        deadline: Optional[float] = None,
        required_capabilities: Optional[List[str]] = None,
        required_devices: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        preemption_policy: PreemptionPolicy = PreemptionPolicy.SAFE_TO_PAUSE,
        metadata: Optional[Dict] = None
    ) -> ScheduleRequest:
        """Admits a work item into the scheduling pipeline."""
        req = ScheduleRequest(
            schedule_id=f"sch_{uuid.uuid4().hex[:8]}",
            mission_id=mission_id,
            task_id=task_id,
            task_node_id=task_node_id,
            created_at=time.time(),
            ready_at=time.time(),
            deadline=deadline,
            priority=priority,
            required_resources=required_resources or [],
            required_capabilities=required_capabilities or [],
            required_devices=required_devices or [],
            dependencies=dependencies or [],
            preemption_policy=preemption_policy,
            state=ScheduleState.CREATED,
            metadata=metadata or {}
        )
        self._requests[req.schedule_id] = req
        self.persistence.save_schedule_request(req)

        await self._publish_event("schedule.created", {
            "schedule_id": req.schedule_id,
            "task_id": req.task_id
        })

        return req

    async def schedule_next(self) -> List[SchedulingDecision]:
        """Core scheduling cycle: Prioritizes ready work, checks capacity, allocates atomic resources, and admits work."""
        decisions: List[SchedulingDecision] = []

        # 1. Reap any expired leases first
        expired = self.reservations.scan_and_reap_expired_leases()
        for exp_sch in expired:
            if exp_sch in self._requests:
                self._requests[exp_sch].state = ScheduleState.WAITING_RESOURCE
                self.workers.release_by_schedule(exp_sch)

        # 2. Check for deadlock cycles in wait graph
        alloc_graph = {
            rsv.resource_id: rsv.schedule_id
            for rsv in self.reservations.get_active_reservations()
        }
        is_dl, cycle = deadlock_detector.detect_cycles(self._wait_graph, alloc_graph)
        if is_dl:
            self.deadlock_count += 1
            victim = deadlock_detector.select_victim(cycle, self._requests)
            if victim:
                await self._preempt_schedule(victim, reason="DEADLOCK_CYCLE_RESOLUTION")
                await self._publish_event("resource.deadlock", {
                    "cycle_tasks": cycle,
                    "victim_task": victim
                })

        # 3. Filter candidates for scheduling
        eligible = [
            req for req in self._requests.values()
            if req.state in {ScheduleState.CREATED, ScheduleState.WAITING_RESOURCE, ScheduleState.DEFERRED}
        ]

        # 4. Compute priority & starvation scoring
        now = time.time()
        for req in eligible:
            priority_scorer.compute_priority_score(req, self._fairness_credits)
            # Detect starvation (waiting > 45s without admission)
            if now - req.ready_at > 45.0 and req.wait_count > 3:
                self.starvation_count += 1
                req.fairness_debt += 50.0  # Aging boost
                await self._publish_event("resource.starvation", {
                    "schedule_id": req.schedule_id,
                    "wait_duration_sec": round(now - req.ready_at, 1)
                })

        # Sort by priority score descending
        eligible.sort(key=lambda r: r.priority_score, reverse=True)

        # 5. Admission evaluation
        for req in eligible:
            # Check worker slot availability
            slot = self.workers.find_compatible_idle_slot(req.required_capabilities)
            if not slot:
                req.state = ScheduleState.WAITING_RESOURCE
                req.wait_count += 1
                decision = SchedulingDecision(
                    schedule_id=req.schedule_id,
                    decision=SchedulingDecisionType.WAIT,
                    reason="No compatible idle worker execution slot available.",
                    priority_score=req.priority_score,
                    conflicts=[ResourceConflictType.CAPACITY_EXCEEDED]
                )
                decisions.append(decision)
                continue

            # Check & reserve resources atomically
            ok, rsvs, conflict, msg = self.reservations.reserve_atomic(
                schedule_id=req.schedule_id,
                task_id=req.task_id,
                requirements=req.required_resources,
                mission_id=req.mission_id,
                task_node_id=req.task_node_id
            )

            if not ok:
                req.state = ScheduleState.WAITING_RESOURCE
                req.wait_count += 1
                self._wait_graph[req.schedule_id] = {r.resource_id for r in req.required_resources}
                decision = SchedulingDecision(
                    schedule_id=req.schedule_id,
                    decision=SchedulingDecisionType.WAIT,
                    reason=msg,
                    priority_score=req.priority_score,
                    conflicts=[conflict] if conflict else []
                )
                decisions.append(decision)
                await self._publish_event("schedule.waiting", {
                    "schedule_id": req.schedule_id,
                    "conflict_type": conflict.value if conflict else "RESOURCE_BUSY"
                })
                continue

            # Resources and worker slot secured: Admit and release to execution
            self._wait_graph.pop(req.schedule_id, None)
            self.workers.assign_slot(slot.slot_id, req.schedule_id, req.task_id)
            req.assigned_slot_id = slot.slot_id
            req.state = ScheduleState.SCHEDULED
            self.persistence.save_schedule_request(req)

            # Fairness credit adjustment: mission consumed resources, decay credits
            mission_key = req.mission_id or "default"
            self._fairness_credits[mission_key] = max(0.0, self._fairness_credits.get(mission_key, 0.0) - 25.0)

            decision = SchedulingDecision(
                schedule_id=req.schedule_id,
                decision=SchedulingDecisionType.ADMIT,
                reason="All required resources and execution slot atomically allocated.",
                priority_score=req.priority_score,
                selected_slot_id=slot.slot_id,
                selected_resources=[r.resource_id for r in rsvs]
            )
            decisions.append(decision)

            await self._publish_event("schedule.admitted", {
                "schedule_id": req.schedule_id,
                "slot_id": slot.slot_id
            })

        return decisions

    async def complete_schedule(self, schedule_id: str, success: bool = True):
        """Releases resources and execution slots upon task completion or failure."""
        req = self._requests.get(schedule_id)
        if not req:
            req = self.persistence.get_schedule_request(schedule_id)

        if req:
            req.state = ScheduleState.COMPLETED if success else ScheduleState.FAILED
            self.persistence.save_schedule_request(req)

        self.reservations.release_schedule_reservations(schedule_id, reason="COMPLETED" if success else "FAILED")
        self.workers.release_by_schedule(schedule_id)
        self._wait_graph.pop(schedule_id, None)

        await self._publish_event("schedule.completed", {
            "schedule_id": schedule_id
        })

    async def _preempt_schedule(self, schedule_id: str, reason: str = "PREEMPTED") -> bool:
        """Safely preempts a running or scheduled task to resolve deadlocks or release urgent resources."""
        req = self._requests.get(schedule_id)
        if not req or req.preemption_policy == PreemptionPolicy.NON_PREEMPTIBLE:
            return False

        logger.warning(f"Preempting schedule '{schedule_id}'. Reason: {reason}")
        self.preemption_count += 1
        req.state = ScheduleState.PREEMPTED
        self.reservations.release_schedule_reservations(schedule_id, reason=reason)
        self.workers.release_by_schedule(schedule_id)
        self.persistence.save_schedule_request(req)

        await self._publish_event("schedule.preempted", {
            "schedule_id": schedule_id,
            "preempted_by": "scheduler.deadlock_resolver",
            "reason": reason
        })
        return True

    def get_telemetry(self) -> SchedulerTelemetry:
        """Returns structured telemetry snapshot."""
        idle_slots = self.workers.get_idle_slots_count()
        total_slots = len(self.workers.list_slots())
        active_rsvs = len(self.reservations.get_active_reservations())
        
        ready_cnt = sum(1 for r in self._requests.values() if r.state in {ScheduleState.CREATED, ScheduleState.DEFERRED})
        waiting_cnt = sum(1 for r in self._requests.values() if r.state == ScheduleState.WAITING_RESOURCE)
        active_cnt = sum(1 for r in self._requests.values() if r.state in {ScheduleState.SCHEDULED, ScheduleState.RUNNING})

        return SchedulerTelemetry(
            health=self.health,
            pressure=self.pressure,
            ready_queue_depth=ready_cnt,
            waiting_queue_depth=waiting_cnt,
            active_schedules=active_cnt,
            total_slots=total_slots,
            idle_slots=idle_slots,
            active_reservations=active_rsvs,
            deadlock_count=self.deadlock_count,
            starvation_count=self.starvation_count,
            preemption_count=self.preemption_count
        )

    async def _publish_event(self, event_type: str, payload: Dict):
        try:
            from events import event_fabric, Event, EventEnvelope, EventPriority, EventSeverity, EventDurability
            event = Event(
                envelope=EventEnvelope(
                    event_type=event_type,
                    source="module.21.scheduler",
                    priority=EventPriority.HIGH if "deadlock" in event_type or "starvation" in event_type else EventPriority.NORMAL,
                    severity=EventSeverity.WARNING if "deadlock" in event_type or "starvation" in event_type else EventSeverity.INFO,
                    durability=EventDurability.DURABLE
                ),
                payload=payload
            )
            await event_fabric.publish(event)
        except Exception as e:
            logger.debug(f"Event fabric publish skipped for {event_type}: {e}")

resource_scheduler = ResourceScheduler()
