"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Process Intelligence Orchestrator: Unified Facade and Event Fabric Integration.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from events import EventFabric, event_fabric
from process_intelligence.bottlenecks import BottleneckDetectionEngine
from process_intelligence.candidates import OptimizationCandidateGenerator
from process_intelligence.conformance import ProcessConformanceAnalyzer
from process_intelligence.discovery import WorkflowDiscoveryEngine
from process_intelligence.experiments import ImprovementExperimentManager
from process_intelligence.failures import FailurePatternDetector
from process_intelligence.governance import WorkflowChangeGovernance
from process_intelligence.graph import ProcessGraphBuilder
from process_intelligence.models import (
    BottleneckFinding,
    ExecutionTraceRecord,
    OptimizationCandidate,
    OptimizationExperimentRecord,
    ProcessDeviationRecord,
    ProcessEventRecord,
    ProcessEventType,
    ProcessGraphRecord,
    WorkflowChangeGovernanceRecord,
    WorkflowPerformanceSnapshot,
)
from process_intelligence.performance import WorkflowPerformanceAnalyzer
from process_intelligence.persistence import ProcessIntelligenceRepository
from process_intelligence.reporting import ProcessIntelligenceReporter
from process_intelligence.simulation import WorkflowSimulationAdapter

logger = logging.getLogger("Omnia.Process.Service")


class ProcessIntelligenceOrchestrator:
    """
    Central orchestration facade for Module 39.
    Provides unified discovery, graph generation, performance and bottleneck analysis,
    candidate synthesis, simulation, controlled experiment management, and change governance.
    """

    def __init__(
        self,
        repository: Optional[ProcessIntelligenceRepository] = None,
        bus: Optional[EventFabric] = None,
    ):
        self.repo = repository or ProcessIntelligenceRepository()
        self.bus = bus or event_fabric

        self.discovery = WorkflowDiscoveryEngine(self.repo)
        self.graph = ProcessGraphBuilder(self.repo)
        self.performance = WorkflowPerformanceAnalyzer(self.repo)
        self.bottlenecks = BottleneckDetectionEngine(self.repo)
        self.conformance = ProcessConformanceAnalyzer(self.repo)
        self.failures = FailurePatternDetector(self.repo)
        self.candidates = OptimizationCandidateGenerator(self.repo)
        self.simulation = WorkflowSimulationAdapter(self.repo)
        self.experiments = ImprovementExperimentManager(self.repo)
        self.governance = WorkflowChangeGovernance(self.repo)
        self.reporting = ProcessIntelligenceReporter(self.repo)

    def _publish_event(self, topic: str, payload: Dict[str, Any]) -> None:
        if self.bus and hasattr(self.bus, "publish"):
            try:
                from events.models import EventEnvelope
                envelope = EventEnvelope(
                    event_type=topic,
                    source="module39.process_intelligence",
                    payload=payload,
                )
                self.bus.publish(envelope)
            except Exception as e:
                logger.debug(f"Event bus emit skipped: {e}")

    # Facade operations
    def record_event(
        self,
        trace_id: str,
        workflow_id: str,
        task_id: str,
        event_type: ProcessEventType,
        timestamp: Optional[str] = None,
        parent_task_id: Optional[str] = None,
        duration_sec: float = 0.0,
        waiting_time_sec: float = 0.0,
        error_category: Optional[str] = None,
        resource_id: Optional[str] = None,
        metadata_payload: Optional[Dict[str, Any]] = None,
    ) -> ProcessEventRecord:
        evt = self.discovery.record_process_event(
            trace_id=trace_id,
            workflow_id=workflow_id,
            task_id=task_id,
            event_type=event_type,
            timestamp=timestamp,
            parent_task_id=parent_task_id,
            duration_sec=duration_sec,
            waiting_time_sec=waiting_time_sec,
            error_category=error_category,
            resource_id=resource_id,
            metadata_payload=metadata_payload,
        )
        self._publish_event("process.event.received", {"trace_id": trace_id, "task_id": task_id, "event_type": event_type.value})
        return evt

    def reconstruct_trace(self, trace_id: str) -> ExecutionTraceRecord:
        trace = self.discovery.reconstruct_trace(trace_id)
        self._publish_event("process.trace.reconstructed", {"trace_id": trace_id, "workflow_id": trace.workflow_id, "duration": trace.total_duration_sec})
        return trace

    def build_process_graph(self, workflow_id: str, version: int = 1) -> ProcessGraphRecord:
        g = self.graph.build_graph_for_workflow(workflow_id, version)
        self._publish_event("process.graph.updated", {"workflow_id": workflow_id, "version": version, "nodes_count": len(g.nodes)})
        return g

    def analyze_performance(self, workflow_id: str) -> WorkflowPerformanceSnapshot:
        snap = self.performance.analyze_workflow_performance(workflow_id)
        self._publish_event("process.performance.analyzed", {"workflow_id": workflow_id, "mean_duration": snap.mean_duration_sec})
        return snap

    def detect_bottlenecks(self, workflow_id: str) -> List[BottleneckFinding]:
        findings = self.bottlenecks.detect_bottlenecks(workflow_id)
        for f in findings:
            self._publish_event("process.bottleneck.detected", {"workflow_id": workflow_id, "component_id": f.component_id, "type": f.bottleneck_type.value})
        return findings

    def audit_conformance(self, trace_id: str, mandatory_steps: List[str]) -> List[ProcessDeviationRecord]:
        devs = self.conformance.audit_trace_conformance(trace_id, mandatory_steps)
        for d in devs:
            self._publish_event("process.deviation.detected", {"trace_id": trace_id, "deviation_type": d.deviation_type.value})
        return devs

    def generate_optimizations(self, workflow_id: str, version: int = 1) -> List[OptimizationCandidate]:
        cands = self.candidates.generate_candidates_from_bottlenecks(workflow_id, version)
        for c in cands:
            self._publish_event("process.optimization.proposed", {"candidate_id": c.candidate_id, "workflow_id": workflow_id})
        return cands

    def simulate_optimization(self, candidate_id: str) -> Dict[str, Any]:
        sim = self.simulation.simulate_candidate_impact(candidate_id)
        self._publish_event("process.simulation.completed", {"candidate_id": candidate_id, "speedup": sim["simulated_speedup_pct"]})
        return sim

    def run_experiment(
        self,
        candidate_id: str,
        workflow_id: str,
        observed_speedup: float,
        error_rate: float,
        latency_spike_pct: float = 0.0,
    ) -> OptimizationExperimentRecord:
        exp = self.experiments.create_experiment(candidate_id, workflow_id)
        evaluated = self.experiments.evaluate_experiment_telemetry(
            experiment_id=exp.experiment_id,
            observed_improvement_pct=observed_speedup,
            current_error_rate=error_rate,
            latency_spike_pct=latency_spike_pct,
        )
        if evaluated.is_guardrail_breached:
            self._publish_event("process.rollback.required", {"experiment_id": exp.experiment_id, "candidate_id": candidate_id})
        else:
            self._publish_event("process.improvement.verified", {"experiment_id": exp.experiment_id, "improvement": observed_speedup})
        return evaluated

    def submit_and_approve_change(
        self,
        workflow_id: str,
        candidate_id: str,
        from_version: int,
        to_version: int,
        approver: str,
        approval_token: str,
    ) -> WorkflowChangeGovernanceRecord:
        gov = self.governance.submit_change_for_approval(workflow_id, candidate_id, from_version, to_version)
        approved = self.governance.approve_workflow_change(gov.governance_id, approver, approval_token)
        self._publish_event("process.change.approved", {"governance_id": gov.governance_id, "workflow_id": workflow_id, "to_version": to_version})
        return approved


# Global singleton instance
process_intelligence_service = ProcessIntelligenceOrchestrator()
