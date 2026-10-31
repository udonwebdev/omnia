"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Process Intelligence Reporting: Performance Summaries & Optimization Briefings.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Reporting")


class ProcessIntelligenceReporter:
    """Generates comprehensive process intelligence briefings for individual workflows and portfolios."""

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def generate_workflow_briefing(self, workflow_id: str) -> Dict[str, Any]:
        """Generates an executive process intelligence briefing for a single workflow."""
        perf = self.repo.get_latest_performance_snapshot(workflow_id)
        graph = self.repo.get_latest_graph_for_workflow(workflow_id)
        bottlenecks = self.repo.list_bottlenecks_for_workflow(workflow_id)
        deviations = self.repo.list_deviations(workflow_id)
        failures = self.repo.list_failure_patterns(workflow_id)
        candidates = self.repo.list_candidates_for_workflow(workflow_id)

        return {
            "workflow_id": workflow_id,
            "trace_count": perf.trace_count if perf else 0,
            "performance": {
                "mean_duration_sec": perf.mean_duration_sec if perf else 0.0,
                "median_duration_sec": perf.median_duration_sec if perf else 0.0,
                "p95_duration_sec": perf.p95_duration_sec if perf else 0.0,
                "mean_waiting_time_sec": perf.mean_waiting_time_sec if perf else 0.0,
                "failure_rate": perf.overall_failure_rate if perf else 0.0,
            },
            "nodes_count": len(graph.nodes) if graph else 0,
            "edges_count": len(graph.edges) if graph else 0,
            "bottlenecks": [
                {
                    "component_id": bn.component_id,
                    "type": bn.bottleneck_type.value,
                    "severity": bn.severity.value,
                    "estimated_delay_sec": bn.estimated_delay_sec,
                    "recommended_action": bn.recommended_action,
                }
                for bn in bottlenecks
            ],
            "conformance_deviations_count": len(deviations),
            "failure_clusters_count": len(failures),
            "optimization_candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "type": c.optimization_type.value,
                    "title": c.title,
                    "speedup_pct": c.expected_time_reduction_pct,
                    "status": c.status.value,
                }
                for c in candidates
            ],
        }
