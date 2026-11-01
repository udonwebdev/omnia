"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Resource Inventory Registry: Multi-Dimensional Hardware, Network & Application Resource Tracking.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from capacity_planning.models import (
    MetricUnit,
    ResourceDimension,
    ResourceInventoryItem,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Inventory")


class ResourceInventoryRegistry:
    """
    Maintains authoritative multi-dimensional view of available, allocated,
    reserved, and consumed resources across Compute, Storage, Networking, and Application dimensions.
    """

    def __init__(self, repository: Optional[CapacityRepository] = None):
        self.repo = repository or CapacityRepository()

    def register_resource(
        self,
        resource_id: str,
        resource_name: str,
        dimension: ResourceDimension,
        resource_type: str,
        source: str,
        total_capacity: float,
        unit: MetricUnit,
        associated_service: str = "omnia-core",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResourceInventoryItem:
        """Enrolls or updates an infrastructure resource item."""
        if total_capacity <= 0:
            raise ValueError(f"Total capacity for '{resource_id}' must be strictly positive (got {total_capacity}).")

        item = ResourceInventoryItem(
            resource_id=resource_id,
            resource_name=resource_name,
            dimension=dimension,
            resource_type=resource_type,
            source=source,
            total_capacity=total_capacity,
            unit=unit,
            associated_service=associated_service,
            metadata=metadata or {},
        )
        self.repo.save_resource(item)
        logger.info(f"Registered capacity resource: {resource_id} ({dimension.value} - {total_capacity} {unit.value})")
        return item

    def get_resource(self, resource_id: str) -> Optional[ResourceInventoryItem]:
        return self.repo.get_resource(resource_id)

    def list_resources(self, dimension: Optional[ResourceDimension] = None, active_only: bool = True) -> List[ResourceInventoryItem]:
        items = self.repo.list_resources(active_only=active_only)
        if dimension:
            items = [i for i in items if i.dimension == dimension]
        return items

    def update_resource_capacity(self, resource_id: str, new_capacity: float) -> ResourceInventoryItem:
        item = self.get_resource(resource_id)
        if not item:
            raise KeyError(f"Resource '{resource_id}' not found in capacity inventory.")
        if new_capacity <= 0:
            raise ValueError(f"New capacity must be positive (got {new_capacity}).")

        item.total_capacity = new_capacity
        self.repo.save_resource(item)
        logger.info(f"Updated resource capacity '{resource_id}' -> {new_capacity} {item.unit.value}")
        return item
