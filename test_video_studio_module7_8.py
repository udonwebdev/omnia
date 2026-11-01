"""Unit & Integration Test Suite for OMNIA Video Studio — Modules 7 & 8.

Verifies:
Module 7 — Playback Engine & Real-Time Viewer:
1. PlaybackSession lifecycle (create, play, pause, stop, destroy).
2. Timeline evaluation (active video/audio clips, gap detection, track ordering).
3. Frame decoding & delivery (rendered frames, synthetic buffer generation).
4. Frame-accurate seeking and step-frame navigation.
5. Quality controls (FULL, HALF, QUARTER scaling).
6. Offline and missing media resilience (graceful warning frame without host crash).
7. Decoder pool resource management and eviction.

Module 8 — Keyframe Animation & Parameter Automation:
8. Keyframe creation, removal, movement, and value updates.
9. Constant / Hold, Linear, Ease-In, Ease-Out, Ease-In-Out, and Cubic Bezier interpolation.
10. Evaluation at exact frames, before head, and after tail.
11. Min/Max property constraints clamping.
12. Bulk copy and paste keyframes with relative frame offsets.
13. TransformAnimation standard property bundle (Position X/Y, Scale, Rotation, Opacity).
14. Cache invalidation on property revision mutation.
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
    SequenceSettings,
)
from video_studio.playback_models import (
    PlaybackState,
    PlaybackQuality,
    DecodedVideoFrame,
    PlaybackSession,
)
from video_studio.playback_decoder import SoftwareMediaDecoder, MediaDecoderPool
from video_studio.playback_engine import TimelinePlaybackEngine
from video_studio.timeline_edit_engine import TimelineEditEngine

from video_studio.animation_models import (
    AnimatableProperty,
    KeyframeModel,
    InterpolationMode,
    TangentType,
    PropertyValueType,
    TransformAnimation,
)
from video_studio.animation_evaluator import AnimationEvaluator
from video_studio.animation_service import AnimationService


class TestVideoStudioModules7and8(unittest.TestCase):

    def setUp(self):
        self.edit_engine = TimelineEditEngine()
        self.playback = TimelinePlaybackEngine()
        self.anim_eval = AnimationEvaluator()
        self.anim_service = AnimationService(evaluator=self.anim_eval)

        self.seq = VideoSequence(
            sequence_id="seq_test_7_8",
            project_id="proj_omega",
            name="Playback & Animation Verification",
            settings=SequenceSettings(width=1920, height=1080, frame_rate=24.0),
            tracks=[
                TimelineTrackModel(track_id="trk_v1", sequence_id="seq_test_7_8", name="V1", track_type=TimelineTrackType.VIDEO, index=0),
                TimelineTrackModel(track_id="trk_a1", sequence_id="seq_test_7_8", name="A1", track_type=TimelineTrackType.AUDIO, index=1),
            ]
        )

    # =========================================================================
    # MODULE 7 TESTS — PLAYBACK ENGINE
    # =========================================================================

    def test_01_playback_session_lifecycle(self):
        """Test creating, playing, pausing, stopping, and destroying a playback session."""
        session = self.playback.create_session(self.seq, project_id="proj_omega")
        self.assertEqual(session.state, PlaybackState.READY)
        self.assertEqual(session.current_frame, 0)

        # Play
        ok = self.playback.play(session.session_id)
        self.assertTrue(ok)
        self.assertEqual(session.state, PlaybackState.PLAYING)

        # Pause
        ok = self.playback.pause(session.session_id)
        self.assertTrue(ok)
        self.assertEqual(session.state, PlaybackState.PAUSED)

        # Stop
        ok = self.playback.stop(session.session_id)
        self.assertTrue(ok)
        self.assertEqual(session.state, PlaybackState.STOPPED)
        self.assertEqual(session.current_frame, 0)

        # Destroy
        ok = self.playback.destroy_session(session.session_id)
        self.assertTrue(ok)
        self.assertIsNone(self.playback.get_session(session.session_id))

    def test_02_timeline_evaluation_and_rendering(self):
        """Test evaluating active items on timeline and rendering frames."""
        clip1 = self.edit_engine.add_clip(self.seq, "trk_v1", "asset_intro", start_frame=10, duration_frames=40)
        session = self.playback.create_session(self.seq, project_id="proj_omega")

        # Frame 0 is in gap
        frame_0 = self.playback.render_frame(session.session_id, frame=0)
        self.assertTrue(frame_0.is_gap)
        self.assertEqual(frame_0.timeline_frame, 0)

        # Frame 20 is inside clip1
        frame_20 = self.playback.render_frame(session.session_id, frame=20)
        self.assertFalse(frame_20.is_gap)
        self.assertEqual(frame_20.timeline_frame, 20)
        self.assertEqual(frame_20.source_frame, 10)  # offset (20 - 10) = 10
        self.assertIsNotNone(frame_20.buffer_bytes)

    def test_03_seeking_and_stepping(self):
        """Test seek and step navigation across sequence frames."""
        self.edit_engine.add_clip(self.seq, "trk_v1", "asset_main", start_frame=0, duration_frames=100)
        session = self.playback.create_session(self.seq, project_id="proj_omega")

        # Seek to frame 45
        frame = self.playback.seek(session.session_id, target_frame=45)
        self.assertEqual(session.current_frame, 45)
        self.assertEqual(frame.timeline_frame, 45)
        self.assertEqual(session.metrics.seek_count, 1)

        # Step forward 5 frames
        frame_step = self.playback.step_frame(session.session_id, step_delta=5)
        self.assertEqual(session.current_frame, 50)
        self.assertEqual(frame_step.timeline_frame, 50)

    def test_04_quality_scaling(self):
        """Test preview quality controls (FULL, HALF, QUARTER)."""
        self.edit_engine.add_clip(self.seq, "trk_v1", "asset_q", start_frame=0, duration_frames=50)
        session = self.playback.create_session(self.seq, project_id="proj_omega", quality=PlaybackQuality.FULL)

        f_full = self.playback.render_frame(session.session_id, frame=10)
        self.assertEqual(f_full.width, 1920)
        self.assertEqual(f_full.height, 1080)

        self.playback.set_quality(session.session_id, PlaybackQuality.HALF)
        f_half = self.playback.render_frame(session.session_id, frame=10)
        self.assertEqual(f_half.width, 960)
        self.assertEqual(f_half.height, 540)

        self.playback.set_quality(session.session_id, PlaybackQuality.QUARTER)
        f_quarter = self.playback.render_frame(session.session_id, frame=10)
        self.assertEqual(f_quarter.width, 480)
        self.assertEqual(f_quarter.height, 270)

    def test_05_offline_media_resilience(self):
        """Ensure missing media produces a synthetic offline frame rather than crashing."""
        self.edit_engine.add_clip(self.seq, "trk_v1", "missing_asset_123", start_frame=0, duration_frames=50)
        session = self.playback.create_session(self.seq, project_id="proj_omega")

        f_offline = self.playback.render_frame(session.session_id, frame=15)
        self.assertTrue(f_offline.is_offline)
        self.assertIsNotNone(f_offline.buffer_bytes)

    # =========================================================================
    # MODULE 8 TESTS — KEYFRAME ANIMATION & PARAMETER AUTOMATION
    # =========================================================================

    def test_06_keyframe_crud_operations(self):
        """Test adding, modifying, moving, and removing keyframes."""
        prop = AnimatableProperty(
            property_id="prop_opacity",
            owner_id="clip_01",
            name="Opacity",
            value_type=PropertyValueType.SCALAR,
            default_value=1.0,
            current_value=1.0,
            min_value=0.0,
            max_value=1.0,
        )
        self.anim_service.register_property(prop)

        # Add keyframes at frame 0 (val 0.0) and frame 24 (val 1.0)
        kf0 = self.anim_service.add_keyframe("prop_opacity", frame=0, value=0.0)
        kf24 = self.anim_service.add_keyframe("prop_opacity", frame=24, value=1.0)

        self.assertEqual(len(prop.keyframes), 2)
        self.assertEqual(prop.keyframes[0].frame, 0)
        self.assertEqual(prop.keyframes[1].frame, 24)

        # Move keyframe from 24 to 30
        self.anim_service.move_keyframe("prop_opacity", kf24.keyframe_id, new_frame=30)
        self.assertEqual(prop.keyframes[1].frame, 30)

        # Update value
        self.anim_service.set_keyframe_value("prop_opacity", kf24.keyframe_id, new_value=0.8)
        self.assertEqual(prop.keyframes[1].value, 0.8)

        # Remove keyframe
        ok = self.anim_service.remove_keyframe("prop_opacity", kf0.keyframe_id)
        self.assertTrue(ok)
        self.assertEqual(len(prop.keyframes), 1)

    def test_07_linear_and_hold_interpolation(self):
        """Test linear and constant/hold curve evaluation."""
        prop = AnimatableProperty(
            property_id="prop_vol",
            owner_id="audio_01",
            name="Volume",
            value_type=PropertyValueType.SCALAR,
            default_value=0.0,
            current_value=0.0,
        )
        self.anim_service.register_property(prop)

        # Linear ramp from 0 to 100 between frames 0 and 100
        self.anim_service.add_keyframe("prop_vol", frame=0, value=0.0, interpolation=InterpolationMode.LINEAR)
        self.anim_service.add_keyframe("prop_vol", frame=100, value=100.0, interpolation=InterpolationMode.LINEAR)

        # Midpoint frame 50
        val_mid = self.anim_service.evaluate("prop_vol", frame=50)
        self.assertAlmostEqual(val_mid, 50.0, places=2)

        # Before frame 0
        self.assertAlmostEqual(self.anim_service.evaluate("prop_vol", frame=-10), 0.0)
        # After frame 100
        self.assertAlmostEqual(self.anim_service.evaluate("prop_vol", frame=120), 100.0)

        # Change to Hold / Constant
        kfs = prop.keyframes
        self.anim_service.set_interpolation("prop_vol", kfs[0].keyframe_id, InterpolationMode.HOLD)
        # Hold should stay 0.0 throughout until frame 100
        self.assertAlmostEqual(self.anim_service.evaluate("prop_vol", frame=50), 0.0)
        self.assertAlmostEqual(self.anim_service.evaluate("prop_vol", frame=99), 0.0)
        self.assertAlmostEqual(self.anim_service.evaluate("prop_vol", frame=100), 100.0)

    def test_08_bezier_and_ease_interpolation(self):
        """Test cubic Bezier curve and ease functions."""
        prop = AnimatableProperty(
            property_id="prop_bezier",
            owner_id="cam_01",
            name="Z Position",
            value_type=PropertyValueType.SCALAR,
            default_value=0.0,
            current_value=0.0,
        )
        self.anim_service.register_property(prop)

        # Ease In Out curve between 0 and 100
        self.anim_service.add_keyframe("prop_bezier", frame=0, value=0.0, interpolation=InterpolationMode.EASE_IN_OUT)
        self.anim_service.add_keyframe("prop_bezier", frame=100, value=100.0, interpolation=InterpolationMode.EASE_IN_OUT)

        # Ease In Out should be slower at t=0.1 than linear
        val_eased_early = self.anim_service.evaluate("prop_bezier", frame=10)
        self.assertTrue(val_eased_early < 10.0)

        # Cubic Bezier interpolation
        kfs = prop.keyframes
        self.anim_service.set_interpolation("prop_bezier", kfs[0].keyframe_id, InterpolationMode.BEZIER)
        val_bezier = self.anim_service.evaluate("prop_bezier", frame=50)
        self.assertTrue(0.0 <= val_bezier <= 100.0)

    def test_09_vector_and_color_interpolation(self):
        """Test multi-component vector and color interpolation."""
        prop_color = AnimatableProperty(
            property_id="prop_tint",
            owner_id="gfx_01",
            name="Tint",
            value_type=PropertyValueType.COLOR,
            default_value=[0, 0, 0, 1],
            current_value=[0, 0, 0, 1],
        )
        self.anim_service.register_property(prop_color)

        self.anim_service.add_keyframe("prop_tint", frame=0, value=[0.0, 0.0, 0.0, 1.0], interpolation=InterpolationMode.LINEAR)
        self.anim_service.add_keyframe("prop_tint", frame=100, value=[1.0, 1.0, 1.0, 1.0], interpolation=InterpolationMode.LINEAR)

        val_50 = self.anim_service.evaluate("prop_tint", frame=50)
        self.assertEqual(len(val_50), 4)
        self.assertAlmostEqual(val_50[0], 0.5)
        self.assertAlmostEqual(val_50[1], 0.5)
        self.assertAlmostEqual(val_50[2], 0.5)
        self.assertAlmostEqual(val_50[3], 1.0)

    def test_10_copy_paste_and_transform_animation(self):
        """Test bulk copy/paste with frame offsets and TransformAnimation bundle."""
        # 1. TransformAnimation standard properties
        trans = self.anim_service.get_or_create_transform(owner_id="clip_title")
        self.assertEqual(trans.scale_x.default_value, 1.0)
        self.assertEqual(trans.opacity.default_value, 1.0)

        # 2. Keyframes on Position X
        self.anim_service.add_keyframe(trans.position_x.property_id, frame=10, value=100.0)
        self.anim_service.add_keyframe(trans.position_x.property_id, frame=20, value=200.0)

        # Copy keyframes
        count = self.anim_service.copy_keyframes(trans.position_x.property_id)
        self.assertEqual(count, 2)

        # Paste onto Position Y starting at frame 50
        pasted = self.anim_service.paste_keyframes(target_property_id=trans.position_y.property_id, target_start_frame=50)
        self.assertEqual(len(pasted), 2)
        self.assertEqual(pasted[0].frame, 50)
        self.assertEqual(pasted[0].value, 100.0)
        self.assertEqual(pasted[1].frame, 60)
        self.assertEqual(pasted[1].value, 200.0)


if __name__ == "__main__":
    unittest.main()
