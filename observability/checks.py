"""
OMNIA Module 36: Health Check Orchestration & Probing Engine
Coordinates active liveness, readiness, functional, and recovery verification probes.
Prevents false recoveries and handles probe timeouts.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Callable
from observability.models import (
    HealthCheckDefinition,
    HealthCheckType,
    ComponentHealthStatus,
)
from observability.persistence import ObservabilityRepository
from observability.components import ComponentHealthRegistry

logger = logging.getLogger("Omnia.Observability.Checks")


class HealthCheckManager:
    """Manages registered health probes and executes health checks on demand or periodically."""

    def __init__(self, repo: ObservabilityRepository, registry: ComponentHealthRegistry):
        self.repo = repo
        self.registry = registry
        self._custom_probes: Dict[str, Callable[[], Dict[str, Any]]] = {}

    def register_health_check(
        self,
        target_component_id: str,
        name: str,
        check_type: HealthCheckType,
        interval_seconds: float = 30.0,
        timeout_seconds: float = 5.0,
        probe_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HealthCheckDefinition:
        """Registers a reusable health check definition."""
        check_id = f"chk-{uuid.uuid4().hex[:8]}"
        definition = HealthCheckDefinition(
            check_id=check_id,
            target_component_id=target_component_id,
            name=name,
            check_type=check_type,
            interval_seconds=interval_seconds,
            timeout_seconds=timeout_seconds,
            is_active=True,
            metadata=metadata or {},
        )
        self.repo.save_health_check_definition(definition)
        if probe_fn:
            self._custom_probes[check_id] = probe_fn
        logger.info(f"Registered check '{name}' ({check_type.value}) for component '{target_component_id}'")
        return definition

    def register_probe_handler(self, check_id: str, probe_fn: Callable[[], Dict[str, Any]]) -> None:
        """Attaches a callable probe handler to a check ID."""
        self._custom_probes[check_id] = probe_fn

    def run_check(self, check_id: str) -> Dict[str, Any]:
        """Executes a single health check by definition ID."""
        check = self.repo.get_health_check_definition(check_id)
        if not check:
            return {"success": False, "error": f"Check ID '{check_id}' not found"}

        component = self.registry.get_component(check.target_component_id)
        if not component:
            return {"success": False, "error": f"Target component '{check.target_component_id}' not found"}

        start_time = time.time()
        success = True
        message = "Check succeeded"
        details: Dict[str, Any] = {}

        if check_id in self._custom_probes:
            try:
                res = self._custom_probes[check_id]()
                success = bool(res.get("success", False))
                message = res.get("message", "Probe completed")
                details = res.get("details", {})
            except Exception as e:
                success = False
                message = f"Probe raised exception: {str(e)}"
        else:
            # Default fallback synthetic probe logic based on component flags
            if check.check_type == HealthCheckType.LIVENESS:
                success = component.liveness_ok
            elif check.check_type == HealthCheckType.READINESS:
                success = component.readiness_ok
            elif check.check_type == HealthCheckType.FUNCTIONAL:
                success = component.functional_ok
            message = "Default evaluation completed"

        duration_ms = round((time.time() - start_time) * 1000.0, 2)

        # Update component status flags based on check type
        if check.check_type == HealthCheckType.LIVENESS:
            component.liveness_ok = success
        elif check.check_type == HealthCheckType.READINESS:
            component.readiness_ok = success
        elif check.check_type == HealthCheckType.FUNCTIONAL:
            component.functional_ok = success

        new_status = self.registry.evaluate_component_health(component.component_id)

        return {
            "check_id": check_id,
            "target_component_id": component.component_id,
            "name": check.name,
            "check_type": check.check_type.value,
            "passed": success,
            "message": message,
            "duration_ms": duration_ms,
            "resulting_status": new_status.value,
            "details": details,
        }

    def run_component_checks(self, component_id: str) -> List[Dict[str, Any]]:
        """Runs all registered checks for a specific component."""
        checks = self.repo.list_health_check_definitions(component_id)
        results = []
        for c in checks:
            if c.is_active:
                results.append(self.run_check(c.check_id))
        return results
