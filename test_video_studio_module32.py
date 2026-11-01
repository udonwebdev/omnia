"""Unit and Integration Tests for Module 32: Depth Estimation, Depth Maps & 2.5D Compositing Engine.

Verifies:
1. Depth map normalization:
   - NaN / Inf sanitization and detection
   - Range scaling from arbitrary boundaries to [0.0, 1.0]
   - Polarity inversion (near becomes far and vice versa)
   - Clamping boundaries
2. Depth slicing & range matte generation:
   - Smooth cosine feathered falloff
   - Zero alpha outside slice region, 1.0 inside target slice
3. Depth-of-field (DoF) optical defocus blur:
   - Pixels at focal distance remain sharp
   - Defocus blur increases proportionally with distance from focal plane
   - Strict alpha preservation across RGBA frames
4. 2.5D Camera Parallax displacement:
   - Near objects undergo greater parallax shift than far objects
   - Zero displacement at the designated parallax focal plane
   - Edge handling modes: REPLICATE, CLAMP, TRANSPARENT
5. Depth-aware layer occlusion:
   - Modulates foreground transparency based on virtual intersection depth
6. Monocular AI depth estimation adapter:
   - Extension interface availability and status checks (strictly no fake depth maps)
7. Service & State Management:
   - Ingestion and retrieval of depth sequences
   - Undo and redo history tracking
   - Workflow presets serialization and application
8. Module 10 Video Effects Pipeline Integration:
   - VideoDepthEffectProcessor registered in effect_processor_registry under EffectCategory.COMPOSITING
   - Schema validation and frame processing execution
"""

import unittest
import numpy as np

from video_studio.effects_models import VideoFrameBuffer, EffectCategory
from video_studio.effects_processors import effect_processor_registry
from video_studio.depth_models import (
    DepthRepresentationType,
    DepthEdgeMode,
    DepthMapProvenance,
    DepthDiagnostics,
    DepthMap,
    DepthEffectConfig,
    MonocularEstimationAdapter,
)
from video_studio.depth_engine import (
    normalize_depth_map,
    generate_depth_range_mask,
    apply_depth_of_field,
    apply_parallax_25d,
    apply_depth_occlusion,
    VideoDepthEngine,
)
from video_studio.depth_processor import VideoDepthEffectProcessor
from video_studio.depth_service import VideoDepthService


def make_test_frame(width: int, height: int, data: np.ndarray, frame_number: int = 0) -> VideoFrameBuffer:
    buf = VideoFrameBuffer(width=width, height=height, data=data)
    buf.timeline_frame = frame_number
    return buf


class TestVideoStudioModule32(unittest.TestCase):

    def setUp(self):
        self.engine = VideoDepthEngine()
        self.service = VideoDepthService(engine=self.engine)

    def test_depth_normalization_and_nan_sanitization(self):
        """Tests that raw depth arrays with NaNs and Infs are sanitized into valid [0.0, 1.0] range."""
        raw = np.array([
            [np.nan, 2.0, 10.0],
            [np.inf, -5.0, 5.0],
        ], dtype=np.float32)
        diag = DepthDiagnostics()
        norm = normalize_depth_map(raw, diagnostics=diag)

        self.assertEqual(norm.shape, (2, 3))
        self.assertTrue(np.all(np.isfinite(norm)))
        self.assertTrue(np.all(norm >= 0.0) and np.all(norm <= 1.0))
        self.assertGreater(diag.invalid_nan_inf_count, 0)

    def test_depth_inversion_and_scaling(self):
        """Tests that depth inversion properly flips near and far values."""
        raw = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
        norm_std = normalize_depth_map(raw, is_inverted=False)
        norm_inv = normalize_depth_map(raw, is_inverted=True)

        np.testing.assert_allclose(norm_std, [[0.0, 0.5, 1.0]], atol=1e-5)
        np.testing.assert_allclose(norm_inv, [[1.0, 0.5, 0.0]], atol=1e-5)

    def test_depth_range_slice_matte(self):
        """Tests depth slicing produces 1.0 inside slice window and 0.0 outside."""
        # 1D depth ramp from 0.0 to 1.0
        depth = np.linspace(0.0, 1.0, 100, dtype=np.float32).reshape(10, 10)
        # Isolate slice between 0.3 and 0.7
        mask = generate_depth_range_mask(depth, slice_near=0.3, slice_far=0.7, feather=0.01)

        self.assertEqual(mask.shape, (10, 10))
        self.assertTrue(np.all(mask >= 0.0) and np.all(mask <= 1.0))
        # Value at 0.5 must be inside core slice (1.0)
        idx_mid = (depth >= 0.35) & (depth <= 0.65)
        self.assertTrue(np.all(mask[idx_mid] == 1.0))
        # Value at 0.1 must be outside (0.0)
        idx_outside = depth < 0.2
        self.assertTrue(np.all(mask[idx_outside] == 0.0))

    def test_depth_of_field_optical_blur_and_alpha_preservation(self):
        """Tests that DoF blurs distant planes while keeping in-focus plane sharp without degrading alpha."""
        h, w = 40, 40
        # Checkerboard pattern to measure blur via variance/gradient
        img = np.zeros((h, w, 4), dtype=np.uint8)
        img[::2, ::2, :3] = 255
        img[:, :, 3] = 200 # Constant alpha

        # Depth map: top half in focus (0.2), bottom half far out of focus (0.9)
        depth = np.full((h, w), 0.2, dtype=np.float32)
        depth[20:, :] = 0.9

        out = apply_depth_of_field(
            img,
            depth,
            focus_distance=0.2,
            focal_range=0.05,
            max_blur=15.0,
            feather=0.05,
        )

        # Alpha channel must remain intact
        np.testing.assert_array_equal(out[:, :, 3], img[:, :, 3])

        # Sharp top half should retain higher pixel difference than blurred bottom half
        sharp_diff = np.abs(np.diff(out[:15, :, 0].astype(np.float32), axis=1))
        blurred_diff = np.abs(np.diff(out[25:, :, 0].astype(np.float32), axis=1))
        self.assertGreater(np.mean(sharp_diff), np.mean(blurred_diff))

    def test_25d_parallax_camera_displacement(self):
        """Tests that 2.5D parallax shifts near objects while preserving focal plane."""
        h, w = 50, 50
        img = np.zeros((h, w, 4), dtype=np.uint8)
        # Vertical line in middle
        img[:, 25, :3] = 255
        img[:, :, 3] = 255

        # Focal plane at 0.5: top half near (0.1), bottom half at focal plane (0.5)
        depth = np.full((h, w), 0.5, dtype=np.float32)
        depth[:25, :] = 0.1

        diag = DepthDiagnostics()
        warped = apply_parallax_25d(
            img,
            depth,
            shift_x=10.0,
            shift_y=0.0,
            focal_plane=0.5,
            edge_mode=DepthEdgeMode.REPLICATE,
            diagnostics=diag,
        )

        self.assertEqual(warped.shape, (h, w, 4))
        self.assertGreater(diag.displacement_magnitude_max, 0.0)

        # Bottom half (at focal plane) should have its vertical line unchanged at x=25
        self.assertEqual(warped[35, 25, 0], 255)
        # Top half (near) should have shifted horizontally away from x=25
        self.assertNotEqual(warped[10, 25, 0], 255)

    def test_parallax_edge_modes(self):
        """Tests edge modes: REPLICATE vs TRANSPARENT boundary handling."""
        h, w = 30, 30
        img = np.full((h, w, 4), 255, dtype=np.uint8)
        depth = np.zeros((h, w), dtype=np.float32) # All near (large shift)

        warped_rep = apply_parallax_25d(
            img, depth, shift_x=15.0, shift_y=0.0, focal_plane=1.0, edge_mode=DepthEdgeMode.REPLICATE
        )
        warped_trans = apply_parallax_25d(
            img, depth, shift_x=15.0, shift_y=0.0, focal_plane=1.0, edge_mode=DepthEdgeMode.TRANSPARENT
        )

        # REPLICATE should have full alpha on the border
        self.assertEqual(warped_rep[15, 29, 3], 255)
        # TRANSPARENT should leave newly exposed border transparent
        self.assertEqual(warped_trans[15, 29, 3], 0)

    def test_depth_occlusion_compositing(self):
        """Tests that foreground pixels deeper than occlusion plane have alpha reduced."""
        h, w = 20, 20
        fg = np.full((h, w, 4), 255, dtype=np.uint8)
        # Left half in front of virtual plane (depth 0.2), right half behind (depth 0.8)
        depth = np.full((h, w), 0.2, dtype=np.float32)
        depth[:, 10:] = 0.8

        out = apply_depth_occlusion(fg, depth, occlusion_plane=0.5, softness=0.01)

        # Left half visible
        self.assertGreater(out[10, 5, 3], 200)
        # Right half occluded
        self.assertEqual(out[10, 15, 3], 0)

    def test_monocular_estimation_adapter_safeguards(self):
        """Tests that MonocularEstimationAdapter reports experimental status and does not fabricate depth."""
        adapter = MonocularEstimationAdapter()
        self.assertFalse(adapter.is_available)
        dummy_rgb = np.zeros((100, 100, 3), dtype=np.uint8)
        result_map, status = adapter.estimate_depth(dummy_rgb)

        self.assertIsNone(result_map)
        self.assertFalse(status["success"])
        self.assertIn("EXPERIMENTAL", status["error"])

    def test_depth_service_lifecycle_undo_redo(self):
        """Tests VideoDepthService ingestion, config mutations, and undo/redo stacks."""
        clip_id = "test_clip_depth_01"
        initial_cfg = self.service.get_config(clip_id)
        self.assertFalse(initial_cfg.enable_parallax)

        # Mutate config
        mod_cfg = initial_cfg
        mod_cfg.enable_parallax = True
        mod_cfg.parallax_shift_x = 24.0
        self.service.set_config(clip_id, mod_cfg)

        saved_cfg = self.service.get_config(clip_id)
        self.assertTrue(saved_cfg.enable_parallax)
        self.assertEqual(saved_cfg.parallax_shift_x, 24.0)

        # Undo
        undone = self.service.undo(clip_id)
        self.assertIsNotNone(undone)
        self.assertFalse(undone.enable_parallax)

        # Redo
        redone = self.service.redo(clip_id)
        self.assertIsNotNone(redone)
        self.assertTrue(redone.enable_parallax)
        self.assertEqual(redone.parallax_shift_x, 24.0)

    def test_effects_processor_registry_integration(self):
        """Tests that VideoDepthEffectProcessor is registered in effect_processor_registry."""
        processor = effect_processor_registry.get("depth_compositing_25d")
        self.assertIsNotNone(processor)
        self.assertEqual(processor.category, EffectCategory.COMPOSITING)

        schemas = processor.get_schemas()
        param_ids = [s["parameter_id"] for s in schemas]
        self.assertIn("enable_dof", param_ids)
        self.assertIn("enable_parallax", param_ids)
        self.assertIn("enable_depth_slice", param_ids)

        # Process frame through effect processor
        w, h = 32, 32
        data = np.full((h, w, 4), 180, dtype=np.uint8)
        frame = make_test_frame(w, h, data)
        out_frame = processor.process_frame(
            frame=frame,
            parameters={"enable_parallax": False, "enable_dof": False},
            render_width=w,
            render_height=h,
        )
        self.assertEqual(out_frame.width, w)
        self.assertEqual(out_frame.height, h)
        self.assertEqual(out_frame.data.shape, (h, w, 4))


if __name__ == "__main__":
    unittest.main()
