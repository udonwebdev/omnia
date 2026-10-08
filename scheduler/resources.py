import time
import logging
from typing import Dict, List, Optional, Set, Tuple

from scheduler.models import (
    ResourceCapacity,
    ResourceRequirement,
    ResourceAccessMode,
    ResourceConflictType
)

logger = logging.getLogger("Omnia.Scheduler.Resources")

class ResourceRegistry:
    """Authoritative inventory and real-time capacity manager for physical and logical resources."""

    def __init__(self):
        self._capacities: Dict[str, ResourceCapacity] = {}
        self._initialize_default_resources()

    def _initialize_default_resources(self):
        """Initializes foundational system resources."""
        # Workstation session & mouse/keyboard
        self.register_resource("desktop:mouse", "INPUT_DEVICE", total_capacity=1.0)
        self.register_resource("desktop:screen", "DISPLAY", total_capacity=1.0)
        self.register_resource("audio:microphone", "AUDIO_INPUT", total_capacity=1.0)
        self.register_resource("audio:speaker", "AUDIO_OUTPUT", total_capacity=1.0)
        
        # Browser session pool (capacity = 5 concurrent sessions)
        self.register_resource("browser:pool", "BROWSER", total_capacity=5.0)

        # Telephony channel pool (capacity = 2 concurrent calls)
        self.register_resource("telephony:pool", "TELEPHONY", total_capacity=2.0)

    def register_resource(self, resource_id: str, resource_type: str, total_capacity: float = 1.0, overcommit_ratio: float = 1.0):
        """Registers a physical or logical resource."""
        self._capacities[resource_id] = ResourceCapacity(
            resource_id=resource_id,
            resource_type=resource_type,
            total_capacity=total_capacity,
            overcommit_ratio=overcommit_ratio
        )

    def unregister_resource(self, resource_id: str):
        self._capacities.pop(resource_id, None)

    def get_capacity(self, resource_id: str) -> Optional[ResourceCapacity]:
        return self._capacities.get(resource_id)

    def list_resources(self) -> List[ResourceCapacity]:
        return list(self._capacities.values())

    def check_availability(self, req: ResourceRequirement) -> Tuple[bool, Optional[ResourceConflictType]]:
        """Checks if a resource requirement can currently be accommodated."""
        cap = self._capacities.get(req.resource_id)
        if not cap:
            return False, ResourceConflictType.RESOURCE_UNAVAILABLE

        if req.access_mode == ResourceAccessMode.EXCLUSIVE:
            if cap.exclusive_owner is not None or len(cap.shared_owners) > 0:
                return False, ResourceConflictType.EXCLUSIVE_CONFLICT
            if cap.available_capacity < req.amount:
                return False, ResourceConflictType.CAPACITY_EXCEEDED
        else:
            if cap.exclusive_owner is not None:
                return False, ResourceConflictType.EXCLUSIVE_CONFLICT
            if cap.available_capacity < req.amount:
                return False, ResourceConflictType.CAPACITY_EXCEEDED

        return True, None

    def allocate(self, req: ResourceRequirement, owner_id: str) -> bool:
        """Allocates capacity to an owner atomically."""
        cap = self._capacities.get(req.resource_id)
        if not cap:
            return False

        if req.access_mode == ResourceAccessMode.EXCLUSIVE:
            if cap.exclusive_owner is not None or len(cap.shared_owners) > 0 or cap.available_capacity < req.amount:
                return False
            cap.exclusive_owner = owner_id
            cap.allocated_capacity += req.amount
            return True
        else:
            if cap.exclusive_owner is not None or cap.available_capacity < req.amount:
                return False
            cap.shared_owners.add(owner_id)
            cap.allocated_capacity += req.amount
            return True

    def release(self, resource_id: str, owner_id: str, amount: float = 1.0) -> bool:
        """Releases allocated capacity back to pool."""
        cap = self._capacities.get(resource_id)
        if not cap:
            return False

        if cap.exclusive_owner == owner_id:
            cap.exclusive_owner = None
            cap.allocated_capacity = max(0.0, cap.allocated_capacity - amount)
            return True
        elif owner_id in cap.shared_owners:
            cap.shared_owners.discard(owner_id)
            cap.allocated_capacity = max(0.0, cap.allocated_capacity - amount)
            return True

        return False

resource_registry = ResourceRegistry()
