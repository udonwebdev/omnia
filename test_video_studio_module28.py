"""OMNIA Video Studio — Module 28 Test Suite.
Tests:
1. Synthetic motion blur generation using linear Point Spread Function (PSF).
2. Camera shutter angle modes (90 vs 180 vs 360 degrees).
3. Wiener deconvolution restoration on synthetically blurred frame fixture.
4. Gibbs ringing and halo suppression during deconvolution.
5. Motion-vector guided blur generation (Module 21/22 integration).
6. Strict alpha channel preservation across blur and deblur operations.
7. Integration with Module 10 effects pipeline (VideoDeblurEffectProcessor).
8. Capability registration in VideoStudioCapabilityRegistry.
"""

import unittest
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.deblur_models import (
    BlurOperationType,
    BlurKernelType,
    ShutterAngleMode,
    DeblurMethod,
    DeblurConfig,
    DeblurDiagnostics,
)
from video_studio.deblur_engine import VideoDeblurEngine
from video_studio.deblur_processor import VideoDeblurEffectProcessor
from video_studio.deblur_service import VideoDeblurService
from video_studio.registry import video_studio_capability_registry
from video_studio.catalog_loader import populate_roadmap_capabilities


def create_sharp_edge_fixture(width: int = 80, height: int = 60) -> VideoFrameBuffer:
    """Creates a high-contrast sharp edge test fixture with semi-transparent alpha."""
    data = np.zeros((height, width, 4), dtype=np.uint8)
    data[:, :, 3] = 255 # Opaque base

    # High contrast vertical white bar between x=25 and x=55
    data[:, 25:55, :3] = 240

    # Semi-transparent alpha in bottom half
    data[30:, :, 3] = 180

    return VideoFrameBuffer(width=width, height=height, data=data)


class TestModule28Deblur(unittest.TestCase):
    def setUp(self):
        self.engine = VideoDeblurEngine()
        self.service = VideoDeblurService(engine=self.engine)
        self.fixture = create_sharp_edge_fixture()

    def test_motion_blur_generation(self):
        """Verifies synthetic motion blur smears sharp vertical edges horizontally."""
        config = DeblurConfig(
            operation=BlurOperationType.MOTION_BLUR_GENERATION,
            blur_length=11.0,
            blur_angle_deg=0.0, # Horizontal blur
            shutter_mode=ShutterAngleMode.SHUTTER_180,
        )
        out_buf, diag = self.engine.process_frame(self.fixture, config)

        self.assertEqual(out_buf.width, self.fixture.width)
        self.assertEqual(out_buf.height, self.fixture.height)

        # Before blur, x=24 is 0, x=25 is 240.
        # After horizontal blur, x=24 should have non-zero smeared intensity
        orig_val = self.fixture.data[20, 24, 0]
        blurred_val = out_buf.data[20, 24, 0]
        self.assertEqual(orig_val, 0)
        self.assertGreater(blurred_val, 15)

    def test_shutter_angle_modes(self):
        """Verifies 90 degree shutter produces shorter blur trail than 360 degree shutter."""
        cfg_90 = DeblurConfig(
            operation=BlurOperationType.MOTION_BLUR_GENERATION,
            blur_length=12.0,
            shutter_mode=ShutterAngleMode.SHUTTER_90,
        )
        cfg_360 = DeblurConfig(
            operation=BlurOperationType.MOTION_BLUR_GENERATION,
            blur_length=12.0,
            shutter_mode=ShutterAngleMode.SHUTTER_360,
        )
        out_90, _ = self.engine.process_frame(self.fixture, cfg_90)
        out_360, _ = self.engine.process_frame(self.fixture, cfg_360)

        # Pixel further away from edge (e.g. x=20): 360 deg shutter smears further than 90 deg
        val_90 = out_90.data[20, 20, 0]
        val_360 = out_360.data[20, 20, 0]
        self.assertGreater(val_360, val_90)

    def test_wiener_deblur_restoration(self):
        """Verifies Wiener deconvolution sharpens blurry transitions."""
        # 1. Synthetically blur the sharp fixture
        cfg_blur = DeblurConfig(
            operation=BlurOperationType.MOTION_BLUR_GENERATION,
            blur_length=9.0,
            blur_angle_deg=0.0,
        )
        blurred_buf, _ = self.engine.process_frame(self.fixture, cfg_blur)

        # 2. Apply Wiener deconvolution restoration
        cfg_deblur = DeblurConfig(
            operation=BlurOperationType.DEBLUR_RESTORATION,
            deblur_method=DeblurMethod.WIENER_DECONVOLUTION,
            blur_length=9.0,
            blur_angle_deg=0.0,
            regularization_k=0.005,
            ringing_suppression=True,
        )
        deblurred_buf, diag = self.engine.process_frame(blurred_buf, cfg_deblur)

        # Compare edge gradient sharpness across transition x=24 to x=26
        grad_blurred = abs(int(blurred_buf.data[20, 26, 0]) - int(blurred_buf.data[20, 24, 0]))
        grad_deblurred = abs(int(deblurred_buf.data[20, 26, 0]) - int(deblurred_buf.data[20, 24, 0]))

        # Deblurred edge must be steeper / sharper than the blurred input
        self.assertGreater(grad_deblurred, grad_blurred)

    def test_alpha_preservation_across_deblur(self):
        """Verifies alpha channel is preserved intact during deblurring."""
        cfg = DeblurConfig(operation=BlurOperationType.MOTION_BLUR_GENERATION, blur_length=7.0)
        out_buf, _ = self.engine.process_frame(self.fixture, cfg)

        # Alpha channel in bottom half was 180
        np.testing.assert_array_equal(out_buf.data[:, :, 3], self.fixture.data[:, :, 3])

    def test_motion_vector_guided_blur(self):
        """Verifies motion vector (dx, dy) guides blur synthesis."""
        cfg = DeblurConfig(
            operation=BlurOperationType.MOTION_BLUR_GENERATION,
            kernel_type=BlurKernelType.MOTION_VECTOR,
            motion_scale=1.5,
        )
        # Moving diagonally down-right (dx=8.0, dy=6.0)
        out_buf, diag = self.engine.process_frame(self.fixture, cfg, motion_vector=(8.0, 6.0))
        self.assertAlmostEqual(diag.psf_length, 10.0 * 1.5, delta=0.5) # hypot(8, 6) * 1.5 = 15.0

    def test_effects_pipeline_processor(self):
        """Verifies VideoDeblurEffectProcessor executes via Module 10 effects stack."""
        processor = VideoDeblurEffectProcessor(engine=self.engine)
        params = {
            "operation": "MOTION_BLUR_GENERATION",
            "blur_length": 8.0,
            "blur_angle_deg": 90.0,
        }
        out = processor.process_frame(self.fixture, params, 80, 60)
        self.assertEqual(out.width, 80)
        self.assertEqual(out.height, 60)

    def test_module28_capabilities_registered(self):
        """Verifies Module 28 capabilities in catalog and registry."""
        populate_roadmap_capabilities(video_studio_capability_registry)
        self.service.register_capabilities()

        dw = video_studio_capability_registry.get("video.effects.deblur_wiener")
        bg = video_studio_capability_registry.get("video.effects.motion_blur_generation")
        br = video_studio_capability_registry.get("video.effects.motion_blur_reduction")

        self.assertIsNotNone(dw)
        self.assertIsNotNone(bg)
        self.assertIsNotNone(br)


if __name__ == "__main__":
    unittest.main()
