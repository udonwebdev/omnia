"""
OMNIA Module 36: Observability Master Service & Event Fabric Integration
Main facade orchestrating metrics, tracing, component health, dependency graphs,
diagnostics, and remediation verification. Integrates with the OMNIA Event Fabric.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from observability.models import (
    OperationalMetric,
    TraceSpan,
    ComponentHealthRecord,
    HealthCheckDefinition,
    InfrastructureDependencyEdge,
    DiagnosticHypothesis,
    InfrastructureRemediationAction,
    ComponentHealthStatus,
    HealthCheckType,
    DependencyType,
    RemediationAutonomyLevel,
)
from observability.persistence import ObservabilityRepository
from observability.telemetry import OperationalTelemetryCollector
from observability.components import ComponentHealthRegistry
from observability.checks import HealthCheckManager
from observability.dependencies import DependencyGraphBuilder
from observability.detector import OperationalAnomalyDetector
from observability.diagnostics import DiagnosticEngine
from observability.remediation import RemediationPlanner
from observability.verification import RecoveryVerifier

logger = logging.getLogger("Omnia.Observability.Service")


class ObservabilityService:
    """Unified service facade for autonomous observability, diagnostics, and self-healing."""

    def __init__(self, db_path: str = "omnia.db", event_bus: Optional[Any] = None):
        self.repo = ObservabilityRepository(db_path=db_path)
        self.telemetry = OperationalTelemetryCollector()
        self.registry = ComponentHealthRegistry(self.repo)
        self.checks = HealthCheckManager(self.repo, self.registry)
        self.dependencies = DependencyGraphBuilder(self.repo)
        self.detector = OperationalAnomalyDetector(self.repo)
        self.diagnostics = DiagnosticEngine(self.repo, self.registry, self.dependencies, self.detector)
        self.remediation = RemediationPlanner(self.repo)
        self.verification = RecoveryVerifier(self.repo, self.registry, self.checks)
        self.event_bus = event_bus

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publishes observability events to the Omnia Event Fabric if available."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                from events.models import EventEnvelope
                envelope = EventEnvelope(
                    topic=topic,
                    payload=payload,
                    source="observability.service",
                )
                self.event_bus.publish(envelope)
            except Exception as e:
                logger.debug(f"Event bus emit skipped or failed: {e}")

    # Core Operations
    def register_component(
        self,
        component_id: str,
        component_name: str,
        module_ownership: str,
        version: str = "1.0.0",
        critical_dependencies: Optional[List[str]] = None,
    ) -> ComponentHealthRecord:
        """Registers an observable component."""
        rec = self.registry.register_component(
            component_id=component_id,
            component_name=component_name,
            module_ownership=module_ownership,
            version=version,
            critical_dependencies=critical_dependencies,
        )
        self._emit_event("observability.component.registered", rec.to_dict())
        return rec

    def record_metric(
        self,
        component_id: str,
        metric_name: str,
        value: float,
        unit: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> OperationalMetric:
        """Records telemetry metric in-memory and persists it."""
        metric = self.telemetry.record_metric(
            component_id=component_id,
            metric_name=metric_name,
            value=value,
            unit=unit,
            labels=labels,
        )
        self.repo.save_metric(metric)
        return metric

    def record_trace(
        self,
        operation_name: str,
        component_id: str,
        duration_ms: float,
        status: str = "OK",
        error: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> TraceSpan:
        """Records and persists a completed trace span with sanitized logs."""
        span = self.telemetry.start_trace_span(
            operation_name=operation_name,
            component_id=component_id,
            tags=tags,
        )
        span.duration_ms = duration_ms
        span.end_time = span.start_time + (duration_ms / 1000.0)
        span.finish(status=status, error=self.telemetry.sanitize_log_text(error) if error else None)
        self.repo.save_trace(span)
        return span

    def add_dependency(
        self,
        source_component_id: str,
        target_component_id: str,
        dependency_type: DependencyType = DependencyType.HARD,
        criticality: float = 1.0,
    ) -> InfrastructureDependencyEdge:
        """Adds an infrastructure dependency edge."""
        edge = self.dependencies.add_dependency(
            source_component_id=source_component_id,
            target_component_id=target_component_id,
            dependency_type=dependency_type,
            criticality=criticality,
        )
        self._emit_event("observability.dependency.added", edge.to_dict())
        return edge

    def register_health_check(
        self,
        target_component_id: str,
        name: str,
        check_type: HealthCheckType,
        interval_seconds: float = 30.0,
        timeout_seconds: float = 5.0,
        probe_fn: Optional[callable] = None,
    ) -> HealthCheckDefinition:
        """Registers a health check probe."""
        return self.checks.register_health_check(
            target_component_id=target_component_id,
            name=name,
            check_type=check_type,
            interval_seconds=interval_seconds,
            timeout_seconds=timeout_seconds,
            probe_fn=probe_fn,
        )

    def run_health_checks(self, component_id: str) -> List[Dict[str, Any]]:
        """Runs health checks for a component and emits alerts if unhealthy."""
        results = self.checks.run_component_checks(component_id)
        comp = self.registry.get_component(component_id)
        if comp and comp.current_status != ComponentHealthStatus.HEALTHY:
            self._emit_event("observability.health.degraded", comp.to_dict())
        return results

    def diagnose_failure(self, component_id: str) -> List[DiagnosticHypothesis]:
        """Diagnoses failure causes and produces ranked hypotheses."""
        hypos = self.diagnostics.diagnose_failure(component_id)
        if hypos:
            self._emit_event("observability.diagnosis.created", {
                "component_id": component_id,
                "top_hypothesis": hypos[0].to_dict(),
            })
        return hypos

    def plan_remediation(
        self,
        target_component_id: str,
        hypothesis: DiagnosticHypothesis,
        autonomy_level: RemediationAutonomyLevel = RemediationAutonomyLevel.LEVEL_3_LOW_RISK_AUTO,
        proposed_action: Optional[str] = None,
        verification_window_seconds: float = 10.0,
    ) -> InfrastructureRemediationAction:
        """Plans a remediation action."""
        action = self.remediation.plan_remediation(
            target_component_id=target_component_id,
            hypothesis=hypothesis,
            autonomy_level=autonomy_level,
            proposed_action=proposed_action,
            verification_window_seconds=verification_window_seconds,
        )
        self._emit_event("observability.remediation.planned", action.to_dict())
        return action

    def authorize_remediation(self, action_id: str, approval_token: str) -> bool:
        """Authorizes an approval-gated remediation action."""
        return self.remediation.authorize_remediation(action_id, approval_token)

    def execute_and_verify(
        self,
        action_id: str,
        custom_action_executor: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """Executes remediation and verifies recovery."""
        res = self.verification.execute_and_verify(
            action_id=action_id,
            custom_action_executor=custom_action_executor,
        )
        self._emit_event("observability.remediation.verified", res)
        return res


# Global singleton
observability_service = ObservabilityService()
