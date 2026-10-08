import asyncio
import time
import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple

from supervisor.models import (
    Mission,
    MissionState,
    SupervisoryState,
    SupervisoryDecision,
    SupervisoryDecisionType,
    DecisionConfidence,
    DecisionUrgency,
    MissionPriority,
    DeadlineRisk,
    ResourcePressure,
    StallClassification,
    MissionPhase,
    SupervisorFailureCategory,
    MissionTelemetry
)
from supervisor.heartbeat import heartbeat_monitor, HeartbeatMonitor
from supervisor.resources import resource_supervisor, ResourceSupervisor
from supervisor.reconciliation import state_reconciler, StateReconciler
from events import (
    event_fabric,
    Event,
    EventEnvelope,
    EventPriority,
    EventSeverity,
    EventDurability,
    EventFilter
)
from capabilities.registry import capability_registry
from policy_engine import PolicyEngine

logger = logging.getLogger("Omnia.Supervisor.Engine")

class AutonomousSupervisor:
    """Production-grade Autonomous Supervisor & Mission Control for Omnia."""

    def __init__(
        self,
        fabric=event_fabric,
        registry=capability_registry,
        hb_monitor: HeartbeatMonitor = heartbeat_monitor,
        res_supervisor: ResourceSupervisor = resource_supervisor,
        reconciler: StateReconciler = state_reconciler
    ):
        self.fabric = fabric
        self.registry = registry
        self.hb_monitor = hb_monitor
        self.res_supervisor = res_supervisor
        self.reconciler = reconciler
        self.policy_engine = PolicyEngine()

        self.missions: Dict[str, Mission] = {}
        self.decisions_history: Dict[str, List[SupervisoryDecision]] = {}
        self.supervisory_state: SupervisoryState = SupervisoryState.IDLE

        self.is_running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._adaptive_interval_sec: float = 1.0

    async def start(self):
        """Starts event-driven subscriptions and the adaptive periodic supervision loop."""
        if self.is_running:
            return
        self.is_running = True
        self.supervisory_state = SupervisoryState.SUPERVISING

        # Subscribe to relevant Module 18 events
        self.fabric.subscribe(
            "supervisor_events",
            EventFilter(),
            self._handle_event
        )

        self._loop_task = asyncio.create_task(self._supervision_loop())
        logger.info("Autonomous Supervisor & Mission Control started.")

    async def stop(self):
        """Stops the supervisor gracefully."""
        self.is_running = False
        self.supervisory_state = SupervisoryState.IDLE
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self.fabric.unsubscribe("supervisor_events")
        logger.info("Autonomous Supervisor & Mission Control stopped.")

    # --- Mission Lifecycle & User Interventions ---

    async def create_mission(
        self,
        objective: str,
        priority: MissionPriority = MissionPriority.NORMAL,
        deadline_sec: float = 3600.0,
        constraints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Mission:
        """Registers and initializes a new mission."""
        now = time.time()
        mission = Mission(
            objective=objective,
            status=MissionState.CREATED,
            priority=priority,
            deadline_ts=now + deadline_sec,
            constraints=constraints or [],
            phase=MissionPhase.DISCOVERY,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        self.missions[mission.mission_id] = mission
        self.decisions_history[mission.mission_id] = []
        self.hb_monitor.register_mission(mission.mission_id)

        # Publish mission.started event
        await self._publish_mission_event("mission.started", mission, {
            "objective": objective,
            "priority": priority.name,
            "deadline_ts": mission.deadline_ts
        })

        logger.info(f"Created mission '{mission.mission_id}': {objective[:40]}")
        return mission

    async def pause_mission(self, mission_id: str, reason: str = "User request") -> bool:
        """User or supervisory pause intervention."""
        mission = self.missions.get(mission_id)
        if not mission or mission.is_terminal():
            return False
        if mission.transition_to(MissionState.PAUSED):
            logger.info(f"Mission '{mission_id}' paused: {reason}")
            await self._record_and_publish_decision(
                mission,
                SupervisoryDecisionType.PAUSE,
                f"Mission paused: {reason}",
                {"user_intervention": True}
            )
            return True
        return False

    async def resume_mission(self, mission_id: str) -> bool:
        """User or supervisory resume intervention."""
        mission = self.missions.get(mission_id)
        if not mission or mission.status != MissionState.PAUSED:
            return False
        if mission.transition_to(MissionState.RUNNING):
            logger.info(f"Mission '{mission_id}' resumed.")
            self.hb_monitor.record_progress(mission_id, "MISSION_RESUMED")
            await self._record_and_publish_decision(
                mission,
                SupervisoryDecisionType.CONTINUE,
                "Mission resumed by user",
                {}
            )
            return True
        return False

    async def abort_mission(self, mission_id: str, reason: str = "User cancellation") -> bool:
        """Terminal abort intervention."""
        mission = self.missions.get(mission_id)
        if not mission or mission.is_terminal():
            return False
        mission.transition_to(MissionState.ABORTED)
        self.hb_monitor.cleanup(mission_id)
        await self._publish_mission_event("mission.aborted", mission, {"reason": reason})
        logger.warning(f"Mission '{mission_id}' aborted: {reason}")
        return True

    def get_mission(self, mission_id: str) -> Optional[Mission]:
        return self.missions.get(mission_id)

    def list_missions(self) -> List[Mission]:
        return list(self.missions.values())

    # --- Event-Driven Reactive Supervision ---

    async def _handle_event(self, event: Event):
        """Processes high-priority real-time events from Event Fabric."""
        if not self.is_running:
            return

        etype = event.type
        task_id = event.task_id or event.correlation_id

        # Find matching mission
        matched_mission = None
        for m in self.missions.values():
            if m.active_task_id == task_id or task_id in m.task_ids:
                matched_mission = m
                break

        # 1. Task Lifecycle Events
        if etype == "task.started" and matched_mission:
            matched_mission.transition_to(MissionState.RUNNING)
            matched_mission.phase = MissionPhase.EXECUTION
            self.hb_monitor.record_progress(matched_mission.mission_id, "TASK_STARTED")

        elif etype == "task.node_started" and matched_mission:
            node_id = event.payload.get("node_id")
            self.hb_monitor.record_heartbeat(matched_mission.mission_id, f"Node: {node_id}", node_id)

        elif etype == "task.node_completed" and matched_mission:
            self.hb_monitor.record_progress(matched_mission.mission_id, "NODE_COMPLETED", event.payload)
            matched_mission.consecutive_failures = 0

        elif etype == "task.node_failed" and matched_mission:
            matched_mission.consecutive_failures += 1
            await self._assess_mission_on_event(matched_mission, "NODE_FAILED", event.payload)

        elif etype == "task.completed" and matched_mission:
            matched_mission.transition_to(MissionState.COMPLETED)
            matched_mission.phase = MissionPhase.COMPLETION
            matched_mission.progress = 100.0
            self.hb_monitor.cleanup(matched_mission.mission_id)
            await self._publish_mission_event("mission.completed", matched_mission, event.payload)

        # 2. Hardware / Device Events
        elif etype == "device.disconnected":
            # Check all active missions that might require devices
            for m in list(self.missions.values()):
                if m.status in {MissionState.CREATED, MissionState.READY, MissionState.RUNNING, MissionState.DEGRADED}:
                    await self._assess_mission_on_event(m, "DEVICE_DISCONNECTED", event.payload)

        # 3. Security Policy Block Events
        elif etype == "security.policy_blocked":
            for m in list(self.missions.values()):
                if m.status == MissionState.RUNNING:
                    logger.critical(f"Security policy blocked action in mission '{m.mission_id}'!")
                    m.transition_to(MissionState.PAUSED)
                    await self._record_and_publish_decision(
                        m,
                        SupervisoryDecisionType.PAUSE,
                        f"Security policy block: {event.payload.get('reason')}",
                        event.payload,
                        urgency=DecisionUrgency.CRITICAL,
                        confidence=DecisionConfidence.HIGH
                    )

    async def _assess_mission_on_event(self, mission: Mission, trigger: str, evidence: Dict[str, Any]):
        """Immediate event-triggered assessment of a mission."""
        self.supervisory_state = SupervisoryState.ASSESSING
        if not mission.has_recovery_budget():
            logger.error(f"Mission '{mission.mission_id}' recovery budget exhausted.")
            mission.transition_to(MissionState.FAILED)
            await self._record_and_publish_decision(
                mission,
                SupervisoryDecisionType.ABORT,
                "Autonomous recovery budget exhausted",
                evidence,
                urgency=DecisionUrgency.CRITICAL
            )
            return

        # Check if recoverable
        mission.transition_to(MissionState.DEGRADED)
        mission.recovery_attempts_used += 1
        await self._record_and_publish_decision(
            mission,
            SupervisoryDecisionType.RECOVER,
            f"Reactive recovery triggered by {trigger}",
            evidence,
            urgency=DecisionUrgency.HIGH
        )

    # --- Periodic Supervisory Assessment Loop ---

    async def _supervision_loop(self):
        """Periodically evaluates all active missions with an adaptive interval."""
        while self.is_running:
            try:
                active_count = sum(1 for m in self.missions.values() if not m.is_terminal())
                if active_count > 0:
                    self.supervisory_state = SupervisoryState.ASSESSING
                    has_degraded = False

                    # Check deadlocks across all active tasks
                    is_deadlock, cycle, victim = self.res_supervisor.detect_deadlock()
                    if is_deadlock and victim:
                        for m in self.missions.values():
                            if m.active_task_id == victim:
                                logger.warning(f"Deadlock broken: Pausing victim mission '{m.mission_id}' (task {victim})")
                                await self.pause_mission(m.mission_id, reason="Deadlock cycle broken by supervisor")
                                break

                    # Check resource pressure
                    pressure, metrics = self.res_supervisor.get_system_resource_pressure()

                    for m in list(self.missions.values()):
                        if m.is_terminal() or m.status == MissionState.PAUSED:
                            continue

                        # Check Deadline
                        now = time.time()
                        if now > m.deadline_ts:
                            logger.error(f"Mission '{m.mission_id}' deadline expired.")
                            m.transition_to(MissionState.TIMED_OUT)
                            await self._record_and_publish_decision(
                                m,
                                SupervisoryDecisionType.ABORT,
                                "Mission hard deadline exceeded",
                                {"deadline_ts": m.deadline_ts}
                            )
                            continue

                        # Check Progress / Stall
                        stall_class, stall_reason, elapsed = self.hb_monitor.assess_stall(
                            m.mission_id,
                            m.expected_progress_interval_sec,
                            m.warning_threshold_sec,
                            m.hard_timeout_sec
                        )

                        if stall_class in {StallClassification.STALLED, StallClassification.NO_PROGRESS, StallClassification.LOOP}:
                            has_degraded = True
                            if not m.has_recovery_budget():
                                logger.error(f"Mission '{m.mission_id}' stalled and out of recovery budget.")
                                m.transition_to(MissionState.FAILED)
                                await self._record_and_publish_decision(
                                    m,
                                    SupervisoryDecisionType.ABORT,
                                    f"Stall recovery budget exhausted ({stall_reason})",
                                    {"stall_classification": stall_class.value, "reason": stall_reason}
                                )
                            else:
                                m.transition_to(MissionState.DEGRADED)
                                m.recovery_attempts_used += 1
                                await self._record_and_publish_decision(
                                    m,
                                    SupervisoryDecisionType.REPLAN if stall_class == StallClassification.LOOP else SupervisoryDecisionType.RECOVER,
                                    stall_reason,
                                    {"stall_classification": stall_class.value, "elapsed_sec": elapsed}
                                )

                    # Adaptive frequency: faster if degraded, slower if healthy
                    self._adaptive_interval_sec = 0.5 if has_degraded else 2.0
                else:
                    self.supervisory_state = SupervisoryState.SUPERVISING
                    self._adaptive_interval_sec = 3.0

            except Exception as e:
                logger.error(f"Exception during supervisory loop tick: {e}", exc_info=True)

            await asyncio.sleep(self._adaptive_interval_sec)

    # --- Decision Recording & Event Publication ---

    async def _record_and_publish_decision(
        self,
        mission: Mission,
        decision_type: SupervisoryDecisionType,
        reason: str,
        evidence: Dict[str, Any],
        confidence: DecisionConfidence = DecisionConfidence.HIGH,
        urgency: DecisionUrgency = DecisionUrgency.NORMAL,
        recommended_action: str = ""
    ) -> SupervisoryDecision:
        """Builds, archives, and broadcasts a formal SupervisoryDecision."""
        self.supervisory_state = SupervisoryState.DECIDING
        decision = SupervisoryDecision(
            mission_id=mission.mission_id,
            task_id=mission.active_task_id,
            decision=decision_type,
            reason=reason,
            evidence=evidence,
            confidence=confidence,
            urgency=urgency,
            recommended_action=recommended_action or decision_type.value
        )
        self.decisions_history.setdefault(mission.mission_id, []).append(decision)

        # Map decision to typed Event Fabric event
        event_type_map = {
            SupervisoryDecisionType.CONTINUE: "mission.progress",
            SupervisoryDecisionType.RECOVER: "mission.recovery_started",
            SupervisoryDecisionType.REPLAN: "mission.replanned",
            SupervisoryDecisionType.REQUEST_APPROVAL: "mission.approval_required",
            SupervisoryDecisionType.PAUSE: "mission.degraded",
            SupervisoryDecisionType.ABORT: "mission.aborted",
            SupervisoryDecisionType.ESCALATE: "mission.degraded"
        }
        mapped_etype = event_type_map.get(decision_type, "mission.degraded")
        
        await self._publish_mission_event(mapped_etype, mission, {
            "decision": decision_type.value,
            "reason": reason,
            "evidence": evidence
        })

        self.supervisory_state = SupervisoryState.SUPERVISING
        return decision

    async def _publish_mission_event(self, event_type: str, mission: Mission, payload: Dict[str, Any]):
        """Publishes a typed mission lifecycle event into the Event Fabric."""
        prio = EventPriority.HIGH if mission.status in {MissionState.DEGRADED, MissionState.RECOVERING, MissionState.FAILED} else EventPriority.NORMAL
        sev = EventSeverity.WARNING if mission.status in {MissionState.DEGRADED, MissionState.FAILED} else EventSeverity.INFO
        
        full_payload = {
            "mission_id": mission.mission_id,
            "status": mission.status.value,
            "phase": mission.phase.value,
            "progress": mission.progress,
            **payload
        }

        evt = Event(
            envelope=EventEnvelope(
                event_type=event_type,
                correlation_id=mission.mission_id,
                task_id=mission.active_task_id,
                source="module.19.supervisor",
                priority=prio,
                severity=sev,
                durability=EventDurability.DURABLE
            ),
            payload=full_payload
        )
        try:
            await self.fabric.publish(evt)
        except Exception as e:
            logger.error(f"Failed to publish mission event '{event_type}': {e}")

autonomous_supervisor = AutonomousSupervisor()
