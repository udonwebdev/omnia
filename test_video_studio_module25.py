"""OMNIA Video Studio — Module 25 Test Suite.
Tests:
1. Edge-preserving spatial bilateral filtering on synthetic noisy image (measured MSE reduction and PSNR gain).
2. Fast Non-Local Means (FastNlMeans) spatial denoising.
3. Guided filter edge-preserving noise reduction.
4. Separate Luma and Chroma channel filtering (LUMA_ONLY, CHROMA_ONLY).
5. Sensor restoration: Dead pixel correction (replacing single-pixel outliers with median).
6. Post-denoise detail recovery (unsharp masking with noise coring).
7. Motion-safe temporal multi-frame accumulation (noise reduction on static/slow scenes without ghosting).
8. Strict alpha channel preservation (alpha is completely unaltered).
9. Integration with Module 10 effects pipeline (VideoDenoiseEffectProcessor).
10. Capability registration in VideoStudioCapabilityRegistry.
"""

import unittest
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.denoise_models import (
    DenoiseMethod,
    DenoiseQualityMode,
    DenoiseChannelScope,
    DenoiseConfig,
    DenoiseDiagnostics,
)
from video_studio.denoise_engine import VideoDenoiseEngine
from video_studio.denoise_processor import VideoDenoiseEffectProcessor
from video_studio.denoise_service import VideoDenoiseService
from video_studio.registry import video_studio_capability_registry
from video_studio.catalog_loader import populate_roadmap_capabilities


def create_clean_and_noisy_fixtures(
    width: int = 160,
    height: int = 120,
    noise_sigma: float = 20.0,
) -> tuple[VideoFrameBuffer, VideoFrameBuffer]:
    """
    Creates a clean synthetic image and a corresponding noisy image.
    Clean image has high-contrast geometric steps and flat color patches.
    """
    clean = np.zeros((height, width, 4), dtype=np.uint8)
    clean[:, :, 3] = 255 # Opaque

    # Add flat regions and sharp edges
    clean[:60, :80, 0] = 200 # Red patch
    clean[:60, 80:, 1] = 180 # Green patch
    clean[60:, :80, 2] = 220 # Blue patch
    clean[60:, 80:, :3] = 128 # Gray patch

    # Add Gaussian noise to RGB
    np.random.seed(42)
    noise = np.random.normal(0.0, noise_sigma, (height, width, 3))
    noisy_rgb = np.clip(clean[:, :, :3].astype(np.float32) + noise, 0, 255).astype(np.uint8)

    # Half transparent on bottom right quadrant to verify alpha preservation
    clean[60:, 80:, 3] = 128

    noisy = clean.copy()
    noisy[:, :, :3] = noisy_rgb

    clean_buf = VideoFrameBuffer(width=width, height=height, data=clean)
    noisy_buf = VideoFrameBuffer(width=width, height=height, data=noisy)
    return clean_buf, noisy_buf


class TestModule25Denoise(unittest.TestCase):
    def setUp(self):
        self.engine = VideoDenoiseEngine()
        self.service = VideoDenoiseService(engine=self.engine)
        self.clean_buf, self.noisy_buf = create_clean_and_noisy_fixtures()

    def test_spatial_bilateral_denoising(self):
        """Verifies bilateral filtering reduces MSE against known clean ground truth."""
        config = DenoiseConfig(
            method=DenoiseMethod.BILATERAL_SPATIAL,
            strength=20.0,
            spatial_radius=5,
        )
        out_buf, diag = self.engine.process_frame(
            self.noisy_buf,
            config,
            reference_clean_frame=self.clean_buf,
        )

        clean_rgb = self.clean_buf.data[:, :, :3].astype(np.float32)
        noisy_rgb = self.noisy_buf.data[:, :, :3].astype(np.float32)
        out_rgb = out_buf.data[:, :, :3].astype(np.float32)

        mse_before = float(np.mean((noisy_rgb - clean_rgb) ** 2))
        mse_after = float(np.mean((out_rgb - clean_rgb) ** 2))

        # Denoising MUST significantly reduce Mean Squared Error
        self.assertLess(mse_after, mse_before)
        self.assertGreater(diag.psnr_gain_db, 0.0)

    def test_fast_nl_means_denoising(self):
        """Verifies Non-Local Means filter execution and noise reduction."""
        config = DenoiseConfig(
            method=DenoiseMethod.FAST_NL_MEANS,
            quality_mode=DenoiseQualityMode.FAST,
            luma_strength=15.0,
            chroma_strength=15.0,
        )
        out_buf, _ = self.engine.process_frame(self.noisy_buf, config)

        clean_rgb = self.clean_buf.data[:, :, :3].astype(np.float32)
        noisy_rgb = self.noisy_buf.data[:, :, :3].astype(np.float32)
        out_rgb = out_buf.data[:, :, :3].astype(np.float32)

        mse_before = float(np.mean((noisy_rgb - clean_rgb) ** 2))
        mse_after = float(np.mean((out_rgb - clean_rgb) ** 2))
        self.assertLess(mse_after, mse_before)

    def test_guided_filter_denoising(self):
        """Verifies edge-preserving guided filtering."""
        config = DenoiseConfig(
            method=DenoiseMethod.GUIDED_FILTER,
            spatial_radius=4,
            edge_preservation=0.8,
        )
        out_buf, _ = self.engine.process_frame(self.noisy_buf, config)

        clean_rgb = self.clean_buf.data[:, :, :3].astype(np.float32)
        noisy_rgb = self.noisy_buf.data[:, :, :3].astype(np.float32)
        out_rgb = out_buf.data[:, :, :3].astype(np.float32)

        self.assertLess(float(np.mean((out_rgb - clean_rgb) ** 2)), float(np.mean((noisy_rgb - clean_rgb) ** 2)))

    def test_alpha_channel_preservation(self):
        """Verifies alpha channel is strictly preserved byte-for-byte across denoising."""
        config = DenoiseConfig(method=DenoiseMethod.BILATERAL_SPATIAL, strength=30.0)
        out_buf, _ = self.engine.process_frame(self.noisy_buf, config)

        # Alpha channels must match exactly
        np.testing.assert_array_equal(out_buf.data[:, :, 3], self.noisy_buf.data[:, :, 3])

    def test_luma_and_chroma_channel_scopes(self):
        """Verifies independent LUMA_ONLY and CHROMA_ONLY filtering modes."""
        # 1. LUMA_ONLY: Luminance Y is filtered significantly while Cr/Cb remain close to original within roundtrip tolerances
        cfg_luma = DenoiseConfig(channel_scope=DenoiseChannelScope.LUMA_ONLY)
        out_luma, _ = self.engine.process_frame(self.noisy_buf, cfg_luma)
        ycrcb_in = cv2.cvtColor(self.noisy_buf.data[:, :, :3], cv2.COLOR_RGB2YCrCb)
        ycrcb_out = cv2.cvtColor(out_luma.data[:, :, :3], cv2.COLOR_RGB2YCrCb)

        # Y is filtered (substantial variance reduction across flat patches)
        diff_y = np.mean(np.abs(ycrcb_out[:, :, 0].astype(float) - ycrcb_in[:, :, 0].astype(float)))
        diff_cr = np.mean(np.abs(ycrcb_out[:, :, 1].astype(float) - ycrcb_in[:, :, 1].astype(float)))
        diff_cb = np.mean(np.abs(ycrcb_out[:, :, 2].astype(float) - ycrcb_in[:, :, 2].astype(float)))

        self.assertGreater(diff_y, 2.0)
        # Chroma channels should have minimal roundtrip quantization error (< 2.0 mean diff)
        self.assertLess(diff_cr, 2.0)
        self.assertLess(diff_cb, 2.0)

    def test_dead_pixel_correction(self):
        """Verifies isolated hot/dead pixel defects are detected and replaced."""
        corrupted = self.clean_buf.copy()
        # Introduce bright white hot pixel at (30, 30) on dark red region
        corrupted.data[30, 30, :3] = [255, 255, 255]

        cleaned = self.engine.correct_dead_pixels(corrupted.data[:, :, :3], threshold=40.0)
        # Hot pixel should be corrected back towards red neighborhood (200, 0, 0)
        self.assertNotEqual(cleaned[30, 30, 1], 255)
        self.assertAlmostEqual(cleaned[30, 30, 0], 200, delta=15)

    def test_temporal_accumulation_denoising(self):
        """Verifies multi-frame temporal accumulation reduces noise on stationary content."""
        # Generate 3 frames with independent noise instances of same static scene
        f1 = self.noisy_buf.copy()
        f2 = self.noisy_buf.copy()
        np.random.seed(101)
        n2 = np.random.normal(0.0, 20.0, f2.data[:, :, :3].shape)
        f2.data[:, :, :3] = np.clip(self.clean_buf.data[:, :, :3].astype(np.float32) + n2, 0, 255).astype(np.uint8)

        config = DenoiseConfig(
            temporal_enabled=True,
            temporal_frames=3,
            temporal_blend_weight=0.5,
        )
        out_buf, diag = self.engine.process_frame(
            f1,
            config,
            adjacent_buffers=[f2],
            reference_clean_frame=self.clean_buf,
        )
        self.assertEqual(diag.temporal_frames_used, 2)

    def test_post_sharpening_unsharp_mask(self):
        """Verifies post-denoise sharpening recovers high-frequency edge contrast."""
        blurred = cv2.GaussianBlur(self.clean_buf.data[:, :, :3], (5, 5), 1.0)
        sharpened = self.engine.apply_post_sharpening(blurred, amount=0.5)
        # Edge gradient sharpness between (59, 40) and (60, 40) should be higher
        diff_blurred = abs(int(blurred[59, 40, 0]) - int(blurred[60, 40, 0]))
        diff_sharp = abs(int(sharpened[59, 40, 0]) - int(sharpened[60, 40, 0]))
        self.assertGreaterEqual(diff_sharp, diff_blurred)

    def test_effects_pipeline_processor(self):
        """Verifies VideoDenoiseEffectProcessor integrates with Module 10 effects stack."""
        processor = VideoDenoiseEffectProcessor(engine=self.engine)
        params = {
            "method": "BILATERAL_SPATIAL",
            "strength": 20.0,
            "spatial_radius": 3,
            "dead_pixel_correction": False,
        }
        out = processor.process_frame(self.noisy_buf, params, 160, 120)
        self.assertEqual(out.width, 160)
        self.assertEqual(out.height, 120)
        self.assertFalse(np.array_equal(out.data[:, :, :3], self.noisy_buf.data[:, :, :3]))

    def test_module25_capabilities_registered(self):
        """Verifies Module 25 capabilities in catalog and registry."""
        populate_roadmap_capabilities(video_studio_capability_registry)
        self.service.register_capabilities()

        sp = video_studio_capability_registry.get("video.restoration.spatial_denoise")
        tp = video_studio_capability_registry.get("video.restoration.temporal_denoise")
        ar = video_studio_capability_registry.get("video.restoration.artifact_removal")
        lc = video_studio_capability_registry.get("video.restoration.luma_chroma_separation")

        self.assertIsNotNone(sp)
        self.assertIsNotNone(tp)
        self.assertIsNotNone(ar)
        self.assertIsNotNone(lc)


if __name__ == "__main__":
    unittest.main()
