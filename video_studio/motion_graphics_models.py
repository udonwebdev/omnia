"""OMNIA Video Studio — Motion Graphics & Animated Typography Models (Module 14).

Defines canonical domain models:
- GraphicLayerType: TEXT, RECTANGLE, ELLIPSE, LINE, IMAGE, GROUP
- GraphicTransform: 2D translation, scale (x, y), rotation (degrees), anchor/pivot (x, y)
- MotionGraphicLayer: Individual vector/text/shape layer with styling, stroke, fill, animatable properties
- MotionGraphicComposition: Versioned document containing layers, dimensions, duration, hierarchy
- TypographyPreset: Reusable text reveal presets (FADE, SLIDE, SCALE, TRACKING, WORD_STAGGER)
- MotionGraphicTemplate: Pre-packaged editable title/lower-third template
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set
import time
import uuid

class GraphicLayerType(str, Enum):
    TEXT = "TEXT"
    RECTANGLE = "RECTANGLE"
    ELLIPSE = "ELLIPSE"
    LINE = "LINE"
    IMAGE = "IMAGE"
    GROUP = "GROUP"

class TextAlignment(str, Enum):
    LEFT = "LEFT"
    CENTER = "CENTER"
    RIGHT = "RIGHT"

class TextTransformCase(str, Enum):
    NONE = "NONE"
    UPPERCASE = "UPPERCASE"
    LOWERCASE = "LOWERCASE"
    CAPITALIZE = "CAPITALIZE"

class TypographyAnimationPreset(str, Enum):
    NONE = "NONE"
    FADE_IN = "FADE_IN"
    FADE_OUT = "FADE_OUT"
    SLIDE_IN_LEFT = "SLIDE_IN_LEFT"
    SLIDE_IN_BOTTOM = "SLIDE_IN_BOTTOM"
    SCALE_POP = "SCALE_POP"
    TRACKING_EXPAND = "TRACKING_EXPAND"
    WORD_STAGGER = "WORD_STAGGER"

@dataclass
class GraphicTransform:
    """Spatial 2D transformation for a motion graphics layer."""
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_degrees: float = 0.0
    anchor_x: float = 0.5   # Normalized 0.0 - 1.0 pivot
    anchor_y: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "rotation_degrees": self.rotation_degrees,
            "anchor_x": self.anchor_x,
            "anchor_y": self.anchor_y,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GraphicTransform":
        return cls(
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            scale_x=float(d.get("scale_x", 1.0)),
            scale_y=float(d.get("scale_y", 1.0)),
            rotation_degrees=float(d.get("rotation_degrees", 0.0)),
            anchor_x=float(d.get("anchor_x", 0.5)),
            anchor_y=float(d.get("anchor_y", 0.5)),
        )

@dataclass
class MotionGraphicLayer:
    """Individual vector/text/shape layer placed within a motion graphics composition."""
    layer_id: str
    name: str
    layer_type: GraphicLayerType
    parent_id: Optional[str] = None
    stack_order: int = 0
    is_visible: bool = True
    is_locked: bool = False
    opacity: float = 1.0
    transform: GraphicTransform = field(default_factory=GraphicTransform)

    # Text-specific properties
    text_content: str = ""
    font_family: str = "Arial"
    font_size: int = 48
    font_weight: str = "bold"
    is_italic: bool = False
    text_alignment: TextAlignment = TextAlignment.CENTER
    text_case: TextTransformCase = TextTransformCase.NONE
    letter_spacing: int = 0
    line_spacing: int = 6
    max_text_width: int = 1400

    # Shape/Geometry properties (Width/Height in canvas pixels)
    width: float = 200.0
    height: float = 100.0
    corner_radius: float = 0.0
    line_end_x: float = 100.0
    line_end_y: float = 100.0

    # Styling colors
    fill_color: str = "#FFFFFF"         # Hex RGB
    fill_alpha: float = 1.0            # 0.0 to 1.0
    stroke_color: str = "#000000"
    stroke_alpha: float = 0.0
    stroke_width: int = 0

    # Image Layer properties
    source_asset_id: Optional[str] = None

    # Animation & Presets
    animation_preset: TypographyAnimationPreset = TypographyAnimationPreset.NONE
    preset_duration_frames: int = 24

    # Module 8 Animated Property references (property_name -> animatable_property_id)
    animated_property_ids: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "name": self.name,
            "layer_type": self.layer_type.value,
            "parent_id": self.parent_id,
            "stack_order": self.stack_order,
            "is_visible": self.is_visible,
            "is_locked": self.is_locked,
            "opacity": self.opacity,
            "transform": self.transform.to_dict(),
            "text_content": self.text_content,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "font_weight": self.font_weight,
            "is_italic": self.is_italic,
            "text_alignment": self.text_alignment.value,
            "text_case": self.text_case.value,
            "letter_spacing": self.letter_spacing,
            "line_spacing": self.line_spacing,
            "max_text_width": self.max_text_width,
            "width": self.width,
            "height": self.height,
            "corner_radius": self.corner_radius,
            "line_end_x": self.line_end_x,
            "line_end_y": self.line_end_y,
            "fill_color": self.fill_color,
            "fill_alpha": self.fill_alpha,
            "stroke_color": self.stroke_color,
            "stroke_alpha": self.stroke_alpha,
            "stroke_width": self.stroke_width,
            "source_asset_id": self.source_asset_id,
            "animation_preset": self.animation_preset.value,
            "preset_duration_frames": self.preset_duration_frames,
            "animated_property_ids": self.animated_property_ids,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MotionGraphicLayer":
        l_type = GraphicLayerType(d["layer_type"])
        t_align = TextAlignment(d.get("text_alignment", TextAlignment.CENTER.value))
        t_case = TextTransformCase(d.get("text_case", TextTransformCase.NONE.value))
        preset = TypographyAnimationPreset(d.get("animation_preset", TypographyAnimationPreset.NONE.value))
        tf = GraphicTransform.from_dict(d.get("transform", {}))
        return cls(
            layer_id=d["layer_id"],
            name=d.get("name", "Layer"),
            layer_type=l_type,
            parent_id=d.get("parent_id"),
            stack_order=d.get("stack_order", 0),
            is_visible=d.get("is_visible", True),
            is_locked=d.get("is_locked", False),
            opacity=float(d.get("opacity", 1.0)),
            transform=tf,
            text_content=d.get("text_content", ""),
            font_family=d.get("font_family", "Arial"),
            font_size=d.get("font_size", 48),
            font_weight=d.get("font_weight", "bold"),
            is_italic=d.get("is_italic", False),
            text_alignment=t_align,
            text_case=t_case,
            letter_spacing=d.get("letter_spacing", 0),
            line_spacing=d.get("line_spacing", 6),
            max_text_width=d.get("max_text_width", 1400),
            width=float(d.get("width", 200.0)),
            height=float(d.get("height", 100.0)),
            corner_radius=float(d.get("corner_radius", 0.0)),
            line_end_x=float(d.get("line_end_x", 100.0)),
            line_end_y=float(d.get("line_end_y", 100.0)),
            fill_color=d.get("fill_color", "#FFFFFF"),
            fill_alpha=float(d.get("fill_alpha", 1.0)),
            stroke_color=d.get("stroke_color", "#000000"),
            stroke_alpha=float(d.get("stroke_alpha", 0.0)),
            stroke_width=d.get("stroke_width", 0),
            source_asset_id=d.get("source_asset_id"),
            animation_preset=preset,
            preset_duration_frames=d.get("preset_duration_frames", 24),
            animated_property_ids=d.get("animated_property_ids", {}),
            metadata=d.get("metadata", {}),
        )

@dataclass
class MotionGraphicComposition:
    """Canonical model for a complete motion graphics document."""
    composition_id: str
    project_id: str
    name: str = "Title Composition"
    width: int = 1920
    height: int = 1080
    frame_rate: float = 24.0
    duration_frames: int = 120
    sequence_id: Optional[str] = None
    timeline_track_id: Optional[str] = None
    timeline_start_frame: int = 0
    layers: List[MotionGraphicLayer] = field(default_factory=list)
    version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def sort_layers(self) -> None:
        """Sorts layers from bottom to top based on stack_order."""
        self.layers.sort(key=lambda l: l.stack_order)

    def get_layer(self, layer_id: str) -> Optional[MotionGraphicLayer]:
        return next((l for l in self.layers if l.layer_id == layer_id), None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "project_id": self.project_id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "frame_rate": self.frame_rate,
            "duration_frames": self.duration_frames,
            "sequence_id": self.sequence_id,
            "timeline_track_id": self.timeline_track_id,
            "timeline_start_frame": self.timeline_start_frame,
            "layers_count": len(self.layers),
            "layers": [l.to_dict() for l in self.layers],
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MotionGraphicComposition":
        layers = [MotionGraphicLayer.from_dict(ld) for ld in d.get("layers", [])]
        comp = cls(
            composition_id=d["composition_id"],
            project_id=d["project_id"],
            name=d.get("name", "Title Composition"),
            width=d.get("width", 1920),
            height=d.get("height", 1080),
            frame_rate=float(d.get("frame_rate", 24.0)),
            duration_frames=d.get("duration_frames", 120),
            sequence_id=d.get("sequence_id"),
            timeline_track_id=d.get("timeline_track_id"),
            timeline_start_frame=d.get("timeline_start_frame", 0),
            layers=layers,
            version=d.get("version", "1.0.0"),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
        )
        comp.sort_layers()
        return comp

@dataclass
class MotionGraphicTemplate:
    """Pre-packaged editable title or motion graphics template."""
    template_id: str
    name: str
    category: str = "Titles"  # Titles, Lower Thirds, End Cards, Callouts
    description: str = ""
    default_duration_frames: int = 120
    composition_blueprint: Dict[str, Any] = field(default_factory=dict)
    placeholder_keys: List[str] = field(default_factory=list)  # Keys like "TITLE_TEXT", "SUBTITLE_TEXT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "default_duration_frames": self.default_duration_frames,
            "placeholder_keys": self.placeholder_keys,
            "composition_blueprint": self.composition_blueprint,
        }
