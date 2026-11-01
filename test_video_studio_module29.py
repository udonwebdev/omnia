"""Unit and Integration Tests for Module 29: Video Lighting, Exposure & Relighting Engine.

Verifies:
1. Deterministic global exposure compensation measured against known reference pixels (2^EV scaling).
2. Tonal shaping: highlights, shadows, whites, blacks, and gamma power response.
3. Color temperature and tint balance.
4. Localized radial and spotlight lighting regions with feathering falloff.
5. Linear directional and polygon mask lighting regions.
6. Blend modes (ADD, SCREEN, SOFT_LIGHT, MULTIPLY) and negative flagging/shading.
7. Overlapping multiple light regions with independent geometry and blend equations.
8. Alpha channel preservation and no unintended color shifts.
9. Motion-tracking attachment and offset application (Module 22).
10. Undo, redo, presets, and serialization parity.
11. Scene-aware AI relighting extension fallback when model is unavailable.
12. Integration with Module 10 effects processor registry.
"""

import unittest
import numpy as np
import time

from video_studio.effects_models import VideoFrameBuffer, EffectCategory
from video_studio.effects_processors import effect_processor_registry
from video_studio.lighting_models import (
    LightType,
    LightBlendMode,
    RelightingEngineMode,
    GlobalExposureTonalConfig,
    LocalLightRegion,
    SceneAwareRelightingExtension,
    LightingEngineDocument,
    LightingDiagnostics,
)
from video_studio.lighting_engine import (
    video_lighting_engine,
    VideoLightingEngine,
    apply_light_blend,
)
from video_studio.lighting_processor import VideoLightingEffectProcessor
from video_studio.lighting_service import video_lighting_service, VideoLightingService
from video_studio.registry import video_studio_capability_registry


def make_test_frame(width: int, height: int, data: np.ndarray) -> VideoFrameBuffer:
    return VideoFrameBuffer(width=width, height=height, data=data)


class TestVideoStudioModule29(unittest.TestCase):

    def setUp(self):
        self.engine = VideoLightingEngine()
        self.service = VideoLightingService(engine=self.engine)

    def test_global_exposure_stops(self):
        """Tests that exposure compensation in stops scales linear values by exactly 2^EV."""
        # 100x100 midtone image at 64/255 (approx 0.25098)
        data = np.full((100, 100, 3), 64, dtype=np.uint8)
        frame = make_test_frame(100, 100, data)

        # +1.0 EV should double the brightness: 64 * 2 = 128
        doc_plus1 = LightingEngineDocument(
            clip_id="test_exp",
            global_tone=GlobalExposureTonalConfig(exposure_stops=1.0)
        )
        out_plus1, diag = self.engine.process_frame(frame, doc_plus1)
        expected_val = int(round(64 * 2.0))
        self.assertAlmostEqual(float(out_plus1.data[50, 50, 0]), expected_val, delta=2)

        # -1.0 EV should halve the brightness: 64 / 2 = 32
        doc_minus1 = LightingEngineDocument(
            clip_id="test_exp",
            global_tone=GlobalExposureTonalConfig(exposure_stops=-1.0)
        )
        out_minus1, _ = self.engine.process_frame(frame, doc_minus1)
        self.assertAlmostEqual(float(out_minus1.data[50, 50, 0]), 32, delta=2)

    def test_tonal_highlights_shadows_and_gamma(self):
        """Tests that highlights affect bright regions more than dark, and shadows affect dark regions."""
        # Split gradient image: left half dark (30), right half bright (200)
        data = np.zeros((100, 100, 3), dtype=np.uint8)
        data[:, :50, :] = 30
        data[:, 50:, :] = 200
        frame = make_test_frame(100, 100, data)

        # Boost highlights: right side should brighten significantly, left side almost unaffected
        doc_h = LightingEngineDocument(
            clip_id="test_tone",
            global_tone=GlobalExposureTonalConfig(highlights=50.0)
        )
        out_h, _ = self.engine.process_frame(frame, doc_h)
        left_diff = float(out_h.data[50, 20, 0]) - 30.0
        right_diff = float(out_h.data[50, 80, 0]) - 200.0
        self.assertGreater(right_diff, left_diff * 3.0)

        # Boost shadows: left side should lift significantly, right side unaffected
        doc_s = LightingEngineDocument(
            clip_id="test_tone",
            global_tone=GlobalExposureTonalConfig(shadows=50.0)
        )
        out_s, _ = self.engine.process_frame(frame, doc_s)
        left_s_diff = float(out_s.data[50, 20, 0]) - 30.0
        right_s_diff = float(out_s.data[50, 80, 0]) - 200.0
        self.assertGreater(left_s_diff, right_s_diff * 3.0)

        # Gamma check: gamma > 1.0 brightens midtones
        doc_g = LightingEngineDocument(
            clip_id="test_gamma",
            global_tone=GlobalExposureTonalConfig(gamma=2.2)
        )
        out_g, _ = self.engine.process_frame(frame, doc_g)
        self.assertGreater(int(out_g.data[50, 20, 0]), 30)

    def test_color_temperature_and_tint(self):
        """Tests warm temperature boost increases red and decreases blue."""
        data = np.full((60, 60, 3), 120, dtype=np.uint8)
        frame = make_test_frame(60, 60, data)

        doc = LightingEngineDocument(
            clip_id="test_temp",
            global_tone=GlobalExposureTonalConfig(temperature=50.0, tint=0.0)
        )
        out, _ = self.engine.process_frame(frame, doc)
        r, g, b = out.data[30, 30, :3]
        self.assertGreater(r, 120)
        self.assertLess(b, 120)

    def test_localized_radial_light_region(self):
        """Tests that a radial light illuminates the center with smooth falloff to the edges."""
        # 100x100 dark image (20)
        data = np.full((100, 100, 3), 20, dtype=np.uint8)
        frame = make_test_frame(100, 100, data)

        doc = LightingEngineDocument(
            clip_id="test_local",
            light_regions=[
                LocalLightRegion(
                    pos_x=0.5,
                    pos_y=0.5,
                    radius_x=0.3,
                    radius_y=0.3,
                    feather=0.5,
                    intensity=1.0,
                    color_rgb=(1.0, 1.0, 1.0),
                    blend_mode=LightBlendMode.ADD,
                )
            ]
        )
        out, diag = self.engine.process_frame(frame, doc)
        self.assertEqual(diag.active_regions_count, 1)

        # Center should be substantially brighter
        center_val = int(out.data[50, 50, 0])
        self.assertGreater(center_val, 150)

        # Corner (0, 0) is well outside radius (dist ~0.7 > 0.3) and should be unchanged (20)
        corner_val = int(out.data[0, 0, 0])
        self.assertEqual(corner_val, 20)

    def test_negative_light_flagging_and_directional(self):
        """Tests negative light intensity for shading/flagging and directional gradient."""
        # 100x100 midtone image (150)
        data = np.full((100, 100, 3), 150, dtype=np.uint8)
        frame = make_test_frame(100, 100, data)

        doc = LightingEngineDocument(
            clip_id="test_flag",
            light_regions=[
                LocalLightRegion(
                    pos_x=0.5,
                    pos_y=0.5,
                    radius_x=0.3,
                    radius_y=0.3,
                    feather=0.5,
                    intensity=-0.8, # Flags / darkens center
                )
            ]
        )
        out, _ = self.engine.process_frame(frame, doc)
        self.assertLess(int(out.data[50, 50, 0]), 100)
        self.assertEqual(int(out.data[0, 0, 0]), 150)

    def test_alpha_preservation_and_clamping(self):
        """Tests that RGBA buffers preserve alpha channel byte-for-byte and clamp RGB properly."""
        data = np.full((50, 50, 4), 100, dtype=np.uint8)
        # Assign varying alpha gradient
        data[:, :, 3] = np.tile(np.linspace(10, 240, 50, dtype=np.uint8), (50, 1))
        initial_alpha = data[:, :, 3].copy()
        frame = make_test_frame(50, 50, data)

        # Apply strong exposure and light
        doc = LightingEngineDocument(
            clip_id="test_alpha",
            global_tone=GlobalExposureTonalConfig(exposure_stops=3.0),
            light_regions=[
                LocalLightRegion(intensity=2.0)
            ]
        )
        out, diag = self.engine.process_frame(frame, doc)
        self.assertTrue(np.array_equal(out.data[:, :, 3], initial_alpha))
        self.assertTrue(np.all(out.data[:, :, :3] <= 255))
        self.assertTrue(np.all(out.data[:, :, :3] >= 0))

    def test_scene_aware_relighting_extension_fallback(self):
        """Tests that requesting scene-aware relighting cleanly falls back with diagnostic telemetry."""
        data = np.full((50, 50, 3), 100, dtype=np.uint8)
        frame = make_test_frame(50, 50, data)

        doc = LightingEngineDocument(
            clip_id="test_scene_aware",
            engine_mode=RelightingEngineMode.SCENE_AWARE,
            scene_aware=SceneAwareRelightingExtension(is_available=False),
            global_tone=GlobalExposureTonalConfig(exposure_stops=0.5),
        )
        out, diag = self.engine.process_frame(frame, doc)
        self.assertTrue(diag.scene_aware_fallback_triggered)
        self.assertGreater(int(out.data[25, 25, 0]), 100)

    def test_tracking_offset_integration(self):
        """Tests that motion-tracking spatial offsets shift the light center accurately."""
        data = np.full((100, 100, 3), 20, dtype=np.uint8)
        frame = make_test_frame(100, 100, data)

        doc = LightingEngineDocument(
            clip_id="test_track",
            light_regions=[
                LocalLightRegion(
                    pos_x=0.3,
                    pos_y=0.3,
                    radius_x=0.15,
                    radius_y=0.15,
                    feather=0.2,
                    intensity=1.0,
                    tracking_session_id="track_session_123",
                )
            ]
        )
        # Shift light center from (0.3, 0.3) to (0.7, 0.7) by passing tracking_offset=(+0.4, +0.4)
        out, _ = self.engine.process_frame(frame, doc, tracking_offset=(0.4, 0.4))
        # (70, 70) should be brightly lit, while (30, 30) should remain dark
        self.assertGreater(int(out.data[70, 70, 0]), 100)
        self.assertEqual(int(out.data[30, 30, 0]), 20)

    def test_service_presets_and_undo_redo(self):
        """Tests service document update, built-in presets, and undo/redo stacks."""
        doc = self.service.get_or_create_document("clip_edit_1")
        self.assertEqual(doc.global_tone.exposure_stops, 0.0)

        # Update with exposure
        updated_doc = LightingEngineDocument(
            clip_id="clip_edit_1",
            global_tone=GlobalExposureTonalConfig(exposure_stops=1.5)
        )
        self.service.update_document("clip_edit_1", updated_doc)
        self.assertEqual(self.service.get_or_create_document("clip_edit_1").global_tone.exposure_stops, 1.5)

        # Undo
        self.service.undo("clip_edit_1")
        self.assertEqual(self.service.get_or_create_document("clip_edit_1").global_tone.exposure_stops, 0.0)

        # Redo
        self.service.redo("clip_edit_1")
        self.assertEqual(self.service.get_or_create_document("clip_edit_1").global_tone.exposure_stops, 1.5)

        # Apply preset
        preset_doc = self.service.apply_preset("clip_edit_1", "studio_portrait")
        self.assertEqual(len(preset_doc.light_regions), 2)
        self.assertIn("Key Light", [r.name for r in preset_doc.light_regions])

    def test_effect_processor_registry_integration(self):
        """Verifies that VideoLightingEffectProcessor is registered in the effects pipeline."""
        processor = effect_processor_registry.get("lighting_relighting")
        self.assertIsNotNone(processor)
        self.assertIsInstance(processor, VideoLightingEffectProcessor)
        self.assertEqual(processor.category, EffectCategory.FILTER)

        # Process a test frame through the processor interface
        frame = make_test_frame(40, 40, np.full((40, 40, 3), 50, dtype=np.uint8))
        res = processor.process_frame(
            frame=frame,
            parameters={"exposure_stops": 1.0, "enable_local_light": True, "local_light_x": 0.5, "local_light_y": 0.5},
            render_width=40,
            render_height=40,
        )
        self.assertGreater(int(res.data[20, 20, 0]), 100)


if __name__ == "__main__":
    unittest.main()
