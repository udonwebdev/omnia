"""
Omnia Module 31: Causal Graph & Root Cause Discovery Engine
Implements causal tracing, consequence projection (blast radius),
cycle protection, and confidence attenuation.
"""

from collections import deque
from typing import List, Dict, Any, Optional, Set

from temporal.models import (
    CausalLink,
    CausalChain,
    CausalChainNode,
    CausalStatus,
)
from temporal.persistence import TemporalPersistence


class CausalReasoner:
    def __init__(self, persistence: TemporalPersistence):
        self.persistence = persistence

    def trace_root_causes(
        self,
        effect_entity_id: str,
        max_depth: int = 5,
        min_confidence: float = 0.1,
    ) -> List[CausalChain]:
        """
        Backward causal traversal from effect_entity_id to uncover root causes.
        Returns candidate causal chains.
        """
        chains: List[CausalChain] = []

        # Queue contains (current_entity_id, path_nodes, cumulative_confidence)
        initial_node = CausalChainNode(
            entity_id=effect_entity_id,
            step_depth=0,
            step_confidence=1.0,
            cumulative_confidence=1.0,
        )
        queue = deque([(effect_entity_id, [initial_node], 1.0, set([effect_entity_id]))])

        while queue:
            curr_id, path, cum_conf, visited = queue.popleft()

            if len(path) > max_depth:
                # Max depth reached; record current chain as discovered
                chains.append(CausalChain(
                    root_cause_id=curr_id,
                    target_effect_id=effect_entity_id,
                    nodes=path,
                    overall_confidence=round(cum_conf, 4),
                ))
                continue

            incoming_causes = self.persistence.get_causes_for_effect(curr_id)

            if not incoming_causes:
                # No further causes; curr_id is a root cause
                if len(path) > 1:
                    chains.append(CausalChain(
                        root_cause_id=curr_id,
                        target_effect_id=effect_entity_id,
                        nodes=path,
                        overall_confidence=round(cum_conf, 4),
                    ))
                continue

            for link in incoming_causes:
                cause_id = link.cause_entity_id
                next_cum_conf = cum_conf * link.confidence

                if next_cum_conf < min_confidence:
                    continue

                if cause_id in visited:
                    # Cycle detected!
                    cycle_node = CausalChainNode(
                        entity_id=cause_id,
                        step_depth=len(path),
                        relation_to_next=link.relation_type.value,
                        step_confidence=link.confidence,
                        cumulative_confidence=round(next_cum_conf, 4),
                    )
                    chains.append(CausalChain(
                        root_cause_id=cause_id,
                        target_effect_id=effect_entity_id,
                        nodes=path + [cycle_node],
                        overall_confidence=round(next_cum_conf, 4),
                        has_cycles=True,
                    ))
                    continue

                new_node = CausalChainNode(
                    entity_id=cause_id,
                    step_depth=len(path),
                    relation_to_next=link.relation_type.value,
                    step_confidence=link.confidence,
                    cumulative_confidence=round(next_cum_conf, 4),
                )
                queue.append((cause_id, path + [new_node], next_cum_conf, visited | {cause_id}))

        return chains

    def trace_consequences(
        self,
        cause_entity_id: str,
        max_depth: int = 5,
        min_confidence: float = 0.1,
    ) -> List[CausalChain]:
        """
        Forward causal projection from cause_entity_id to determine blast radius/consequences.
        """
        chains: List[CausalChain] = []

        initial_node = CausalChainNode(
            entity_id=cause_entity_id,
            step_depth=0,
            step_confidence=1.0,
            cumulative_confidence=1.0,
        )
        queue = deque([(cause_entity_id, [initial_node], 1.0, set([cause_entity_id]))])

        while queue:
            curr_id, path, cum_conf, visited = queue.popleft()

            if len(path) > max_depth:
                chains.append(CausalChain(
                    root_cause_id=cause_entity_id,
                    target_effect_id=curr_id,
                    nodes=path,
                    overall_confidence=round(cum_conf, 4),
                ))
                continue

            outgoing_effects = self.persistence.get_effects_for_cause(curr_id)

            if not outgoing_effects:
                if len(path) > 1:
                    chains.append(CausalChain(
                        root_cause_id=cause_entity_id,
                        target_effect_id=curr_id,
                        nodes=path,
                        overall_confidence=round(cum_conf, 4),
                    ))
                continue

            for link in outgoing_effects:
                effect_id = link.effect_entity_id
                next_cum_conf = cum_conf * link.confidence

                if next_cum_conf < min_confidence:
                    continue

                if effect_id in visited:
                    cycle_node = CausalChainNode(
                        entity_id=effect_id,
                        step_depth=len(path),
                        relation_to_next=link.relation_type.value,
                        step_confidence=link.confidence,
                        cumulative_confidence=round(next_cum_conf, 4),
                    )
                    chains.append(CausalChain(
                        root_cause_id=cause_entity_id,
                        target_effect_id=effect_id,
                        nodes=path + [cycle_node],
                        overall_confidence=round(next_cum_conf, 4),
                        has_cycles=True,
                    ))
                    continue

                new_node = CausalChainNode(
                    entity_id=effect_id,
                    step_depth=len(path),
                    relation_to_next=link.relation_type.value,
                    step_confidence=link.confidence,
                    cumulative_confidence=round(next_cum_conf, 4),
                )
                queue.append((effect_id, path + [new_node], next_cum_conf, visited | {effect_id}))

        return chains
