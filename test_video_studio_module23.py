"""OMNIA Video Studio — Module 23 Test Suite.
Tests:
1. Green-screen and Blue-screen key extraction with CIE L*a*b* perceptual separation.
2. Custom key color sampling from frame coordinates.
3. Edge refinement: feathering, choke (erosion), expansion (dilation), edge contrast shaping.
4. Chroma spill suppression: green spill neutralization on foreground edges.
5. Multi-sample key color extraction.
6. Viewer display modes: MATTE_ONLY, FOREGROUND_KEYED, COMPOSITE (over background), SPILL_ONLY.
7. Mask integration: attaching chroma matte as CompositingMask in MultilayerCompositor.
8. Capability registration in VideoStudioCapabilityRegistry.
"""

import unittest
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer
from video_studio.chroma_models import (
    ChromaColorSpace,
    ChromaKeyType,
    MatteDisplayMode,
    KeyColorSample,
    ChromaKeyConfig,
)
from video_studio.chroma_engine import ChromaKeyEngine
from video_studio.chroma_processor import ChromaKeyEffectProcessor
from video_studio.chroma_service import ChromaKeyService
from video_studio.compositor import MultilayerCompositor
from video_studio.registry import video_studio_capability_registry
from video_studio.catalog_loader import populate_roadmap_capabilities


def create_synthetic_greenscreen_frame(width: int = 200, height: int = 150) -> VideoFrameBuffer:
    """
    Creates a synthetic test frame:
    - Background: Pure green (0, 255, 0)
    - Foreground subject: Red rectangle (220, 30, 30) centered at (50, 40) to (150, 110)
    - Spill region: Left edge of subject tinted with green spill (150, 180, 50)
    """
    img = np.zeros((height, width, 4), dtype=np.uint8)
    # Background pure green, fully opaque
    img[:, :, 0] = 0
    img[:, :, 1] = 255
    img[:, :, 2] = 0
    img[:, :, 3] = 255

    # Center red rectangle (foreground)
    img[40:110, 50:150, 0] = 220
    img[40:110, 50:150, 1] = 30
    img[40:110, 50:150, 2] = 30

    # Spill contaminated region on right strip
    img[40:110, 140:150, 0] = 120
    img[40:110, 140:150, 1] = 180 # contaminated with excess green spill
    img[40:110, 140:150, 2] = 50

    return VideoFrameBuffer(width=width, height=height, data=img)


class TestModule23ChromaKey(unittest.TestCase):
    def setUp(self):
        self.engine = ChromaKeyEngine()
        self.compositor = MultilayerCompositor()
        self.service = ChromaKeyService(engine=self.engine, compositor=self.compositor)
        self.frame = create_synthetic_greenscreen_frame()

    def test_green_screen_matte_extraction(self):
        """Verifies clean extraction of pure green background to transparent alpha."""
        config = ChromaKeyConfig(
            key_type=ChromaKeyType.GREEN_SCREEN,
            color_space=ChromaColorSpace.LAB,
            tolerance=40.0,
            softness=10.0,
        )
        matte = self.engine.extract_matte(self.frame.data[:, :, :3], config)

        # Background pixel (10, 10): should be 0.0 (transparent)
        self.assertAlmostEqual(matte[10, 10], 0.0, places=2)

        # Foreground red center pixel (75, 100): should be 1.0 (opaque)
        self.assertAlmostEqual(matte[75, 100], 1.0, places=2)

    def test_blue_screen_matte_extraction(self):
        """Verifies blue screen key extraction."""
        # Create blue screen frame
        blue_data = np.zeros((100, 100, 4), dtype=np.uint8)
        blue_data[:, :, 2] = 255 # Pure blue
        blue_data[:, :, 3] = 255
        # Yellow square in center (255, 255, 0)
        blue_data[30:70, 30:70, 0] = 255
        blue_data[30:70, 30:70, 1] = 255
        blue_data[30:70, 30:70, 2] = 0
        blue_frame = VideoFrameBuffer(width=100, height=100, data=blue_data)

        config = ChromaKeyConfig(
            key_type=ChromaKeyType.BLUE_SCREEN,
            key_samples=[KeyColorSample(r=0, g=0, b=255)],
            color_space=ChromaColorSpace.LAB,
            tolerance=35.0,
            softness=10.0,
        )
        matte = self.engine.extract_matte(blue_frame.data[:, :, :3], config)
        self.assertAlmostEqual(matte[10, 10], 0.0, places=2)
        self.assertAlmostEqual(matte[50, 50], 1.0, places=2)

    def test_edge_refinement_choke_and_feather(self):
        """Verifies choke (erosion) and feathering on extracted matte."""
        config_raw = ChromaKeyConfig(choke=0, feather_radius=0)
        config_choke = ChromaKeyConfig(choke=-3, feather_radius=0)
        config_feather = ChromaKeyConfig(choke=0, feather_radius=5)

        raw = self.engine.refine_matte(self.engine.extract_matte(self.frame.data[:, :, :3], config_raw), config_raw)
        choked = self.engine.refine_matte(self.engine.extract_matte(self.frame.data[:, :, :3], config_choke), config_choke)
        feathered = self.engine.refine_matte(self.engine.extract_matte(self.frame.data[:, :, :3], config_feather), config_feather)

        # Choking must reduce the total sum of foreground alpha pixels
        self.assertLess(np.sum(choked), np.sum(raw))

        # Feathered boundary pixel at (40, 100) must be smoothly soft between 0 and 1
        self.assertGreater(feathered[40, 100], 0.0)
        self.assertLess(feathered[40, 100], 1.0)

    def test_spill_suppression(self):
        """Verifies excess green spill is neutralized on foreground pixels."""
        config = ChromaKeyConfig(
            spill_suppression=True,
            spill_strength=0.9,
            spill_threshold=0.05,
        )
        matte = self.engine.extract_matte(self.frame.data[:, :, :3], config)
        despilled, spill_map = self.engine.suppress_spill(self.frame.data[:, :, :3], matte, config)

        # Inspect contaminated region pixel (75, 145) where original green was 180
        orig_green = self.frame.data[75, 145, 1]
        despilled_green = despilled[75, 145, 1]
        self.assertEqual(orig_green, 180)
        self.assertLess(despilled_green, orig_green)
        self.assertGreater(spill_map[75, 145], 0.0)

    def test_sample_key_color_from_frame(self):
        """Verifies color sampling from frame coordinates."""
        sample = self.service.sample_key_color_from_frame("clip_test", self.frame, x=10, y=10, sample_radius=2)
        self.assertEqual(sample.r, 0)
        self.assertEqual(sample.g, 255)
        self.assertEqual(sample.b, 0)

        cfg = self.service.get_or_create_config("clip_test")
        self.assertEqual(cfg.key_type, ChromaKeyType.CUSTOM_COLOR)
        self.assertEqual(len(cfg.key_samples), 1)

    def test_viewer_display_modes(self):
        """Verifies display mode output formats."""
        cfg = ChromaKeyConfig()

        # Matte Only mode
        cfg.display_mode = MatteDisplayMode.MATTE_ONLY
        res_matte = self.engine.process_frame(self.frame, cfg)
        # In matte mode, RGB channels are grayscale alpha
        self.assertEqual(res_matte.data[10, 10, 0], 0)
        self.assertEqual(res_matte.data[75, 100, 0], 255)

        # Foreground Keyed mode
        cfg.display_mode = MatteDisplayMode.FOREGROUND_KEYED
        res_fg = self.engine.process_frame(self.frame, cfg)
        self.assertEqual(res_fg.data[10, 10, 3], 0) # Background is transparent
        self.assertEqual(res_fg.data[75, 100, 3], 255) # Subject is opaque

        # Composite mode over background
        bg_buf = VideoFrameBuffer(width=200, height=150, data=np.full((150, 200, 4), 200, dtype=np.uint8))
        cfg.display_mode = MatteDisplayMode.COMPOSITE
        res_comp = self.engine.process_frame(self.frame, cfg, background_frame=bg_buf)
        # Background pixel should show background color (200)
        self.assertEqual(res_comp.data[10, 10, 0], 200)

    def test_compositor_mask_attachment(self):
        """Verifies attaching extracted matte as CompositingMask in MultilayerCompositor."""
        mask = self.service.attach_as_compositor_mask("clip_test", self.frame, compositor=self.compositor)
        self.assertIn("clip_test", self.compositor.clip_masks)
        self.assertEqual(self.compositor.clip_masks["clip_test"].mask_id, mask.mask_id)
        self.assertIsNotNone(mask.mask_data)

    def test_effects_pipeline_processor(self):
        """Verifies ChromaKeyEffectProcessor executes via standard effects stack."""
        processor = ChromaKeyEffectProcessor(engine=self.engine)
        params = {
            "key_type": "GREEN_SCREEN",
            "tolerance": 45.0,
            "softness": 15.0,
            "display_mode": "FOREGROUND_KEYED",
        }
        out = processor.process_frame(self.frame, params, 200, 150)
        self.assertEqual(out.data[10, 10, 3], 0)
        self.assertEqual(out.data[75, 100, 3], 255)

    def test_module23_capabilities_registered(self):
        """Verifies Module 23 capabilities in catalog and registry."""
        populate_roadmap_capabilities(video_studio_capability_registry)
        self.service.register_capabilities()

        ck = video_studio_capability_registry.get("video.compositing.chroma_key")
        me = video_studio_capability_registry.get("video.compositing.matte_extraction")
        sp = video_studio_capability_registry.get("video.compositing.spill_suppression")
        ks = video_studio_capability_registry.get("video.compositing.key_sampling")

        self.assertIsNotNone(ck)
        self.assertIsNotNone(me)
        self.assertIsNotNone(sp)
        self.assertIsNotNone(ks)


if __name__ == "__main__":
    unittest.main()
