"""OMNIA Video Studio — Timeline Edit Operations Engine (Module 5).

High-level editing engine that coordinates:
- Pre-mutation constraint validation via TimelineConstraintEngine
- Reversible command execution via TimelineCommand & TimelineTransaction
- Optimistic concurrency control (revision checks)
- Synchronization and link group preservation
- Undo / Redo history management
- Automatic update of spatial interval index (TimelineQueryEngine)
- Clean non-destructive operations (source media assets remain untouched)
"""

from typing import Dict, Any, List, Optional, Tuple, Set
import uuid
import time
import logging

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineMarker,
    TimelineRegion,
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
from video_studio.timeline_query import TimelineQueryEngine, timeline_query_engine

logger = logging.getLogger("Omnia.VideoStudio.EditEngine")

class StaleRevisionError(Exception):
    """Raised when an edit command supplies an outdated sequence revision."""
    pass

class TimelineEditEngine:
    """Coordinates timeline operations, constraint verification, undo/redo, and indexing."""

    def __init__(
        self,
        constraint_engine: Optional[TimelineConstraintEngine] = None,
        query_engine: Optional[TimelineQueryEngine] = None,
    ):
        self.constraints = constraint_engine or timeline_constraint_engine
        self.query_engine = query_engine or timeline_query_engine
        self._history_managers: Dict[str, TimelineHistoryManager] = {}

    def get_history_manager(self, sequence: VideoSequence) -> TimelineHistoryManager:
        if sequence.sequence_id not in self._history_managers:
            self._history_managers[sequence.sequence_id] = TimelineHistoryManager(sequence)
        else:
            self._history_managers[sequence.sequence_id].sequence = sequence
        return self._history_managers[sequence.sequence_id]

    def _check_revision(self, sequence: VideoSequence, expected_revision: Optional[int]) -> None:
        if expected_revision is not None and expected_revision != sequence.revision:
            raise StaleRevisionError(
                f"Optimistic concurrency violation: Sequence revision is {sequence.revision}, "
                f"but command expected revision {expected_revision}."
            )

    def _sync_spatial_index(self, sequence: VideoSequence) -> None:
        """Refreshes the spatial search index after timeline state changes."""
        self.query_engine.invalidate_index(sequence.sequence_id)
        self.query_engine.get_or_build_index(sequence)

    # -------------------------------------------------------------------------
    # Core Operations
    # -------------------------------------------------------------------------

    def add_clip(
        self,
        sequence: VideoSequence,
        track_id: str,
        source_reference_id: str,
        start_frame: int,
        duration_frames: int,
        source_in_frame: int = 0,
        name: str = "Clip",
        item_type: str = "MEDIA_CLIP",
        item_id: Optional[str] = None,
        expected_revision: Optional[int] = None,
    ) -> TimelineItemModel:
        """Adds a new clip to a track with full constraint validation."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_add_item(
            sequence=sequence,
            track_id=track_id,
            start_frame=start_frame,
            duration_frames=duration_frames,
            source_in_frame=source_in_frame,
        )
        if not valid:
            raise EditConstraintViolation(msg)

        new_item_id = item_id or str(uuid.uuid4())
        item_dict = {
            "item_id": new_item_id,
            "track_id": track_id,
            "source_reference_id": source_reference_id,
            "name": name,
            "item_type": item_type,
            "timeline_range": {
                "start_frame": start_frame,
                "duration_frames": duration_frames,
            },
            "source_range": {
                "in_frame": source_in_frame,
                "duration_frames": duration_frames,
            },
            "speed": 1.0,
            "is_enabled": True,
            "state": "NORMAL",
        }

        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.ADD_ITEM,
            sequence_id=sequence.sequence_id,
            target_id=new_item_id,
            payload={"track_id": track_id, "item": item_dict},
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Add clip '{name}'",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to commit Add Clip transaction.")

        self._sync_spatial_index(sequence)
        # Return added item
        for track in sequence.tracks:
            for it in track.items:
                if it.item_id == new_item_id:
                    return it
        raise RuntimeError("Item not found after Add Clip execution.")

    def remove_item(
        self,
        sequence: VideoSequence,
        item_id: str,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Removes an item from the timeline and untangles any link dependencies."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_remove_item(sequence, item_id)
        if not valid:
            raise EditConstraintViolation(msg)

        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.REMOVE_ITEM,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Remove item '{item_id}'",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError(f"Failed to remove item '{item_id}'.")

        self._sync_spatial_index(sequence)
        return True

    def move_item(
        self,
        sequence: VideoSequence,
        item_id: str,
        new_start_frame: int,
        target_track_id: Optional[str] = None,
        move_linked: bool = True,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Moves an item, optionally moving all linked items by identical delta frames."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_move_item(
            sequence=sequence,
            item_id=item_id,
            new_start_frame=new_start_frame,
            target_track_id=target_track_id,
        )
        if not valid:
            raise EditConstraintViolation(msg)

        item, current_track = self.constraints._find_item_and_track(sequence, item_id)
        if not item or not current_track:
            raise EditConstraintViolation(f"Item '{item_id}' not found.")

        delta_frames = new_start_frame - item.timeline_range.start_frame
        tx_commands: List[TimelineCommand] = []

        # Target track change command if applicable
        if target_track_id and target_track_id != current_track.track_id:
            cmd_track = TimelineCommand(
                command_id=str(uuid.uuid4()),
                op_type=TimelineOpType.CHANGE_TRACK,
                sequence_id=sequence.sequence_id,
                target_id=item_id,
                payload={"target_track_id": target_track_id},
            )
            tx_commands.append(cmd_track)

        # Primary move
        cmd_move = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.MOVE_ITEM,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
            payload={"new_start_frame": new_start_frame},
        )
        tx_commands.append(cmd_move)

        # Linked items move
        if move_linked and delta_frames != 0:
            linked_ids = sequence.get_linked_items(item_id)
            for l_id in linked_ids:
                if l_id == item_id:
                    continue
                l_item, l_track = self.constraints._find_item_and_track(sequence, l_id)
                if l_item and l_track and not l_track.is_locked:
                    l_new_start = l_item.timeline_range.start_frame + delta_frames
                    if l_new_start >= 0:
                        tx_commands.append(
                            TimelineCommand(
                                command_id=str(uuid.uuid4()),
                                op_type=TimelineOpType.MOVE_ITEM,
                                sequence_id=sequence.sequence_id,
                                target_id=l_id,
                                payload={"new_start_frame": l_new_start},
                            )
                        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Move item '{item_id}' to frame {new_start_frame}",
            commands=tx_commands,
        )

        history = self.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError(f"Failed to commit move transaction for '{item_id}'.")

        self._sync_spatial_index(sequence)
        return True

    def trim_start(
        self,
        sequence: VideoSequence,
        item_id: str,
        delta_frames: int,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Trims head of clip inwards (+delta) or outwards (-delta)."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_trim_start(sequence, item_id, delta_frames)
        if not valid:
            raise EditConstraintViolation(msg)

        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.TRIM_START,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
            payload={"delta_frames": delta_frames},
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Trim start on '{item_id}' by {delta_frames} frames",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError(f"Failed to trim start on '{item_id}'.")

        self._sync_spatial_index(sequence)
        return True

    def trim_end(
        self,
        sequence: VideoSequence,
        item_id: str,
        delta_frames: int,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Trims tail of clip inwards (-delta) or outwards (+delta)."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_trim_end(sequence, item_id, delta_frames)
        if not valid:
            raise EditConstraintViolation(msg)

        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.TRIM_END,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
            payload={"delta_frames": delta_frames},
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Trim end on '{item_id}' by {delta_frames} frames",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError(f"Failed to trim end on '{item_id}'.")

        self._sync_spatial_index(sequence)
        return True

    def split_item(
        self,
        sequence: VideoSequence,
        item_id: str,
        split_frame: int,
        right_item_id: Optional[str] = None,
        split_linked: bool = False,
        expected_revision: Optional[int] = None,
    ) -> Tuple[TimelineItemModel, TimelineItemModel]:
        """Razor cut at split_frame. Non-destructive slice sharing source media."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_split_item(sequence, item_id, split_frame)
        if not valid:
            raise EditConstraintViolation(msg)

        r_id = right_item_id or str(uuid.uuid4())
        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.SPLIT_ITEM,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
            payload={"split_frame": split_frame, "right_item_id": r_id},
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Split item '{item_id}' at frame {split_frame}",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError(f"Failed to split item '{item_id}'.")

        self._sync_spatial_index(sequence)

        left_item = None
        right_item = None
        for track in sequence.tracks:
            for it in track.items:
                if it.item_id == item_id:
                    left_item = it
                elif it.item_id == r_id:
                    right_item = it

        if not left_item or not right_item:
            raise RuntimeError("Split items could not be retrieved post-split.")

        return left_item, right_item

    def change_track(
        self,
        sequence: VideoSequence,
        item_id: str,
        target_track_id: str,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Moves an item between tracks of compatible types."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_change_track(sequence, item_id, target_track_id)
        if not valid:
            raise EditConstraintViolation(msg)

        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.CHANGE_TRACK,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
            payload={"target_track_id": target_track_id},
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Change track for item '{item_id}' to '{target_track_id}'",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError(f"Failed to change track for '{item_id}'.")

        self._sync_spatial_index(sequence)
        return True

    def change_source_range(
        self,
        sequence: VideoSequence,
        item_id: str,
        in_frame: int,
        duration_frames: int,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Adjusts source range without changing media files."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_change_source_range(sequence, item_id, in_frame, duration_frames)
        if not valid:
            raise EditConstraintViolation(msg)

        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.CHANGE_SOURCE_RANGE,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
            payload={"in_frame": in_frame, "duration_frames": duration_frames},
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Change source range for '{item_id}'",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        return history.commit_transaction(tx)

    def set_item_enabled(
        self,
        sequence: VideoSequence,
        item_id: str,
        is_enabled: bool,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Enables or disables an item on the timeline."""
        self._check_revision(sequence, expected_revision)
        op_type = TimelineOpType.ENABLE_ITEM if is_enabled else TimelineOpType.DISABLE_ITEM
        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=op_type,
            sequence_id=sequence.sequence_id,
            target_id=item_id,
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"{'Enable' if is_enabled else 'Disable'} item '{item_id}'",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        return history.commit_transaction(tx)

    def link_items(
        self,
        sequence: VideoSequence,
        item_ids: List[str],
        expected_revision: Optional[int] = None,
    ) -> str:
        """Binds two or more items into a link group."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_link_items(sequence, item_ids)
        if not valid:
            raise EditConstraintViolation(msg)

        link_id = str(uuid.uuid4())
        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.LINK_ITEMS,
            sequence_id=sequence.sequence_id,
            target_id=link_id,
            payload={"link_id": link_id, "item_ids": item_ids},
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Link items {item_ids}",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        success = history.commit_transaction(tx)
        if not success:
            raise RuntimeError("Failed to link items.")
        return link_id

    def unlink_items(
        self,
        sequence: VideoSequence,
        item_ids: List[str],
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Dissolves any link groups containing the given items."""
        self._check_revision(sequence, expected_revision)
        valid, msg = self.constraints.can_unlink_items(sequence, item_ids)
        if not valid:
            raise EditConstraintViolation(msg)

        cmd = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.UNLINK_ITEMS,
            sequence_id=sequence.sequence_id,
            target_id="",
            payload={"item_ids": item_ids},
        )

        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=sequence.sequence_id,
            description=f"Unlink items {item_ids}",
            commands=[cmd],
        )

        history = self.get_history_manager(sequence)
        return history.commit_transaction(tx)

    def undo(self, sequence: VideoSequence) -> bool:
        """Reverts the latest transaction and syncs index."""
        history = self.get_history_manager(sequence)
        res = history.undo()
        if res:
            self._sync_spatial_index(sequence)
        return res

    def redo(self, sequence: VideoSequence) -> bool:
        """Re-applies the latest undone transaction and syncs index."""
        history = self.get_history_manager(sequence)
        res = history.redo()
        if res:
            self._sync_spatial_index(sequence)
        return res

# Global singleton instance
timeline_edit_engine = TimelineEditEngine()
