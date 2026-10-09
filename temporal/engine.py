"""
Omnia Module 31: Temporal State Reconstruction & Change Detection Engine
Implements point-in-time state reconstruction (as_of) and temporal delta detection.
"""

import time
from typing import Dict, Any, List, Optional

from temporal.models import (
    TemporalStateRecord,
    StateTransitionDiff,
)
from temporal.persistence import TemporalPersistence


class TemporalEngine:
    """
    Evaluates bi-temporal intervals:
    - Valid Time: when the fact occurred in reality
    - Transaction Time: when Omnia recorded the observation
    Provides point-in-time state reconstruction and change detection.
    """

    def __init__(self, persistence: TemporalPersistence):
        self.persistence = persistence

    def reconstruct_state_as_of(
        self,
        entity_id: str,
        as_of_valid_time: float,
        as_of_transaction_time: Optional[float] = None
    ) -> Optional[TemporalStateRecord]:
        """
        Reconstructs what state was valid for entity_id at `as_of_valid_time`,
        as known to Omnia up to `as_of_transaction_time` (defaults to now).
        """
        all_states = self.persistence.get_states_for_entity(
            entity_id=entity_id,
            as_of_transaction_time=as_of_transaction_time
        )
        if not all_states:
            return None

        # Filter records that encompass as_of_valid_time
        # A state is valid if valid_from <= as_of_valid_time < (valid_until or infinity)
        candidates = []
        for s in all_states:
            if s.valid_from <= as_of_valid_time:
                if s.valid_until is None or s.valid_until > as_of_valid_time:
                    candidates.append(s)

        if not candidates:
            return None

        # If multiple candidates exist (e.g. retroactive correction),
        # pick the one with the latest transaction_time
        candidates.sort(key=lambda s: s.transaction_time, reverse=True)
        winner = candidates[0]
        if winner.is_deleted:
            return None
        return winner

    def detect_state_transitions(
        self,
        entity_id: str,
        start_valid_time: Optional[float] = None,
        end_valid_time: Optional[float] = None,
        as_of_transaction_time: Optional[float] = None,
    ) -> List[StateTransitionDiff]:
        """
        Detects attribute changes across consecutive valid states of an entity.
        Returns a chronologically ordered list of state transitions.
        """
        all_states = self.persistence.get_states_for_entity(
            entity_id=entity_id,
            as_of_transaction_time=as_of_transaction_time
        )
        if not all_states:
            return []

        # Sort by valid_from
        filtered = []
        for s in all_states:
            if start_valid_time is not None and s.valid_from < start_valid_time:
                continue
            if end_valid_time is not None and s.valid_from > end_valid_time:
                continue
            filtered.append(s)

        filtered.sort(key=lambda s: s.valid_from)
        transitions: List[StateTransitionDiff] = []

        for i in range(1, len(filtered)):
            curr = filtered[i]
            prev = filtered[i - 1]

            prev_payload = prev.state_payload
            curr_payload = curr.state_payload

            # Find changed keys
            all_keys = set(prev_payload.keys()) | set(curr_payload.keys())
            changed = []
            prev_diff = {}
            curr_diff = {}

            for k in all_keys:
                v_prev = prev_payload.get(k)
                v_curr = curr_payload.get(k)
                if v_prev != v_curr:
                    changed.append(k)
                    prev_diff[k] = v_prev
                    curr_diff[k] = v_curr

            if changed:
                diff = StateTransitionDiff(
                    entity_id=entity_id,
                    from_state_id=prev.state_id,
                    to_state_id=curr.state_id,
                    transition_time=curr.valid_from,
                    changed_keys=changed,
                    previous_values=prev_diff,
                    new_values=curr_diff,
                )
                transitions.append(diff)

        return transitions
