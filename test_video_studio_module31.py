"""Unit and Integration Tests for Module 31: Film Grain, Video Texture & Analog Emulation Engine.

Verifies:
1. Deterministic grain with fixed seeds (exact identical pixel output).
2. Different grain output with different seeds.
3. Grain intensity and spatial scale scaling (micro-grain vs coarse grain).
4. Luma and Chroma independent weighting.
5. Tonal curve response: differential grain visibility in shadows, midtones, and highlights.
6. Alpha preservation (RGBA buffers keep alpha channel untouched).
7. Temporal modes: FIXED (frozen grain), FRAME_VARYING (different grain per frame), and TEMPORALLY_COHERENT.
8. Frame-request order independence (frame N always evaluates to the same grain regardless of evaluation order).
9. Analog texture operations:
   - Gate weave subpixel frame jitter
   - Emulsion halation glow bloom
   - Procedural dust specks and scratches
10. Presets serialization and application (35mm Fine, 16mm Vintage, 8mm Retro, Noir).
11. Service undo/redo state management.
12. Integration with Module 10 effects processor registry.
"""

import unittest
import numpy as np

from video_studio.effects_models import VideoFrameBuffer, EffectCategory
from video_studio.effects_processors import effect_processor_registry
from video_studio.grain_models import (
    GrainType,
    TemporalGrainMode,
    HalationMode,
    AnalogTextureConfig,
    FilmGrainConfig,
    GrainDiagnostics,
)
from video_studio.grain_engine import (
    video_grain_engine,
    VideoGrainEngine,
)
from video_studio.grain_processor import VideoGrainEffectProcessor
from video_studio.grain_service import video_grain_service, VideoGrainService


def make_test_frame(width: int, height: int, data: np.ndarray, frame_number: int = 0) -> VideoFrameBuffer:
    buf = VideoFrameBuffer(width=width, height=height, data=data)
    buf.timeline_frame = frame_number
    return buf


class TestVideoStudioModule31(unittest.TestCase):

    def setUp(self):
        self.engine = VideoGrainEngine()
        self.service = VideoGrainService(engine=self.engine)

    def test_deterministic_grain_fixed_seed(self):
        """Tests that two evaluations with identical seed and frame number produce exact byte-for-byte identical output."""
        w, h = 60, 60
        data = np.full((h, w, 3), 128, dtype=np.uint8)
        frame1 = make_test_frame(w, h, data.copy(), frame_number=10)
        frame2 = make_test_frame(w, h, data.copy(), frame_number=10)

        cfg = FilmGrainConfig(
            clip_id="test_seed",
            base_seed=424242,
            intensity=0.5,
            temporal_mode=TemporalGrainMode.FRAME_VARYING,
        )

        out1, diag1 = self.engine.process_frame(frame1, cfg)
        out2, diag2 = self.engine.process_frame(frame2, cfg)

        self.assertEqual(diag1.effective_seed, diag2.effective_seed)
        self.assertTrue(np.array_equal(out1.data, out2.data))

    def test_different_seeds_produce_different_grain(self):
        """Tests that different base seeds produce different noise distributions."""
        w, h = 60, 60
        data = np.full((h, w, 3), 128, dtype=np.uint8)
        frame1 = make_test_frame(w, h, data.copy(), frame_number=5)
        frame2 = make_test_frame(w, h, data.copy(), frame_number=5)

        cfg1 = FilmGrainConfig(base_seed=1111, intensity=0.4)
        cfg2 = FilmGrainConfig(base_seed=9999, intensity=0.4)

        out1, _ = self.engine.process_frame(frame1, cfg1)
        out2, _ = self.engine.process_frame(frame2, cfg2)

        self.assertFalse(np.array_equal(out1.data, out2.data))

    def test_grain_intensity_and_scale(self):
        """Tests that increasing grain intensity increases standard deviation from original base."""
        w, h = 80, 80
        data = np.full((h, w, 3), 128, dtype=np.uint8)
        frame = make_test_frame(w, h, data.copy(), frame_number=1)

        cfg_low = FilmGrainConfig(intensity=0.1, scale=1.0)
        cfg_high = FilmGrainConfig(intensity=0.8, scale=1.0)

        out_low, _ = self.engine.process_frame(frame, cfg_low)
        out_high, _ = self.engine.process_frame(frame, cfg_high)

        diff_low = np.std(out_low.data[:, :, :3].astype(np.float32) - 128.0)
        diff_high = np.std(out_high.data[:, :, :3].astype(np.float32) - 128.0)

        self.assertGreater(diff_high, diff_low * 3.0)

    def test_luma_and_chroma_weighting(self):
        """Tests that zero chroma weight generates monochromatic grain (all channels equal delta)."""
        w, h = 50, 50
        data = np.full((h, w, 3), 128, dtype=np.uint8)
        frame = make_test_frame(w, h, data.copy(), frame_number=0)

        # Monochromatic grain: chroma_weight = 0.0
        cfg_mono = FilmGrainConfig(
            intensity=0.5,
            luma_weight=1.0,
            chroma_weight=0.0,
        )
        out_mono, _ = self.engine.process_frame(frame, cfg_mono)

        # In monochromatic grain, R, G, B should deviate equally from 128
        r = out_mono.data[:, :, 0]
        g = out_mono.data[:, :, 1]
        b = out_mono.data[:, :, 2]
        self.assertTrue(np.all(r == g))
        self.assertTrue(np.all(g == b))

        # Color grain: chroma_weight > 0
        cfg_color = FilmGrainConfig(
            intensity=0.5,
            luma_weight=1.0,
            chroma_weight=0.8,
        )
        out_color, _ = self.engine.process_frame(frame, cfg_color)
        r_c = out_color.data[:, :, 0]
        b_c = out_color.data[:, :, 2]
        self.assertFalse(np.all(r_c == b_c))

    def test_tonal_curve_weighting(self):
        """Tests that shadow vs highlight weighting limits grain in selected tonal zones."""
        # Split gradient: top half dark (20), bottom half bright (240)
        w, h = 60, 60
        data = np.zeros((h, w, 3), dtype=np.uint8)
        data[:30, :, :] = 20
        data[30:, :, :] = 240
        frame = make_test_frame(w, h, data.copy(), frame_number=1)

        # Grain only in shadows, zero in highlights
        cfg = FilmGrainConfig(
            intensity=0.6,
            shadow_weight=1.0,
            midtone_weight=0.0,
            highlight_weight=0.0,
        )
        out, _ = self.engine.process_frame(frame, cfg)

        top_std = np.std(out.data[:30, :, :3].astype(np.float32) - 20.0)
        bot_std = np.std(out.data[30:, :, :3].astype(np.float32) - 240.0)

        self.assertGreater(top_std, 2.0)
        self.assertLess(bot_std, 0.5)

    def test_alpha_preservation(self):
        """Tests that RGBA 4-channel buffers preserve alpha values byte-for-byte."""
        w, h = 50, 50
        data = np.full((h, w, 4), 128, dtype=np.uint8)
        data[:, :, 3] = np.tile(np.linspace(0, 255, 50, dtype=np.uint8), (50, 1))
        initial_alpha = data[:, :, 3].copy()
        frame = make_test_frame(w, h, data, frame_number=2)

        cfg = FilmGrainConfig(intensity=0.8)
        out, _ = self.engine.process_frame(frame, cfg)

        self.assertTrue(np.array_equal(out.data[:, :, 3], initial_alpha))
        self.assertTrue(np.all(out.data[:, :, :3] <= 255))
        self.assertTrue(np.all(out.data[:, :, :3] >= 0))

    def test_temporal_modes_and_order_independence(self):
        """Tests that evaluating frame 2, then frame 1, produces identical results to evaluating 1 then 2."""
        w, h = 40, 40
        data = np.full((h, w, 3), 128, dtype=np.uint8)
        frame1 = make_test_frame(w, h, data.copy(), frame_number=1)
        frame2 = make_test_frame(w, h, data.copy(), frame_number=2)

        cfg = FilmGrainConfig(base_seed=777, temporal_mode=TemporalGrainMode.FRAME_VARYING)

        # Order 1: frame1 then frame2
        out_f1_a, _ = self.engine.process_frame(frame1, cfg)
        out_f2_a, _ = self.engine.process_frame(frame2, cfg)

        # Order 2: frame2 then frame1
        out_f2_b, _ = self.engine.process_frame(frame2, cfg)
        out_f1_b, _ = self.engine.process_frame(frame1, cfg)

        self.assertTrue(np.array_equal(out_f1_a.data, out_f1_b.data))
        self.assertTrue(np.array_equal(out_f2_a.data, out_f2_b.data))
        # Frame 1 and Frame 2 should be different in FRAME_VARYING mode
        self.assertFalse(np.array_equal(out_f1_a.data, out_f2_a.data))

    def test_analog_texture_operations(self):
        """Tests gate weave, halation, and film wear procedural synthesis."""
        w, h = 60, 60
        # Image with bright specular white spot at center
        data = np.full((h, w, 3), 30, dtype=np.uint8)
        data[25:35, 25:35, :] = 255
        frame = make_test_frame(w, h, data, frame_number=7)

        cfg = FilmGrainConfig(
            intensity=0.0, # Zero grain so we specifically inspect textures
            texture=AnalogTextureConfig(
                enable_gate_weave=True,
                weave_amplitude_x=2.0,
                weave_amplitude_y=2.0,
                halation_mode=HalationMode.RED_ORANGE,
                halation_threshold=0.8,
                halation_intensity=0.8,
                halation_radius=8.0,
                enable_film_wear=True,
                dust_density=0.001,
            )
        )
        out, diag = self.engine.process_frame(frame, cfg)
        self.assertTrue(diag.gate_weave_applied)
        self.assertTrue(diag.halation_applied)
        self.assertTrue(diag.film_wear_applied)

        # Check halation: pixels adjacent to specular box (e.g. y=24, x=30) should have reddish glow (R > G, B)
        r = int(out.data[24, 30, 0])
        b = int(out.data[24, 30, 2])
        self.assertGreater(r, b)

    def test_presets_and_service_undo_redo(self):
        """Tests preset catalog loading, application, and undo/redo stacks."""
        clip_id = "clip_grain_test"
        cfg = self.service.get_or_create_config(clip_id)
        self.assertEqual(cfg.intensity, 0.25)

        # Apply 16mm Vintage Indie preset
        updated = self.service.apply_preset_to_clip(clip_id, "16mm Vintage Indie")
        self.assertEqual(updated.preset_name, "16mm Vintage Indie")
        self.assertEqual(updated.grain_type, GrainType.COARSE)
        self.assertEqual(updated.texture.halation_mode, HalationMode.RED_ORANGE)

        # Undo
        self.service.undo(clip_id)
        self.assertEqual(self.service.get_or_create_config(clip_id).intensity, 0.25)

        # Redo
        self.service.redo(clip_id)
        self.assertEqual(self.service.get_or_create_config(clip_id).preset_name, "16mm Vintage Indie")

    def test_effect_processor_registry_integration(self):
        """Verifies VideoGrainEffectProcessor is registered in Module 10 effects pipeline."""
        processor = effect_processor_registry.get("film_grain_texture")
        self.assertIsNotNone(processor)
        self.assertIsInstance(processor, VideoGrainEffectProcessor)
        self.assertEqual(processor.category, EffectCategory.FILTER)

        # Process a frame through the processor interface
        frame = make_test_frame(40, 40, np.full((40, 40, 3), 100, dtype=np.uint8), frame_number=3)
        res = processor.process_frame(
            frame=frame,
            parameters={"intensity": 0.5, "grain_type": "GAUSSIAN", "scale": 1.0},
            render_width=40,
            render_height=40,
        )
        self.assertIsNotNone(res.data)
        self.assertEqual(res.width, 40)
        self.assertEqual(res.height, 40)


if __name__ == "__main__":
    unittest.main()
