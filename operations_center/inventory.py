"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Service Inventory Registry: Hierarchical Component Catalog & Dependency Mapping.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from operations_center.models import (
    ServiceCriticality,
    ServiceRecord,
    SystemHealthState,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.Inventory")


class ServiceInventoryRegistry:
    """Manages centralized registration, dependencies, and metadata of Omnia services."""

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def register_service(
        self,
        service_id: str,
        service_name: str,
        description: str,
        version: str,
        environment: str,
        owner: str,
        criticality: ServiceCriticality = ServiceCriticality.HIGH,
        health_endpoint: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
    ) -> ServiceRecord:
        """Registers a service or subsystem component into the unified inventory."""
        service = ServiceRecord(
            service_id=service_id,
            service_name=service_name,
            description=description,
            version=version,
            environment=environment,
            owner=owner,
            criticality=criticality,
            health_endpoint=health_endpoint,
            dependencies=dependencies or [],
            current_state=SystemHealthState.UNKNOWN,
        )
        self.repo.save_service(service)
        logger.info(f"Registered service '{service_id}': {service_name} [{criticality.value}]")
        return service

    def update_dependencies(self, service_id: str, dependencies: List[str]) -> ServiceRecord:
        """Updates operational dependencies for a service."""
        service = self.repo.get_service(service_id)
        if not service:
            raise ValueError(f"Service '{service_id}' not found.")
        service.dependencies = dependencies
        self.repo.save_service(service)
        return service

    def get_service_dependencies(self, service_id: str) -> List[str]:
        """Returns direct dependencies of a service."""
        service = self.repo.get_service(service_id)
        if not service:
            raise ValueError(f"Service '{service_id}' not found.")
        return service.dependencies

    def get_downstream_dependents(self, service_id: str) -> List[str]:
        """Returns all services in inventory that directly depend on service_id."""
        dependents = []
        for s in self.repo.list_services():
            if service_id in s.dependencies:
                dependents.append(s.service_id)
        return dependents
