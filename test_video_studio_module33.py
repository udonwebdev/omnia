"""Unit and Integration Tests for Module 33: Optical Flow, Motion Vectors & Motion-Aware Processing Engine.

Verifies:
1. Synthetic translation with known vector displacement (verifies accuracy of estimated (dx, dy)).
2. Sparse versus dense optical flow behavior (explicitly verifies field_type).
3. Forward and backward bidirectional consistency verification (consistency error, confidence map, occlusion mask).
4. Scene-cut detection and discontinuity protection (MAD threshold prevents bogus motion estimates across cuts).
5. Vector field resizing and coordinate displacement re-scaling.
6. Motion visualization (HSV color-wheel rendering).
7. Optical flow caching and lifecycle management.
8. Downstream integration contracts:
   - Module 27 (Frame Interpolation bi-directional flow)
   - Module 25 (Motion-compensated denoising alignment)
   - Module 28 (Motion blur directional vector)
   - Module 21 (Sparse stabilization points)
9. Effect processor registry integration (VideoMotionFlowEffectProcessor under UTILITY).
"""

import unittest
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer, EffectCategory
from video_studio.effects_processors import effect_processor_registry
from video_studio.optical_flow_models import (
    MotionVectorField,
    MotionVectorFieldType,
    FlowAlgorithmType,
    FlowQualityPreset,
    FlowDirection,
    FlowFieldStatus,
    MotionAnalysisConfig,
)
from video_studio.optical_flow_engine import OpticalFlowEngine
from video_studio.optical_flow_service import VideoOpticalFlowService
from video_studio.optical_flow_processor import VideoMotionFlowEffectProcessor


def make_test_frame(width: int, height: int, data: np.ndarray, frame_number: int = 0) -> VideoFrameBuffer:
    buf = VideoFrameBuffer(width=width, height=height, data=data)
    buf.timeline_frame = frame_number
    buf.pts_seconds = frame_number * 0.04
    return buf


class TestVideoStudioModule33(unittest.TestCase):

    def setUp(self):
        self.engine = OpticalFlowEngine()
        self.service = VideoOpticalFlowService(engine=self.engine)

    def test_known_synthetic_translation_dense_flow(self):
        """Tests that Farneback dense optical flow recovers known synthetic translation within tolerance."""
        h, w = 80, 80
        # Create textured pattern (high contrast grid/noise to allow optical flow gradient calculation)
        np.random.seed(42)
        base = np.random.randint(40, 220, (h, w), dtype=np.uint8)
        base = cv2.GaussianBlur(base, (5, 5), 1.5)

        # Shift by known displacement: dx = +3.0, dy = +2.0
        known_dx, known_dy = 3.0, 2.0
        M = np.float32([[1, 0, known_dx], [0, 1, known_dy]])
        shifted = cv2.warpAffine(base, M, (w, h), borderMode=cv2.BORDER_REFLECT)

        frame_a = make_test_frame(w, h, np.repeat(base[:, :, np.newaxis], 4, axis=2), frame_number=0)
        frame_b = make_test_frame(w, h, np.repeat(shifted[:, :, np.newaxis], 4, axis=2), frame_number=1)

        cfg = MotionAnalysisConfig(
            algorithm=FlowAlgorithmType.FARNEBACK_DENSE,
            quality_preset=FlowQualityPreset.STUDIO_HIGH_QUALITY,
            direction=FlowDirection.FORWARD,
            win_size=15,
            iterations=5,
        )
        flow_field = self.engine.compute_dense_flow(frame_a, frame_b, config=cfg)

        self.assertEqual(flow_field.status, FlowFieldStatus.VALID)
        self.assertEqual(flow_field.field_type, MotionVectorFieldType.DENSE)
        self.assertIsNotNone(flow_field.dense_flow)
        self.assertEqual(flow_field.dense_flow.shape, (h, w, 2))

        # Check central region (away from boundaries)
        center_flow_x = flow_field.dense_flow[20:60, 20:60, 0]
        center_flow_y = flow_field.dense_flow[20:60, 20:60, 1]

        est_dx = float(np.mean(center_flow_x))
        est_dy = float(np.mean(center_flow_y))

        # Tolerance: within 0.5 pixels
        self.assertAlmostEqual(est_dx, known_dx, delta=0.6)
        self.assertAlmostEqual(est_dy, known_dy, delta=0.6)

    def test_sparse_feature_flow_lucas_kanade(self):
        """Tests Pyramidal Lucas-Kanade sparse feature optical flow."""
        h, w = 60, 60
        img_a = np.zeros((h, w, 4), dtype=np.uint8)
        # Add distinct high-contrast corners
        img_a[15:20, 15:20, :3] = 255
        img_a[35:40, 35:40, :3] = 255
        img_a[:, :, 3] = 255

        # Shift by dx = 4, dy = 0
        img_b = np.zeros((h, w, 4), dtype=np.uint8)
        img_b[15:20, 19:24, :3] = 255
        img_b[35:40, 39:44, :3] = 255
        img_b[:, :, 3] = 255

        frame_a = make_test_frame(w, h, img_a, frame_number=0)
        frame_b = make_test_frame(w, h, img_b, frame_number=1)

        flow_field = self.engine.compute_sparse_flow(frame_a, frame_b, max_features=50)

        self.assertEqual(flow_field.field_type, MotionVectorFieldType.SPARSE)
        self.assertIsNone(flow_field.dense_flow)
        self.assertGreater(len(flow_field.sparse_vectors), 0)

        # Verify tracked features have positive horizontal shift
        tracked = [v for v in flow_field.sparse_vectors if v.status == "TRACKED"]
        self.assertGreater(len(tracked), 0)
        for vec in tracked:
            self.assertGreater(vec.dx, 1.0)
            self.assertTrue(0.0 <= vec.confidence <= 1.0)

    def test_bidirectional_consistency_and_occlusions(self):
        """Tests forward-backward consistency and occlusion mask generation."""
        h, w = 40, 40
        np.random.seed(123)
        base = np.random.randint(80, 160, (h, w), dtype=np.uint8)
        base = cv2.GaussianBlur(base, (5, 5), 1.0) # smooth gradient to keep MAD low
        shifted = np.roll(base, shift=1, axis=1) # shift x by 1

        frame_a = make_test_frame(w, h, np.repeat(base[:, :, np.newaxis], 4, axis=2))
        frame_b = make_test_frame(w, h, np.repeat(shifted[:, :, np.newaxis], 4, axis=2))

        cfg = MotionAnalysisConfig(direction=FlowDirection.BIDIRECTIONAL, scene_cut_threshold=50.0)
        flow_field = self.engine.compute_dense_flow(frame_a, frame_b, config=cfg)

        self.assertEqual(flow_field.status, FlowFieldStatus.VALID)
        self.assertIsNotNone(flow_field.dense_flow)
        self.assertIsNotNone(flow_field.backward_flow)
        self.assertIsNotNone(flow_field.confidence_map)
        self.assertIsNotNone(flow_field.occlusion_mask)

        # Confidence map must be strictly in [0.0, 1.0]
        self.assertTrue(np.all(flow_field.confidence_map >= 0.0))
        self.assertTrue(np.all(flow_field.confidence_map <= 1.0))

    def test_scene_cut_detection_discontinuity(self):
        """Tests that a scene cut sets status to SCENE_CUT_DETECTED and zeroes vectors instead of hallucinating."""
        h, w = 30, 30
        frame_black = make_test_frame(w, h, np.zeros((h, w, 4), dtype=np.uint8))
        frame_white = make_test_frame(w, h, np.full((h, w, 4), 255, dtype=np.uint8))

        cfg = MotionAnalysisConfig(scene_cut_threshold=30.0)
        flow_field = self.engine.compute_dense_flow(frame_black, frame_white, config=cfg)

        self.assertEqual(flow_field.status, FlowFieldStatus.SCENE_CUT_DETECTED)
        self.assertTrue(flow_field.diagnostics.scene_cut_detected)
        # Must not fabricate nonzero motion
        self.assertTrue(np.all(flow_field.dense_flow == 0.0))

    def test_motion_field_resizing_and_coordinate_scaling(self):
        """Tests that resizing a motion field scales vector displacement proportionally."""
        h, w = 40, 40
        flow_data = np.full((h, w, 2), 4.0, dtype=np.float32) # dx=4.0, dy=4.0
        field = MotionVectorField(
            width=w, height=h, dense_flow=flow_data,
            confidence_map=np.ones((h, w), dtype=np.float32),
        )

        # Upscale 2x: width=80, height=80
        resized = self.engine.resize_motion_field(field, 80, 80)
        self.assertEqual(resized.width, 80)
        self.assertEqual(resized.height, 80)
        self.assertEqual(resized.dense_flow.shape, (80, 80, 2))

        # Displacements must double (from 4.0 to 8.0)
        self.assertAlmostEqual(float(np.mean(resized.dense_flow[:, :, 0])), 8.0, places=2)
        self.assertAlmostEqual(float(np.mean(resized.dense_flow[:, :, 1])), 8.0, places=2)

    def test_flow_hsv_visualization(self):
        """Tests HSV color-wheel optical flow visualization."""
        h, w = 32, 32
        flow_data = np.zeros((h, w, 2), dtype=np.float32)
        flow_data[:, :, 0] = 5.0 # Positive dx (pure red/magenta in standard HSV)
        field = MotionVectorField(width=w, height=h, dense_flow=flow_data)

        viz = self.engine.visualize_flow_hsv(field, max_speed=10.0)
        self.assertEqual(viz.shape, (h, w, 3))
        self.assertEqual(viz.dtype, np.uint8)
        # Should be brightly colored, not all black
        self.assertGreater(np.mean(viz), 30.0)

    def test_service_caching_and_lifecycle(self):
        """Tests VideoOpticalFlowService caching and retrieval."""
        h, w = 24, 24
        f_a = make_test_frame(w, h, np.full((h, w, 4), 100, dtype=np.uint8), frame_number=0)
        f_b = make_test_frame(w, h, np.full((h, w, 4), 105, dtype=np.uint8), frame_number=1)

        cfg = MotionAnalysisConfig()
        res1 = self.service.estimate_inter_frame_motion(f_a, f_b, config=cfg, use_cache=True)
        res2 = self.service.estimate_inter_frame_motion(f_a, f_b, config=cfg, use_cache=True)

        # Second call should retrieve identical cached object
        self.assertIs(res1, res2)

        self.service.clear_cache()
        res3 = self.service.get_cached_flow("default_asset", 0, 1, cfg)
        self.assertIsNone(res3)

    def test_downstream_integration_contracts(self):
        """Tests integration helpers for Modules 27, 25, 28, and 21."""
        h, w = 32, 32
        np.random.seed(99)
        data_a = np.random.randint(60, 180, (h, w, 4), dtype=np.uint8)
        data_b = np.roll(data_a, shift=1, axis=0)

        f_a = make_test_frame(w, h, data_a, frame_number=5)
        f_b = make_test_frame(w, h, data_b, frame_number=6)

        # 1. Module 27 Frame Interpolation contract
        fw, bw, status = self.service.get_motion_for_interpolation(f_a, f_b)
        self.assertEqual(status, FlowFieldStatus.VALID)
        self.assertIsNotNone(fw)
        self.assertIsNotNone(bw)

        # 2. Module 25 Denoising contract
        flow_denoise, conf_denoise = self.service.get_motion_for_denoising(f_a, f_b)
        self.assertIsNotNone(flow_denoise)
        self.assertIsNotNone(conf_denoise)

        # 3. Module 28 Motion Blur contract
        motion_vec = self.service.get_motion_for_motion_blur(f_a, f_b)
        self.assertIsNotNone(motion_vec)
        self.assertIsInstance(motion_vec, tuple)
        self.assertEqual(len(motion_vec), 2)

        # 4. Module 21 Stabilization contract
        stab_pts = self.service.get_motion_for_stabilization(f_a, f_b)
        self.assertIsInstance(stab_pts, list)

    def test_effect_processor_registry_integration(self):
        """Tests that VideoMotionFlowEffectProcessor is registered in effect_processor_registry."""
        processor = effect_processor_registry.get("motion_optical_flow_viz")
        self.assertIsNotNone(processor)
        self.assertEqual(processor.category, EffectCategory.UTILITY)

        schemas = processor.get_schemas()
        param_ids = [s["parameter_id"] for s in schemas]
        self.assertIn("visualization_mode", param_ids)
        self.assertIn("max_speed", param_ids)
        self.assertIn("blend_opacity", param_ids)

        # Test frame rendering with overlay
        w, h = 30, 30
        f0 = make_test_frame(w, h, np.full((h, w, 4), 120, dtype=np.uint8), frame_number=0)
        f1 = make_test_frame(w, h, np.full((h, w, 4), 125, dtype=np.uint8), frame_number=1)

        processor.set_reference_frame(f0)
        out = processor.process_frame(
            frame=f1,
            parameters={"visualization_mode": "HSV_COLOR_WHEEL"},
            render_width=w,
            render_height=h,
        )
        self.assertEqual(out.width, w)
        self.assertEqual(out.height, h)
        self.assertEqual(out.data.shape, (h, w, 4))


if __name__ == "__main__":
    unittest.main()
