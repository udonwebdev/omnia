import time
import logging
from typing import Dict, List, Optional

from scheduler.models import ExecutionSlot

logger = logging.getLogger("Omnia.Scheduler.Workers")

class WorkerSlotManager:
    """Manages execution slots, worker capacity, and work-stealing compatibility."""

    def __init__(self):
        self._slots: Dict[str, ExecutionSlot] = {}
        self._initialize_default_slots()

    def _initialize_default_slots(self):
        """Creates baseline execution workers."""
        self.register_slot("slot_local_01", "Local Execution Worker 1", worker_type="LOCAL", supported_caps=["*"])
        self.register_slot("slot_local_02", "Local Execution Worker 2", worker_type="LOCAL", supported_caps=["*"])
        self.register_slot("slot_browser_01", "Browser Automation Worker", worker_type="BROWSER", supported_caps=["browser.*"])
        self.register_slot("slot_adb_01", "ADB Mesh Device Worker", worker_type="ADB", supported_caps=["device.android.*"])

    def register_slot(
        self,
        slot_id: str,
        name: str,
        worker_type: str = "LOCAL",
        capacity: float = 1.0,
        supported_caps: Optional[List[str]] = None
    ) -> ExecutionSlot:
        slot = ExecutionSlot(
            slot_id=slot_id,
            slot_name=name,
            worker_type=worker_type,
            capacity=capacity,
            supported_capabilities=supported_caps or ["*"],
            health="HEALTHY",
            updated_at=time.time()
        )
        self._slots[slot_id] = slot
        return slot

    def unregister_slot(self, slot_id: str):
        self._slots.pop(slot_id, None)

    def find_compatible_idle_slot(self, required_caps: List[str], worker_type_preference: Optional[str] = None) -> Optional[ExecutionSlot]:
        """Finds an idle slot compatible with required capabilities."""
        for slot in self._slots.values():
            if not slot.is_idle:
                continue

            if worker_type_preference and slot.worker_type != worker_type_preference and slot.worker_type != "LOCAL":
                continue

            # Check capability compatibility
            if "*" in slot.supported_capabilities:
                return slot

            caps_match = all(
                any(sc == rc or sc.endswith(".*") and rc.startswith(sc[:-2]) for sc in slot.supported_capabilities)
                for rc in required_caps
            )
            if caps_match:
                return slot

        return None

    def assign_slot(self, slot_id: str, schedule_id: str, task_id: str) -> bool:
        slot = self._slots.get(slot_id)
        if not slot or not slot.is_idle:
            return False
        slot.current_schedule_id = schedule_id
        slot.current_task_id = task_id
        slot.updated_at = time.time()
        return True

    def release_slot(self, slot_id: str) -> bool:
        slot = self._slots.get(slot_id)
        if not slot:
            return False
        slot.current_schedule_id = None
        slot.current_task_id = None
        slot.updated_at = time.time()
        return True

    def release_by_schedule(self, schedule_id: str):
        for slot in self._slots.values():
            if slot.current_schedule_id == schedule_id:
                slot.current_schedule_id = None
                slot.current_task_id = None
                slot.updated_at = time.time()

    def list_slots(self) -> List[ExecutionSlot]:
        return list(self._slots.values())

    def get_idle_slots_count(self) -> int:
        return sum(1 for s in self._slots.values() if s.is_idle)

worker_slot_manager = WorkerSlotManager()
