"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Process Graph Builder: Node Aggregation, Transition Frequencies & Path Analysis.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

from process_intelligence.models import (
    ProcessEventType,
    ProcessGraphEdge,
    ProcessGraphNode,
    ProcessGraphRecord,
)
from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Graph")


class ProcessGraphBuilder:
    """
    Builds versioned process graphs from reconstructed execution traces across multiple runs.
    Identifies common execution paths, transition frequencies, and cycle bottlenecks.
    """

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def build_graph_for_workflow(self, workflow_id: str, version: int = 1) -> ProcessGraphRecord:
        """Aggregates all execution traces for a workflow into a directed process graph."""
        traces = self.repo.list_traces_for_workflow(workflow_id)
        if not traces:
            logger.warning(f"No execution traces found for workflow '{workflow_id}'")
            return ProcessGraphRecord(
                graph_id=f"graph-{uuid.uuid4().hex[:8]}",
                workflow_id=workflow_id,
                version=version,
            )

        nodes: Dict[str, ProcessGraphNode] = {}
        edge_map: Dict[str, ProcessGraphEdge] = {}
        paths: List[List[str]] = []

        for trace in traces:
            events = self.repo.list_events_for_trace(trace.trace_id)
            if not events:
                continue

            sorted_events = sorted(events, key=lambda e: e.timestamp)
            current_path: List[str] = []
            prev_node_id: Optional[str] = None

            for evt in sorted_events:
                node_id = evt.task_id
                if node_id not in nodes:
                    node_type = "APPROVAL" if "approval" in node_id.lower() or "approval" in evt.event_type.value.lower() else "ACTIVITY"
                    nodes[node_id] = ProcessGraphNode(
                        node_id=node_id,
                        task_name=node_id,
                        node_type=node_type,
                    )

                node = nodes[node_id]
                node.execution_count += 1
                node.total_active_duration_sec += evt.duration_sec
                node.total_waiting_duration_sec += evt.waiting_time_sec
                if evt.event_type == ProcessEventType.TASK_FAIL:
                    node.failure_count += 1

                current_path.append(node_id)

                if prev_node_id and prev_node_id != node_id:
                    edge_key = f"{prev_node_id}->{node_id}"
                    if edge_key not in edge_map:
                        edge_map[edge_key] = ProcessGraphEdge(
                            source_node_id=prev_node_id,
                            target_node_id=node_id,
                            transition_count=0,
                            avg_transition_latency_sec=0.0,
                        )
                    edge = edge_map[edge_key]
                    edge.transition_count += 1
                    edge.avg_transition_latency_sec = (edge.avg_transition_latency_sec + evt.waiting_time_sec) / 2.0

                prev_node_id = node_id

            if current_path:
                paths.append(current_path)

        # Retain top 5 distinct paths
        unique_paths = []
        for p in paths:
            if p not in unique_paths:
                unique_paths.append(p)
            if len(unique_paths) >= 5:
                break

        graph = ProcessGraphRecord(
            graph_id=f"graph-{uuid.uuid4().hex[:8]}",
            workflow_id=workflow_id,
            version=version,
            nodes=nodes,
            edges=list(edge_map.values()),
            common_paths=unique_paths,
        )
        self.repo.save_process_graph(graph)
        logger.info(
            f"Built process graph for '{workflow_id}' (v{version}): {len(nodes)} nodes, {len(edge_map)} edges"
        )
        return graph
