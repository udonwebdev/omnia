"""
OMNIA Module 36: Diagnostic Root-Cause Analysis Engine
Synthesizes health status, dependency cascades, trace errors, and metric anomalies
to produce ranked Diagnostic Hypotheses with evidence references and uncertainty scoring.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional
from observability.models import (
    DiagnosticHypothesis,
    FailureCategory,
    ComponentHealthStatus,
)
from observability.persistence import ObservabilityRepository
from observability.components import ComponentHealthRegistry
from observability.dependencies import DependencyGraphBuilder
from observability.detector import OperationalAnomalyDetector

logger = logging.getLogger("Omnia.Observability.Diagnostics")


class DiagnosticEngine:
    """Performs structured root-cause analysis without hallucinating causes."""

    def __init__(
        self,
        repo: ObservabilityRepository,
        registry: ComponentHealthRegistry,
        dep_graph: DependencyGraphBuilder,
        detector: OperationalAnomalyDetector,
    ):
        self.repo = repo
        self.registry = registry
        self.dep_graph = dep_graph
        self.detector = detector

    def diagnose_failure(self, component_id: str) -> List[DiagnosticHypothesis]:
        """
        Investigates a degraded or unhealthy component:
        1. Checks direct component health and recent failure message.
        2. Inspects dependencies (upstream causes).
        3. Scans recent trace spans and metric anomalies.
        4. Synthesizes ranked hypotheses.
        """
        component = self.registry.get_component(component_id)
        if not component:
            return []

        hypotheses: List[DiagnosticHypothesis] = []
        now = time.time()

        # Step 1: Upstream dependency check (Is an upstream dependency down?)
        deps = self.dep_graph.get_dependencies_for(component_id)
        for d in deps:
            target_comp = self.registry.get_component(d.target_component_id)
            if target_comp and target_comp.current_status in (
                ComponentHealthStatus.UNHEALTHY,
                ComponentHealthStatus.UNAVAILABLE,
                ComponentHealthStatus.DEGRADED,
            ):
                # Upstream dependency is failed!
                cascades = self.dep_graph.calculate_cascading_impact(d.target_component_id)
                hypo = DiagnosticHypothesis(
                    hypothesis_id=f"hypo-{uuid.uuid4().hex[:8]}",
                    suspected_component_id=d.target_component_id,
                    failure_category=FailureCategory.DEPENDENCY_FAILURE,
                    confidence=0.92 if d.dependency_type.value == "HARD" else 0.75,
                    explanation=(
                        f"Component '{component_id}' degradation is directly caused by failure of its "
                        f"{d.dependency_type.value} upstream dependency '{d.target_component_id}' "
                        f"(Status: {target_comp.current_status.value})."
                    ),
                    supporting_evidence=[
                        f"Upstream component '{d.target_component_id}' status: {target_comp.current_status.value}",
                        f"Dependency edge type: {d.dependency_type.value}",
                        f"Upstream status message: {target_comp.status_message}",
                    ],
                    contradicting_evidence=[],
                    cascading_impact_components=[c["component_id"] for c in cascades.get("impacted_components", [])],
                    recommended_remediation_action=f"Remediate upstream service '{d.target_component_id}'",
                    timestamp=now,
                )
                hypotheses.append(hypo)
                self.repo.save_diagnostic_hypothesis(hypo)

        # Step 2: Direct component anomalies & error traces
        anomalies = self.detector.analyze_metrics_for_component(component_id)
        traces = self.repo.list_traces(component_id=component_id, status="ERROR", limit=5)

        if anomalies:
            evidence = [a["message"] for a in anomalies]
            cat_str = anomalies[0]["failure_category"]
            category = FailureCategory(cat_str) if cat_str in [c.value for c in FailureCategory] else FailureCategory.PERFORMANCE_DEGRADATION
            hypo = DiagnosticHypothesis(
                hypothesis_id=f"hypo-{uuid.uuid4().hex[:8]}",
                suspected_component_id=component_id,
                failure_category=category,
                confidence=0.85,
                explanation=f"Telemetry indicates metric threshold violations: {anomalies[0]['type']}.",
                supporting_evidence=evidence,
                contradicting_evidence=[],
                cascading_impact_components=[],
                recommended_remediation_action="Scale resources or clear component queues/caches",
                timestamp=now,
            )
            hypotheses.append(hypo)
            self.repo.save_diagnostic_hypothesis(hypo)

        if traces:
            trace_evidence = [f"Trace {t.trace_id} ({t.operation_name}) failed: {t.error_message}" for t in traces]
            first_err = traces[0].error_message or ""
            cat = self.detector.classify_failure_signal(first_err)
            hypo = DiagnosticHypothesis(
                hypothesis_id=f"hypo-{uuid.uuid4().hex[:8]}",
                suspected_component_id=component_id,
                failure_category=cat,
                confidence=0.88,
                explanation=f"Operational trace errors observed during execution: {first_err[:100]}",
                supporting_evidence=trace_evidence,
                contradicting_evidence=[],
                cascading_impact_components=[],
                recommended_remediation_action="Restart worker or reconnect dependent backend",
                timestamp=now,
            )
            hypotheses.append(hypo)
            self.repo.save_diagnostic_hypothesis(hypo)

        # Step 3: Default hypothesis if component is unhealthy but no specific triggers caught
        if not hypotheses and component.current_status != ComponentHealthStatus.HEALTHY:
            hypo = DiagnosticHypothesis(
                hypothesis_id=f"hypo-{uuid.uuid4().hex[:8]}",
                suspected_component_id=component_id,
                failure_category=FailureCategory.UNKNOWN_FAILURE,
                confidence=0.50,
                explanation=f"Component reports unhealthy contract state: {component.status_message}",
                supporting_evidence=[f"Status message: {component.status_message}", f"Liveness={component.liveness_ok}, Readiness={component.readiness_ok}, Functional={component.functional_ok}"],
                contradicting_evidence=[],
                cascading_impact_components=[],
                recommended_remediation_action="Execute full deep diagnostic probe",
                timestamp=now,
            )
            hypotheses.append(hypo)
            self.repo.save_diagnostic_hypothesis(hypo)

        # Sort descending by confidence
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        return hypotheses
