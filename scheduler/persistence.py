import sqlite3
import json
import time
import logging
from typing import Optional, List, Dict, Any

from persistence.store import persistence_store, sanitize_payload
from scheduler.models import (
    ScheduleRequest,
    ResourceReservation,
    SchedulingDecision,
    ExecutionSlot,
    ScheduleState,
    ReservationState,
    ResourceAccessMode,
    SchedulingPriority,
    PreemptionPolicy,
    SchedulingDecisionType,
    ResourceRequirement
)

logger = logging.getLogger("Omnia.Scheduler.Persistence")

class SchedulerPersistenceManager:
    """Manages transactional durability, querying, and crash recovery for the scheduler."""

    def __init__(self, store=None):
        self.store = store or persistence_store

    def save_schedule_request(self, req: ScheduleRequest):
        conn = self.store._get_connection()
        try:
            with conn:
                sanitized_meta = sanitize_payload(req.metadata)
                req_res_dicts = [
                    {"resource_id": r.resource_id, "resource_type": r.resource_type, "access_mode": r.access_mode.value, "amount": r.amount}
                    for r in req.required_resources
                ]
                conn.execute("""
                    INSERT INTO schedule_requests (
                        schedule_id, mission_id, task_id, task_node_id, created_at,
                        ready_at, deadline, priority, urgency, risk_level,
                        estimated_duration_sec, preemption_policy, parallelizable,
                        required_resources_json, exclusive_resources_json, shared_resources_json,
                        required_capabilities_json, required_devices_json, dependencies_json,
                        state, assigned_slot_id, priority_score, wait_count, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(schedule_id) DO UPDATE SET
                        state = excluded.state,
                        assigned_slot_id = excluded.assigned_slot_id,
                        priority_score = excluded.priority_score,
                        wait_count = excluded.wait_count,
                        metadata_json = excluded.metadata_json
                """, (
                    req.schedule_id, req.mission_id, req.task_id, req.task_node_id,
                    req.created_at, req.ready_at, req.deadline, req.priority.name,
                    req.urgency, req.risk_level, req.estimated_duration_sec,
                    req.preemption_policy.value, 1 if req.parallelizable else 0,
                    json.dumps(req_res_dicts), json.dumps([]), json.dumps([]),
                    json.dumps(req.required_capabilities), json.dumps(req.required_devices),
                    json.dumps(req.dependencies), req.state.value, req.assigned_slot_id,
                    req.priority_score, req.wait_count, json.dumps(sanitized_meta)
                ))
        finally:
            conn.close()

    def get_schedule_request(self, schedule_id: str) -> Optional[ScheduleRequest]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedule_requests WHERE schedule_id = ?", (schedule_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_request(row)
        finally:
            conn.close()

    def list_active_schedules(self) -> List[ScheduleRequest]:
        terminal = [ScheduleState.COMPLETED.value, ScheduleState.FAILED.value, ScheduleState.REJECTED.value, ScheduleState.CANCELLED.value]
        placeholders = ",".join(["?"] * len(terminal))
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM schedule_requests WHERE state NOT IN ({placeholders}) ORDER BY priority_score DESC", terminal)
            rows = cursor.fetchall()
            return [self._row_to_request(r) for r in rows]
        finally:
            conn.close()

    def save_reservation(self, rsv: ResourceReservation):
        conn = self.store._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO resource_reservations (
                        reservation_id, schedule_id, mission_id, task_id, task_node_id,
                        resource_id, resource_type, access_mode, amount, created_at,
                        expires_at, state, lease_id, lease_heartbeat, release_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(reservation_id) DO UPDATE SET
                        state = excluded.state,
                        expires_at = excluded.expires_at,
                        lease_heartbeat = excluded.lease_heartbeat,
                        release_reason = excluded.release_reason
                """, (
                    rsv.reservation_id, rsv.schedule_id, rsv.mission_id, rsv.task_id,
                    rsv.task_node_id, rsv.resource_id, rsv.resource_type,
                    rsv.access_mode.value, rsv.amount, rsv.created_at,
                    rsv.expires_at, rsv.state.value, rsv.lease_id,
                    rsv.lease_heartbeat, rsv.release_reason
                ))
        finally:
            conn.close()

    def reconcile_on_startup(self) -> Dict[str, int]:
        """Crash reconciliation: marks stale reservations as EXPIRED / RECOVERABLE."""
        conn = self.store._get_connection()
        try:
            now = time.time()
            with conn:
                # Mark expired active reservations
                cursor = conn.execute(
                    "UPDATE resource_reservations SET state = 'EXPIRED', release_reason = 'CRASH_RECONCILE' WHERE state = 'ACTIVE' AND expires_at < ?",
                    (now,)
                )
                expired_count = cursor.rowcount

                # Reset running schedules that lost workers to WAITING_RESOURCE
                cursor2 = conn.execute(
                    "UPDATE schedule_requests SET state = 'WAITING_RESOURCE' WHERE state = 'RUNNING'"
                )
                recovering_schedules = cursor2.rowcount

                logger.info(f"Scheduler startup reconciliation: {expired_count} reservations expired, {recovering_schedules} schedules reset.")
                return {"expired_reservations": expired_count, "recovering_schedules": recovering_schedules}
        finally:
            conn.close()

    def _row_to_request(self, row: sqlite3.Row) -> ScheduleRequest:
        req_res_dicts = json.loads(row["required_resources_json"] or "[]")
        res_reqs = [
            ResourceRequirement(
                resource_id=d["resource_id"],
                resource_type=d.get("resource_type", "GENERIC"),
                access_mode=ResourceAccessMode(d.get("access_mode", "EXCLUSIVE")),
                amount=d.get("amount", 1.0)
            )
            for d in req_res_dicts
        ]
        return ScheduleRequest(
            schedule_id=row["schedule_id"],
            mission_id=row["mission_id"],
            task_id=row["task_id"],
            task_node_id=row["task_node_id"],
            created_at=row["created_at"],
            ready_at=row["ready_at"] or row["created_at"],
            deadline=row["deadline"],
            priority=SchedulingPriority[row["priority"]],
            urgency=row["urgency"],
            risk_level=row["risk_level"],
            estimated_duration_sec=row["estimated_duration_sec"],
            preemption_policy=PreemptionPolicy(row["preemption_policy"]),
            parallelizable=bool(row["parallelizable"]),
            required_resources=res_reqs,
            required_capabilities=json.loads(row["required_capabilities_json"] or "[]"),
            required_devices=json.loads(row["required_devices_json"] or "[]"),
            dependencies=json.loads(row["dependencies_json"] or "[]"),
            state=ScheduleState(row["state"]),
            assigned_slot_id=row["assigned_slot_id"],
            priority_score=row["priority_score"],
            wait_count=row["wait_count"],
            metadata=json.loads(row["metadata_json"] or "{}")
        )

scheduler_persistence_manager = SchedulerPersistenceManager()
