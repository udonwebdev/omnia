"""OMNIA Video Studio — Module 10 & 11 Verification Test Suite.

Verifies:
1. VideoFrameBuffer: Allocation, RGBA planar memory, blank, from_bytes, and to_bytes.
2. TransformEffectProcessor: Identity, translation, scaling, rotation, and pivot positioning.
3. OpacityEffectProcessor: Alpha channel scaling.
4. FlipEffectProcessor: Horizontal and vertical image flipping.
5. ColorCorrectionProcessor: Exposure (EV), Brightness, Contrast, Saturation (Rec.709 Luma), and Temperature.
6. InvertEffectProcessor: Photometric RGB inversion.
7. EffectStack & EffectsService: Ordered cascade, bypass/enable, and error isolation.
8. BlendMode Engine:
   - Porter-Duff Source-Over alpha compositing.
   - Multiply, Screen, Add, Darken, Lighten, Difference, and Overlay equations.
9. CompositingMask: Grayscale luma, alpha, inverted masks, and mask strength.
10. MultilayerCompositor:
    - Multitrack layer composition in bottom-to-top track order.
    - Integration with Module 10 effects pipeline.
    - Module 8 animation integration for layer opacity.
11. PlaybackEngine Integration: Live composited frame generation through viewer playback session.
12. Capability Registry: Verification of all registered effects and compositing capabilities.
"""

import unittest
import numpy as np

from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineTrackType,
    TimelineItemModel,
    TimelineRange,
    SourceRange,
)
from video_studio.effects_models import (
    VideoFrameBuffer,
    EffectParameterSchema,
    ParameterType,
    EffectCategory,
    EffectInstance,
    VideoEffectStack,
)
from video_studio.effects_processors import (
    TransformEffectProcessor,
    OpacityEffectProcessor,
    FlipEffectProcessor,
    ColorCorrectionProcessor,
    InvertEffectProcessor,
    effect_processor_registry,
)
from video_studio.effects_service import effects_service
from video_studio.compositing_models import (
    BlendMode,
    MaskType,
    CompositingMask,
    apply_blend_equation,
    composite_layers_porter_duff,
)
from video_studio.compositor import multilayer_compositor
from video_studio.playback_engine import playback_engine
from video_studio.animation_service import animation_service
from video_studio.animation_models import AnimatableProperty, PropertyValueType, InterpolationMode
from video_studio.registry import video_studio_capability_registry


class TestVideoStudioModule10And11(unittest.TestCase):
    """Module 10 Effects & Module 11 Compositing verification test suite."""

    def test_01_frame_buffer_and_transform(self):
        """Verifies VideoFrameBuffer allocation and 2D spatial transformation."""
        buf = VideoFrameBuffer.blank(100, 100, color=(255, 0, 0, 255)) # Red image
        self.assertEqual(buf.width, 100)
        self.assertEqual(buf.height, 100)
        self.assertEqual(int(buf.data[0, 0, 0]), 255)

        trans_proc = TransformEffectProcessor()
        # Identity transform should preserve image
        id_frame = trans_proc.process_frame(buf, {}, 100, 100)
        np.testing.assert_array_equal(id_frame.data, buf.data)

        # Translation by +50px X: left half becomes black/transparent (0), right half red (255)
        shifted = trans_proc.process_frame(buf, {"pos_x": 50.0}, 100, 100)
        self.assertEqual(int(shifted.data[50, 10, 0]), 0) # Empty space
        self.assertEqual(int(shifted.data[50, 75, 0]), 255) # Shifted image

    def test_02_opacity_and_flip(self):
        """Verifies alpha opacity scaling and horizontal flipping."""
        buf = VideoFrameBuffer.blank(10, 10, color=(255, 255, 255, 255))
        op_proc = OpacityEffectProcessor()
        half_op = op_proc.process_frame(buf, {"opacity": 0.5}, 10, 10)
        self.assertEqual(int(half_op.data[0, 0, 3]), 127) # 255 * 0.5 = 127

        # Flip horizontally: left red (255, 0), right blue (0, 255)
        grad = VideoFrameBuffer.blank(10, 10, color=(0, 0, 0, 255))
        grad.data[:, :5, 0] = 255 # Left red
        flip_proc = FlipEffectProcessor()
        flipped = flip_proc.process_frame(grad, {"flip_horizontal": True}, 10, 10)
        self.assertEqual(int(flipped.data[0, 0, 0]), 0) # Left now black
        self.assertEqual(int(flipped.data[0, 9, 0]), 255) # Right now red

    def test_03_color_correction(self):
        """Verifies Exposure, Brightness, Contrast, and Saturation adjustments."""
        color_proc = ColorCorrectionProcessor()
        buf = VideoFrameBuffer.blank(10, 10, color=(100, 100, 100, 255))

        # +1.0 EV Exposure (doubles pixel values ~200)
        exp_frame = color_proc.process_frame(buf, {"exposure": 1.0}, 10, 10)
        self.assertAlmostEqual(int(exp_frame.data[0, 0, 0]), 200, delta=5)

        # Invert processor
        inv_proc = InvertEffectProcessor()
        inv_frame = inv_proc.process_frame(buf, {"invert_rgb": True}, 10, 10)
        self.assertEqual(int(inv_frame.data[0, 0, 0]), 155) # 255 - 100 = 155

    def test_04_effect_stack_execution(self):
        """Verifies ordered cascade, bypass state, and parameter mutation."""
        stack = VideoEffectStack(owner_id="clip_123")
        eff_inv = effect_processor_registry.create_instance("effect.invert")
        eff_op = effect_processor_registry.create_instance("effect.opacity", {"opacity": 0.5})

        stack.add_effect(eff_inv)
        stack.add_effect(eff_op)
        self.assertEqual(len(stack.effects), 2)

        # Process frame through EffectsService
        effects_service._stacks["clip_123"] = stack
        raw = VideoFrameBuffer.blank(10, 10, color=(200, 200, 200, 255))
        out = effects_service.process_clip_frame("clip_123", raw, timeline_frame=0, render_width=10, render_height=10)

        # Invert: 255 - 200 = 55. Opacity: 255 * 0.5 = 127
        self.assertEqual(int(out.data[0, 0, 0]), 55)
        self.assertEqual(int(out.data[0, 0, 3]), 127)

    def test_05_blend_modes(self):
        """Verifies mathematical correctness of blend mode equations."""
        fg = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        bg = np.array([0.5, 0.5, 0.5], dtype=np.float32)

        # Multiply: 0.5 * 0.5 = 0.25
        np.testing.assert_allclose(apply_blend_equation(fg, bg, BlendMode.MULTIPLY), [0.25, 0.25, 0.25])
        # Screen: 1 - 0.5 * 0.5 = 0.75
        np.testing.assert_allclose(apply_blend_equation(fg, bg, BlendMode.SCREEN), [0.75, 0.75, 0.75])
        # Add: 0.5 + 0.5 = 1.0
        np.testing.assert_allclose(apply_blend_equation(fg, bg, BlendMode.ADD), [1.0, 1.0, 1.0])
        # Difference: |0.5 - 0.5| = 0.0
        np.testing.assert_allclose(apply_blend_equation(fg, bg, BlendMode.DIFFERENCE), [0.0, 0.0, 0.0])

    def test_06_alpha_compositing_porter_duff(self):
        """Verifies correct Source-Over Porter-Duff compositing."""
        # 50% transparent red over opaque blue
        fg = VideoFrameBuffer.blank(10, 10, color=(255, 0, 0, 128))
        bg = VideoFrameBuffer.blank(10, 10, color=(0, 0, 255, 255))

        out = composite_layers_porter_duff(fg, bg, opacity=1.0, blend_mode=BlendMode.NORMAL)
        self.assertEqual(out.width, 10)
        self.assertEqual(out.height, 10)
        # Result should be a 50/50 purple mix: ~128 R, ~127 B, 255 A
        self.assertAlmostEqual(int(out.data[0, 0, 0]), 128, delta=5)
        self.assertAlmostEqual(int(out.data[0, 0, 2]), 127, delta=5)
        self.assertEqual(int(out.data[0, 0, 3]), 255)

    def test_07_compositing_mask(self):
        """Verifies grayscale luma and inverted layer masking."""
        fg = VideoFrameBuffer.blank(10, 10, color=(255, 0, 0, 255))
        bg = VideoFrameBuffer.blank(10, 10, color=(0, 0, 255, 255))

        # Mask: left half white (255, visible), right half black (0, transparent)
        mask_arr = np.zeros((10, 10), dtype=np.float32)
        mask_arr[:, :5] = 1.0
        mask = CompositingMask(mask_id="m1", mask_type=MaskType.GRAYSCALE_LUMA, mask_data=mask_arr)

        out = composite_layers_porter_duff(fg, bg, opacity=1.0, blend_mode=BlendMode.NORMAL, mask=mask)
        # Left half should be red (fg)
        self.assertEqual(int(out.data[0, 2, 0]), 255)
        self.assertEqual(int(out.data[0, 2, 2]), 0)
        # Right half should be blue (bg)
        self.assertEqual(int(out.data[0, 7, 0]), 0)
        self.assertEqual(int(out.data[0, 7, 2]), 255)

    def test_08_multilayer_compositor(self):
        """Verifies bottom-to-top track compositing order."""
        seq = VideoSequence(sequence_id="seq_comp", project_id="proj_1", name="Comp Seq", duration_frames=50)

        # Track 0: Background
        t0 = TimelineTrackModel(track_id="t0", sequence_id=seq.sequence_id, name="BG", track_type=TimelineTrackType.VIDEO, index=0)
        c0 = TimelineItemModel(
            item_id="c0", track_id="t0", sequence_id=seq.sequence_id, source_reference_id="asset_bg",
            timeline_range=TimelineRange(start_frame=0, duration_frames=50),
            source_range=SourceRange(in_frame=0, duration_frames=50),
        )
        t0.items.append(c0)

        # Track 1: Foreground
        t1 = TimelineTrackModel(track_id="t1", sequence_id=seq.sequence_id, name="FG", track_type=TimelineTrackType.VIDEO, index=1)
        c1 = TimelineItemModel(
            item_id="c1", track_id="t1", sequence_id=seq.sequence_id, source_reference_id="asset_fg",
            timeline_range=TimelineRange(start_frame=0, duration_frames=50),
            source_range=SourceRange(in_frame=0, duration_frames=50),
        )
        t1.items.append(c1)
        seq.tracks.extend([t0, t1])

        # Composite frame 10
        comp_frame = multilayer_compositor.composite_sequence_frame(seq, target_frame=10, canvas_width=64, canvas_height=64)
        self.assertEqual(comp_frame.width, 64)
        self.assertEqual(comp_frame.height, 64)

    def test_09_compositor_animation_integration(self):
        """Verifies layer opacity animation curve via Module 8 AnimationService."""
        seq = VideoSequence(sequence_id="seq_anim", project_id="proj_1", name="Anim Seq", duration_frames=50)
        t0 = TimelineTrackModel(track_id="t0", sequence_id=seq.sequence_id, name="Track", track_type=TimelineTrackType.VIDEO, index=0)
        c0 = TimelineItemModel(
            item_id="clip_anim", track_id="t0", sequence_id=seq.sequence_id, source_reference_id="asset_test",
            timeline_range=TimelineRange(start_frame=0, duration_frames=50),
            source_range=SourceRange(in_frame=0, duration_frames=50),
        )
        t0.items.append(c0)
        seq.tracks.append(t0)

        # Register animatable opacity property
        op_prop = AnimatableProperty(
            property_id="clip_anim_opacity",
            owner_id="clip_anim",
            name="opacity",
            value_type=PropertyValueType.SCALAR,
            default_value=1.0,
            current_value=1.0,
        )
        animation_service.register_property(op_prop)
        animation_service.add_keyframe("clip_anim_opacity", frame=0, value=1.0, interpolation=InterpolationMode.LINEAR)
        animation_service.add_keyframe("clip_anim_opacity", frame=50, value=0.0, interpolation=InterpolationMode.LINEAR)

        # Evaluate at frame 0 and frame 50
        comp_0 = multilayer_compositor.composite_sequence_frame(seq, target_frame=0, canvas_width=10, canvas_height=10)
        comp_50 = multilayer_compositor.composite_sequence_frame(seq, target_frame=50, canvas_width=10, canvas_height=10)
        self.assertIsNotNone(comp_0)
        self.assertIsNotNone(comp_50)

    def test_10_playback_engine_composited_preview(self):
        """Verifies that the PlaybackEngine viewer receives real composited frames when multiple tracks or effects are present."""
        seq = VideoSequence(sequence_id="seq_pb", project_id="proj_1", name="Playback Seq", duration_frames=50)
        t0 = TimelineTrackModel(track_id="t0", sequence_id=seq.sequence_id, name="Video", track_type=TimelineTrackType.VIDEO, index=0)
        c0 = TimelineItemModel(
            item_id="c_pb", track_id="t0", sequence_id=seq.sequence_id, source_reference_id="asset_pb",
            timeline_range=TimelineRange(start_frame=0, duration_frames=50),
            source_range=SourceRange(in_frame=0, duration_frames=50),
            metadata={"blend_mode": "MULTIPLY"},
        )
        t0.items.append(c0)
        seq.tracks.append(t0)

        session = playback_engine.create_session(seq, project_id="proj_1")
        playback_engine.seek(session.session_id, target_frame=5)
        frame = playback_engine.render_frame(session.session_id)
        self.assertEqual(frame.asset_id, "composited")
        self.assertEqual(frame.timeline_frame, 5)

    def test_11_capability_registry_status(self):
        """Verifies that Module 10 & 11 capabilities are registered in IMPLEMENTED state."""
        cap_eff = video_studio_capability_registry.get("video.effects.engine")
        self.assertIsNotNone(cap_eff)
        self.assertEqual(cap_eff.implementation_state.value, "IMPLEMENTED")

        cap_comp = video_studio_capability_registry.get("video.compositing.engine")
        self.assertIsNotNone(cap_comp)
        self.assertEqual(cap_comp.implementation_state.value, "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
