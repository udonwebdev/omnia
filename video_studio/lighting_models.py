"""OMNIA Video Studio — Lighting, Exposure & Relighting Models (Module 29).

Defines serialization models, enums, parameters, and diagnostics for:
- Deterministic global exposure and tonal correction.
- Localized lighting regions (point/radial, directional, polygon/bezier mask) with falloff and blend modes.
- Scene-aware relighting extension interfaces (registered as experimental/unavailable without physical model).
- Keyframe and motion-tracking bindings.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import uuid
import time
import numpy as np


class LightType(str, Enum):
    """Supported light region geometry and distribution types."""
    POINT_RADIAL = "POINT_RADIAL"       # Omnidirectional radial falloff from center (x, y)
    DIRECTIONAL = "DIRECTIONAL"         # Linear gradient across angle or parallel light beam
    POLYGON_MASK = "POLYGON_MASK"       # Parametric or arbitrary polygon mask region
    SPOTLIGHT = "SPOTLIGHT"             # Conical spot with cone angle and penumbra


class LightBlendMode(str, Enum):
    """Compositing and light transfer blend modes."""
    ADD = "ADD"                         # Linear Dodge: I + L (additive light)
    SCREEN = "SCREEN"                   # Soft highlight screen: 1 - (1 - I) * (1 - L)
    SOFT_LIGHT = "SOFT_LIGHT"           # Natural lighting contrast: Photoshop soft-light equation
    OVERLAY = "OVERLAY"                 # High-contrast lighting adjustment
    MULTIPLY = "MULTIPLY"               # Shading / darkening light cast
    COLOR_DODGE = "COLOR_DODGE"         # Intense specular flare/dodge


class RelightingEngineMode(str, Enum):
    """Execution mode for lighting."""
    DETERMINISTIC_2D = "DETERMINISTIC_2D" # Standard 2D image-space exposure, tone, and localized lights
    SCENE_AWARE = "SCENE_AWARE"           # Scene-aware / normal-depth relighting (extension)


@dataclass
class GlobalExposureTonalConfig:
    """Deterministic global exposure, tonal distribution, and white-balance settings."""
    exposure_stops: float = 0.0          # EV stops [-5.0, 5.0], scaled as 2^EV
    brightness: float = 0.0              # Direct offset [-100.0, 100.0]
    contrast: float = 1.0                # Multiplier around pivot [0.1, 3.0]
    contrast_pivot: float = 0.435        # Center pivot for contrast expansion
    highlights: float = 0.0              # Shoulder compression/boost [-100.0, 100.0]
    shadows: float = 0.0                 # Toe compression/boost [-100.0, 100.0]
    whites: float = 0.0                  # Extreme upper tonal range compression/expansion [-100.0, 100.0]
    blacks: float = 0.0                  # Extreme lower tonal range compression/expansion [-100.0, 100.0]
    gamma: float = 1.0                   # Midtone power curve [0.2, 3.0]
    black_point: float = 0.0             # Output black level clamp/remap [0.0, 0.5]
    white_point: float = 1.0             # Output white level clamp/remap [0.5, 1.0]
    temperature: float = 0.0             # Kelvin shift / warmth [-100.0, 100.0]
    tint: float = 0.0                    # Magenta vs Green [-100.0, 100.0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exposure_stops": self.exposure_stops,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "contrast_pivot": self.contrast_pivot,
            "highlights": self.highlights,
            "shadows": self.shadows,
            "whites": self.whites,
            "blacks": self.blacks,
            "gamma": self.gamma,
            "black_point": self.black_point,
            "white_point": self.white_point,
            "temperature": self.temperature,
            "tint": self.tint,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalExposureTonalConfig":
        return cls(
            exposure_stops=float(data.get("exposure_stops", 0.0)),
            brightness=float(data.get("brightness", 0.0)),
            contrast=float(data.get("contrast", 1.0)),
            contrast_pivot=float(data.get("contrast_pivot", 0.435)),
            highlights=float(data.get("highlights", 0.0)),
            shadows=float(data.get("shadows", 0.0)),
            whites=float(data.get("whites", 0.0)),
            blacks=float(data.get("blacks", 0.0)),
            gamma=float(data.get("gamma", 1.0)),
            black_point=float(data.get("black_point", 0.0)),
            white_point=float(data.get("white_point", 1.0)),
            temperature=float(data.get("temperature", 0.0)),
            tint=float(data.get("tint", 0.0)),
        )


@dataclass
class LocalLightRegion:
    """Represents an editable 2D localized light region."""
    region_id: str = field(default_factory=lambda: f"light_{uuid.uuid4().hex[:8]}")
    name: str = "Local Light"
    is_enabled: bool = True
    light_type: LightType = LightType.POINT_RADIAL

    # Spatial coordinates (normalized 0.0 to 1.0 across frame width/height)
    pos_x: float = 0.5                  # Horizontal center (0.0=left, 1.0=right)
    pos_y: float = 0.5                  # Vertical center (0.0=top, 1.0=bottom)
    radius_x: float = 0.25              # Normalized horizontal radius
    radius_y: float = 0.25              # Normalized vertical radius (for elliptical shapes)
    angle_deg: float = 0.0              # Orientation angle in degrees
    feather: float = 0.5                # Falloff softness [0.0 = sharp, 1.0 = smooth bell]

    # For directional or spotlight
    direction_angle_deg: float = 0.0    # Direction of light beam [0 to 360]
    spot_cone_angle_deg: float = 45.0   # Spotlight cone spread

    # Arbitrary polygon points if light_type == POLYGON_MASK: list of [x, y] normalized
    polygon_points: List[List[float]] = field(default_factory=list)

    # Photometric / visual properties
    intensity: float = 1.0              # Intensity multiplier [-3.0 to 3.0, negative darkens/flags]
    color_rgb: Tuple[float, float, float] = (1.0, 1.0, 1.0) # Light color multiplier [0.0, 1.0]
    color_temperature: float = 0.0      # Additional local Kelvin tint [-100.0, 100.0]
    blend_mode: LightBlendMode = LightBlendMode.ADD
    opacity: float = 1.0                # Layer opacity [0.0 to 1.0]
    invert_mask: bool = False           # Invert lighting attenuation

    # Tracking attachment (Module 22 integration)
    tracking_session_id: Optional[str] = None
    track_offset_x: float = 0.0
    track_offset_y: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "name": self.name,
            "is_enabled": self.is_enabled,
            "light_type": self.light_type.value,
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
            "radius_x": self.radius_x,
            "radius_y": self.radius_y,
            "angle_deg": self.angle_deg,
            "feather": self.feather,
            "direction_angle_deg": self.direction_angle_deg,
            "spot_cone_angle_deg": self.spot_cone_angle_deg,
            "polygon_points": self.polygon_points,
            "intensity": self.intensity,
            "color_rgb": list(self.color_rgb),
            "color_temperature": self.color_temperature,
            "blend_mode": self.blend_mode.value,
            "opacity": self.opacity,
            "invert_mask": self.invert_mask,
            "tracking_session_id": self.tracking_session_id,
            "track_offset_x": self.track_offset_x,
            "track_offset_y": self.track_offset_y,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LocalLightRegion":
        c_rgb = data.get("color_rgb", [1.0, 1.0, 1.0])
        return cls(
            region_id=data.get("region_id", f"light_{uuid.uuid4().hex[:8]}"),
            name=data.get("name", "Local Light"),
            is_enabled=data.get("is_enabled", True),
            light_type=LightType(data.get("light_type", LightType.POINT_RADIAL.value)),
            pos_x=float(data.get("pos_x", 0.5)),
            pos_y=float(data.get("pos_y", 0.5)),
            radius_x=float(data.get("radius_x", 0.25)),
            radius_y=float(data.get("radius_y", 0.25)),
            angle_deg=float(data.get("angle_deg", 0.0)),
            feather=float(data.get("feather", 0.5)),
            direction_angle_deg=float(data.get("direction_angle_deg", 0.0)),
            spot_cone_angle_deg=float(data.get("spot_cone_angle_deg", 45.0)),
            polygon_points=data.get("polygon_points", []),
            intensity=float(data.get("intensity", 1.0)),
            color_rgb=(float(c_rgb[0]), float(c_rgb[1]), float(c_rgb[2])),
            color_temperature=float(data.get("color_temperature", 0.0)),
            blend_mode=LightBlendMode(data.get("blend_mode", LightBlendMode.ADD.value)),
            opacity=float(data.get("opacity", 1.0)),
            invert_mask=bool(data.get("invert_mask", False)),
            tracking_session_id=data.get("tracking_session_id"),
            track_offset_x=float(data.get("track_offset_x", 0.0)),
            track_offset_y=float(data.get("track_offset_y", 0.0)),
        )


@dataclass
class SceneAwareRelightingExtension:
    """Extension interface for future AI / surface-normal scene relighting.
    Kept strictly experimental / inactive unless a validated neural/physics model is available.
    """
    is_available: bool = False
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    backend: str = "UNAVAILABLE"
    status_message: str = "Scene-aware AI relighting model not loaded. Falling back to deterministic 2D lighting."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_available": self.is_available,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "backend": self.backend,
            "status_message": self.status_message,
        }


@dataclass
class LightingEngineDocument:
    """Complete versioned, serializable lighting and exposure configuration."""
    document_id: str = field(default_factory=lambda: f"light_doc_{uuid.uuid4().hex[:8]}")
    clip_id: str = ""
    schema_version: str = "1.0.0"
    is_enabled: bool = True
    engine_mode: RelightingEngineMode = RelightingEngineMode.DETERMINISTIC_2D

    # Global processing
    global_tone: GlobalExposureTonalConfig = field(default_factory=GlobalExposureTonalConfig)

    # Localized light regions (max 16 regions to enforce resource constraints)
    light_regions: List[LocalLightRegion] = field(default_factory=list)

    # Scene-aware extension metadata
    scene_aware: SceneAwareRelightingExtension = field(default_factory=SceneAwareRelightingExtension)

    revision: int = 1
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "clip_id": self.clip_id,
            "schema_version": self.schema_version,
            "is_enabled": self.is_enabled,
            "engine_mode": self.engine_mode.value,
            "global_tone": self.global_tone.to_dict(),
            "light_regions": [r.to_dict() for r in self.light_regions],
            "scene_aware": self.scene_aware.to_dict(),
            "revision": self.revision,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LightingEngineDocument":
        doc = cls(
            document_id=data.get("document_id", f"light_doc_{uuid.uuid4().hex[:8]}"),
            clip_id=data.get("clip_id", ""),
            schema_version=data.get("schema_version", "1.0.0"),
            is_enabled=data.get("is_enabled", True),
            engine_mode=RelightingEngineMode(data.get("engine_mode", RelightingEngineMode.DETERMINISTIC_2D.value)),
            global_tone=GlobalExposureTonalConfig.from_dict(data.get("global_tone", {})),
            light_regions=[LocalLightRegion.from_dict(r) for r in data.get("light_regions", [])],
            revision=int(data.get("revision", 1)),
            updated_at=float(data.get("updated_at", time.time())),
        )
        if "scene_aware" in data and isinstance(data["scene_aware"], dict):
            doc.scene_aware = SceneAwareRelightingExtension(
                is_available=bool(data["scene_aware"].get("is_available", False)),
                model_name=data["scene_aware"].get("model_name"),
                model_version=data["scene_aware"].get("model_version"),
                backend=data["scene_aware"].get("backend", "UNAVAILABLE"),
                status_message=data["scene_aware"].get("status_message", ""),
            )
        return doc


@dataclass
class LightingDiagnostics:
    """Execution telemetry and diagnostics for lighting and relighting processing."""
    clip_id: str = ""
    frame_number: int = 0
    processing_time_ms: float = 0.0
    active_regions_count: int = 0
    clipping_underflow_pct: float = 0.0   # Percentage of pixels clamped to 0.0
    clipping_overflow_pct: float = 0.0    # Percentage of pixels clamped to 1.0
    mean_luminance_before: float = 0.0
    mean_luminance_after: float = 0.0
    scene_aware_fallback_triggered: bool = False
    status: str = "SUCCESS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "frame_number": self.frame_number,
            "processing_time_ms": round(self.processing_time_ms, 3),
            "active_regions_count": self.active_regions_count,
            "clipping_underflow_pct": round(self.clipping_underflow_pct, 2),
            "clipping_overflow_pct": round(self.clipping_overflow_pct, 2),
            "mean_luminance_before": round(self.mean_luminance_before, 4),
            "mean_luminance_after": round(self.mean_luminance_after, 4),
            "scene_aware_fallback_triggered": self.scene_aware_fallback_triggered,
            "status": self.status,
        }
