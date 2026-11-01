"""OMNIA Video Studio — Timeline Validation Engine (Module 4).

Validates sequence consistency, track integrity, item bounds, link references,
and nested sequence acyclicity (DFS graph traversal to prevent circular sequences A -> B -> A).
"""

from typing import Dict, Any, List, Set, Tuple, Optional
import logging

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineItemType,
)

logger = logging.getLogger("Omnia.VideoStudio.Validation")

class TimelineValidationError(Exception):
    """Raised when sequence or item invariants are violated."""
    pass

class TimelineValidationEngine:
    """Enforces structural invariants across sequences, tracks, and items."""

    def validate_sequence(
        self,
        sequence: VideoSequence,
        all_sequences: Optional[Dict[str, VideoSequence]] = None,
    ) -> Tuple[bool, List[str]]:
        """Performs full structural validation on a sequence."""
        errors: List[str] = []

        if not sequence.sequence_id or not isinstance(sequence.sequence_id, str):
            errors.append("Sequence must have a valid non-empty sequence_id.")

        if not sequence.project_id:
            errors.append("Sequence must belong to a project_id.")

        if sequence.settings.width <= 0 or sequence.settings.height <= 0:
            errors.append(f"Invalid sequence resolution: {sequence.settings.width}x{sequence.settings.height}")

        if sequence.settings.frame_rate <= 0:
            errors.append(f"Invalid sequence frame rate: {sequence.settings.frame_rate}")

        # Check track order and duplicate IDs
        seen_track_ids: Set[str] = set()
        seen_item_ids: Set[str] = set()

        for track in sequence.tracks:
            if track.track_id in seen_track_ids:
                errors.append(f"Duplicate track_id detected: {track.track_id}")
            seen_track_ids.add(track.track_id)

            if track.sequence_id != sequence.sequence_id:
                errors.append(f"Track {track.track_id} sequence_id mismatch: expected {sequence.sequence_id}, got {track.sequence_id}")

            # Validate items in track
            for item in track.items:
                if item.item_id in seen_item_ids:
                    errors.append(f"Duplicate item_id detected: {item.item_id}")
                seen_item_ids.add(item.item_id)

                if item.track_id != track.track_id:
                    errors.append(f"Item {item.item_id} track_id mismatch: expected {track.track_id}, got {item.track_id}")

                # Validate ranges
                v_tl, msg_tl = item.timeline_range.validate()
                if not v_tl:
                    errors.append(f"Item {item.item_id} invalid timeline range: {msg_tl}")

                v_src, msg_src = item.source_range.validate()
                if not v_src:
                    errors.append(f"Item {item.item_id} invalid source range: {msg_src}")

                # Validate nested sequences
                if item.item_type == TimelineItemType.NESTED_SEQUENCE:
                    if item.source_reference_id == sequence.sequence_id:
                        errors.append(f"Direct circular nesting: sequence {sequence.sequence_id} references itself in item {item.item_id}")
                    elif all_sequences and item.source_reference_id in all_sequences:
                        # Check graph acyclicity
                        if self._has_cycle(sequence.sequence_id, item.source_reference_id, all_sequences):
                            errors.append(f"Circular sequence nesting detected: {sequence.sequence_id} -> {item.source_reference_id} -> ... -> {sequence.sequence_id}")

        # Validate link groups
        for lg_id, lg in sequence.link_groups.items():
            for item_id in lg.item_ids:
                if item_id not in seen_item_ids:
                    errors.append(f"LinkGroup {lg_id} references missing item: {item_id}")

        return (len(errors) == 0, errors)

    def _has_cycle(
        self,
        origin_seq_id: str,
        current_seq_id: str,
        all_sequences: Dict[str, VideoSequence],
        visited: Optional[Set[str]] = None,
    ) -> bool:
        """DFS traversal checking if current_seq_id can reach origin_seq_id."""
        if visited is None:
            visited = set()

        if current_seq_id == origin_seq_id:
            return True

        if current_seq_id in visited or current_seq_id not in all_sequences:
            return False

        visited.add(current_seq_id)
        target_seq = all_sequences[current_seq_id]

        for tr in target_seq.tracks:
            for it in tr.items:
                if it.item_type == TimelineItemType.NESTED_SEQUENCE:
                    nested_id = it.source_reference_id
                    if self._has_cycle(origin_seq_id, nested_id, all_sequences, visited.copy()):
                        return True
        return False

# Global singleton
timeline_validation_engine = TimelineValidationEngine()
