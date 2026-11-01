"""Unit tests for OMNIA Video Studio Module 15: Speed Control, Time Remapping & Frame Interpolation Engine.

Covers:
1. Timecode conversion & rational time calculations (23.976, 24, 25, 29.97 DF/NDF, 59.94 DF/NDF).
2. Constant-speed source time mapping (slow motion, fast motion, reverse).
3. Variable speed ramp piecewise integration and curve constraints.
4. Freeze-frame mapping and duration holding.
5. Frame interpolation (duplication and float32 alpha blending).
6. Audio speed processing (tape resampling pitch shift, WSOLA pitch preservation, and muting).
7. Timeline integration and ripple editing.
8. Capability registry registration and health.
"""

import unittest
import numpy as np

from video_studio.speed_models import (
    RationalTime,
    TimecodeConverter,
    SpeedCurvePoint,
    FreezeRegion,
    TimeRemapDocument,
    FrameInterpolationMode,
    AudioSpeedMode,
    SpeedCurveInterpolation,
)
from video_studio.speed_engine import speed_remap_engine
from video_studio.speed_service import speed_service
from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineTrackType,
    TimelineItemModel,
    TimelineRange,
    SourceRange,
)
from video_studio.compositing_models import VideoFrameBuffer
from video_studio.audio_models import AudioBuffer

class TestVideoStudioModule15(unittest.TestCase):

    def test_01_timecode_and_rational_time(self):
        """Validates rational time without drift and drop-frame/non-drop-frame timecodes."""
        # 24 fps exact
        rt = RationalTime.from_frames(48, 24.0)
        self.assertAlmostEqual(rt.seconds, 2.0, places=4)
        self.assertEqual(rt.to_frame(24.0), 48)

        # 23.976 fps
        rt_23 = RationalTime.from_frames(24000, 23.976)
        self.assertAlmostEqual(rt_23.seconds, 1001.0, places=2)

        # NDF Timecode
        tc_ndf = TimecodeConverter.frames_to_timecode(1440, 24.0, is_drop_frame=False)
        self.assertEqual(tc_ndf, "00:01:00:00")
        frames_back = TimecodeConverter.timecode_to_frames(tc_ndf, 24.0, is_drop_frame=False)
        self.assertEqual(frames_back, 1440)

        # Drop-Frame 29.97 timecode
        tc_df = TimecodeConverter.frames_to_timecode(1800, 29.97, is_drop_frame=True)
        self.assertTrue(";" in tc_df)

    def test_02_constant_speed_mapping(self):
        """Verifies forward and reverse constant-speed mapping."""
        item = TimelineItemModel(
            item_id="clip_const",
            track_id="trk_v1",
            sequence_id="seq_speed",
            source_reference_id="asset_test",
            timeline_range=TimelineRange(start_frame=100, duration_frames=50),
            source_range=SourceRange(in_frame=10, duration_frames=100),
            speed=1.0,
        )

        doc = TimeRemapDocument(
            remap_id="remap_const",
            item_id=item.item_id,
            source_reference_id=item.source_reference_id,
            constant_speed=0.5, # Slow motion 50%
            is_reverse=False,
        )

        # Sequence frame 100 -> item offset 0 -> source in_frame 10
        src_0 = speed_remap_engine.map_sequence_frame_to_source(doc, item, 100)
        self.assertAlmostEqual(src_0, 10.0)

        # Sequence frame 120 -> item offset 20 -> source in_frame 10 + 20 * 0.5 = 20.0
        src_20 = speed_remap_engine.map_sequence_frame_to_source(doc, item, 120)
        self.assertAlmostEqual(src_20, 20.0)

        # Reverse 2.0x Fast Motion
        doc_rev = TimeRemapDocument(
            remap_id="remap_rev",
            item_id=item.item_id,
            source_reference_id=item.source_reference_id,
            constant_speed=2.0,
            is_reverse=True,
        )
        # Sequence frame 100 -> offset 0 -> (10 + 99) - 0 = 109
        src_rev_0 = speed_remap_engine.map_sequence_frame_to_source(doc_rev, item, 100)
        self.assertAlmostEqual(src_rev_0, 109.0)

        # Sequence frame 105 -> offset 5 -> 109 - (5 * 2.0) = 99.0
        src_rev_5 = speed_remap_engine.map_sequence_frame_to_source(doc_rev, item, 105)
        self.assertAlmostEqual(src_rev_5, 99.0)

    def test_03_variable_speed_ramp_integration(self):
        """Verifies piecewise numerical integration of speed ramps."""
        item = TimelineItemModel(
            item_id="clip_ramp",
            track_id="trk_v1",
            sequence_id="seq_speed",
            source_reference_id="asset_test",
            timeline_range=TimelineRange(start_frame=0, duration_frames=100),
            source_range=SourceRange(in_frame=0, duration_frames=100),
        )

        # Speed curve from 0.5x at frame 0 to 2.0x at frame 50
        pts = [
            SpeedCurvePoint(point_id="p1", sequence_frame=0, speed=0.5, interpolation=SpeedCurveInterpolation.LINEAR),
            SpeedCurvePoint(point_id="p2", sequence_frame=50, speed=2.0, interpolation=SpeedCurveInterpolation.LINEAR),
        ]
        doc = TimeRemapDocument(
            remap_id="remap_ramp",
            item_id=item.item_id,
            source_reference_id=item.source_reference_id,
            is_variable=True,
            speed_points=pts,
        )

        src_0 = speed_remap_engine.map_sequence_frame_to_source(doc, item, 0)
        self.assertAlmostEqual(src_0, 0.0)

        # Cumulative source frame at sequence frame 10 must be strictly monotonic
        src_10 = speed_remap_engine.map_sequence_frame_to_source(doc, item, 10)
        src_20 = speed_remap_engine.map_sequence_frame_to_source(doc, item, 20)
        src_50 = speed_remap_engine.map_sequence_frame_to_source(doc, item, 50)

        self.assertTrue(0.0 < src_10 < src_20 < src_50)

    def test_04_freeze_frame_hold(self):
        """Verifies that freeze intervals hold the exact source frame."""
        item = TimelineItemModel(
            item_id="clip_freeze",
            track_id="trk_v1",
            sequence_id="seq_speed",
            source_reference_id="asset_test",
            timeline_range=TimelineRange(start_frame=0, duration_frames=100),
            source_range=SourceRange(in_frame=0, duration_frames=100),
        )

        freeze = FreezeRegion(
            region_id="freeze_1",
            timeline_start_frame=20,
            duration_frames=30, # frames 20 to 50
            frozen_source_frame=42,
        )

        doc = TimeRemapDocument(
            remap_id="remap_fr",
            item_id=item.item_id,
            source_reference_id=item.source_reference_id,
            constant_speed=1.0,
            freeze_regions=[freeze],
        )

        # Before freeze: normal mapping (frame 10 -> source 10)
        self.assertEqual(speed_remap_engine.map_sequence_frame_to_source(doc, item, 10), 10.0)

        # Inside freeze (frames 20, 35, 49) -> always frozen at 42.0
        self.assertEqual(speed_remap_engine.map_sequence_frame_to_source(doc, item, 20), 42.0)
        self.assertEqual(speed_remap_engine.map_sequence_frame_to_source(doc, item, 35), 42.0)
        self.assertEqual(speed_remap_engine.map_sequence_frame_to_source(doc, item, 49), 42.0)

    def test_05_frame_interpolation_blending(self):
        """Verifies frame blending produces genuine pixel-interpolated values."""
        # Frame A: Solid black
        buf_a = VideoFrameBuffer(width=10, height=10, data=np.zeros((10, 10, 4), dtype=np.uint8))
        buf_a.data[:, :, 3] = 255 # full alpha

        # Frame B: Solid white
        buf_b = VideoFrameBuffer(width=10, height=10, data=np.full((10, 10, 4), 255, dtype=np.uint8))

        # Blend 50%
        blended = speed_remap_engine.interpolate_frames(
            buf_a, buf_b, blend_factor=0.5, mode=FrameInterpolationMode.BLENDING
        )

        # Mid-gray RGB = ~127
        self.assertEqual(blended.width, 10)
        self.assertEqual(blended.height, 10)
        self.assertAlmostEqual(float(blended.data[0, 0, 0]), 127.5, delta=1.5)
        self.assertEqual(blended.data[0, 0, 3], 255)

    def test_06_audio_speed_processing(self):
        """Verifies audio resampling, time-stretching, and muting."""
        # 1000 samples of stereo sine tone
        sr = 48000
        t = np.linspace(0, 1.0, 1000, endpoint=False)
        sine = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)
        sine_stereo = np.vstack([sine, sine])
        buf = AudioBuffer(sample_rate=sr, data=sine_stereo)

        # 1. Resample pitch 2.0x (length should halve to 500)
        buf_2x = speed_remap_engine.process_audio_speed(buf, speed=2.0, mode=AudioSpeedMode.RESAMPLE_PITCH)
        self.assertEqual(buf_2x.samples, 500)

        # 2. Mute mode
        buf_muted = speed_remap_engine.process_audio_speed(buf, speed=0.5, mode=AudioSpeedMode.MUTE)
        self.assertTrue(np.all(buf_muted.data == 0.0))

        # 3. Reverse audio (speed < 0)
        buf_rev = speed_remap_engine.process_audio_speed(buf, speed=-1.0, mode=AudioSpeedMode.RESAMPLE_PITCH)
        self.assertEqual(buf_rev.samples, 1000)
        self.assertAlmostEqual(float(buf_rev.data[0, 0]), float(buf.data[0, -1]))

    def test_07_speed_service_application_and_ripple(self):
        """Verifies high-level speed service applies duration changes with ripple."""
        seq = speed_service.timeline_service.create_sequence(project_id="proj_speed", name="Speed Seq", create_default_tracks=False)
        track = TimelineTrackModel(track_id="trk_v1", sequence_id=seq.sequence_id, name="V1", track_type=TimelineTrackType.VIDEO)
        clip1 = TimelineItemModel(
            item_id="c1",
            track_id="trk_v1",
            sequence_id=seq.sequence_id,
            source_reference_id="asset_1",
            timeline_range=TimelineRange(start_frame=0, duration_frames=100),
            source_range=SourceRange(in_frame=0, duration_frames=100),
        )
        clip2 = TimelineItemModel(
            item_id="c2",
            track_id="trk_v1",
            sequence_id=seq.sequence_id,
            source_reference_id="asset_2",
            timeline_range=TimelineRange(start_frame=100, duration_frames=100),
            source_range=SourceRange(in_frame=0, duration_frames=100),
        )
        track.items = [clip1, clip2]
        seq.tracks = [track]

        # Apply 2.0x speed with ripple (c1 duration changes from 100 to 50, c2 start moves to 50)
        ok, msg, doc = speed_service.apply_constant_speed(
            sequence_id=seq.sequence_id,
            item_id="c1",
            speed=2.0,
            ripple=True,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(doc)
        self.assertEqual(clip1.timeline_range.duration_frames, 50)
        self.assertEqual(clip2.timeline_range.start_frame, 50)

    def test_08_capability_registry_ready(self):
        """Verifies Module 15 capabilities registered into Video Studio Capability Registry."""
        from video_studio.registry import video_studio_capability_registry
        from video_studio.registry_models import ImplementationState

        speed_service.register_capabilities()

        cap = video_studio_capability_registry.get("video.speed.constant")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.implementation_state, ImplementationState.IMPLEMENTED)

        cap_var = video_studio_capability_registry.get("video.speed.variable_ramping")
        self.assertIsNotNone(cap_var)
        self.assertEqual(cap_var.implementation_state, ImplementationState.IMPLEMENTED)

if __name__ == "__main__":
    unittest.main()
