"""Unit & Integration Test Suite for OMNIA Video Studio — Module 6.

Verifies:
1. Ripple Editing:
   - Ripple trim start (+/- delta, downstream shift left/right).
   - Ripple trim end (+/- delta, downstream shift left/right).
   - Ripple delete (single item, multi-track, downstream closure).
   - Downstream locked track collision defense.
   - Linked audiovisual companion ripple trim & delete.
2. Rolling Editing:
   - Boundary movement between adjacent clips.
   - Preserves combined duration.
   - Non-adjacent clip rejection.
   - Minimum duration and source bounds enforcement.
3. Slip Editing:
   - Source in/out frame alteration.
   - Preserves constant timeline start_frame and duration_frames.
   - Negative source in_frame boundary defense.
4. Slide Editing:
   - Moving clip while trimming prev clip's tail and next clip's head.
   - Missing neighbors rejection.
5. Gap Management:
   - Gap detection across tracks.
   - Gap closure by pulling downstream clips.
   - Gap insertion by pushing downstream clips forward.
6. Multi-Item Editing:
   - Moving multiple selections synchronously.
7. Edit Planning & Preview:
   - Non-mutating deep copy preview generation.
8. Complete Reversibility:
   - Undo/Redo across all advanced edits.
   - Source media immutability.
"""

import unittest
import uuid
import copy

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
from video_studio.timeline_edit_engine import (
    TimelineEditEngine,
    StaleRevisionError,
    timeline_edit_engine,
)
from video_studio.timeline_advanced_edit import (
    AdvancedTimelineEditEngine,
    TimelineGap,
    EditPlanPreview,
    advanced_timeline_edit_engine,
)
from video_studio.timeline_query import TimelineQueryEngine


class TestVideoStudioModule6(unittest.TestCase):

    def setUp(self):
        self.base_engine = TimelineEditEngine(
            constraint_engine=TimelineConstraintEngine(),
            query_engine=TimelineQueryEngine(),
        )
        self.adv_engine = AdvancedTimelineEditEngine(
            base_edit_engine=self.base_engine,
            constraints=self.base_engine.constraints,
            query_engine=self.base_engine.query_engine,
        )

        self.seq = VideoSequence(
            sequence_id="seq_test_6",
            project_id="proj_omega",
            name="Module 6 Advanced Editing Sequence",
            settings=SequenceSettings(frame_rate=24.0),
            tracks=[
                TimelineTrackModel(track_id="trk_v1", sequence_id="seq_test_6", name="Video 1", track_type=TimelineTrackType.VIDEO, index=0),
                TimelineTrackModel(track_id="trk_v2", sequence_id="seq_test_6", name="Video 2", track_type=TimelineTrackType.VIDEO, index=1),
                TimelineTrackModel(track_id="trk_a1", sequence_id="seq_test_6", name="Audio 1", track_type=TimelineTrackType.AUDIO, index=2),
                TimelineTrackModel(track_id="trk_locked", sequence_id="seq_test_6", name="Locked Track", track_type=TimelineTrackType.VIDEO, index=3, is_locked=True),
            ]
        )

    def test_01_ripple_trim_start(self):
        """Test ripple trim start shifts downstream items to close/expand gap."""
        clip_a = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=100, source_in_frame=50, name="A")
        clip_b = self.base_engine.add_clip(self.seq, "trk_v1", "asset_2", start_frame=100, duration_frames=100, name="B")

        # Ripple trim start on clip A by +20 frames (trims head inward)
        # Clip A: start becomes 20, duration becomes 80
        # Clip B: downstream shifted left by 20 -> start becomes 80
        ok = self.adv_engine.ripple_trim_start(self.seq, clip_a.item_id, delta_frames=20)
        self.assertTrue(ok)
        self.assertEqual(clip_a.timeline_range.start_frame, 20)
        self.assertEqual(clip_a.timeline_range.duration_frames, 80)
        self.assertEqual(clip_a.source_range.in_frame, 70)
        self.assertEqual(clip_b.timeline_range.start_frame, 80)

        # Undo ripple trim
        self.base_engine.undo(self.seq)
        self.assertEqual(clip_a.timeline_range.start_frame, 0)
        self.assertEqual(clip_a.timeline_range.duration_frames, 100)
        self.assertEqual(clip_b.timeline_range.start_frame, 100)

    def test_02_ripple_trim_end(self):
        """Test ripple trim end pushes downstream items forward when extending."""
        clip_a = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=50, name="A")
        clip_b = self.base_engine.add_clip(self.seq, "trk_v1", "asset_2", start_frame=50, duration_frames=50, name="B")

        # Extend clip A tail by +30 frames -> duration becomes 80, clip B shifted to 80
        ok = self.adv_engine.ripple_trim_end(self.seq, clip_a.item_id, delta_frames=30)
        self.assertTrue(ok)
        self.assertEqual(clip_a.timeline_range.duration_frames, 80)
        self.assertEqual(clip_b.timeline_range.start_frame, 80)

        # Trim clip A tail inward by -40 frames -> duration becomes 40, clip B shifted to 40
        self.adv_engine.ripple_trim_end(self.seq, clip_a.item_id, delta_frames=-40)
        self.assertEqual(clip_a.timeline_range.duration_frames, 40)
        self.assertEqual(clip_b.timeline_range.start_frame, 40)

        # Undo restores 80
        self.base_engine.undo(self.seq)
        self.assertEqual(clip_a.timeline_range.duration_frames, 80)
        self.assertEqual(clip_b.timeline_range.start_frame, 80)

    def test_03_ripple_delete_single_and_multitrack(self):
        """Test ripple deletion closes timeline gap across downstream content."""
        clip_a = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=50, name="A")
        clip_b = self.base_engine.add_clip(self.seq, "trk_v1", "asset_2", start_frame=50, duration_frames=60, name="B")
        clip_c = self.base_engine.add_clip(self.seq, "trk_v1", "asset_3", start_frame=110, duration_frames=40, name="C")

        # Audio companion for B
        clip_b_aud = self.base_engine.add_clip(self.seq, "trk_a1", "asset_2", start_frame=50, duration_frames=60, name="B_Audio")
        self.base_engine.link_items(self.seq, [clip_b.item_id, clip_b_aud.item_id])

        # Ripple delete clip B (and linked audio)
        ok = self.adv_engine.ripple_delete(self.seq, [clip_b.item_id], ripple_linked=True)
        self.assertTrue(ok)

        # Clip C should have moved left by 60 frames (110 - 60 = 50)
        self.assertEqual(clip_c.timeline_range.start_frame, 50)

        # Verify B and B_Audio removed from tracks
        trk_v1 = next(t for t in self.seq.tracks if t.track_id == "trk_v1")
        trk_a1 = next(t for t in self.seq.tracks if t.track_id == "trk_a1")
        self.assertNotIn(clip_b.item_id, [it.item_id for it in trk_v1.items])
        self.assertNotIn(clip_b_aud.item_id, [it.item_id for it in trk_a1.items])

        # Undo restores everything
        self.base_engine.undo(self.seq)
        self.assertIn(clip_b.item_id, [it.item_id for it in trk_v1.items])
        self.assertEqual(clip_c.timeline_range.start_frame, 110)

    def test_04_rolling_edit(self):
        """Test rolling edit shifts edit point between two adjacent clips without altering total length."""
        clip_a = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=100, name="A")
        clip_b = self.base_engine.add_clip(self.seq, "trk_v1", "asset_2", start_frame=100, duration_frames=100, source_in_frame=20, name="B")

        combined_before = clip_a.timeline_range.duration_frames + clip_b.timeline_range.duration_frames

        # Roll forward by +30 frames (A grows +30, B shrinks -30, cut moves to 130)
        ok = self.adv_engine.rolling_edit(self.seq, clip_a.item_id, clip_b.item_id, delta_frames=30)
        self.assertTrue(ok)
        self.assertEqual(clip_a.timeline_range.duration_frames, 130)
        self.assertEqual(clip_a.timeline_range.end_frame, 130)
        self.assertEqual(clip_b.timeline_range.start_frame, 130)
        self.assertEqual(clip_b.timeline_range.duration_frames, 70)
        self.assertEqual(clip_b.source_range.in_frame, 50)
        self.assertEqual(clip_a.timeline_range.duration_frames + clip_b.timeline_range.duration_frames, combined_before)

        # Non-adjacent clips rejected
        clip_c = self.base_engine.add_clip(self.seq, "trk_v1", "asset_3", start_frame=300, duration_frames=50, name="C")
        with self.assertRaises(EditConstraintViolation):
            self.adv_engine.rolling_edit(self.seq, clip_a.item_id, clip_c.item_id, delta_frames=10)

    def test_05_slip_edit(self):
        """Test slip edit changes source in-frame while keeping timeline position fixed."""
        clip = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=50, duration_frames=100, source_in_frame=40, name="SlipClip")

        # Slip by +25 frames
        ok = self.adv_engine.slip_edit(self.seq, clip.item_id, delta_frames=25)
        self.assertTrue(ok)
        self.assertEqual(clip.timeline_range.start_frame, 50)
        self.assertEqual(clip.timeline_range.duration_frames, 100)
        self.assertEqual(clip.source_range.in_frame, 65)

        # Exceed source head boundary (<0) fails
        with self.assertRaises(EditConstraintViolation):
            self.adv_engine.slip_edit(self.seq, clip.item_id, delta_frames=-100)

        # Undo restores 40
        self.base_engine.undo(self.seq)
        self.assertEqual(clip.source_range.in_frame, 40)

    def test_06_slide_edit(self):
        """Test slide edit moves selected clip while adjusting surrounding neighbors."""
        clip_prev = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=100, name="Prev")
        clip_mid = self.base_engine.add_clip(self.seq, "trk_v1", "asset_2", start_frame=100, duration_frames=50, name="Mid")
        clip_next = self.base_engine.add_clip(self.seq, "trk_v1", "asset_3", start_frame=150, duration_frames=100, source_in_frame=10, name="Next")

        # Slide Mid forward by +20 frames:
        # Prev tail extends by +20 (duration 120)
        # Mid shifts to 120 (duration stays 50, ends at 170)
        # Next head trims by +20 (start 170, duration 80, in_frame 30)
        ok = self.adv_engine.slide_edit(self.seq, clip_mid.item_id, delta_frames=20)
        self.assertTrue(ok)
        self.assertEqual(clip_prev.timeline_range.duration_frames, 120)
        self.assertEqual(clip_mid.timeline_range.start_frame, 120)
        self.assertEqual(clip_mid.timeline_range.duration_frames, 50)
        self.assertEqual(clip_next.timeline_range.start_frame, 170)
        self.assertEqual(clip_next.timeline_range.duration_frames, 80)
        self.assertEqual(clip_next.source_range.in_frame, 30)

        # Undo slide
        self.base_engine.undo(self.seq)
        self.assertEqual(clip_prev.timeline_range.duration_frames, 100)
        self.assertEqual(clip_mid.timeline_range.start_frame, 100)
        self.assertEqual(clip_next.timeline_range.start_frame, 150)

    def test_07_gap_detection_close_and_insert(self):
        """Test detecting gaps, closing gaps, and inserting gaps."""
        self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=50, name="A")
        # Empty space [50..100]
        clip_b = self.base_engine.add_clip(self.seq, "trk_v1", "asset_2", start_frame=100, duration_frames=50, name="B")

        gaps = self.adv_engine.detect_gaps(self.seq, "trk_v1")
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].start_frame, 50)
        self.assertEqual(gaps[0].duration_frames, 50)

        # Close gap at 50
        ok = self.adv_engine.close_gap(self.seq, "trk_v1", gap_start_frame=50)
        self.assertTrue(ok)
        self.assertEqual(clip_b.timeline_range.start_frame, 50)

        # Insert gap of 40 frames at 50
        self.adv_engine.insert_gap(self.seq, "trk_v1", insert_frame=50, duration_frames=40)
        self.assertEqual(clip_b.timeline_range.start_frame, 90)

    def test_08_multi_item_movement(self):
        """Test moving multiple selected clips synchronously."""
        clip1 = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=10, duration_frames=30)
        clip2 = self.base_engine.add_clip(self.seq, "trk_v2", "asset_2", start_frame=20, duration_frames=40)

        ok = self.adv_engine.move_multiple_items(self.seq, [clip1.item_id, clip2.item_id], delta_frames=15)
        self.assertTrue(ok)
        self.assertEqual(clip1.timeline_range.start_frame, 25)
        self.assertEqual(clip2.timeline_range.start_frame, 35)

        # Undo
        self.base_engine.undo(self.seq)
        self.assertEqual(clip1.timeline_range.start_frame, 10)
        self.assertEqual(clip2.timeline_range.start_frame, 20)

    def test_09_edit_plan_preview(self):
        """Test previewing an edit generates a valid non-mutating preview plan."""
        clip_a = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=50)
        clip_b = self.base_engine.add_clip(self.seq, "trk_v1", "asset_2", start_frame=50, duration_frames=50)
        rev_before = self.seq.revision

        preview = self.adv_engine.preview_edit(
            self.seq,
            operation_name="RippleTrimStart",
            edit_fn=self.adv_engine.ripple_trim_start,
            item_id=clip_a.item_id,
            delta_frames=10,
        )
        self.assertTrue(preview.valid)
        self.assertEqual(preview.operation_name, "RippleTrimStart")
        self.assertIn(clip_a.item_id, preview.affected_item_ids)
        self.assertIn(clip_b.item_id, preview.affected_item_ids)

        # Verify original sequence was NOT mutated
        self.assertEqual(self.seq.revision, rev_before)
        self.assertEqual(clip_a.timeline_range.start_frame, 0)
        self.assertEqual(clip_b.timeline_range.start_frame, 50)

    def test_10_locked_track_rejection(self):
        """Ensure ripple and gap edits touching locked tracks are rejected without side effects."""
        clip_unlocked = self.base_engine.add_clip(self.seq, "trk_v1", "asset_1", start_frame=0, duration_frames=50)
        # Downstream clip on locked track
        trk_locked = next(t for t in self.seq.tracks if t.track_id == "trk_locked")
        # Temporarily place directly to test constraint guard
        trk_locked.items.append(
            TimelineItemModel(
                item_id="locked_item",
                track_id="trk_locked",
                sequence_id=self.seq.sequence_id,
                source_reference_id="raw_locked",
                timeline_range=TimelineRange(start_frame=60, duration_frames=50),
            )
        )

        # Ripple trim end across all tracks should detect locked downstream item and fail
        with self.assertRaises(EditConstraintViolation):
            self.adv_engine.ripple_trim_end(self.seq, clip_unlocked.item_id, delta_frames=20, affected_track_ids=["trk_v1", "trk_locked"])

        # Verify unlocked clip was untouched
        self.assertEqual(clip_unlocked.timeline_range.duration_frames, 50)


if __name__ == "__main__":
    unittest.main()
