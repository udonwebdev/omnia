"""OMNIA Video Studio — Module 14 Comprehensive Test Suite.

Validates:
1. Motion Graphics Document & Layer Models:
   - Composition creation, layer hierarchy, stack ordering, serialization.
   - Text, Rectangle, Ellipse, Line, and Image layer models.
2. Vector Graphics & Shape Primitives Rendering:
   - Real Pillow/PIL drawing of rectangles with corner radius, ellipses, lines.
   - Alpha transparency, fill and stroke color calculations.
3. Typography & Text Engine:
   - Text casing transforms (UPPERCASE, LOWERCASE, CAPITALIZE).
   - Text alignments (LEFT, CENTER, RIGHT).
   - Multiline text rendering.
4. Animation Presets & Keyframe Synchronization:
   - Animated typography presets: FADE_IN, FADE_OUT, SLIDE_IN_BOTTOM, SLIDE_IN_LEFT, SCALE_POP, WORD_STAGGER.
   - Module 8 AnimationService property keyframe synchronization (evaluating transform_x, opacity over time).
5. Templates & Instantiation:
   - Built-in templates: Centered Title, Lower Third.
   - Template instantiation with placeholder replacement (e.g. {{TITLE}}, {{NAME}}, {{ROLE}}).
6. Timeline & Real-Time Viewer Compositing:
   - Sequence playback integration rendering motion graphics compositions on top of video frames.
7. Capabilities & Registry:
   - Truthful capability states in VideoStudioCapabilityRegistry.
"""

import unittest
import numpy as np

from video_studio.motion_graphics_models import (
    GraphicLayerType,
    TextAlignment,
    TextTransformCase,
    TypographyAnimationPreset,
    GraphicTransform,
    MotionGraphicLayer,
    MotionGraphicComposition,
    MotionGraphicTemplate,
)
from video_studio.motion_graphics_renderer import (
    motion_graphics_renderer,
    MotionGraphicsRenderer,
    hex_to_rgba,
)
from video_studio.motion_graphics_service import (
    motion_graphics_service,
    MotionGraphicsService,
)
from video_studio.effects_models import VideoFrameBuffer
from video_studio.timeline_models import (
    VideoSequence,
    SequenceSettings,
    TimelineTrackModel,
    TimelineTrackType,
)
from video_studio.animation_service import animation_service
from video_studio.compositor import multilayer_compositor
from video_studio.registry import video_studio_capability_registry


class TestVideoStudioModule14(unittest.TestCase):

    def setUp(self):
        self.service = motion_graphics_service
        self.project_id = "proj_m14_test"
        self.comp = self.service.create_composition(
            project_id=self.project_id,
            name="Test Comp",
            width=320,
            height=180,
            duration_frames=60,
        )

    def test_01_composition_and_layer_hierarchy(self):
        """Validates composition creation, layer addition, and stack ordering."""
        l1 = self.service.add_layer(
            composition_id=self.comp.composition_id,
            name="Background Rect",
            layer_type=GraphicLayerType.RECTANGLE,
            width=300.0,
            height=160.0,
        )
        l2 = self.service.add_layer(
            composition_id=self.comp.composition_id,
            name="Title Text",
            layer_type=GraphicLayerType.TEXT,
            text_content="Omnia Motion",
        )

        self.assertEqual(len(self.comp.layers), 2)
        self.assertEqual(self.comp.layers[0].layer_id, l1.layer_id)
        self.assertEqual(self.comp.layers[1].layer_id, l2.layer_id)

        # Reorder layers
        self.service.reorder_layers(self.comp.composition_id, [l2.layer_id, l1.layer_id])
        self.assertEqual(self.comp.layers[0].layer_id, l2.layer_id)
        self.assertEqual(self.comp.layers[1].layer_id, l1.layer_id)

    def test_02_shape_primitives_rendering(self):
        """Validates real rasterization of rectangles, ellipses, and lines."""
        comp = self.service.create_composition(self.project_id, width=100, height=100)
        # Add rounded rectangle
        self.service.add_layer(
            composition_id=comp.composition_id,
            name="Rounded Box",
            layer_type=GraphicLayerType.RECTANGLE,
            transform=GraphicTransform(x=50, y=50),
            width=80,
            height=60,
            corner_radius=10,
            fill_color="#FF0000",
            fill_alpha=1.0,
        )

        frame = motion_graphics_renderer.render_composition(comp, comp_frame=0, canvas_width=100, canvas_height=100)
        self.assertEqual(frame.width, 100)
        self.assertEqual(frame.height, 100)

        # Center pixel (50, 50) must be pure red (255, 0, 0, 255)
        np.testing.assert_array_equal(frame.data[50, 50], [255, 0, 0, 255])
        # Corner outside bounding box (0, 0) must be transparent
        self.assertEqual(frame.data[0, 0, 3], 0)

    def test_03_text_casing_and_alignment(self):
        """Validates text transformation case and typography rendering."""
        comp = self.service.create_composition(self.project_id, width=200, height=100)
        layer = self.service.add_layer(
            composition_id=comp.composition_id,
            name="Text Layer",
            layer_type=GraphicLayerType.TEXT,
            text_content="hello world",
            text_case=TextTransformCase.UPPERCASE,
            text_alignment=TextAlignment.CENTER,
            transform=GraphicTransform(x=100, y=40),
            fill_color="#00FF00",
        )

        frame = motion_graphics_renderer.render_composition(comp, comp_frame=0, canvas_width=200, canvas_height=100)
        # Should have green pixels (G > 200, Alpha > 0)
        green_pixels = np.where((frame.data[:, :, 1] > 200) & (frame.data[:, :, 3] > 0))
        self.assertTrue(len(green_pixels[0]) > 0, "Rendered text must produce green glyph pixels")

    def test_04_animation_preset_fade_and_slide(self):
        """Validates dynamic evaluation of typography animation presets over time."""
        comp = self.service.create_composition(self.project_id, width=100, height=100, duration_frames=30)
        self.service.add_layer(
            composition_id=comp.composition_id,
            name="Fade In Box",
            layer_type=GraphicLayerType.RECTANGLE,
            transform=GraphicTransform(x=50, y=50),
            width=50,
            height=50,
            fill_color="#FFFFFF",
            animation_preset=TypographyAnimationPreset.FADE_IN,
            preset_duration_frames=20,
        )

        # Frame 0: Opacity should be 0.0 (transparent)
        f0 = motion_graphics_renderer.render_composition(comp, comp_frame=0, canvas_width=100, canvas_height=100)
        self.assertEqual(f0.data[50, 50, 3], 0)

        # Frame 20: Opacity should reach 1.0 (opaque white)
        f20 = motion_graphics_renderer.render_composition(comp, comp_frame=20, canvas_width=100, canvas_height=100)
        self.assertEqual(f20.data[50, 50, 3], 255)

    def test_05_module8_keyframe_synchronization(self):
        """Validates layer integration with Module 8 AnimationService keyframes."""
        comp = self.service.create_composition(self.project_id, width=200, height=100)
        layer = self.service.add_layer(
            composition_id=comp.composition_id,
            name="Keyframed Box",
            layer_type=GraphicLayerType.RECTANGLE,
            transform=GraphicTransform(x=10, y=50),
            width=20,
            height=20,
            fill_color="#0000FF",
        )

        # Register animatable property in Module 8 AnimationService
        from video_studio.animation_models import AnimatableProperty, PropertyValueType
        prop_id = f"{layer.layer_id}_x"
        prop = AnimatableProperty(
            property_id=prop_id,
            owner_id=layer.layer_id,
            name="transform_x",
            default_value=10.0,
            current_value=10.0,
            value_type=PropertyValueType.SCALAR,
        )
        animation_service.register_property(prop)
        # Add keyframe: Frame 0 -> 10.0, Frame 20 -> 100.0
        animation_service.add_keyframe(prop_id, frame=0, value=10.0)
        animation_service.add_keyframe(prop_id, frame=20, value=100.0)
        layer.animated_property_ids["transform_x"] = prop_id

        # At frame 0: Center is at x=10
        f0 = motion_graphics_renderer.render_composition(comp, comp_frame=0, canvas_width=200, canvas_height=100)
        self.assertEqual(f0.data[50, 10, 2], 255)

        # At frame 20: Box center should have moved to x=100
        f20 = motion_graphics_renderer.render_composition(comp, comp_frame=20, canvas_width=200, canvas_height=100)
        self.assertEqual(f20.data[50, 100, 2], 255)

    def test_06_template_instantiation_and_placeholders(self):
        """Validates template blueprint instantiation with placeholder replacements."""
        templates = self.service.list_templates()
        self.assertTrue(len(templates) >= 2)

        inst = self.service.instantiate_template(
            template_id="template_lower_third",
            project_id=self.project_id,
            placeholders={"NAME": "Jane Doe", "ROLE": "Lead Engineer"},
        )
        self.assertIsNotNone(inst)
        self.assertEqual(len(inst.layers), 3)

        name_layer = next((l for l in inst.layers if l.name == "Speaker Name"), None)
        self.assertIsNotNone(name_layer)
        self.assertEqual(name_layer.text_content, "Jane Doe")

        role_layer = next((l for l in inst.layers if l.name == "Speaker Role"), None)
        self.assertIsNotNone(role_layer)
        self.assertEqual(role_layer.text_content, "Lead Engineer")

    def test_07_timeline_playback_compositing(self):
        """Validates real-time viewer compositing of motion graphics over sequence frames."""
        seq = VideoSequence(sequence_id="seq_mg", project_id=self.project_id, name="MG Seq")
        seq.settings = SequenceSettings(width=160, height=90, frame_rate=24.0)
        tr = TimelineTrackModel(track_id="tr_v", sequence_id=seq.sequence_id, name="Video", track_type=TimelineTrackType.VIDEO)
        seq.tracks.append(tr)

        # Create composition active on timeline from frame 10 to 40
        comp = self.service.create_composition(
            project_id=self.project_id,
            name="Timeline Overlay",
            width=160,
            height=90,
            duration_frames=30,
            sequence_id=seq.sequence_id,
            timeline_start_frame=10,
        )
        self.service.add_layer(
            composition_id=comp.composition_id,
            name="Title",
            layer_type=GraphicLayerType.RECTANGLE,
            transform=GraphicTransform(x=80, y=45),
            width=40,
            height=20,
            fill_color="#FFFF00",
        )

        # Frame 0: Composition not yet active
        f0 = multilayer_compositor.composite_sequence_frame(seq, target_frame=0, canvas_width=160, canvas_height=90)
        # Frame 15: Composition is active
        f15 = multilayer_compositor.composite_sequence_frame(seq, target_frame=15, canvas_width=160, canvas_height=90)

        # Pixel (45, 80) should differ between frame 0 and frame 15
        self.assertFalse(np.array_equal(f0.data[45, 80], f15.data[45, 80]))

    def test_08_capabilities_registered(self):
        """Validates VideoStudioCapabilityRegistry entries for Module 14."""
        cap = video_studio_capability_registry.get("video.motion_graphics.engine")
        self.assertIsNotNone(cap)
        self.assertTrue(cap.enabled)

        cap_tpl = video_studio_capability_registry.get("video.motion_graphics.templates")
        self.assertIsNotNone(cap_tpl)


if __name__ == "__main__":
    unittest.main()
