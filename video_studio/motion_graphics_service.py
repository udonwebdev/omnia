"""OMNIA Video Studio — Motion Graphics & Title Service (Module 14).

Coordinates:
- Creation, persistence, layer management, and hierarchy for MotionGraphicComposition
- Reusable motion graphics templates (Minimal Title, Centered Title, Lower Third, End Card)
- Template instantiation with placeholder replacements
- Sequence timeline placement and tracking
- Capability registration for Module 14 in VideoStudioCapabilityRegistry
"""

from typing import Dict, Any, List, Optional, Tuple
import time
import uuid
import logging

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
)
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("Omnia.VideoStudio.MotionGraphicsService")

class MotionGraphicsService:
    """Manages motion graphics compositions, templates, and timeline placements."""

    def __init__(self, renderer: Optional[MotionGraphicsRenderer] = None):
        self.renderer = renderer or motion_graphics_renderer
        # Storage: comp_id -> MotionGraphicComposition
        self._compositions: Dict[str, MotionGraphicComposition] = {}
        # Templates: template_id -> MotionGraphicTemplate
        self._templates: Dict[str, MotionGraphicTemplate] = {}

        self._init_builtin_templates()
        self._register_capabilities()

    def _register_capabilities(self) -> None:
        caps = [
            ("video.motion_graphics.engine", "Motion Graphics Engine", "Vector element, text, and shape layer engine", ImplementationState.IMPLEMENTED),
            ("video.motion_graphics.typography", "Animated Typography", "Font styling, tracking, line wrapping, and presets", ImplementationState.IMPLEMENTED),
            ("video.motion_graphics.primitives", "Graphic Primitives", "Rectangles with rounded corners, ellipses, and lines", ImplementationState.IMPLEMENTED),
            ("video.motion_graphics.templates", "Motion Graphics Templates", "Reusable lower thirds, titles, and end cards", ImplementationState.IMPLEMENTED),
            ("video.motion_graphics.keyframe_sync", "Module 8 Keyframe Sync", "Spatial transform and opacity keyframe automation", ImplementationState.IMPLEMENTED),
            ("video.motion_graphics.preview", "Live Viewer Graphics Rendering", "Real-time viewer compositing of active compositions", ImplementationState.IMPLEMENTED),
        ]

        for cap_id, name, desc, state in caps:
            try:
                descriptor = VideoStudioCapabilityDescriptor(
                    id=cap_id,
                    name=name,
                    category=VideoStudioCategory.EDITING,
                    description=desc,
                    implementation_state=state,
                    enabled=True,
                )
                video_studio_capability_registry.register(descriptor)
            except Exception as e:
                logger.debug(f"Capability '{cap_id}' registration note: {e}")

    def _init_builtin_templates(self) -> None:
        """Sets up editable built-in motion graphics templates."""
        # 1. Centered Title
        t_center = MotionGraphicTemplate(
            template_id="template_centered_title",
            name="Centered Modern Title",
            category="Titles",
            description="Clean, centered title with animated slide and subtitle.",
            default_duration_frames=72,
            placeholder_keys=["TITLE", "SUBTITLE"],
            composition_blueprint={
                "name": "Centered Modern Title",
                "width": 1920,
                "height": 1080,
                "duration_frames": 72,
                "layers": [
                    {
                        "name": "Main Title",
                        "layer_type": "TEXT",
                        "text_content": "{{TITLE}}",
                        "font_size": 72,
                        "font_weight": "bold",
                        "fill_color": "#FFFFFF",
                        "transform": {"x": 960.0, "y": 480.0},
                        "animation_preset": "SLIDE_IN_BOTTOM",
                        "preset_duration_frames": 24,
                    },
                    {
                        "name": "Subtitle",
                        "layer_type": "TEXT",
                        "text_content": "{{SUBTITLE}}",
                        "font_size": 32,
                        "font_weight": "normal",
                        "fill_color": "#CCCCCC",
                        "transform": {"x": 960.0, "y": 570.0},
                        "animation_preset": "FADE_IN",
                        "preset_duration_frames": 36,
                    },
                ],
            },
        )

        # 2. Lower Third
        t_lower_third = MotionGraphicTemplate(
            template_id="template_lower_third",
            name="News Lower Third",
            category="Lower Thirds",
            description="Modern two-tier broadcast lower third with background accent box.",
            default_duration_frames=120,
            placeholder_keys=["NAME", "ROLE"],
            composition_blueprint={
                "name": "News Lower Third",
                "width": 1920,
                "height": 1080,
                "duration_frames": 120,
                "layers": [
                    {
                        "name": "Background Box",
                        "layer_type": "RECTANGLE",
                        "width": 600.0,
                        "height": 110.0,
                        "corner_radius": 8.0,
                        "fill_color": "#111827",
                        "fill_alpha": 0.85,
                        "transform": {"x": 420.0, "y": 920.0, "anchor_x": 0.5, "anchor_y": 0.5},
                        "animation_preset": "SLIDE_IN_LEFT",
                        "preset_duration_frames": 18,
                    },
                    {
                        "name": "Speaker Name",
                        "layer_type": "TEXT",
                        "text_content": "{{NAME}}",
                        "font_size": 36,
                        "font_weight": "bold",
                        "fill_color": "#38BDF8",
                        "text_alignment": "LEFT",
                        "transform": {"x": 150.0, "y": 880.0},
                        "animation_preset": "FADE_IN",
                        "preset_duration_frames": 24,
                    },
                    {
                        "name": "Speaker Role",
                        "layer_type": "TEXT",
                        "text_content": "{{ROLE}}",
                        "font_size": 22,
                        "font_weight": "normal",
                        "fill_color": "#E2E8F0",
                        "text_alignment": "LEFT",
                        "transform": {"x": 150.0, "y": 925.0},
                        "animation_preset": "FADE_IN",
                        "preset_duration_frames": 30,
                    },
                ],
            },
        )

        self._templates[t_center.template_id] = t_center
        self._templates[t_lower_third.template_id] = t_lower_third

    # =========================================================================
    # Composition Management
    # =========================================================================

    def create_composition(
        self,
        project_id: str,
        name: str = "New Title",
        width: int = 1920,
        height: int = 1080,
        duration_frames: int = 120,
        sequence_id: Optional[str] = None,
        timeline_track_id: Optional[str] = None,
        timeline_start_frame: int = 0,
    ) -> MotionGraphicComposition:
        comp_id = f"comp_{uuid.uuid4().hex[:10]}"
        comp = MotionGraphicComposition(
            composition_id=comp_id,
            project_id=project_id,
            name=name,
            width=width,
            height=height,
            duration_frames=duration_frames,
            sequence_id=sequence_id,
            timeline_track_id=timeline_track_id,
            timeline_start_frame=timeline_start_frame,
        )
        self._compositions[comp_id] = comp
        return comp

    def get_composition(self, composition_id: str) -> Optional[MotionGraphicComposition]:
        return self._compositions.get(composition_id)

    def delete_composition(self, composition_id: str) -> bool:
        return self._compositions.pop(composition_id, None) is not None

    def list_compositions_for_project(self, project_id: str) -> List[MotionGraphicComposition]:
        return [c for c in self._compositions.values() if c.project_id == project_id]

    def list_compositions_for_sequence(self, sequence_id: str) -> List[MotionGraphicComposition]:
        return [c for c in self._compositions.values() if c.sequence_id == sequence_id]

    # =========================================================================
    # Layer Operations
    # =========================================================================

    def add_layer(
        self,
        composition_id: str,
        name: str,
        layer_type: GraphicLayerType,
        transform: Optional[GraphicTransform] = None,
        **kwargs,
    ) -> MotionGraphicLayer:
        comp = self.get_composition(composition_id)
        if not comp:
            raise ValueError(f"Composition '{composition_id}' not found.")

        layer_id = f"layer_{uuid.uuid4().hex[:8]}"
        stack_order = len(comp.layers)
        layer = MotionGraphicLayer(
            layer_id=layer_id,
            name=name,
            layer_type=layer_type,
            stack_order=stack_order,
            transform=transform or GraphicTransform(),
            **kwargs,
        )
        comp.layers.append(layer)
        comp.sort_layers()
        comp.updated_at = time.time()
        return layer

    def remove_layer(self, composition_id: str, layer_id: str) -> bool:
        comp = self.get_composition(composition_id)
        if not comp:
            return False
        orig_len = len(comp.layers)
        comp.layers = [l for l in comp.layers if l.layer_id != layer_id]
        if len(comp.layers) < orig_len:
            comp.sort_layers()
            comp.updated_at = time.time()
            return True
        return False

    def reorder_layers(self, composition_id: str, ordered_layer_ids: List[str]) -> bool:
        comp = self.get_composition(composition_id)
        if not comp:
            return False
        for idx, lid in enumerate(ordered_layer_ids):
            layer = comp.get_layer(lid)
            if layer:
                layer.stack_order = idx
        comp.sort_layers()
        comp.updated_at = time.time()
        return True

    # =========================================================================
    # Templates
    # =========================================================================

    def list_templates(self) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._templates.values()]

    def instantiate_template(
        self,
        template_id: str,
        project_id: str,
        placeholders: Dict[str, str],
        sequence_id: Optional[str] = None,
        timeline_start_frame: int = 0,
    ) -> MotionGraphicComposition:
        tpl = self._templates.get(template_id)
        if not tpl:
            raise ValueError(f"Template '{template_id}' not found.")

        bp = tpl.composition_blueprint
        comp = self.create_composition(
            project_id=project_id,
            name=f"{tpl.name} Instance",
            width=bp.get("width", 1920),
            height=bp.get("height", 1080),
            duration_frames=bp.get("duration_frames", 120),
            sequence_id=sequence_id,
            timeline_start_frame=timeline_start_frame,
        )

        for l_data in bp.get("layers", []):
            text_val = l_data.get("text_content", "")
            for k, v in placeholders.items():
                text_val = text_val.replace(f"{{{{{k}}}}}", v)

            tf_data = l_data.get("transform", {})
            tf = GraphicTransform(
                x=tf_data.get("x", 0.0),
                y=tf_data.get("y", 0.0),
                scale_x=tf_data.get("scale_x", 1.0),
                scale_y=tf_data.get("scale_y", 1.0),
                anchor_x=tf_data.get("anchor_x", 0.5),
                anchor_y=tf_data.get("anchor_y", 0.5),
            )

            l_type = GraphicLayerType(l_data["layer_type"])
            preset = TypographyAnimationPreset(l_data.get("animation_preset", "NONE"))

            self.add_layer(
                composition_id=comp.composition_id,
                name=l_data.get("name", "Layer"),
                layer_type=l_type,
                transform=tf,
                text_content=text_val,
                font_size=l_data.get("font_size", 48),
                font_weight=l_data.get("font_weight", "bold"),
                fill_color=l_data.get("fill_color", "#FFFFFF"),
                fill_alpha=l_data.get("fill_alpha", 1.0),
                width=l_data.get("width", 200.0),
                height=l_data.get("height", 100.0),
                corner_radius=l_data.get("corner_radius", 0.0),
                animation_preset=preset,
                preset_duration_frames=l_data.get("preset_duration_frames", 24),
            )

        return comp


# Global singleton
motion_graphics_service = MotionGraphicsService()
