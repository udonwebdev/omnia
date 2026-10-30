"""
OMNIA Module 36: Infrastructure Dependency Graph Engine
Models dependencies between components (hard, soft, optional),
propagates cascading failure probabilities, and detects single points of failure.
"""

import uuid
import logging
from typing import Dict, Any, List, Set, Optional
from collections import defaultdict, deque
from observability.models import (
    InfrastructureDependencyEdge,
    DependencyType,
    ComponentHealthStatus,
)
from observability.persistence import ObservabilityRepository

logger = logging.getLogger("Omnia.Observability.Dependencies")


class DependencyGraphBuilder:
    """Builds and analyzes directed acyclic dependency graphs across components."""

    def __init__(self, repo: ObservabilityRepository):
        self.repo = repo
        self._edges: Dict[str, InfrastructureDependencyEdge] = {}
        # source -> list of edges where source depends on target
        self._outgoing: Dict[str, List[InfrastructureDependencyEdge]] = defaultdict(list)
        # target -> list of edges where sources depend on this target
        self._incoming: Dict[str, List[InfrastructureDependencyEdge]] = defaultdict(list)
        self._load_from_repo()

    def _load_from_repo(self) -> None:
        """Loads existing edges from persistence."""
        edges = self.repo.list_dependency_edges()
        for e in edges:
            self._edges[e.edge_id] = e
            self._outgoing[e.source_component_id].append(e)
            self._incoming[e.target_component_id].append(e)

    def add_dependency(
        self,
        source_component_id: str,
        target_component_id: str,
        dependency_type: DependencyType = DependencyType.HARD,
        criticality: float = 1.0,
        failure_propagation_probability: float = 0.85,
    ) -> InfrastructureDependencyEdge:
        """Adds a dependency relationship: source depends on target."""
        edge_id = f"dep-{uuid.uuid4().hex[:8]}"
        edge = InfrastructureDependencyEdge(
            edge_id=edge_id,
            source_component_id=source_component_id,
            target_component_id=target_component_id,
            dependency_type=dependency_type,
            criticality=criticality,
            failure_propagation_probability=failure_propagation_probability,
        )
        self._edges[edge_id] = edge
        self._outgoing[source_component_id].append(edge)
        self._incoming[target_component_id].append(edge)
        self.repo.save_dependency_edge(edge)
        logger.info(f"Added dependency: '{source_component_id}' -> '{target_component_id}' ({dependency_type.value})")
        return edge

    def get_dependencies_for(self, component_id: str) -> List[InfrastructureDependencyEdge]:
        """Returns dependencies that this component relies on."""
        return self._outgoing.get(component_id, [])

    def get_dependents_of(self, component_id: str) -> List[InfrastructureDependencyEdge]:
        """Returns components that rely on this component."""
        return self._incoming.get(component_id, [])

    def calculate_cascading_impact(self, failed_component_id: str) -> Dict[str, Any]:
        """
        Calculates transitive cascading degradation or failure risk when a component fails.
        Uses BFS along incoming dependency edges (dependents).
        """
        impacted: Dict[str, Dict[str, Any]] = {}
        queue: deque = deque([(failed_component_id, 1.0, 0)])
        visited: Set[str] = {failed_component_id}

        while queue:
            curr_id, current_prob, depth = queue.popleft()
            dependents = self.get_dependents_of(curr_id)

            for edge in dependents:
                source_id = edge.source_component_id
                # Calculate downstream impact probability
                edge_weight = edge.failure_propagation_probability if edge.dependency_type == DependencyType.HARD else (edge.failure_propagation_probability * 0.5)
                derived_prob = current_prob * edge_weight

                if source_id not in impacted or derived_prob > impacted[source_id]["failure_risk"]:
                    impacted[source_id] = {
                        "component_id": source_id,
                        "dependency_type": edge.dependency_type.value,
                        "failure_risk": round(derived_prob, 3),
                        "distance_from_root": depth + 1,
                        "via_component": curr_id,
                    }

                if source_id not in visited:
                    visited.add(source_id)
                    queue.append((source_id, derived_prob, depth + 1))

        return {
            "root_failure_component": failed_component_id,
            "total_downstream_impacted": len(impacted),
            "impacted_components": list(impacted.values()),
        }

    def detect_single_points_of_failure(self) -> List[Dict[str, Any]]:
        """Identifies components whose failure affects high-criticality systems with no redundancy."""
        spofs = []
        for comp_id, dependents in self._incoming.items():
            hard_dependents = [d for d in dependents if d.dependency_type == DependencyType.HARD]
            if len(hard_dependents) >= 2 or any(d.criticality >= 0.9 for d in hard_dependents):
                spofs.append({
                    "component_id": comp_id,
                    "hard_dependent_count": len(hard_dependents),
                    "dependent_ids": [d.source_component_id for d in hard_dependents],
                    "risk_assessment": "CRITICAL_SPOF" if len(hard_dependents) >= 3 else "HIGH_SPOF",
                })
        return spofs
