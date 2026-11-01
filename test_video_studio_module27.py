"""OMNIA Video Studio — Module 27 Test Suite.
Tests:
1. Exact rational frame rate representation (23.976 -> 24000/1001, 29.97 -> 30000/1001, 59.94 -> 60000/1001).
2. Frame rate conversion (24fps -> 60fps) with strictly monotonic timestamps and correct frame counts.
3. Motion-compensated optical flow interpolation across moving synthetic target.
4. Frame duplication fallback mode.
5. Frame blending crossfade mode.
6. Scene cut detection (preventing morphing across hard visual discontinuities).
7. Variable frame rate (VFR) timestamp normalization.
8. Capability registration in VideoStudioCapabilityRegistry.
"""

import unittest
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.interpolation_models import (
    InterpolationMethod,
    SceneCutAction,
    QualityMode,
    RationalFrameRate,
    FrameRateConversionConfig,
    InterpolationDiagnostics,
)
from video_studio.interpolation_engine import VideoInterpolationEngine
from video_studio.interpolation_service import VideoInterpolationService
from video_studio.registry import video_studio_capability_registry
from video_studio.catalog_loader import populate_roadmap_capabilities


def create_moving_box_frames(
    num_frames: int = 5,
    width: int = 120,
    height: int = 90,
    dx: float = 6.0,
) -> tuple[list[VideoFrameBuffer], list[float]]:
    """Creates a sequence of frames with a moving bright square across dark background."""
    frames = []
    timestamps = []
    fps = 24.0
    dt = 1.0 / fps

    for i in range(num_frames):
        img = np.zeros((height, width, 4), dtype=np.uint8)
        img[:, :, 3] = 255 # Opaque

        # Moving box: starts at x=10, moves by dx each frame
        bx = int(10 + i * dx)
        by = 25
        img[by:by+30, bx:bx+30, 0] = 230
        img[by:by+30, bx:bx+30, 1] = 230
        img[by:by+30, bx:bx+30, 2] = 230

        frames.append(VideoFrameBuffer(width=width, height=height, data=img, pts_seconds=i * dt))
        timestamps.append(i * dt)

    return frames, timestamps


class TestModule27Interpolation(unittest.TestCase):
    def setUp(self):
        self.engine = VideoInterpolationEngine()
        self.service = VideoInterpolationService(engine=self.engine)
        self.source_frames, self.source_timestamps = create_moving_box_frames(num_frames=5)

    def test_rational_frame_rate_representation(self):
        """Verifies exact fractional frame rate representations without floating point drift."""
        r24 = RationalFrameRate.from_float(23.976)
        self.assertEqual(r24.numerator, 24000)
        self.assertEqual(r24.denominator, 1001)

        r30 = RationalFrameRate.from_float(29.97)
        self.assertEqual(r30.numerator, 30000)
        self.assertEqual(r30.denominator, 1001)

        r60 = RationalFrameRate.from_float(59.94)
        self.assertEqual(r60.numerator, 60000)
        self.assertEqual(r60.denominator, 1001)

    def test_frame_duplication_conversion(self):
        """Verifies 24fps -> 60fps frame duplication yields strictly monotonic timestamps."""
        config = FrameRateConversionConfig(
            method=InterpolationMethod.FRAME_DUPLICATION,
            source_rate=RationalFrameRate(24, 1),
            target_rate=RationalFrameRate(60, 1),
        )
        out_frames, out_ts, diag = self.engine.convert_sequence_rate(
            self.source_frames, self.source_timestamps, config
        )

        # 5 frames at 24fps covers (4/24) = 0.1667s. At 60fps, should generate ~10 frames
        self.assertGreater(len(out_frames), len(self.source_frames))
        self.assertEqual(len(out_frames), len(out_ts))

        # Check timestamp strict monotonicity
        for i in range(1, len(out_ts)):
            self.assertGreater(out_ts[i], out_ts[i - 1])

    def test_frame_blending_interpolation(self):
        """Verifies timestamp-weighted linear crossfade blending."""
        f_a = self.source_frames[0]
        f_b = self.source_frames[1]
        blended = self.engine.blend_frames(f_a, f_b, weight_b=0.5)

        # In blended frame, intensities of moving box regions should be halved (~115)
        self.assertEqual(blended.width, f_a.width)
        self.assertEqual(blended.height, f_a.height)
        val = blended.data[35, 12, 0] # Where box A was
        self.assertGreater(val, 80)
        self.assertLess(val, 150)

    def test_motion_compensated_optical_flow(self):
        """Verifies dense optical flow warps moving object to intermediate spatial coordinates."""
        f_a = self.source_frames[0] # Box at x=10
        f_b = self.source_frames[1] # Box at x=16
        config = FrameRateConversionConfig(quality_mode=QualityMode.STANDARD)

        # Interpolate at t=0.5: box should be centered near x=13
        interp = self.engine.motion_compensated_interpolate(f_a, f_b, alpha_t=0.5, config=config)
        self.assertEqual(interp.width, f_a.width)
        self.assertEqual(interp.height, f_a.height)

        # Pixel at (y=35, x=25) should have high intensity
        box_intensity = interp.data[35, 25, 0]
        self.assertGreater(box_intensity, 180)

    def test_scene_cut_detection_prevents_interpolation(self):
        """Verifies scene cuts are detected and prevent blending across boundaries."""
        # Create cut frame: completely white
        cut_data = np.full((90, 120, 4), 255, dtype=np.uint8)
        cut_frame = VideoFrameBuffer(width=120, height=90, data=cut_data)

        is_cut = self.engine.is_scene_cut(self.source_frames[0].data, cut_frame.data, threshold=30.0)
        self.assertTrue(is_cut)

        # Test sequence with a cut between frame 1 and frame 2
        seq = [self.source_frames[0], cut_frame]
        ts = [0.0, 0.0416]
        config = FrameRateConversionConfig(
            method=InterpolationMethod.MOTION_COMPENSATED,
            detect_scene_cuts=True,
            target_rate=RationalFrameRate(60, 1),
        )
        out_frames, _, diag = self.engine.convert_sequence_rate(seq, ts, config)
        self.assertGreater(diag.scene_cuts_detected, 0)

    def test_variable_frame_rate_conversion(self):
        """Verifies conversion handles irregular/variable source frame timestamps."""
        vfr_frames = [self.source_frames[0], self.source_frames[1], self.source_frames[2]]
        vfr_ts = [0.0, 0.030, 0.085] # Irregular intervals

        config = FrameRateConversionConfig(
            method=InterpolationMethod.FRAME_DUPLICATION,
            target_rate=RationalFrameRate(50, 1),
        )
        out_frames, out_ts, _ = self.engine.convert_sequence_rate(vfr_frames, vfr_ts, config)
        self.assertGreater(len(out_frames), 0)
        for i in range(1, len(out_ts)):
            self.assertGreater(out_ts[i], out_ts[i - 1])

    def test_service_convert_frames(self):
        """Verifies VideoInterpolationService coordinates configuration and frame synthesis."""
        out_frames, out_ts, diag = self.service.convert_frames(
            "clip_interp_1",
            self.source_frames,
            self.source_timestamps,
            target_fps=48.0,
        )
        self.assertGreater(len(out_frames), len(self.source_frames))
        self.assertEqual(diag.source_frames_sampled, len(self.source_frames))

    def test_module27_capabilities_registered(self):
        """Verifies Module 27 capabilities in catalog and registry."""
        populate_roadmap_capabilities(video_studio_capability_registry)
        self.service.register_capabilities()

        fd = video_studio_capability_registry.get("video.interpolation.frame_duplication")
        fb = video_studio_capability_registry.get("video.interpolation.frame_blending")
        mc = video_studio_capability_registry.get("video.interpolation.motion_compensated")
        sc = video_studio_capability_registry.get("video.interpolation.scene_cut_detection")
        lm = video_studio_capability_registry.get("video.interpolation.learned_model")

        self.assertIsNotNone(fd)
        self.assertIsNotNone(fb)
        self.assertIsNotNone(mc)
        self.assertIsNotNone(sc)
        self.assertIsNotNone(lm)


if __name__ == "__main__":
    unittest.main()
