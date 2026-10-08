import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple

from scheduler.models import (
    ResourceReservation,
    ResourceRequirement,
    ReservationState,
    ResourceConflictType,
    ResourceAccessMode
)
from scheduler.resources import resource_registry, ResourceRegistry

logger = logging.getLogger("Omnia.Scheduler.Reservations")

class ReservationManager:
    """Manages transactional, atomic multi-resource reservations and leases."""

    def __init__(self, registry: Optional[ResourceRegistry] = None):
        self.registry = registry or resource_registry
        self._reservations: Dict[str, ResourceReservation] = {}  # reservation_id -> record
        self._schedule_reservations: Dict[str, List[str]] = {}   # schedule_id -> [reservation_ids]

    def reserve_atomic(
        self,
        schedule_id: str,
        task_id: str,
        requirements: List[ResourceRequirement],
        mission_id: Optional[str] = None,
        task_node_id: Optional[str] = None,
        lease_duration_sec: float = 60.0
    ) -> Tuple[bool, List[ResourceReservation], Optional[ResourceConflictType], str]:
        """Atomically acquires all requested resources in deterministic sorted order to prevent deadlocks.
        If any single resource is unavailable, all staged reservations are rolled back completely.
        """
        if not requirements:
            return True, [], None, "No resources requested."

        # Invariant 36: Acquire in deterministic sorted order by resource_id to prevent deadlocks
        sorted_reqs = sorted(requirements, key=lambda r: r.resource_id)

        # 1. Verification Phase: Ensure ALL requested resources are available
        for req in sorted_reqs:
            avail, conflict = self.registry.check_availability(req)
            if not avail:
                return False, [], conflict, f"Resource '{req.resource_id}' unavailable ({conflict.value})."

        # 2. Acquisition Phase: Atomically allocate and issue leases
        staged_reservations: List[ResourceReservation] = []
        now = time.time()
        lease_id = f"lease_{uuid.uuid4().hex[:8]}"

        for req in sorted_reqs:
            allocated = self.registry.allocate(req, owner_id=schedule_id)
            if not allocated:
                # Rollback all previously staged allocations
                logger.error(f"Atomic reservation collision during staging: Rolling back {len(staged_reservations)} resources.")
                for staged in staged_reservations:
                    self.registry.release(staged.resource_id, owner_id=schedule_id, amount=staged.amount)
                return False, [], ResourceConflictType.EXCLUSIVE_CONFLICT, f"Atomic allocation failed for {req.resource_id}."

            rsv = ResourceReservation(
                reservation_id=f"rsv_{uuid.uuid4().hex[:8]}",
                schedule_id=schedule_id,
                mission_id=mission_id,
                task_id=task_id,
                task_node_id=task_node_id,
                resource_id=req.resource_id,
                resource_type=req.resource_type,
                access_mode=req.access_mode,
                amount=req.amount,
                created_at=now,
                expires_at=now + lease_duration_sec,
                state=ReservationState.ACTIVE,
                lease_id=lease_id,
                lease_heartbeat=now
            )
            staged_reservations.append(rsv)

        # 3. Commit Phase: Register reservations
        for rsv in staged_reservations:
            self._reservations[rsv.reservation_id] = rsv
            self._schedule_reservations.setdefault(schedule_id, []).append(rsv.reservation_id)

        logger.info(f"Atomic reservation committed for schedule '{schedule_id}': {[r.resource_id for r in staged_reservations]}")
        return True, staged_reservations, None, "Atomic reservation granted."

    def release_schedule_reservations(self, schedule_id: str, reason: str = "COMPLETED") -> int:
        """Releases all active resource reservations held by a schedule."""
        rsv_ids = self._schedule_reservations.pop(schedule_id, [])
        count = 0
        for rid in rsv_ids:
            rsv = self._reservations.get(rid)
            if rsv and rsv.state == ReservationState.ACTIVE:
                self.registry.release(rsv.resource_id, owner_id=schedule_id, amount=rsv.amount)
                rsv.state = ReservationState.RELEASED
                rsv.release_reason = reason
                count += 1
        return count

    def renew_lease(self, schedule_id: str, extension_sec: float = 30.0) -> bool:
        """Heartbeats and extends active leases for a running schedule."""
        rsv_ids = self._schedule_reservations.get(schedule_id, [])
        if not rsv_ids:
            return False
        now = time.time()
        for rid in rsv_ids:
            rsv = self._reservations.get(rid)
            if rsv and rsv.state == ReservationState.ACTIVE:
                rsv.lease_heartbeat = now
                rsv.expires_at = now + extension_sec
        return True

    def scan_and_reap_expired_leases(self) -> List[str]:
        """Identifies and reclaims reservations whose leases have expired without worker heartbeats."""
        now = time.time()
        reaped_schedules: List[str] = []

        for schedule_id, rsv_ids in list(self._schedule_reservations.items()):
            for rid in rsv_ids:
                rsv = self._reservations.get(rid)
                if rsv and rsv.state == ReservationState.ACTIVE and rsv.is_expired(now):
                    logger.warning(f"Lease expired for schedule '{schedule_id}' on resource '{rsv.resource_id}'. Reclaiming.")
                    self.release_schedule_reservations(schedule_id, reason="LEASE_EXPIRED")
                    reaped_schedules.append(schedule_id)
                    break

        return reaped_schedules

    def get_active_reservations(self) -> List[ResourceReservation]:
        return [r for r in self._reservations.values() if r.state == ReservationState.ACTIVE]

reservation_manager = ReservationManager()
