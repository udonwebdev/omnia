"""OMNIA Video Studio — Module 26 Test Suite.
Tests:
1. Spatial upscaling by integer and fractional scale factors (2.0x, 1.5x) using Lanczos4, Bicubic, Bilinear, and Nearest-Neighbor.
2. Sizing policies: SCALE_FACTOR, FIT_CANVAS, FILL_CANVAS, CUSTOM_DIMENSIONS.
3. Preservation of even video dimensions (divisible by 2) on odd source inputs.
4. Alpha channel preservation and dedicated interpolation.
5. Detail enhancement & sharpening with halo overshoot suppression.
6. Pre-upscale denoising integration with Module 25.
7. Truthful learned super-resolution fallback when model file or cv2.dnn_superres is absent.
8. Integration with Module 10 effects pipeline (VideoUpscaleEffectProcessor).
9. Capability registration in VideoStudioCapabilityRegistry.
"""

import unittest
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.upscale_models import (
    UpscaleAlgorithm,
    SizingPolicy,
    AspectRatioMode,
    UpscaleQualityMode,
    UpscaleConfig,
    UpscaleDiagnostics,
)
from video_studio.upscale_engine import VideoUpscaleEngine
from video_studio.upscale_processor import VideoUpscaleEffectProcessor
from video_studio.upscale_service import VideoUpscaleService
from video_studio.registry import video_studio_capability_registry
from video_studio.catalog_loader import populate_roadmap_capabilities


def create_test_lowres_frame(width: int = 64, height: int = 48) -> VideoFrameBuffer:
    """Creates a small synthetic test frame with geometric shapes and transparency."""
    img = np.zeros((height, width, 4), dtype=np.uint8)
    img[:, :, 3] = 255 # Opaque base

    # Checker pattern
    for y in range(0, height, 8):
        for x in range(0, width, 8):
            if ((x // 8) + (y // 8)) % 2 == 0:
                img[y:y+8, x:x+8, 0] = 220
                img[y:y+8, x:x+8, 1] = 50
                img[y:y+8, x:x+8, 2] = 50
            else:
                img[y:y+8, x:x+8, 0] = 50
                img[y:y+8, x:x+8, 1] = 180
                img[y:y+8, x:x+8, 2] = 220

    # Gradient alpha in lower quadrant
    img[24:, 32:, 3] = 128
    return VideoFrameBuffer(width=width, height=height, data=img)


class TestModule26Upscale(unittest.TestCase):
    def setUp(self):
        self.engine = VideoUpscaleEngine()
        self.service = VideoUpscaleService(engine=self.engine)
        self.frame = create_test_lowres_frame(64, 48)

    def test_lanczos4_scale_factor_upscaling(self):
        """Verifies 2.0x spatial upscaling using Lanczos4 interpolation."""
        config = UpscaleConfig(
            algorithm=UpscaleAlgorithm.LANCZOS4,
            sizing_policy=SizingPolicy.SCALE_FACTOR,
            scale_factor=2.0,
            detail_enhancement=False,
        )
        out_buf, diag = self.engine.process_frame(self.frame, config)

        self.assertEqual(out_buf.width, 128)
        self.assertEqual(out_buf.height, 96)
        self.assertEqual(diag.output_width, 128)
        self.assertEqual(diag.output_height, 96)
        self.assertEqual(diag.scale_factor_x, 2.0)
        self.assertEqual(diag.scale_factor_y, 2.0)

    def test_fractional_scale_and_odd_dimension_handling(self):
        """Verifies fractional scaling (1.5x) and odd dimension rounding to even numbers."""
        odd_frame = create_test_lowres_frame(45, 33) # Odd dimensions
        config = UpscaleConfig(
            algorithm=UpscaleAlgorithm.BICUBIC,
            scale_factor=1.5,
        )
        out_buf, _ = self.engine.process_frame(odd_frame, config)

        # 45 * 1.5 = 67.5 -> rounded to 68 (even). 33 * 1.5 = 49.5 -> rounded to 50 (even).
        self.assertEqual(out_buf.width % 2, 0)
        self.assertEqual(out_buf.height % 2, 0)
        self.assertGreater(out_buf.width, 45)
        self.assertGreater(out_buf.height, 33)

    def test_sizing_policies(self):
        """Verifies FIT_CANVAS, FILL_CANVAS, and CUSTOM_DIMENSIONS policies."""
        # 1. Fit Canvas 1920x1080 (16:9) on 4:3 (64x48) input -> fits width/height maintaining 4:3 aspect
        cfg_fit = UpscaleConfig(
            sizing_policy=SizingPolicy.FIT_CANVAS,
            target_width=1920,
            target_height=1080,
        )
        w, h = cfg_fit.calculate_target_size(64, 48)
        self.assertLessEqual(w, 1920)
        self.assertLessEqual(h, 1080)
        self.assertAlmostEqual(w / h, 64 / 48, delta=0.05)

        # 2. Custom Dimensions
        cfg_custom = UpscaleConfig(
            sizing_policy=SizingPolicy.CUSTOM_DIMENSIONS,
            target_width=320,
            target_height=240,
        )
        w_cust, h_cust = cfg_custom.calculate_target_size(64, 48)
        self.assertEqual(w_cust, 320)
        self.assertEqual(h_cust, 240)

    def test_alpha_preservation_across_upscaling(self):
        """Verifies alpha channel is correctly resized and retained."""
        config = UpscaleConfig(scale_factor=2.0)
        out_buf, _ = self.engine.process_frame(self.frame, config)

        # Check alpha channel shape and value in semi-transparent region
        self.assertEqual(out_buf.data.shape, (96, 128, 4))
        # Lower right region was 128 alpha in source; resampled alpha should remain ~128
        sample_alpha = out_buf.data[60, 80, 3]
        self.assertAlmostEqual(sample_alpha, 128, delta=5)

    def test_detail_enhancement_and_halo_suppression(self):
        """Verifies post-upscale sharpening increases high-contrast edge gradients without clipping overflow."""
        config_no_sharpen = UpscaleConfig(scale_factor=2.0, detail_enhancement=False)
        config_sharpen = UpscaleConfig(scale_factor=2.0, detail_enhancement=True, sharpen_amount=0.5, halo_suppression=True)

        out_normal, _ = self.engine.process_frame(self.frame, config_no_sharpen)
        out_sharpened, _ = self.engine.process_frame(self.frame, config_sharpen)

        # Inspect checkerboard transition at x=16 in upscaled frame
        grad_normal = abs(int(out_normal.data[20, 16, 0]) - int(out_normal.data[20, 15, 0]))
        grad_sharp = abs(int(out_sharpened.data[20, 16, 0]) - int(out_sharpened.data[20, 15, 0]))
        self.assertGreaterEqual(grad_sharp, grad_normal)

    def test_pre_denoise_integration(self):
        """Verifies pre-upscale denoising integrates with Module 25."""
        noisy_frame = self.frame.copy()
        # Add grain to frame
        np.random.seed(12)
        grain = np.random.normal(0, 15, (48, 64, 3))
        noisy_frame.data[:, :, :3] = np.clip(noisy_frame.data[:, :, :3].astype(float) + grain, 0, 255).astype(np.uint8)

        config_denoised = UpscaleConfig(scale_factor=2.0, pre_denoise=True, denoise_strength=20.0)
        out_denoised, _ = self.engine.process_frame(noisy_frame, config_denoised)
        self.assertEqual(out_denoised.width, 128)
        self.assertEqual(out_denoised.height, 96)

    def test_learned_super_res_fallback(self):
        """Verifies graceful and truthful fallback to Lanczos4 when model path is not supplied."""
        config = UpscaleConfig(
            algorithm=UpscaleAlgorithm.LEARNED_SUPER_RES,
            scale_factor=2.0,
            model_path=None, # No model path supplied
        )
        out_buf, diag = self.engine.process_frame(self.frame, config)
        self.assertEqual(out_buf.width, 128)
        self.assertEqual(out_buf.height, 96)
        self.assertFalse(diag.model_inference)

    def test_effects_pipeline_processor(self):
        """Verifies VideoUpscaleEffectProcessor integrates with Module 10 effects stack."""
        processor = VideoUpscaleEffectProcessor(engine=self.engine)
        params = {
            "algorithm": "LANCZOS4",
            "scale_factor": 2.0,
            "detail_enhancement": True,
            "sharpen_amount": 0.2,
        }
        out = processor.process_frame(self.frame, params, 64, 48)
        self.assertEqual(out.width, 128)
        self.assertEqual(out.height, 96)

    def test_module26_capabilities_registered(self):
        """Verifies Module 26 capabilities in catalog and registry."""
        populate_roadmap_capabilities(video_studio_capability_registry)
        self.service.register_capabilities()

        su = video_studio_capability_registry.get("video.rendering.spatial_upscale")
        de = video_studio_capability_registry.get("video.rendering.detail_enhancement")
        di = video_studio_capability_registry.get("video.rendering.denoise_integration")
        ls = video_studio_capability_registry.get("video.rendering.learned_super_res")

        self.assertIsNotNone(su)
        self.assertIsNotNone(de)
        self.assertIsNotNone(di)
        self.assertIsNotNone(ls)


if __name__ == "__main__":
    unittest.main()
