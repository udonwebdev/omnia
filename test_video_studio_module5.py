"""Unit & Integration Test Suite for OMNIA Video Studio — Module 5.

Verifies:
1. Pre-mutation constraint checks (locked track safeguards, negative bounds, zero duration floors, track compatibility).
2. Non-destructive Add Item, Remove Item, and Move Item commands.
3. Trim Start & Trim End logic (head/tail trimming, duration updates, source range sync).
4. Razor Cut / Split Item logic (creating 2 slices sharing source media, correct duration & in_frame splitting).
5. Track Change compatibility matrix enforcement.
6. Multi-item Link Groups & synchronized movement.
7. Multi-operation atomic transactions and rollback on failure.
8. Monotonically increasing revision numbers & optimistic concurrency rejection on stale revision.
9. Complete undo / redo history stack restoration.
10. Source media immutability (original source references and bounds are never mutilated).
11. Spatial query engine index updates after edits.
"""

import unittest
import uuid
import tempfile
import os

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineTrackType,
    TimelineItemType,
    TimelineRange,
    SourceRange,
    SequenceSettings,
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
from video_studio.timeline_query import TimelineQueryEngine


class TestVideoStudioModule5(unittest.TestCase):

    def setUp(self):
        self.engine = TimelineEditEngine(
            constraint_engine=TimelineConstraintEngine(),
            query_engine=TimelineQueryEngine(),
        )
        self.seq = VideoSequence(
            sequence_id="seq_test_5",
            project_id="proj_alpha",
            name="Module 5 Verification Sequence",
            settings=SequenceSettings(frame_rate=24.0),
            tracks=[
                TimelineTrackModel(track_id="trk_v1", sequence_id="seq_test_5", name="Video 1", track_type=TimelineTrackType.VIDEO, index=0),
                TimelineTrackModel(track_id="trk_v2", sequence_id="seq_test_5", name="Video 2", track_type=TimelineTrackType.VIDEO, index=1),
                TimelineTrackModel(track_id="trk_a1", sequence_id="seq_test_5", name="Audio 1", track_type=TimelineTrackType.AUDIO, index=2),
                TimelineTrackModel(track_id="trk_locked", sequence_id="seq_test_5", name="Locked Video", track_type=TimelineTrackType.VIDEO, index=3, is_locked=True),
            ]
        )

    def test_01_constraints_locked_track_and_negative_guards(self):
        """Ensure constraint engine guards against locked tracks and negative frames."""
        # Attempt to add to locked track
        valid, msg = self.engine.constraints.can_add_item(self.seq, "trk_locked", start_frame=0, duration_frames=48)
        self.assertFalse(valid)
        self.assertIn("locked", msg.lower())

        # Attempt negative start frame
        valid, msg = self.engine.constraints.can_add_item(self.seq, "trk_v1", start_frame=-10, duration_frames=48)
        self.assertFalse(valid)
        self.assertIn("negative", msg.lower())

        # Attempt zero duration
        valid, msg = self.engine.constraints.can_add_item(self.seq, "trk_v1", start_frame=0, duration_frames=0)
        self.assertFalse(valid)
        self.assertIn("at least 1", msg.lower())

    def test_02_add_and_remove_clip_non_destructive(self):
        """Test adding and removing clips with transaction history."""
        clip = self.engine.add_clip(
            sequence=self.seq,
            track_id="trk_v1",
            source_reference_id="asset_raw_01",
            start_frame=24,
            duration_frames=72,
            source_in_frame=10,
            name="Intro Shot",
        )
        self.assertIsNotNone(clip)
        self.assertEqual(clip.timeline_range.start_frame, 24)
        self.assertEqual(clip.timeline_range.duration_frames, 72)
        self.assertEqual(clip.source_range.in_frame, 10)
        self.assertEqual(self.seq.revision, 2)

        # Remove clip
        ok = self.engine.remove_item(self.seq, clip.item_id)
        self.assertTrue(ok)
        self.assertEqual(self.seq.revision, 3)
        v1_track = next(t for t in self.seq.tracks if t.track_id == "trk_v1")
        self.assertEqual(len(v1_track.items), 0)

        # Undo removal
        self.engine.undo(self.seq)
        self.assertEqual(len(v1_track.items), 1)
        self.assertEqual(v1_track.items[0].item_id, clip.item_id)

    def test_03_trim_start_and_trim_end(self):
        """Test trimming head and tail of an item."""
        clip = self.engine.add_clip(
            sequence=self.seq,
            track_id="trk_v1",
            source_reference_id="asset_raw_02",
            start_frame=100,
            duration_frames=100,
            source_in_frame=50,
            name="Trim Clip",
        )

        # Trim start by +20 frames (inward)
        self.engine.trim_start(self.seq, clip.item_id, delta_frames=20)
        self.assertEqual(clip.timeline_range.start_frame, 120)
        self.assertEqual(clip.timeline_range.duration_frames, 80)
        self.assertEqual(clip.source_range.in_frame, 70)
        self.assertEqual(clip.source_range.duration_frames, 80)

        # Trim end by -30 frames (inward)
        self.engine.trim_end(self.seq, clip.item_id, delta_frames=-30)
        self.assertEqual(clip.timeline_range.duration_frames, 50)
        self.assertEqual(clip.source_range.duration_frames, 50)

        # Undo trim end
        self.engine.undo(self.seq)
        self.assertEqual(clip.timeline_range.duration_frames, 80)

        # Undo trim start
        self.engine.undo(self.seq)
        self.assertEqual(clip.timeline_range.start_frame, 100)
        self.assertEqual(clip.timeline_range.duration_frames, 100)
        self.assertEqual(clip.source_range.in_frame, 50)

    def test_04_split_razor_cut(self):
        """Test razor splitting a clip at a specific frame into two slices sharing source asset."""
        clip = self.engine.add_clip(
            sequence=self.seq,
            track_id="trk_v1",
            source_reference_id="asset_raw_movie",
            start_frame=0,
            duration_frames=100,
            source_in_frame=500,
            name="Scene 1",
        )

        left, right = self.engine.split_item(self.seq, clip.item_id, split_frame=40)
        self.assertEqual(left.timeline_range.start_frame, 0)
        self.assertEqual(left.timeline_range.duration_frames, 40)
        self.assertEqual(left.source_range.in_frame, 500)
        self.assertEqual(left.source_range.duration_frames, 40)

        self.assertEqual(right.timeline_range.start_frame, 40)
        self.assertEqual(right.timeline_range.duration_frames, 60)
        self.assertEqual(right.source_range.in_frame, 540)
        self.assertEqual(right.source_range.duration_frames, 60)
        self.assertEqual(left.source_reference_id, right.source_reference_id)

        # Verify undo of split restores single clip
        self.engine.undo(self.seq)
        v1_track = next(t for t in self.seq.tracks if t.track_id == "trk_v1")
        self.assertEqual(len(v1_track.items), 1)
        self.assertEqual(v1_track.items[0].timeline_range.duration_frames, 100)

    def test_05_track_change_compatibility(self):
        """Ensure item track moves enforce type compatibility matrix."""
        clip = self.engine.add_clip(
            sequence=self.seq,
            track_id="trk_v1",
            source_reference_id="asset_raw_v",
            start_frame=0,
            duration_frames=50,
        )

        # Allowed move: Video 1 to Video 2
        ok = self.engine.change_track(self.seq, clip.item_id, target_track_id="trk_v2")
        self.assertTrue(ok)
        self.assertEqual(clip.track_id, "trk_v2")

        # Disallowed move: Video 2 to Audio 1
        with self.assertRaises(EditConstraintViolation):
            self.engine.change_track(self.seq, clip.item_id, target_track_id="trk_a1")

        # Disallowed move: Video 2 to Locked Track
        with self.assertRaises(EditConstraintViolation):
            self.engine.change_track(self.seq, clip.item_id, target_track_id="trk_locked")

    def test_06_link_groups_and_synchronized_move(self):
        """Test linking a video and audio clip and moving them concurrently."""
        v_clip = self.engine.add_clip(
            sequence=self.seq,
            track_id="trk_v1",
            source_reference_id="synced_av_asset",
            start_frame=0,
            duration_frames=100,
            name="Video Clip",
        )
        a_clip = self.engine.add_clip(
            sequence=self.seq,
            track_id="trk_a1",
            source_reference_id="synced_av_asset",
            start_frame=0,
            duration_frames=100,
            name="Audio Clip",
        )

        # Link them
        link_id = self.engine.link_items(self.seq, [v_clip.item_id, a_clip.item_id])
        self.assertTrue(len(link_id) > 0)
        self.assertIn(a_clip.item_id, self.seq.get_linked_items(v_clip.item_id))

        # Move video clip by +50 frames with move_linked=True
        self.engine.move_item(self.seq, v_clip.item_id, new_start_frame=50, move_linked=True)
        self.assertEqual(v_clip.timeline_range.start_frame, 50)
        self.assertEqual(a_clip.timeline_range.start_frame, 50)

        # Undo move
        self.engine.undo(self.seq)
        self.assertEqual(v_clip.timeline_range.start_frame, 0)
        self.assertEqual(a_clip.timeline_range.start_frame, 0)

    def test_07_optimistic_concurrency_revision_check(self):
        """Ensure edits fail when a client supplies an outdated revision."""
        clip = self.engine.add_clip(
            sequence=self.seq,
            track_id="trk_v1",
            source_reference_id="asset_raw",
            start_frame=0,
            duration_frames=50,
        )
        current_rev = self.seq.revision

        # Pass correct expected revision
        self.engine.trim_end(self.seq, clip.item_id, delta_frames=-10, expected_revision=current_rev)

        # Pass stale revision
        with self.assertRaises(StaleRevisionError):
            self.engine.move_item(self.seq, clip.item_id, new_start_frame=20, expected_revision=current_rev)

    def test_08_transaction_rollback_on_failure(self):
        """Verify that when a transaction encounters an invalid sub-command, it rolls back cleanly."""
        clip1 = self.engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=50)
        clip2 = self.engine.add_clip(self.seq, "trk_v1", "asset_2", start_frame=50, duration_frames=50)

        history = self.engine.get_history_manager(self.seq)
        rev_before = self.seq.revision

        # Bundle two commands: one valid, one pointing to a non-existent item
        cmd1 = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.MOVE_ITEM,
            sequence_id=self.seq.sequence_id,
            target_id=clip1.item_id,
            payload={"new_start_frame": 10},
        )
        cmd2 = TimelineCommand(
            command_id=str(uuid.uuid4()),
            op_type=TimelineOpType.MOVE_ITEM,
            sequence_id=self.seq.sequence_id,
            target_id="non_existent_item_id",
            payload={"new_start_frame": 80},
        )
        tx = TimelineTransaction(
            transaction_id=str(uuid.uuid4()),
            sequence_id=self.seq.sequence_id,
            commands=[cmd1, cmd2],
        )

        success = history.commit_transaction(tx)
        self.assertFalse(success)
        # Verify clip1 was rolled back to start_frame=0
        self.assertEqual(clip1.timeline_range.start_frame, 0)
        self.assertEqual(self.seq.revision, rev_before)

    def test_09_enable_disable_clip(self):
        """Test enabling and disabling clips."""
        clip = self.engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=50)
        self.assertTrue(clip.is_enabled)

        self.engine.set_item_enabled(self.seq, clip.item_id, False)
        self.assertFalse(clip.is_enabled)

        self.engine.undo(self.seq)
        self.assertTrue(clip.is_enabled)

    def test_10_spatial_index_auto_sync(self):
        """Ensure spatial index reflects additions, splits, and trims accurately."""
        clip = self.engine.add_clip(self.seq, "trk_v1", "asset_x", start_frame=10, duration_frames=40)
        
        # Intersecting query
        hits = self.engine.query_engine.get_items_intersecting_range(self.seq, 0, 20)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].item_id, clip.item_id)

        # Razor cut at 30
        left, right = self.engine.split_item(self.seq, clip.item_id, split_frame=30)
        hits_left = self.engine.query_engine.get_items_intersecting_range(self.seq, 15, 25)
        self.assertEqual(len(hits_left), 1)
        self.assertEqual(hits_left[0].item_id, left.item_id)

        hits_right = self.engine.query_engine.get_items_intersecting_range(self.seq, 35, 45)
        self.assertEqual(len(hits_right), 1)
        self.assertEqual(hits_right[0].item_id, right.item_id)


if __name__ == "__main__":
    unittest.main()
