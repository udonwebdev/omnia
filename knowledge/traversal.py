"""
Omnia Module 30: Knowledge Graph Traversal & Path Discovery Engine
Implements bounded graph exploration, pathfinding, and neighborhood extraction
with cycle protection and depth control.
"""

from collections import deque
from typing import List, Optional, Set, Dict, Any

from knowledge.models import (
    GraphEntity,
    GraphRelationship,
    GraphTraversalPath,
    Subgraph,
)
from knowledge.persistence import KnowledgePersistence


class GraphTraversalEngine:
    def __init__(self, persistence: KnowledgePersistence):
        self.persistence = persistence

    def extract_subgraph(
        self,
        center_entity_id: str,
        max_depth: int = 2,
        min_confidence: float = 0.0,
        allowed_predicates: Optional[List[str]] = None,
    ) -> Subgraph:
        """
        Extracts a bounded k-hop neighborhood around a center entity.
        Prevents cycles and respects confidence thresholds.
        """
        center_entity = self.persistence.get_entity(center_entity_id)
        if not center_entity:
            return Subgraph(center_entity_id=center_entity_id, depth=0)

        visited_entities: Dict[str, GraphEntity] = {center_entity_id: center_entity}
        visited_relationships: Dict[str, GraphRelationship] = {}

        # Queue contains (entity_id, current_depth)
        queue = deque([(center_entity_id, 0)])

        while queue:
            curr_id, curr_depth = queue.popleft()
            if curr_depth >= max_depth:
                continue

            # Fetch adjacent relationships
            adjacent_rels = self.persistence.find_adjacent_relationships(curr_id)

            for rel in adjacent_rels:
                if rel.confidence < min_confidence:
                    continue
                if allowed_predicates and rel.predicate not in allowed_predicates:
                    continue

                visited_relationships[rel.relationship_id] = rel

                # Determine next node
                neighbor_id = rel.target_id if rel.source_id == curr_id else rel.source_id

                if neighbor_id not in visited_entities:
                    neighbor_ent = self.persistence.get_entity(neighbor_id)
                    if neighbor_ent:
                        visited_entities[neighbor_id] = neighbor_ent
                        queue.append((neighbor_id, curr_depth + 1))

        return Subgraph(
            center_entity_id=center_entity_id,
            depth=max_depth,
            entities=list(visited_entities.values()),
            relationships=list(visited_relationships.values()),
        )

    def find_shortest_path(
        self,
        start_entity_id: str,
        target_entity_id: str,
        max_depth: int = 5,
        min_confidence: float = 0.0,
    ) -> Optional[GraphTraversalPath]:
        """
        Discovers the shortest path between start_entity_id and target_entity_id using BFS.
        Returns a GraphTraversalPath or None if disconnected.
        """
        if start_entity_id == target_entity_id:
            start_ent = self.persistence.get_entity(start_entity_id)
            if not start_ent:
                return None
            return GraphTraversalPath(
                start_entity_id=start_entity_id,
                target_entity_id=target_entity_id,
                entities=[start_ent],
                relationships=[],
                total_depth=0,
                path_weight=0.0,
            )

        start_ent = self.persistence.get_entity(start_entity_id)
        target_ent = self.persistence.get_entity(target_entity_id)
        if not start_ent or not target_ent:
            return None

        # Queue item: (current_node, [nodes_in_path], [rels_in_path], cumulative_weight)
        queue = deque([(start_entity_id, [start_ent], [], 0.0)])
        visited: Set[str] = {start_entity_id}

        while queue:
            curr_id, path_nodes, path_rels, cum_weight = queue.popleft()

            if len(path_rels) >= max_depth:
                continue

            for rel in self.persistence.find_adjacent_relationships(curr_id):
                if rel.confidence < min_confidence:
                    continue

                neighbor_id = rel.target_id if rel.source_id == curr_id else rel.source_id

                if neighbor_id == target_entity_id:
                    # Found target
                    final_nodes = path_nodes + [target_ent]
                    final_rels = path_rels + [rel]
                    return GraphTraversalPath(
                        start_entity_id=start_entity_id,
                        target_entity_id=target_entity_id,
                        entities=final_nodes,
                        relationships=final_rels,
                        total_depth=len(final_rels),
                        path_weight=round(cum_weight + rel.weight, 3),
                    )

                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    neighbor_node = self.persistence.get_entity(neighbor_id)
                    if neighbor_node:
                        queue.append((
                            neighbor_id,
                            path_nodes + [neighbor_node],
                            path_rels + [rel],
                            cum_weight + rel.weight,
                        ))

        return None
