"""
OMNIA Module 36: Component Health Registry & Contract Manager
Maintains component registrations, evaluates liveness/readiness/functional contracts,
tracks status transitions, and enforces heartbeat/staleness intervals.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from observability.models import (
    ComponentHealthRecord,
    ComponentHealthStatus,
    HealthCheckType,
)
from observability.persistence import ObservabilityRepository

logger = logging.getLogger("Omnia.Observability.Components")


class ComponentHealthRegistry:
    """Registry maintaining real-time component health state and contracts."""

    def __init__(self, repo: ObservabilityRepository):
        self.repo = repo
        self._components: Dict[str, ComponentHealthRecord] = {}
        self._load_from_repo()

    def _load_from_repo(self) -> None:
        """Loads registered components from persistence."""
        records = self.repo.list_component_health()
        for r in records:
            self._components[r.component_id] = r

    def register_component(
        self,
        component_id: str,
        component_name: str,
        module_ownership: str,
        version: str = "1.0.0",
        critical_dependencies: Optional[List[str]] = None,
    ) -> ComponentHealthRecord:
        """Registers or updates a component's health tracking contract."""
        record = ComponentHealthRecord(
            component_id=component_id,
            component_name=component_name,
            module_ownership=module_ownership,
            version=version,
            current_status=ComponentHealthStatus.HEALTHY,
            status_message="Registered and initialized",
            critical_dependencies=critical_dependencies or [],
            last_check_timestamp=time.time(),
            last_healthy_timestamp=time.time(),
            liveness_ok=True,
            readiness_ok=True,
            functional_ok=True,
        )
        self._components[component_id] = record
        self.repo.save_component_health(record)
        logger.info(f"Registered component '{component_id}' ({component_name}) under {module_ownership}")
        return record

    def get_component(self, component_id: str) -> Optional[ComponentHealthRecord]:
        """Retrieves a component health record."""
        return self._components.get(component_id) or self.repo.get_component_health(component_id)

    def list_components(self) -> List[ComponentHealthRecord]:
        """Returns all registered component health records."""
        return list(self._components.values())

    def update_health_status(
        self,
        component_id: str,
        status: ComponentHealthStatus,
        message: str,
        liveness_ok: Optional[bool] = None,
        readiness_ok: Optional[bool] = None,
        functional_ok: Optional[bool] = None,
    ) -> Optional[ComponentHealthRecord]:
        """Updates health status, failure count, and timestamps."""
        record = self.get_component(component_id)
        if not record:
            logger.warning(f"Component '{component_id}' not found for health status update")
            return None

        now = time.time()
        record.last_check_timestamp = now
        record.current_status = status
        record.status_message = message

        if liveness_ok is not None:
            record.liveness_ok = liveness_ok
        if readiness_ok is not None:
            record.readiness_ok = readiness_ok
        if functional_ok is not None:
            record.functional_ok = functional_ok

        if status == ComponentHealthStatus.HEALTHY:
            record.last_healthy_timestamp = now
            record.consecutive_failures = 0
        else:
            record.last_failure_timestamp = now
            record.consecutive_failures += 1

        self._components[component_id] = record
        self.repo.save_component_health(record)
        logger.info(f"Updated status for '{component_id}' to {status.value}: {message}")
        return record

    def evaluate_component_health(self, component_id: str) -> ComponentHealthStatus:
        """
        Evaluates health contract according to invariant:
        Healthy only if liveness, readiness, and functional checks pass.
        """
        record = self.get_component(component_id)
        if not record:
            return ComponentHealthStatus.UNKNOWN

        if not record.liveness_ok:
            status = ComponentHealthStatus.UNAVAILABLE
            record.current_status = status
            record.status_message = "Liveness probe failed"
        elif not record.readiness_ok:
            status = ComponentHealthStatus.DEGRADED
            record.current_status = status
            record.status_message = "Readiness probe failed"
        elif not record.functional_ok:
            status = ComponentHealthStatus.UNHEALTHY
            record.current_status = status
            record.status_message = "Functional probe failed"
        else:
            status = ComponentHealthStatus.HEALTHY
            record.current_status = status
            record.status_message = "All health contract criteria satisfied"

        self.repo.save_component_health(record)
        return status
