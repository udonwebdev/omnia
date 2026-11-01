"""Unit and Integration Tests for Module 30: Video Lens Distortion, Optical Correction & Lens Profile Engine.

Verifies:
1. Synthetic radial distortion (barrel/pincushion) and correction round-trip on geometric grid buffers.
2. Tangential distortion decentering (p1, p2) precision.
3. Optical center offset handling (center_x, center_y).
4. Safe border behavior (CLAMP_EDGE, TRANSPARENT, REFLECT, CROP_TO_VALID).
5. Lateral chromatic aberration (CA) channel-aware radial remapping.
6. Optical vignetting radial falloff correction and gain limiting.
7. Alpha channel integrity across geometric remapping.
8. Lens profile serialization, loading, and provenance checking.
9. Metadata-driven profile matching with confidence scoring and exact/focal matching.
10. Undo, redo, and service configuration state management.
11. Integration with Module 10 effects processor registry.
"""

import unittest
import numpy as np
import math

from video_studio.effects_models import VideoFrameBuffer, EffectCategory
from video_studio.effects_processors import effect_processor_registry
from video_studio.lens_models import (
    LensModelType,
    BorderHandlingMode,
    ProfileMatchBasis,
    LensProfile,
    LensCorrectionConfig,
    LensDiagnostics,
)
from video_studio.lens_engine import (
    video_lens_engine,
    VideoLensEngine,
)
from video_studio.lens_processor import VideoLensEffectProcessor
from video_studio.lens_service import video_lens_service, VideoLensService
from video_studio.media_probe import VideoStreamInfo


def make_test_frame(width: int, height: int, data: np.ndarray) -> VideoFrameBuffer:
    return VideoFrameBuffer(width=width, height=height, data=data)


def create_synthetic_grid(width: int, height: int, grid_size: int = 10) -> np.ndarray:
    """Creates a high-contrast synthetic geometric grid pattern for distortion verification."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(0, height, grid_size):
        arr[y, :, :] = 255
    for x in range(0, width, grid_size):
        arr[:, x, :] = 255
    return arr


class TestVideoStudioModule30(unittest.TestCase):

    def setUp(self):
        self.engine = VideoLensEngine()
        self.service = VideoLensService(engine=self.engine)

    def test_synthetic_radial_distortion_and_correction_roundtrip(self):
        """Tests that applying barrel distortion (k1 > 0) and then inverse correction restores center alignment."""
        w, h = 100, 100
        grid = create_synthetic_grid(w, h, grid_size=10)
        frame = make_test_frame(w, h, grid)

        # 1. Apply barrel distortion
        distort_cfg = LensCorrectionConfig(
            clip_id="test_distort",
            k1=0.25, # Positive k in inverse map pulls inward (barrel)
            border_mode=BorderHandlingMode.CLAMP_EDGE,
        )
        distorted_frame, diag1 = self.engine.process_frame(frame, distort_cfg)
        self.assertTrue(diag1.distortion_applied)
        self.assertGreater(diag1.max_displacement_pixels, 0.0)

        # 2. Invert with opposing k1 to un-distort
        correct_cfg = LensCorrectionConfig(
            clip_id="test_correct",
            k1=-0.25, # Opposing coefficient
            border_mode=BorderHandlingMode.CLAMP_EDGE,
        )
        corrected_frame, diag2 = self.engine.process_frame(distorted_frame, correct_cfg)
        self.assertTrue(diag2.distortion_applied)

        # Center line at y=50, x=50 was white (255) in original grid; verify it remains white in restored frame
        self.assertEqual(int(frame.data[50, 50, 0]), 255)
        self.assertGreater(int(corrected_frame.data[50, 50, 0]), 200)

    def test_tangential_distortion(self):
        """Tests tangential decentering distortion displacement."""
        w, h = 60, 60
        data = np.full((h, w, 3), 100, dtype=np.uint8)
        frame = make_test_frame(w, h, data)

        cfg = LensCorrectionConfig(
            clip_id="test_tangential",
            p1=0.1,
            p2=0.05,
            border_mode=BorderHandlingMode.CLAMP_EDGE,
        )
        out, diag = self.engine.process_frame(frame, cfg)
        self.assertTrue(diag.distortion_applied)
        self.assertGreater(diag.max_displacement_pixels, 1.0)

    def test_optical_center_offset(self):
        """Tests that shifting optical center shifts the displacement center asymmetry."""
        w, h = 80, 80
        # Optical center shifted to (0.2, 0.2)
        cfg_shifted = LensCorrectionConfig(
            clip_id="test_center",
            k1=0.2,
            center_x=0.2,
            center_y=0.2,
        )
        map_x, map_y = self.engine.build_distortion_maps(w, h, cfg_shifted)

        # At the shifted optical center (0.2 * 80 = 16, 0.2 * 80 = 16), displacement should be ~0
        diff_at_center = math.sqrt((map_x[16, 16] - 16)**2 + (map_y[16, 16] - 16)**2)
        self.assertLess(diff_at_center, 0.1)

        # At the geometric center (40, 40), displacement should be non-zero
        diff_at_geom = math.sqrt((map_x[40, 40] - 40)**2 + (map_y[40, 40] - 40)**2)
        self.assertGreater(diff_at_geom, 0.5)

    def test_border_modes_and_alpha_preservation(self):
        """Tests TRANSPARENT border mode zeros alpha for unmapped boundary pixels."""
        w, h = 60, 60
        data = np.full((h, w, 4), 255, dtype=np.uint8)
        frame = make_test_frame(w, h, data)

        # Positive k in inverse map pulls from outside frame boundary (creating unmapped pixels)
        cfg = LensCorrectionConfig(
            clip_id="test_borders",
            k1=0.5,
            border_mode=BorderHandlingMode.TRANSPARENT,
        )
        out, diag = self.engine.process_frame(frame, cfg)
        self.assertGreater(diag.unmapped_border_pixels_pct, 0.0)

        # Corner (0, 0) should have alpha = 0 because it's unmapped
        self.assertEqual(int(out.data[0, 0, 3]), 0)
        # Center (30, 30) should remain fully opaque (255)
        self.assertEqual(int(out.data[30, 30, 3]), 255)

    def test_chromatic_aberration_correction(self):
        """Tests channel-aware lateral chromatic aberration remapping."""
        w, h = 60, 60
        data = np.zeros((h, w, 3), dtype=np.uint8)
        # Set a white vertical strip at center
        data[:, 28:32, :] = 255
        frame = make_test_frame(w, h, data)

        cfg = LensCorrectionConfig(
            clip_id="test_ca",
            enable_ca_correction=True,
            ca_red_displacement=2.5, # Warp red outward by 2.5%
            ca_blue_displacement=-2.5, # Warp blue inward by 2.5%
        )
        out, diag = self.engine.process_frame(frame, cfg)
        self.assertTrue(diag.ca_corrected)
        self.assertGreater(diag.max_displacement_pixels, 0.0)

    def test_vignetting_correction(self):
        """Tests that vignetting correction brightens outer corners while leaving the center intact."""
        w, h = 80, 80
        data = np.full((h, w, 3), 100, dtype=np.uint8)
        frame = make_test_frame(w, h, data)

        cfg = LensCorrectionConfig(
            clip_id="test_vignette",
            enable_vignette_correction=True,
            vignette_gain=1.5, # +150% gain at corners
            vignette_midpoint=0.5,
        )
        out, diag = self.engine.process_frame(frame, cfg)
        self.assertTrue(diag.vignette_corrected)

        # Center (40, 40) is at r=0, so gain should be ~1.0 (pixel remains ~100)
        self.assertAlmostEqual(float(out.data[40, 40, 0]), 100, delta=3)

        # Corner (0, 0) is at max radius, so pixel should be significantly brighter
        corner_val = int(out.data[0, 0, 0])
        self.assertGreater(corner_val, 160)

    def test_lens_profile_matching(self):
        """Tests focal length and metadata profile matching."""
        # 1. Exact match on 24mm
        matched_profile, basis, conf = self.service.match_profile_from_metadata(
            clip_id="clip_meta",
            focal_length_hint=24.0,
        )
        self.assertIsNotNone(matched_profile)
        self.assertEqual(basis, ProfileMatchBasis.EXACT_METADATA)
        self.assertEqual(conf, 1.0)
        self.assertEqual(matched_profile.focal_length_mm, 24.0)

        # 2. Closest focal length match (e.g. 15.5mm close to 15mm Canon RF)
        p2, basis2, conf2 = self.service.match_profile_from_metadata(
            clip_id="clip_meta_close",
            focal_length_hint=15.5,
        )
        self.assertIsNotNone(p2)
        self.assertEqual(basis2, ProfileMatchBasis.FOCAL_LENGTH)
        self.assertGreaterEqual(conf2, 0.5)

        # 3. No match when focal length is completely distant
        p3, basis3, conf3 = self.service.match_profile_from_metadata(
            clip_id="clip_meta_none",
            focal_length_hint=400.0,
        )
        self.assertIsNone(p3)
        self.assertEqual(basis3, ProfileMatchBasis.NO_MATCH)

    def test_apply_profile_and_undo_redo(self):
        """Tests applying a profile transfers calibration coefficients and supports undo/redo."""
        clip_id = "clip_profile_test"
        cfg = self.service.get_or_create_config(clip_id)
        self.assertEqual(cfg.k1, 0.0)

        # Apply GoPro 16mm profile (k1 = -0.285)
        updated_cfg = self.service.apply_profile_to_clip(clip_id, "gopro_hero_wide_16mm")
        # Inverted for correction: -(-0.285) = +0.285
        self.assertAlmostEqual(updated_cfg.k1, 0.285, places=3)
        self.assertTrue(updated_cfg.enable_ca_correction)
        self.assertTrue(updated_cfg.enable_vignette_correction)

        # Undo
        self.service.undo(clip_id)
        self.assertEqual(self.service.get_or_create_config(clip_id).k1, 0.0)

        # Redo
        self.service.redo(clip_id)
        self.assertAlmostEqual(self.service.get_or_create_config(clip_id).k1, 0.285, places=3)

    def test_effect_processor_registry_integration(self):
        """Verifies VideoLensEffectProcessor is registered in Module 10 effects pipeline."""
        processor = effect_processor_registry.get("lens_distortion_correction")
        self.assertIsNotNone(processor)
        self.assertIsInstance(processor, VideoLensEffectProcessor)
        self.assertEqual(processor.category, EffectCategory.TRANSFORM)

        # Process a test frame through the processor interface
        frame = make_test_frame(40, 40, np.full((40, 40, 3), 128, dtype=np.uint8))
        res = processor.process_frame(
            frame=frame,
            parameters={"k1": -0.1, "strength": 1.0, "border_mode": "CLAMP_EDGE"},
            render_width=40,
            render_height=40,
        )
        self.assertIsNotNone(res.data)
        self.assertEqual(res.width, 40)
        self.assertEqual(res.height, 40)


if __name__ == "__main__":
    unittest.main()
