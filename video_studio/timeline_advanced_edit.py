"""OMNIA Video Studio — Advanced Timeline Editing Engine (Module 6).

Implements professional timeline editing operations on top of Modules 4 & 5:
- Ripple Editing:
    * ripple_trim_start(sequence, item_id, delta_frames, affected_tracks, ripple_linked)
    * ripple_trim_end(sequence, item_id, delta_frames, affected_tracks, ripple_linked)
    * ripple_delete(sequence, item_ids, affected_tracks, ripple_linked)
    * ripple_insert(sequence, track_id, item, insert_frame, affected_tracks, ripple_linked)
- Rolling Editing:
    * rolling_edit(sequence, prev_item_id, next_item_id, delta_frames, roll_linked)
- Slip Editing:
    * slip_edit(sequence, item_id, delta_frames, slip_linked)
- Slide Editing:
    * slide_edit(sequence, item_id, delta_frames, slide_linked)
- Gap Management:
    * detect_gaps(sequence, track_id)
    * close_gap(sequence, track_id, gap_start_frame, affected_tracks)
    * insert_gap(sequence, track_id, gap_start_frame, duration_frames, affected_tracks)
- Multi-Item Operations:
    * move_multiple_items(sequence, item_ids, delta_frames)
    * ripple_delete_multiple(sequence, item_ids, affected_tracks)
- Edit Preview and Validation:
    * preview_edit(sequence, edit_fn, *args, **kwargs) -> EditPlanPreview
"""

from typing import Dict, Any, List, Optional, Tuple, Set, Callable
from dataclasses import dataclass, field
import uuid
import time
import copy
import logging

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineTrackType,
    TimelineItemType,
    TimelineItemState,
    TimelineRange,
    SourceRange,
    LinkGroup,
)
from video_studio.timeline_constraints import (
    TimelineConstraintEngine,
    EditConstraintViolation,
    timeline_constraint_engine,
)
from video_studio.timeline_commands import (
    TimelineCommand,
    TimelineTransaction,
    TimelineHistoryManager,
    TimelineOpType,
)
from video_studio.timeline_edit_engine import (
    TimelineEditEngine,
    StaleRevisionError,
    timeline_edit_engine,
)
from video_studio.timeline_query import TimelineQueryEngine, timeline_query_engine

logger = logging.getLogger("Omnia.VideoStudio.AdvancedEdit")

@dataclass
class TimelineGap:
    """Represents an empty span between items on a track."""
    track_id: str
    start_frame: int
    end_frame: int
    duration_frames: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_id": self.track_id,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "duration_frames": self.duration_frames,
        }

@dataclass
class EditPlanPreview:
    """Non-mutating preview of a prospective advanced timeline edit."""
    valid: bool
    operation_name: str
    error_message: Optional[str] = None
    affected_item_ids: List[str] = field(default_factory=list)
    affected_track_ids: List[str] = field(default_factory=list)
    timeline_range_changes: Dict[str, Dict[str, int]] = field(default_factory=dict)
    source_range_changes: Dict[str, Dict[str, int]] = field(default_factory=dict)
    removed_item_ids: List[str] = field(default_factory=list)
    delta_duration_frames: int = 0
    resulting_duration_frames: int = 0
    resulting_revision: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "operation_name": self.operation_name,
            "error_message": self.error_message,
            "affected_item_ids": self.affected_item_ids,
            "affected_track_ids": self.affected_track_ids,
            "timeline_range_changes": self.timeline_range_changes,
            "source_range_changes": self.source_range_changes,
            "removed_item_ids": self.removed_item_ids,
            "delta_duration_frames": self.delta_duration_frames,
            "resulting_duration_frames": self.resulting_duration_frames,
            "resulting_revision": self.resulting_revision,
        }

class AdvancedTimelineEditEngine:
    """Engine executing frame-accurate ripple, rolling, slip, slide, gap and multi-item edits."""

    def __init__(
        self,
        base_edit_engine: Optional[TimelineEditEngine] = None,
        constraints: Optional[TimelineConstraintEngine] = None,
        query_engine: Optional[TimelineQueryEngine] = None,
    ):
        self.base_engine = base_edit_engine or timeline_edit_engine
        self.constraints = constraints or timeline_constraint_engine
        self.query_engine = query_engine or timeline_query_engine

    def _find_item_and_track(
        self, sequence: VideoSequence, item_id: str
    ) -> Tuple[Optional[TimelineItemModel], Optional[TimelineTrackModel]]:
        return self.constraints._find_item_and_track(sequence, item_id)

    def _get_downstream_items(
        self,
        sequence: VideoSequence,
        threshold_frame: int,
        target_tracks: Optional[Set[str]] = None,
        exclude_item_ids: Optional[Set[str]] = None,
    ) -> List[Tuple[TimelineItemModel, TimelineTrackModel]]:
        """Returns all items starting at or after threshold_frame on specified tracks."""
        exclude = exclude_item_ids or set()
        downstream = []
        for track in sequence.tracks:
            if target_tracks is not None and track.track_id not in target_tracks:
                continue
            for item in track.items:
                if item.item_id in exclude:
                    continue
                if item.timeline_range.start_frame >= threshold_frame:
                    downstream.append((item, track))
        return downstream

    # =========================================================================
    # 1. RIPPLE EDITING
    # =========================================================================

    def ripple_trim_start(
        self,
        sequence: VideoSequence,
        item_id: str,
        delta_frames: int,  # >0 trims head inward, downstream shifts LEFT by delta; <0 extends head outward
        affected_track_ids: Optional[List[str]] = None,
        ripple_linked: bool = True,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Trims head of item by delta_frames and ripples downstream clips by -delta_frames."""
        self.base_engine._check_revision(sequence, expected_revision)

        # 1. Validation of target item trim
        valid, msg = self.constraints.can_trim_start(sequence, item_id, delta_frames)
        if not valid:
            raise EditConstraintViolation(msg)

        item, track = self._find_item_and_track(sequence, item_id)
        if not item or not track:
            raise EditConstraintViolation(f"Item '{item_id}' not found.")

        # Determine target tracks for downstream ripple
        tracks_to_ripple: Set[str] = set(affected_track_ids) if affected_track_ids is not None else {t.track_id for t in sequence.tracks if not t.is_locked}
        if track.track_id not in tracks_to_ripple:
            tracks_to_ripple.add(track.track_id)

        # Determine downstream items (items starting >= original item.end_frame)
        threshold = item.timeline_range.end_frame
        downstream = self._get_downstream_items(
            sequence, threshold_frame=threshold, target_tracks=tracks_to_ripple, exclude_item_ids={item.item_id}
        )

        # Check locked tracks among downstream
        for d_item, d_track in downstream:
            if d_track.is_locked:
                raise EditConstraintViolation(f"Cannot ripple move downstream item '{d_item.name}' on locked track '{d_track.name}'.")
            if d_item.timeline_range.start_frame - delta_frames < 0:
                raise EditConstraintViolation(f"Ripple would place downstream item '{d_item.name}' at negative frame.")

        # Assemble commands
        commands: List[TimelineCommand] = []

        # Target clip head trim
        cmd_trim = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.TRIM_START,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
            payload={"delta_frames": delta_frames},
        )
        commands.append(cmd_trim)

        # Linked companion items trim
        if ripple_linked:
            for l_id in sequence.get_linked_items(item_id):
                if l_id == item_id:
                    continue
                l_item, l_track = self._find_item_and_track(sequence, l_id)
                if l_item and l_track and not l_track.is_locked:
                    l_val, _ = self.constraints.can_trim_start(sequence, l_id, delta_frames)
                    if l_val:
                        commands.append(
                            TimelineCommand(
                                command_id=str(uuid.uuid4()),
                                op_type=TimelineOpType.TRIM_START,
                                sequence_id=sequence.sequence_id,
                                target_id=l_id,
                                payload={"delta_frames": delta_frames},
                            )
                        )

        # Ripple downstream clips: shift start by -delta_frames
        for d_item, d_track in downstream:
            commands.append(
                TimelineCommand(
                    command_id=str(uuid.uuid4()),
                    op_type=TimelineOpType.MOVE_ITEM,
                    sequence_id=sequence.sequence_id,
                    target_id=d_item.item_id,
                    payload={"new_start_frame": d_item.timeline_range.start_frame - delta_frames},
                )
            )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Ripple Trim Start on '{item.name}' by {delta_frames} frames",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError(f"Failed to commit Ripple Trim Start on '{item_id}'.")

        self.base_engine._sync_spatial_index(sequence)
        return True

    def ripple_trim_end(
        self,
        sequence: VideoSequence,
        item_id: str,
        delta_frames: int,  # >0 extends tail outward, downstream shifts RIGHT; <0 trims tail, downstream shifts LEFT
        affected_track_ids: Optional[List[str]] = None,
        ripple_linked: bool = True,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Trims tail of item by delta_frames and ripples downstream clips by delta_frames."""
        self.base_engine._check_revision(sequence, expected_revision)

        valid, msg = self.constraints.can_trim_end(sequence, item_id, delta_frames)
        if not valid:
            raise EditConstraintViolation(msg)

        item, track = self._find_item_and_track(sequence, item_id)
        if not item or not track:
            raise EditConstraintViolation(f"Item '{item_id}' not found.")

        tracks_to_ripple: Set[str] = set(affected_track_ids) if affected_track_ids is not None else {t.track_id for t in sequence.tracks if not t.is_locked}
        if track.track_id not in tracks_to_ripple:
            tracks_to_ripple.add(track.track_id)

        threshold = item.timeline_range.end_frame
        downstream = self._get_downstream_items(
            sequence, threshold_frame=threshold, target_tracks=tracks_to_ripple, exclude_item_ids={item.item_id}
        )

        for d_item, d_track in downstream:
            if d_track.is_locked:
                raise EditConstraintViolation(f"Cannot ripple move downstream item '{d_item.name}' on locked track '{d_track.name}'.")
            if d_item.timeline_range.start_frame + delta_frames < 0:
                raise EditConstraintViolation(f"Ripple would place downstream item '{d_item.name}' at negative frame.")

        commands: List[TimelineCommand] = []

        # Target clip tail trim
        cmd_trim = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.TRIM_END,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
            payload={"delta_frames": delta_frames},
        )
        commands.append(cmd_trim)

        # Linked companion items tail trim
        if ripple_linked:
            for l_id in sequence.get_linked_items(item_id):
                if l_id == item_id:
                    continue
                l_item, l_track = self._find_item_and_track(sequence, l_id)
                if l_item and l_track and not l_track.is_locked:
                    l_val, _ = self.constraints.can_trim_end(sequence, l_id, delta_frames)
                    if l_val:
                        commands.append(
                            TimelineCommand(
                                command_id=str(uuid.uuid4()),
                                op_type=TimelineOpType.TRIM_END,
                                sequence_id=sequence.sequence_id,
                                target_id=l_id,
                                payload={"delta_frames": delta_frames},
                            )
                        )

        # Ripple downstream clips: shift start by +delta_frames
        for d_item, d_track in downstream:
            commands.append(
                TimelineCommand(
                    command_id=str(uuid.uuid4()),
                    op_type=TimelineOpType.MOVE_ITEM,
                    sequence_id=sequence.sequence_id,
                    target_id=d_item.item_id,
                    payload={"new_start_frame": d_item.timeline_range.start_frame + delta_frames},
                )
            )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Ripple Trim End on '{item.name}' by {delta_frames} frames",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError(f"Failed to commit Ripple Trim End on '{item_id}'.")

        self.base_engine._sync_spatial_index(sequence)
        return True

    def ripple_delete(
        self,
        sequence: VideoSequence,
        item_ids: List[str],
        affected_track_ids: Optional[List[str]] = None,
        ripple_linked: bool = True,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Deletes items and pulls all downstream material leftward to close the gap."""
        self.base_engine._check_revision(sequence, expected_revision)
        if not item_ids:
            return False

        all_target_ids: Set[str] = set(item_ids)
        if ripple_linked:
            for i_id in list(all_target_ids):
                all_target_ids.update(sequence.get_linked_items(i_id))

        items_to_delete: List[Tuple[TimelineItemModel, TimelineTrackModel]] = []
        min_start = float("inf")
        max_duration = 0

        for i_id in all_target_ids:
            it, trk = self._find_item_and_track(sequence, i_id)
            if not it or not trk:
                raise EditConstraintViolation(f"Item '{i_id}' not found.")
            if trk.is_locked:
                raise EditConstraintViolation(f"Cannot ripple delete item on locked track '{trk.name}'.")
            items_to_delete.append((it, trk))
            if it.timeline_range.start_frame < min_start:
                min_start = it.timeline_range.start_frame
            if it.timeline_range.duration_frames > max_duration:
                max_duration = it.timeline_range.duration_frames

        # Tracks participating in the ripple
        tracks_to_ripple: Set[str] = set(affected_track_ids) if affected_track_ids is not None else {t.track_id for t in sequence.tracks if not t.is_locked}
        for _, trk in items_to_delete:
            tracks_to_ripple.add(trk.track_id)

        # Downstream items starting >= min_start
        downstream = self._get_downstream_items(
            sequence, threshold_frame=int(min_start), target_tracks=tracks_to_ripple, exclude_item_ids=all_target_ids
        )

        for d_item, d_track in downstream:
            if d_track.is_locked:
                raise EditConstraintViolation(f"Cannot ripple move downstream item '{d_item.name}' on locked track '{d_track.name}'.")

        commands: List[TimelineCommand] = []

        # 1. Remove items
        for it, trk in items_to_delete:
            commands.append(
                TimelineCommand(
                    command_id=str(uuid.uuid4()),
                    op_type=TimelineOpType.REMOVE_ITEM,
                    sequence_id=sequence.sequence_id,
                    target_id=it.item_id,
                )
            )

        # 2. Shift downstream items left by duration of deleted item
        # If multiple items deleted on different tracks with different lengths, calculate per-track pull
        dur_by_track: Dict[str, int] = {}
        for it, trk in items_to_delete:
            dur_by_track[trk.track_id] = dur_by_track.get(trk.track_id, 0) + it.timeline_range.duration_frames

        for d_item, d_track in downstream:
            shift = dur_by_track.get(d_track.track_id, max_duration)
            new_pos = max(0, d_item.timeline_range.start_frame - shift)
            commands.append(
                TimelineCommand(
                    command_id=str(uuid.uuid4()),
                    op_type=TimelineOpType.MOVE_ITEM,
                    sequence_id=sequence.sequence_id,
                    target_id=d_item.item_id,
                    payload={"new_start_frame": new_pos},
                )
            )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Ripple Delete {len(items_to_delete)} items",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to commit Ripple Delete transaction.")

        self.base_engine._sync_spatial_index(sequence)
        return True

    # =========================================================================
    # 2. ROLLING EDITING
    # =========================================================================

    def rolling_edit(
        self,
        sequence: VideoSequence,
        prev_item_id: str,
        next_item_id: str,
        delta_frames: int,  # >0 moves cut point forward (lengthens prev, shortens next); <0 moves cut point backward
        roll_linked: bool = True,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Adjusts the shared boundary between two adjacent clips, maintaining combined duration."""
        self.base_engine._check_revision(sequence, expected_revision)

        prev_it, prev_trk = self._find_item_and_track(sequence, prev_item_id)
        next_it, next_trk = self._find_item_and_track(sequence, next_item_id)

        if not prev_it or not prev_trk:
            raise EditConstraintViolation(f"Previous item '{prev_item_id}' not found.")
        if not next_it or not next_trk:
            raise EditConstraintViolation(f"Next item '{next_item_id}' not found.")

        if prev_trk.is_locked or next_trk.is_locked:
            raise EditConstraintViolation("Cannot perform rolling edit across locked tracks.")

        # Verify adjacency
        if prev_it.timeline_range.end_frame != next_it.timeline_range.start_frame:
            raise EditConstraintViolation(
                f"Clips '{prev_it.name}' and '{next_it.name}' are not strictly adjacent "
                f"({prev_it.timeline_range.end_frame} != {next_it.timeline_range.start_frame})."
            )

        # 1. Prev clip tail trim by delta_frames
        v1, m1 = self.constraints.can_trim_end(sequence, prev_item_id, delta_frames)
        if not v1:
            raise EditConstraintViolation(f"Previous clip rolling constraint violation: {m1}")

        # 2. Next clip head trim by delta_frames (delta>0 means head trims inward, moves start right)
        v2, m2 = self.constraints.can_trim_start(sequence, next_item_id, delta_frames)
        if not v2:
            raise EditConstraintViolation(f"Next clip rolling constraint violation: {m2}")

        commands: List[TimelineCommand] = [
            TimelineCommand(
                command_id=str(uuid.uuid4()),
                op_type=TimelineOpType.TRIM_END,
                sequence_id=sequence.sequence_id,
                target_id=prev_item_id,
                payload={"delta_frames": delta_frames},
            ),
            TimelineCommand(
                command_id=str(uuid.uuid4()),
                op_type=TimelineOpType.TRIM_START,
                sequence_id=sequence.sequence_id,
                target_id=next_item_id,
                payload={"delta_frames": delta_frames},
            ),
        ]

        # Handle linked companions if requested
        if roll_linked:
            prev_linked = sequence.get_linked_items(prev_item_id)
            next_linked = sequence.get_linked_items(next_item_id)
            for p_lid in prev_linked:
                if p_lid == prev_item_id:
                    continue
                for n_lid in next_linked:
                    if n_lid == next_item_id:
                        continue
                    p_lit, p_ltrk = self._find_item_and_track(sequence, p_lid)
                    n_lit, n_ltrk = self._find_item_and_track(sequence, n_lid)
                    if p_lit and n_lit and not p_ltrk.is_locked and not n_ltrk.is_locked:
                        if p_lit.timeline_range.end_frame == n_lit.timeline_range.start_frame:
                            commands.extend([
                                TimelineCommand(
                                    command_id=str(uuid.uuid4()),
                                    op_type=TimelineOpType.TRIM_END,
                                    sequence_id=sequence.sequence_id,
                                    target_id=p_lid,
                                    payload={"delta_frames": delta_frames},
                                ),
                                TimelineCommand(
                                    command_id=str(uuid.uuid4()),
                                    op_type=TimelineOpType.TRIM_START,
                                    sequence_id=sequence.sequence_id,
                                    target_id=n_lid,
                                    payload={"delta_frames": delta_frames},
                                ),
                            ])

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Rolling edit between '{prev_it.name}' and '{next_it.name}' by {delta_frames} frames",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to commit rolling edit transaction.")

        self.base_engine._sync_spatial_index(sequence)
        return True

    # =========================================================================
    # 3. SLIP EDITING
    # =========================================================================

    def slip_edit(
        self,
        sequence: VideoSequence,
        item_id: str,
        delta_frames: int,  # Shifts media source in-frame while timeline position & duration remain fixed
        slip_linked: bool = True,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Slips the source media window without changing timeline placement or duration."""
        self.base_engine._check_revision(sequence, expected_revision)

        item, track = self._find_item_and_track(sequence, item_id)
        if not item or not track:
            raise EditConstraintViolation(f"Item '{item_id}' not found.")
        if track.is_locked:
            raise EditConstraintViolation(f"Cannot slip item on locked track '{track.name}'.")

        new_in = item.source_range.in_frame + delta_frames
        dur = item.source_range.duration_frames

        if new_in < 0:
            raise EditConstraintViolation(f"Slip edit would exceed source media head boundary (in_frame={new_in} < 0).")

        commands: List[TimelineCommand] = [
            TimelineCommand(
                command_id=str(uuid.uuid4()),
                op_type=TimelineOpType.CHANGE_SOURCE_RANGE,
                sequence_id=sequence.sequence_id,
                target_id=item_id,
                payload={"in_frame": new_in, "duration_frames": dur},
            )
        ]

        if slip_linked:
            for l_id in sequence.get_linked_items(item_id):
                if l_id == item_id:
                    continue
                l_item, l_track = self._find_item_and_track(sequence, l_id)
                if l_item and l_track and not l_track.is_locked:
                    l_new_in = l_item.source_range.in_frame + delta_frames
                    if l_new_in >= 0:
                        commands.append(
                            TimelineCommand(
                                command_id=str(uuid.uuid4()),
                                op_type=TimelineOpType.CHANGE_SOURCE_RANGE,
                                sequence_id=sequence.sequence_id,
                                target_id=l_id,
                                payload={"in_frame": l_new_in, "duration_frames": l_item.source_range.duration_frames},
                            )
                        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Slip edit on '{item.name}' by {delta_frames} frames",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to commit slip edit transaction.")

        return True

    # =========================================================================
    # 4. SLIDE EDITING
    # =========================================================================

    def slide_edit(
        self,
        sequence: VideoSequence,
        item_id: str,
        delta_frames: int,  # Moves item on timeline while trimming prev item's tail and next item's head
        slide_linked: bool = True,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Slides an item along timeline, adjusting previous clip's tail and next clip's head."""
        self.base_engine._check_revision(sequence, expected_revision)

        item, track = self._find_item_and_track(sequence, item_id)
        if not item or not track:
            raise EditConstraintViolation(f"Item '{item_id}' not found.")
        if track.is_locked:
            raise EditConstraintViolation(f"Cannot slide item on locked track '{track.name}'.")

        # Find adjacent neighbors on the same track
        sorted_items = sorted(track.items, key=lambda x: x.timeline_range.start_frame)
        idx = next((i for i, x in enumerate(sorted_items) if x.item_id == item_id), None)
        if idx is None:
            raise EditConstraintViolation("Item indexing error in track.")

        prev_item = sorted_items[idx - 1] if idx > 0 else None
        next_item = sorted_items[idx + 1] if idx < len(sorted_items) - 1 else None

        if not prev_item or not next_item:
            raise EditConstraintViolation("Slide edit requires both a preceding and following adjacent clip.")

        # Check adjacency
        if prev_item.timeline_range.end_frame != item.timeline_range.start_frame:
            raise EditConstraintViolation("Preceding clip is not adjacent to sliding clip.")
        if item.timeline_range.end_frame != next_item.timeline_range.start_frame:
            raise EditConstraintViolation("Following clip is not adjacent to sliding clip.")

        # Preceding clip tail trim by delta_frames
        v_prev, m_prev = self.constraints.can_trim_end(sequence, prev_item.item_id, delta_frames)
        if not v_prev:
            raise EditConstraintViolation(f"Slide edit previous clip constraint violation: {m_prev}")

        # Sliding clip movement by delta_frames
        new_start = item.timeline_range.start_frame + delta_frames
        v_move, m_move = self.constraints.can_move_item(sequence, item_id, new_start)
        if not v_move:
            raise EditConstraintViolation(f"Slide edit move constraint violation: {m_move}")

        # Following clip head trim by delta_frames
        v_next, m_next = self.constraints.can_trim_start(sequence, next_item.item_id, delta_frames)
        if not v_next:
            raise EditConstraintViolation(f"Slide edit next clip constraint violation: {m_next}")

        commands: List[TimelineCommand] = [
            TimelineCommand(
                command_id=str(uuid.uuid4()),
                op_type=TimelineOpType.TRIM_END,
                sequence_id=sequence.sequence_id,
                target_id=prev_item.item_id,
                payload={"delta_frames": delta_frames},
            ),
            TimelineCommand(
                command_id=str(uuid.uuid4()),
                op_type=TimelineOpType.MOVE_ITEM,
                sequence_id=sequence.sequence_id,
                target_id=item_id,
                payload={"new_start_frame": new_start},
            ),
            TimelineCommand(
                command_id=str(uuid.uuid4()),
                op_type=TimelineOpType.TRIM_START,
                sequence_id=sequence.sequence_id,
                target_id=next_item.item_id,
                payload={"delta_frames": delta_frames},
            ),
        ]

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Slide edit on '{item.name}' by {delta_frames} frames",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to commit slide edit transaction.")

        self.base_engine._sync_spatial_index(sequence)
        return True

    # =========================================================================
    # 5. GAP MANAGEMENT
    # =========================================================================

    def detect_gaps(self, sequence: VideoSequence, track_id: Optional[str] = None) -> List[TimelineGap]:
        """Detects and returns all timeline gaps across specified or all tracks."""
        gaps: List[TimelineGap] = []
        tracks = [t for t in sequence.tracks if track_id is None or t.track_id == track_id]

        for trk in tracks:
            sorted_items = sorted(trk.items, key=lambda x: x.timeline_range.start_frame)
            current_playhead = 0
            for it in sorted_items:
                if it.timeline_range.start_frame > current_playhead:
                    gaps.append(
                        TimelineGap(
                            track_id=trk.track_id,
                            start_frame=current_playhead,
                            end_frame=it.timeline_range.start_frame,
                            duration_frames=it.timeline_range.start_frame - current_playhead,
                        )
                    )
                current_playhead = max(current_playhead, it.timeline_range.end_frame)
        return gaps

    def close_gap(
        self,
        sequence: VideoSequence,
        track_id: str,
        gap_start_frame: int,
        affected_track_ids: Optional[List[str]] = None,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Finds gap starting at gap_start_frame and pulls all downstream material to close it."""
        self.base_engine._check_revision(sequence, expected_revision)

        track_gaps = [g for g in self.detect_gaps(sequence, track_id) if g.start_frame == gap_start_frame]
        if not track_gaps:
            raise EditConstraintViolation(f"No gap found on track '{track_id}' at frame {gap_start_frame}.")

        gap = track_gaps[0]
        shift = gap.duration_frames

        tracks_to_ripple: Set[str] = set(affected_track_ids) if affected_track_ids is not None else {track_id}
        downstream = self._get_downstream_items(
            sequence, threshold_frame=gap.end_frame, target_tracks=tracks_to_ripple
        )

        for d_item, d_track in downstream:
            if d_track.is_locked:
                raise EditConstraintViolation(f"Cannot close gap: downstream track '{d_track.name}' is locked.")

        commands: List[TimelineCommand] = []
        for d_item, d_track in downstream:
            commands.append(
                TimelineCommand(
                    command_id=str(uuid.uuid4()),
                    op_type=TimelineOpType.MOVE_ITEM,
                    sequence_id=sequence.sequence_id,
                    target_id=d_item.item_id,
                    payload={"new_start_frame": d_item.timeline_range.start_frame - shift},
                )
            )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Close gap of {shift} frames at {gap_start_frame}",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to commit close gap transaction.")

        self.base_engine._sync_spatial_index(sequence)
        return True

    def insert_gap(
        self,
        sequence: VideoSequence,
        track_id: str,
        insert_frame: int,
        duration_frames: int,
        affected_track_ids: Optional[List[str]] = None,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Inserts an empty gap by pushing downstream clips forward by duration_frames."""
        self.base_engine._check_revision(sequence, expected_revision)
        if duration_frames <= 0:
            raise EditConstraintViolation(f"Gap duration must be positive: {duration_frames}")

        tracks_to_ripple: Set[str] = set(affected_track_ids) if affected_track_ids is not None else {track_id}
        downstream = self._get_downstream_items(
            sequence, threshold_frame=insert_frame, target_tracks=tracks_to_ripple
        )

        for d_item, d_track in downstream:
            if d_track.is_locked:
                raise EditConstraintViolation(f"Cannot insert gap: downstream track '{d_track.name}' is locked.")

        commands: List[TimelineCommand] = []
        for d_item, d_track in downstream:
            commands.append(
                TimelineCommand(
                    command_id=str(uuid.uuid4()),
                    op_type=TimelineOpType.MOVE_ITEM,
                    sequence_id=sequence.sequence_id,
                    target_id=d_item.item_id,
                    payload={"new_start_frame": d_item.timeline_range.start_frame + duration_frames},
                )
            )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Insert gap of {duration_frames} frames at frame {insert_frame}",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to commit insert gap transaction.")

        self.base_engine._sync_spatial_index(sequence)
        return True

    # =========================================================================
    # 6. MULTI-ITEM OPERATIONS
    # =========================================================================

    def move_multiple_items(
        self,
        sequence: VideoSequence,
        item_ids: List[str],
        delta_frames: int,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Moves a collection of selected clips synchronously by delta_frames."""
        self.base_engine._check_revision(sequence, expected_revision)
        if not item_ids:
            return False

        commands: List[TimelineCommand] = []
        for i_id in item_ids:
            it, trk = self._find_item_and_track(sequence, i_id)
            if not it or not trk:
                raise EditConstraintViolation(f"Item '{i_id}' not found.")
            if trk.is_locked:
                raise EditConstraintViolation(f"Cannot move item '{it.name}' on locked track '{trk.name}'.")
            new_start = it.timeline_range.start_frame + delta_frames
            if new_start < 0:
                raise EditConstraintViolation(f"Moving '{it.name}' would place it at negative frame {new_start}.")

            commands.append(
                TimelineCommand(
                    command_id=str(uuid.uuid4()),
                    op_type=TimelineOpType.MOVE_ITEM,
                    sequence_id=sequence.sequence_id,
                    target_id=i_id,
                    payload={"new_start_frame": new_start},
                )
            )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Move {len(item_ids)} items by {delta_frames} frames",
            commands=commands,
        )

        history = self.base_engine.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to move multiple items.")

        self.base_engine._sync_spatial_index(sequence)
        return True

    # =========================================================================
    # 7. EDIT PLANNING & PREVIEW
    # =========================================================================

    def preview_edit(
        self,
        sequence: VideoSequence,
        operation_name: str,
        edit_fn: Callable[..., Any],
        *args,
        **kwargs,
    ) -> EditPlanPreview:
        """Executes edit on a deep copy of sequence to generate a preview plan without mutating original."""
        orig_seq_id = sequence.sequence_id
        seq_copy = copy.deepcopy(sequence)
        preview_id = f"preview_{uuid.uuid4().hex}"
        seq_copy.sequence_id = preview_id
        for trk in seq_copy.tracks:
            trk.sequence_id = preview_id
            for it in trk.items:
                it.sequence_id = preview_id
        try:
            edit_fn(seq_copy, *args, **kwargs)

            # Analyze diff
            affected_items = []
            affected_tracks = set()
            timeline_changes = {}
            source_changes = {}
            removed_items = []

            orig_items = {it.item_id: it for trk in sequence.tracks for it in trk.items}
            new_items = {it.item_id: it for trk in seq_copy.tracks for it in trk.items}

            for i_id, orig_it in orig_items.items():
                if i_id not in new_items:
                    removed_items.append(i_id)
                    affected_items.append(i_id)
                    affected_tracks.add(orig_it.track_id)
                else:
                    new_it = new_items[i_id]
                    if (
                        orig_it.timeline_range.start_frame != new_it.timeline_range.start_frame
                        or orig_it.timeline_range.duration_frames != new_it.timeline_range.duration_frames
                    ):
                        affected_items.append(i_id)
                        affected_tracks.add(new_it.track_id)
                        timeline_changes[i_id] = {
                            "old_start": orig_it.timeline_range.start_frame,
                            "new_start": new_it.timeline_range.start_frame,
                            "old_duration": orig_it.timeline_range.duration_frames,
                            "new_duration": new_it.timeline_range.duration_frames,
                        }
                    if (
                        orig_it.source_range.in_frame != new_it.source_range.in_frame
                        or orig_it.source_range.duration_frames != new_it.source_range.duration_frames
                    ):
                        affected_items.append(i_id)
                        source_changes[i_id] = {
                            "old_in": orig_it.source_range.in_frame,
                            "new_in": new_it.source_range.in_frame,
                            "old_duration": orig_it.source_range.duration_frames,
                            "new_duration": new_it.source_range.duration_frames,
                        }

            return EditPlanPreview(
                valid=True,
                operation_name=operation_name,
                affected_item_ids=list(set(affected_items)),
                affected_track_ids=list(affected_tracks),
                timeline_range_changes=timeline_changes,
                source_range_changes=source_changes,
                removed_item_ids=removed_items,
                delta_duration_frames=seq_copy.duration_frames - sequence.duration_frames,
                resulting_duration_frames=seq_copy.duration_frames,
                resulting_revision=seq_copy.revision,
            )
        except Exception as e:
            return EditPlanPreview(
                valid=False,
                operation_name=operation_name,
                error_message=str(e),
                resulting_revision=sequence.revision,
            )

# Global singleton
advanced_timeline_edit_engine = AdvancedTimelineEditEngine()
