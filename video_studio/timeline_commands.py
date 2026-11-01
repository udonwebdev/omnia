"""OMNIA Video Studio — Timeline Command & Transaction Architecture (Module 5).

Implements the reversible command pattern and multi-operation transactions for the timeline:
- Commands: ADD_ITEM, REMOVE_ITEM, MOVE_ITEM, TRIM_START, TRIM_END, SPLIT_ITEM,
  CHANGE_TRACK, CHANGE_SOURCE_RANGE, ENABLE_ITEM, DISABLE_ITEM,
  ADD_TRACK, REMOVE_TRACK, UPDATE_TRACK,
  ADD_MARKER, REMOVE_MARKER, UPDATE_MARKER, MOVE_MARKER,
  ADD_REGION, REMOVE_REGION, UPDATE_REGION,
  LINK_ITEMS, UNLINK_ITEMS
- Transaction grouping: multiple operations bundled atomically
- Rollback and Commit
- Undo and Redo history stack with revision tracking
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
import time
import uuid
import copy
import logging

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineItemType,
    TimelineItemState,
    TimelineMarker,
    TimelineRegion,
    TimelineRange,
    SourceRange,
    LinkGroup,
)

logger = logging.getLogger("Omnia.VideoStudio.Commands")

class TimelineOpType(str, Enum):
    ADD_ITEM = "ADD_ITEM"
    REMOVE_ITEM = "REMOVE_ITEM"
    MOVE_ITEM = "MOVE_ITEM"
    TRIM_START = "TRIM_START"
    TRIM_END = "TRIM_END"
    SPLIT_ITEM = "SPLIT_ITEM"
    CHANGE_TRACK = "CHANGE_TRACK"
    CHANGE_SOURCE_RANGE = "CHANGE_SOURCE_RANGE"
    ENABLE_ITEM = "ENABLE_ITEM"
    DISABLE_ITEM = "DISABLE_ITEM"
    ADD_TRACK = "ADD_TRACK"
    REMOVE_TRACK = "REMOVE_TRACK"
    UPDATE_TRACK = "UPDATE_TRACK"
    ADD_MARKER = "ADD_MARKER"
    REMOVE_MARKER = "REMOVE_MARKER"
    UPDATE_MARKER = "UPDATE_MARKER"
    MOVE_MARKER = "MOVE_MARKER"
    ADD_REGION = "ADD_REGION"
    REMOVE_REGION = "REMOVE_REGION"
    UPDATE_REGION = "UPDATE_REGION"
    LINK_ITEMS = "LINK_ITEMS"
    UNLINK_ITEMS = "UNLINK_ITEMS"

@dataclass
class TimelineCommand:
    """Reversible command operating on a sequence."""
    command_id: str
    op_type: TimelineOpType
    sequence_id: str
    target_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    previous_state: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def execute(self, sequence: VideoSequence) -> bool:
        """Applies the command forward."""
        if self.op_type == TimelineOpType.ADD_ITEM:
            track = next((t for t in sequence.tracks if t.track_id == self.payload["track_id"]), None)
            if not track:
                return False
            item_data = self.payload["item"]
            itype = item_data.get("item_type", TimelineItemType.MEDIA_CLIP)
            if isinstance(itype, str):
                try:
                    itype = TimelineItemType(itype)
                except ValueError:
                    itype = TimelineItemType.MEDIA_CLIP

            istate = item_data.get("state", TimelineItemState.READY)
            if isinstance(istate, str):
                try:
                    istate = TimelineItemState(istate)
                except ValueError:
                    istate = TimelineItemState.READY

            item = TimelineItemModel(
                item_id=item_data["item_id"],
                track_id=track.track_id,
                sequence_id=sequence.sequence_id,
                source_reference_id=item_data["source_reference_id"],
                name=item_data.get("name", "Clip"),
                item_type=itype,
                timeline_range=TimelineRange(
                    start_frame=item_data["timeline_range"]["start_frame"],
                    duration_frames=item_data["timeline_range"]["duration_frames"],
                ),
                source_range=SourceRange(
                    in_frame=item_data["source_range"]["in_frame"],
                    duration_frames=item_data["source_range"]["duration_frames"],
                ),
                speed=item_data.get("speed", 1.0),
                is_enabled=item_data.get("is_enabled", True),
                state=istate,
            )
            track.items.append(item)
            sequence.calculate_duration_frames()
            return True

        elif self.op_type == TimelineOpType.REMOVE_ITEM:
            for track in sequence.tracks:
                for idx, it in enumerate(track.items):
                    if it.item_id == self.target_id:
                        self.previous_state["track_id"] = track.track_id
                        self.previous_state["item"] = it.to_dict()
                        track.items.pop(idx)
                        sequence.calculate_duration_frames()
                        return True
            return False

        elif self.op_type == TimelineOpType.MOVE_ITEM:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        self.previous_state["start_frame"] = it.timeline_range.start_frame
                        it.timeline_range.start_frame = self.payload["new_start_frame"]
                        sequence.calculate_duration_frames()
                        return True
            return False

        elif self.op_type == TimelineOpType.TRIM_START:
            # payload: {"delta_frames": int}
            delta = self.payload["delta_frames"]
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        self.previous_state["start_frame"] = it.timeline_range.start_frame
                        self.previous_state["timeline_duration"] = it.timeline_range.duration_frames
                        self.previous_state["source_in"] = it.source_range.in_frame
                        self.previous_state["source_duration"] = it.source_range.duration_frames

                        it.timeline_range.start_frame += delta
                        it.timeline_range.duration_frames -= delta
                        it.source_range.in_frame += delta
                        it.source_range.duration_frames -= delta
                        sequence.calculate_duration_frames()
                        return True
            return False

        elif self.op_type == TimelineOpType.TRIM_END:
            # payload: {"delta_frames": int}
            delta = self.payload["delta_frames"]
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        self.previous_state["timeline_duration"] = it.timeline_range.duration_frames
                        self.previous_state["source_duration"] = it.source_range.duration_frames

                        it.timeline_range.duration_frames += delta
                        it.source_range.duration_frames += delta
                        sequence.calculate_duration_frames()
                        return True
            return False

        elif self.op_type == TimelineOpType.SPLIT_ITEM:
            # Razor cut at split_frame
            # payload: {"split_frame": int, "right_item_id": str}
            split_frame = self.payload["split_frame"]
            right_item_id = self.payload.get("right_item_id") or str(uuid.uuid4())
            self.payload["right_item_id"] = right_item_id

            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        start = it.timeline_range.start_frame
                        total_dur = it.timeline_range.duration_frames
                        src_in = it.source_range.in_frame

                        left_dur = split_frame - start
                        right_dur = total_dur - left_dur

                        # Record previous state for undo
                        self.previous_state["original_duration"] = total_dur
                        self.previous_state["original_source_duration"] = it.source_range.duration_frames
                        self.previous_state["track_id"] = track.track_id
                        self.previous_state["right_item_id"] = right_item_id

                        # Left clip keeps same item_id, adjusts duration
                        it.timeline_range.duration_frames = left_dur
                        it.source_range.duration_frames = left_dur

                        # Right clip created
                        right_item = TimelineItemModel(
                            item_id=right_item_id,
                            track_id=track.track_id,
                            sequence_id=sequence.sequence_id,
                            source_reference_id=it.source_reference_id,
                            name=f"{it.name} (Cut)",
                            item_type=it.item_type,
                            timeline_range=TimelineRange(
                                start_frame=split_frame,
                                duration_frames=right_dur,
                            ),
                            source_range=SourceRange(
                                in_frame=src_in + left_dur,
                                duration_frames=right_dur,
                            ),
                            speed=it.speed,
                            is_enabled=it.is_enabled,
                            state=it.state,
                        )
                        track.items.append(right_item)
                        sequence.calculate_duration_frames()
                        return True
            return False

        elif self.op_type == TimelineOpType.CHANGE_TRACK:
            target_track_id = self.payload["target_track_id"]
            for current_track in sequence.tracks:
                for idx, it in enumerate(current_track.items):
                    if it.item_id == self.target_id:
                        target_track = next((t for t in sequence.tracks if t.track_id == target_track_id), None)
                        if not target_track:
                            return False
                        self.previous_state["source_track_id"] = current_track.track_id
                        current_track.items.pop(idx)
                        it.track_id = target_track_id
                        target_track.items.append(it)
                        return True
            return False

        elif self.op_type == TimelineOpType.CHANGE_SOURCE_RANGE:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        self.previous_state["in_frame"] = it.source_range.in_frame
                        self.previous_state["duration_frames"] = it.source_range.duration_frames
                        it.source_range.in_frame = self.payload["in_frame"]
                        it.source_range.duration_frames = self.payload["duration_frames"]
                        return True
            return False

        elif self.op_type == TimelineOpType.ENABLE_ITEM:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        self.previous_state["is_enabled"] = it.is_enabled
                        it.is_enabled = True
                        return True
            return False

        elif self.op_type == TimelineOpType.DISABLE_ITEM:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        self.previous_state["is_enabled"] = it.is_enabled
                        it.is_enabled = False
                        return True
            return False

        elif self.op_type == TimelineOpType.ADD_TRACK:
            track = TimelineTrackModel(
                track_id=self.payload["track_id"],
                sequence_id=sequence.sequence_id,
                name=self.payload["name"],
                track_type=self.payload["track_type"],
                index=len(sequence.tracks),
            )
            sequence.tracks.append(track)
            return True

        elif self.op_type == TimelineOpType.REMOVE_TRACK:
            for idx, track in enumerate(sequence.tracks):
                if track.track_id == self.target_id:
                    self.previous_state["track"] = track.to_dict()
                    self.previous_state["index"] = idx
                    sequence.tracks.pop(idx)
                    sequence.calculate_duration_frames()
                    return True
            return False

        elif self.op_type == TimelineOpType.UPDATE_TRACK:
            for track in sequence.tracks:
                if track.track_id == self.target_id:
                    self.previous_state["track"] = track.to_dict()
                    if "name" in self.payload:
                        track.name = self.payload["name"]
                    if "is_locked" in self.payload:
                        track.is_locked = self.payload["is_locked"]
                    if "is_muted" in self.payload:
                        track.is_muted = self.payload["is_muted"]
                    if "is_solo" in self.payload:
                        track.is_solo = self.payload["is_solo"]
                    if "is_visible" in self.payload:
                        track.is_visible = self.payload["is_visible"]
                    return True
            return False

        elif self.op_type == TimelineOpType.ADD_MARKER:
            marker = TimelineMarker(
                marker_id=self.payload["marker_id"],
                sequence_id=sequence.sequence_id,
                frame=self.payload["frame"],
                name=self.payload.get("name", "Marker"),
                category=self.payload.get("category", "GENERAL"),
                color_hex=self.payload.get("color_hex", "#00f0ff"),
            )
            sequence.markers.append(marker)
            return True

        elif self.op_type == TimelineOpType.REMOVE_MARKER:
            for idx, m in enumerate(sequence.markers):
                if m.marker_id == self.target_id:
                    self.previous_state["marker"] = m.to_dict()
                    sequence.markers.pop(idx)
                    return True
            return False

        elif self.op_type == TimelineOpType.MOVE_MARKER:
            for m in sequence.markers:
                if m.marker_id == self.target_id:
                    self.previous_state["frame"] = m.frame
                    m.frame = self.payload["frame"]
                    return True
            return False

        elif self.op_type == TimelineOpType.UPDATE_MARKER:
            for m in sequence.markers:
                if m.marker_id == self.target_id:
                    self.previous_state["marker"] = m.to_dict()
                    if "name" in self.payload:
                        m.name = self.payload["name"]
                    if "color_hex" in self.payload:
                        m.color_hex = self.payload["color_hex"]
                    if "category" in self.payload:
                        m.category = self.payload["category"]
                    return True
            return False

        elif self.op_type == TimelineOpType.ADD_REGION:
            region = TimelineRegion(
                region_id=self.payload["region_id"],
                sequence_id=sequence.sequence_id,
                start_frame=self.payload["start_frame"],
                duration_frames=self.payload["duration_frames"],
                name=self.payload.get("name", "Region"),
                color_hex=self.payload.get("color_hex", "#ff007f"),
            )
            sequence.regions.append(region)
            return True

        elif self.op_type == TimelineOpType.REMOVE_REGION:
            for idx, r in enumerate(sequence.regions):
                if r.region_id == self.target_id:
                    self.previous_state["region"] = r.to_dict()
                    sequence.regions.pop(idx)
                    return True
            return False

        elif self.op_type == TimelineOpType.LINK_ITEMS:
            # payload: {"item_ids": List[str], "link_id": str}
            link_id = self.payload.get("link_id") or str(uuid.uuid4())
            group = LinkGroup(
                link_group_id=link_id,
                sequence_id=sequence.sequence_id,
                item_ids=set(self.payload["item_ids"]),
            )
            old_links = []
            for it_id in self.payload["item_ids"]:
                for lg in sequence.link_groups.values():
                    if it_id in lg.item_ids:
                        old_links.append(lg.to_dict())
            self.previous_state["old_links"] = old_links
            sequence.link_groups[link_id] = group
            return True

        elif self.op_type == TimelineOpType.UNLINK_ITEMS:
            item_ids = set(self.payload.get("item_ids", []))
            removed = []
            new_groups = {}
            for lg_id, lg in sequence.link_groups.items():
                if self.target_id and lg.link_group_id == self.target_id:
                    removed.append(lg.to_dict())
                elif any(i in item_ids for i in lg.item_ids):
                    removed.append(lg.to_dict())
                else:
                    new_groups[lg_id] = lg
            self.previous_state["removed_links"] = removed
            sequence.link_groups = new_groups
            return True

        return False

    def undo(self, sequence: VideoSequence) -> bool:
        """Rolls back the effect of the command."""
        if self.op_type == TimelineOpType.ADD_ITEM:
            item_id = self.payload["item"]["item_id"]
            for track in sequence.tracks:
                track.items = [it for it in track.items if it.item_id != item_id]
            sequence.calculate_duration_frames()
            return True

        elif self.op_type == TimelineOpType.REMOVE_ITEM:
            track = next((t for t in sequence.tracks if t.track_id == self.previous_state.get("track_id")), None)
            if not track or "item" not in self.previous_state:
                return False
            data = self.previous_state["item"]
            itype = data.get("item_type", TimelineItemType.MEDIA_CLIP)
            if isinstance(itype, str):
                try:
                    itype = TimelineItemType(itype)
                except ValueError:
                    itype = TimelineItemType.MEDIA_CLIP

            istate = data.get("state", TimelineItemState.READY)
            if isinstance(istate, str):
                try:
                    istate = TimelineItemState(istate)
                except ValueError:
                    istate = TimelineItemState.READY

            item = TimelineItemModel(
                item_id=data["item_id"],
                track_id=track.track_id,
                sequence_id=sequence.sequence_id,
                source_reference_id=data["source_reference_id"],
                name=data.get("name", "Clip"),
                item_type=itype,
                timeline_range=TimelineRange(
                    start_frame=data["timeline_range"]["start_frame"],
                    duration_frames=data["timeline_range"]["duration_frames"],
                ),
                source_range=SourceRange(
                    in_frame=data["source_range"]["in_frame"],
                    duration_frames=data["source_range"]["duration_frames"],
                ),
                speed=data.get("speed", 1.0),
                is_enabled=data.get("is_enabled", True),
                state=istate,
            )
            track.items.append(item)
            sequence.calculate_duration_frames()
            return True

        elif self.op_type == TimelineOpType.MOVE_ITEM:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        it.timeline_range.start_frame = self.previous_state["start_frame"]
                        sequence.calculate_duration_frames()
                        return True
            return False

        elif self.op_type == TimelineOpType.TRIM_START:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        it.timeline_range.start_frame = self.previous_state["start_frame"]
                        it.timeline_range.duration_frames = self.previous_state["timeline_duration"]
                        it.source_range.in_frame = self.previous_state["source_in"]
                        it.source_range.duration_frames = self.previous_state["source_duration"]
                        sequence.calculate_duration_frames()
                        return True
            return False

        elif self.op_type == TimelineOpType.TRIM_END:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        it.timeline_range.duration_frames = self.previous_state["timeline_duration"]
                        it.source_range.duration_frames = self.previous_state["source_duration"]
                        sequence.calculate_duration_frames()
                        return True
            return False

        elif self.op_type == TimelineOpType.SPLIT_ITEM:
            # Delete right slice and restore left slice duration
            right_id = self.previous_state["right_item_id"]
            track_id = self.previous_state["track_id"]
            orig_dur = self.previous_state["original_duration"]
            orig_src_dur = self.previous_state["original_source_duration"]

            track = next((t for t in sequence.tracks if t.track_id == track_id), None)
            if not track:
                return False

            track.items = [it for it in track.items if it.item_id != right_id]
            left_item = next((it for it in track.items if it.item_id == self.target_id), None)
            if left_item:
                left_item.timeline_range.duration_frames = orig_dur
                left_item.source_range.duration_frames = orig_src_dur
            sequence.calculate_duration_frames()
            return True

        elif self.op_type == TimelineOpType.CHANGE_TRACK:
            src_track_id = self.previous_state["source_track_id"]
            for current_track in sequence.tracks:
                for idx, it in enumerate(current_track.items):
                    if it.item_id == self.target_id:
                        src_track = next((t for t in sequence.tracks if t.track_id == src_track_id), None)
                        if not src_track:
                            return False
                        current_track.items.pop(idx)
                        it.track_id = src_track_id
                        src_track.items.append(it)
                        return True
            return False

        elif self.op_type == TimelineOpType.CHANGE_SOURCE_RANGE:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        it.source_range.in_frame = self.previous_state["in_frame"]
                        it.source_range.duration_frames = self.previous_state["duration_frames"]
                        return True
            return False

        elif self.op_type == TimelineOpType.ENABLE_ITEM or self.op_type == TimelineOpType.DISABLE_ITEM:
            for track in sequence.tracks:
                for it in track.items:
                    if it.item_id == self.target_id:
                        it.is_enabled = self.previous_state["is_enabled"]
                        return True
            return False

        elif self.op_type == TimelineOpType.ADD_TRACK:
            sequence.tracks = [t for t in sequence.tracks if t.track_id != self.payload["track_id"]]
            return True

        elif self.op_type == TimelineOpType.REMOVE_TRACK:
            track_data = self.previous_state["track"]
            index = self.previous_state["index"]
            track = TimelineTrackModel(
                track_id=track_data["track_id"],
                sequence_id=sequence.sequence_id,
                name=track_data["name"],
                track_type=track_data["track_type"],
                index=index,
                is_locked=track_data.get("is_locked", False),
                is_muted=track_data.get("is_muted", False),
                is_solo=track_data.get("is_solo", False),
                is_visible=track_data.get("is_visible", True),
            )
            # Reconstruct items
            for it_data in track_data.get("items", []):
                item = TimelineItemModel(
                    item_id=it_data["item_id"],
                    track_id=track.track_id,
                    sequence_id=sequence.sequence_id,
                    source_reference_id=it_data["source_reference_id"],
                    name=it_data.get("name", "Clip"),
                    timeline_range=TimelineRange(
                        start_frame=it_data["timeline_range"]["start_frame"],
                        duration_frames=it_data["timeline_range"]["duration_frames"],
                    ),
                    source_range=SourceRange(
                        in_frame=it_data["source_range"]["in_frame"],
                        duration_frames=it_data["source_range"]["duration_frames"],
                    ),
                )
                track.items.append(item)
            sequence.tracks.insert(index, track)
            sequence.calculate_duration_frames()
            return True

        elif self.op_type == TimelineOpType.UPDATE_TRACK:
            track_data = self.previous_state["track"]
            for track in sequence.tracks:
                if track.track_id == self.target_id:
                    track.name = track_data["name"]
                    track.is_locked = track_data.get("is_locked", False)
                    track.is_muted = track_data.get("is_muted", False)
                    track.is_solo = track_data.get("is_solo", False)
                    track.is_visible = track_data.get("is_visible", True)
                    return True
            return False

        elif self.op_type == TimelineOpType.ADD_MARKER:
            sequence.markers = [m for m in sequence.markers if m.marker_id != self.payload["marker_id"]]
            return True

        elif self.op_type == TimelineOpType.REMOVE_MARKER:
            m_data = self.previous_state["marker"]
            m = TimelineMarker(
                marker_id=m_data["marker_id"],
                sequence_id=sequence.sequence_id,
                frame=m_data["frame"],
                name=m_data["name"],
                category=m_data["category"],
                color_hex=m_data["color_hex"],
            )
            sequence.markers.append(m)
            return True

        elif self.op_type == TimelineOpType.MOVE_MARKER:
            for m in sequence.markers:
                if m.marker_id == self.target_id:
                    m.frame = self.previous_state["frame"]
                    return True
            return False

        elif self.op_type == TimelineOpType.UPDATE_MARKER:
            m_data = self.previous_state["marker"]
            for m in sequence.markers:
                if m.marker_id == self.target_id:
                    m.name = m_data["name"]
                    m.color_hex = m_data["color_hex"]
                    m.category = m_data["category"]
                    return True
            return False

        elif self.op_type == TimelineOpType.ADD_REGION:
            sequence.regions = [r for r in sequence.regions if r.region_id != self.payload["region_id"]]
            return True

        elif self.op_type == TimelineOpType.REMOVE_REGION:
            r_data = self.previous_state["region"]
            r = TimelineRegion(
                region_id=r_data["region_id"],
                sequence_id=sequence.sequence_id,
                start_frame=r_data["start_frame"],
                duration_frames=r_data["duration_frames"],
                name=r_data["name"],
                color_hex=r_data["color_hex"],
            )
            sequence.regions.append(r)
            return True

        elif self.op_type == TimelineOpType.LINK_ITEMS:
            link_id = self.payload.get("link_id")
            if link_id in sequence.link_groups:
                del sequence.link_groups[link_id]
            for lg_data in self.previous_state.get("old_links", []):
                lg_obj = LinkGroup(
                    link_group_id=lg_data["link_group_id"],
                    sequence_id=sequence.sequence_id,
                    item_ids=set(lg_data["item_ids"]),
                )
                sequence.link_groups[lg_obj.link_group_id] = lg_obj
            return True

        elif self.op_type == TimelineOpType.UNLINK_ITEMS:
            for r_lg in self.previous_state.get("removed_links", []):
                lg_obj = LinkGroup(
                    link_group_id=r_lg["link_group_id"],
                    sequence_id=sequence.sequence_id,
                    item_ids=set(r_lg["item_ids"]),
                )
                sequence.link_groups[lg_obj.link_group_id] = lg_obj
            return True

        return False

@dataclass
class TimelineTransaction:
    """Atomic group of timeline commands committed together."""
    transaction_id: str
    sequence_id: str
    description: str = "Timeline Edit"
    commands: List[TimelineCommand] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    committed: bool = False

    def append(self, cmd: TimelineCommand) -> None:
        self.commands.append(cmd)

class TimelineHistoryManager:
    """Maintains transactional undo/redo stacks for a sequence."""

    def __init__(self, sequence: VideoSequence, max_history: int = 50):
        self.sequence = sequence
        self.max_history = max_history
        self._undo_stack: List[TimelineTransaction] = []
        self._redo_stack: List[TimelineTransaction] = []

    def commit_transaction(self, tx: TimelineTransaction) -> bool:
        """Applies transaction, clears redo stack, and increments sequence revision."""
        # Execute all commands
        for cmd in tx.commands:
            ok = cmd.execute(self.sequence)
            if not ok:
                # Rollback partially executed commands
                self.rollback_transaction(tx)
                return False

        tx.committed = True
        self._undo_stack.append(tx)
        if len(self._undo_stack) > self.max_history:
            self._undo_stack.pop(0)

        self._redo_stack.clear()
        self.sequence.revision += 1
        self.sequence.updated_at = time.time()
        return True

    def rollback_transaction(self, tx: TimelineTransaction) -> None:
        """Rolls back any commands that were applied in this transaction."""
        for cmd in reversed(tx.commands):
            cmd.undo(self.sequence)

    def undo(self) -> bool:
        """Reverts the latest transaction."""
        if not self._undo_stack:
            return False

        tx = self._undo_stack.pop()
        for cmd in reversed(tx.commands):
            cmd.undo(self.sequence)

        self._redo_stack.append(tx)
        self.sequence.revision += 1
        self.sequence.updated_at = time.time()
        return True

    def redo(self) -> bool:
        """Re-applies the latest undone transaction."""
        if not self._redo_stack:
            return False

        tx = self._redo_stack.pop()
        for cmd in tx.commands:
            cmd.execute(self.sequence)

        self._undo_stack.append(tx)
        self.sequence.revision += 1
        self.sequence.updated_at = time.time()
        return True

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)
