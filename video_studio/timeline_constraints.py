"""OMNIA Video Studio — Timeline Constraint & Validation Engine (Module 5).

Provides reusable pre-mutation constraint checks and server-side rules:
- can_add_item()
- can_remove_item()
- can_move_item()
- can_trim_start()
- can_trim_end()
- can_split_item()
- can_change_track()
- can_change_source_range()
- can_link_items()
- can_unlink_items()

Ensures track locking, negative frame guards, duration floors, track compatibility,
and source boundary limits are strictly enforced.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineTrackType,
    TimelineItemType,
    TimelineRange,
    SourceRange,
)

logger = logging.getLogger("Omnia.VideoStudio.Constraints")

class EditConstraintViolation(Exception):
    """Raised when an edit command violates timeline constraint rules."""
    pass

class TimelineConstraintEngine:
    """Evaluates edit operations against sequence and track constraints."""

    # Track type compatibility matrix
    COMPATIBLE_TRACK_TYPES = {
        TimelineTrackType.VIDEO: {TimelineTrackType.VIDEO, TimelineTrackType.ADJUSTMENT, TimelineTrackType.OVERLAY},
        TimelineTrackType.AUDIO: {TimelineTrackType.AUDIO},
        TimelineTrackType.SUBTITLE: {TimelineTrackType.SUBTITLE, TimelineTrackType.CAPTION},
        TimelineTrackType.CAPTION: {TimelineTrackType.CAPTION, TimelineTrackType.SUBTITLE},
        TimelineTrackType.ADJUSTMENT: {TimelineTrackType.ADJUSTMENT, TimelineTrackType.VIDEO},
        TimelineTrackType.OVERLAY: {TimelineTrackType.OVERLAY, TimelineTrackType.VIDEO},
        TimelineTrackType.EFFECT: {TimelineTrackType.EFFECT},
        TimelineTrackType.CONTROL: {TimelineTrackType.CONTROL},
    }

    def can_add_item(
        self,
        sequence: VideoSequence,
        track_id: str,
        start_frame: int,
        duration_frames: int,
        source_in_frame: int = 0,
    ) -> Tuple[bool, str]:
        track = next((t for t in sequence.tracks if t.track_id == track_id), None)
        if not track:
            return False, f"Track '{track_id}' not found in sequence."
        if track.is_locked:
            return False, f"Track '{track.name}' ({track_id}) is locked."
        if start_frame < 0:
            return False, f"Start frame cannot be negative: {start_frame}"
        if duration_frames <= 0:
            return False, f"Duration frames must be at least 1: {duration_frames}"
        if source_in_frame < 0:
            return False, f"Source in_frame cannot be negative: {source_in_frame}"
        return True, "Valid"

    def can_remove_item(
        self,
        sequence: VideoSequence,
        item_id: str,
    ) -> Tuple[bool, str]:
        item, track = self._find_item_and_track(sequence, item_id)
        if not item:
            return False, f"Item '{item_id}' not found."
        if track and track.is_locked:
            return False, f"Cannot remove item from locked track '{track.name}'."
        return True, "Valid"

    def can_move_item(
        self,
        sequence: VideoSequence,
        item_id: str,
        new_start_frame: int,
        target_track_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        item, current_track = self._find_item_and_track(sequence, item_id)
        if not item or not current_track:
            return False, f"Item '{item_id}' not found."

        if current_track.is_locked:
            return False, f"Current track '{current_track.name}' is locked."

        if new_start_frame < 0:
            return False, f"New start frame cannot be negative: {new_start_frame}"

        dest_track = current_track
        if target_track_id and target_track_id != current_track.track_id:
            dest_track = next((t for t in sequence.tracks if t.track_id == target_track_id), None)
            if not dest_track:
                return False, f"Target track '{target_track_id}' not found."
            if dest_track.is_locked:
                return False, f"Target track '{dest_track.name}' is locked."
            # Check compatibility
            compat = self.COMPATIBLE_TRACK_TYPES.get(current_track.track_type, set())
            if dest_track.track_type not in compat:
                return False, f"Incompatible track move from {current_track.track_type.value} to {dest_track.track_type.value}."

        return True, "Valid"

    def can_trim_start(
        self,
        sequence: VideoSequence,
        item_id: str,
        delta_frames: int,  # positive = trim head inwards, negative = extend head outwards
    ) -> Tuple[bool, str]:
        item, track = self._find_item_and_track(sequence, item_id)
        if not item or not track:
            return False, f"Item '{item_id}' not found."
        if track.is_locked:
            return False, f"Track '{track.name}' is locked."

        new_start = item.timeline_range.start_frame + delta_frames
        new_duration = item.timeline_range.duration_frames - delta_frames
        new_source_in = item.source_range.in_frame + delta_frames

        if new_start < 0:
            return False, f"Trim would place timeline start at negative frame: {new_start}"
        if new_duration < 1:
            return False, f"Trim would result in non-positive duration: {new_duration}"
        if new_source_in < 0:
            return False, f"Trim would exceed source media head boundary (in_frame < 0): {new_source_in}"

        return True, "Valid"

    def can_trim_end(
        self,
        sequence: VideoSequence,
        item_id: str,
        delta_frames: int,  # negative = trim tail inwards, positive = extend tail outwards
    ) -> Tuple[bool, str]:
        item, track = self._find_item_and_track(sequence, item_id)
        if not item or not track:
            return False, f"Item '{item_id}' not found."
        if track.is_locked:
            return False, f"Track '{track.name}' is locked."

        new_duration = item.timeline_range.duration_frames + delta_frames
        if new_duration < 1:
            return False, f"Trim would result in non-positive duration: {new_duration}"

        return True, "Valid"

    def can_split_item(
        self,
        sequence: VideoSequence,
        item_id: str,
        split_frame: int,
    ) -> Tuple[bool, str]:
        item, track = self._find_item_and_track(sequence, item_id)
        if not item or not track:
            return False, f"Item '{item_id}' not found."
        if track.is_locked:
            return False, f"Cannot split item on locked track '{track.name}'."

        start = item.timeline_range.start_frame
        end = item.timeline_range.end_frame

        if split_frame <= start or split_frame >= end:
            return False, f"Split frame {split_frame} must be strictly inside clip bounds [{start}..{end}]."

        # Both slices must have at least 1 frame
        left_dur = split_frame - start
        right_dur = end - split_frame
        if left_dur < 1 or right_dur < 1:
            return False, "Split would create a zero-length slice."

        return True, "Valid"

    def can_change_track(
        self,
        sequence: VideoSequence,
        item_id: str,
        target_track_id: str,
    ) -> Tuple[bool, str]:
        item, current_track = self._find_item_and_track(sequence, item_id)
        if not item or not current_track:
            return False, f"Item '{item_id}' not found."
        if current_track.is_locked:
            return False, f"Source track '{current_track.name}' is locked."

        target_track = next((t for t in sequence.tracks if t.track_id == target_track_id), None)
        if not target_track:
            return False, f"Target track '{target_track_id}' not found."
        if target_track.is_locked:
            return False, f"Target track '{target_track.name}' is locked."

        compat = self.COMPATIBLE_TRACK_TYPES.get(current_track.track_type, set())
        if target_track.track_type not in compat:
            return False, f"Cannot move item from {current_track.track_type.value} track to {target_track.track_type.value} track."

        return True, "Valid"

    def can_change_source_range(
        self,
        sequence: VideoSequence,
        item_id: str,
        new_in_frame: int,
        new_duration_frames: int,
    ) -> Tuple[bool, str]:
        item, track = self._find_item_and_track(sequence, item_id)
        if not item or not track:
            return False, f"Item '{item_id}' not found."
        if track.is_locked:
            return False, f"Track '{track.name}' is locked."
        if new_in_frame < 0:
            return False, f"Source in_frame cannot be negative: {new_in_frame}"
        if new_duration_frames < 1:
            return False, f"Source duration must be at least 1: {new_duration_frames}"
        return True, "Valid"

    def can_link_items(
        self,
        sequence: VideoSequence,
        item_ids: List[str],
    ) -> Tuple[bool, str]:
        if len(item_ids) < 2:
            return False, "Must provide at least 2 items to link."
        found_items = []
        for i_id in item_ids:
            it, _ = self._find_item_and_track(sequence, i_id)
            if not it:
                return False, f"Item '{i_id}' not found in sequence."
            found_items.append(it)
        return True, "Valid"

    def can_unlink_items(
        self,
        sequence: VideoSequence,
        item_ids: List[str],
    ) -> Tuple[bool, str]:
        if not item_ids:
            return False, "No items specified for unlinking."
        return True, "Valid"

    def _find_item_and_track(
        self,
        sequence: VideoSequence,
        item_id: str,
    ) -> Tuple[Optional[TimelineItemModel], Optional[TimelineTrackModel]]:
        for track in sequence.tracks:
            for item in track.items:
                if item.item_id == item_id:
                    return item, track
        return None, None

# Global singleton
timeline_constraint_engine = TimelineConstraintEngine()
