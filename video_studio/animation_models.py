"""OMNIA Video Studio — Professional Keyframe & Animation Models (Module 8).

Defines:
- InterpolationMode: CONSTANT/HOLD, LINEAR, BEZIER, EASE_IN, EASE_OUT, EASE_IN_OUT, CUSTOM_CURVE
- TangentType: FREE, ALIGNED, AUTOMATIC, LINEAR, FLAT
- PropertyValueType: SCALAR, INTEGER, BOOLEAN, ENUM, VECTOR2, VECTOR3, VECTOR4, COLOR, ANGLE
- KeyframeModel: Precise frame timing, typed values, and Bezier control handles
- AnimatableProperty: Canonical container for animatable channels
- TransformAnimation: Standard animatable properties (Position X/Y, Scale X/Y, Rotation, Opacity)
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
import time
import uuid

class InterpolationMode(str, Enum):
    CONSTANT = "CONSTANT"
    HOLD = "HOLD"
    LINEAR = "LINEAR"
    BEZIER = "BEZIER"
    EASE_IN = "EASE_IN"
    EASE_OUT = "EASE_OUT"
    EASE_IN_OUT = "EASE_IN_OUT"
    CUSTOM_CURVE = "CUSTOM_CURVE"

class TangentType(str, Enum):
    FREE = "FREE"
    ALIGNED = "ALIGNED"
    AUTOMATIC = "AUTOMATIC"
    LINEAR = "LINEAR"
    FLAT = "FLAT"

class PropertyValueType(str, Enum):
    SCALAR = "SCALAR"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    VECTOR2 = "VECTOR2"
    VECTOR3 = "VECTOR3"
    VECTOR4 = "VECTOR4"
    COLOR = "COLOR"
    ANGLE = "ANGLE"

@dataclass
class KeyframeModel:
    """Canonical model for a single parameter keyframe."""
    keyframe_id: str
    property_id: str
    frame: int  # Exact integer frame coordinate
    value: Any
    interpolation: InterpolationMode = InterpolationMode.LINEAR
    in_tangent: Tuple[float, float] = (0.0, 0.0)  # (dt_frames, d_value)
    out_tangent: Tuple[float, float] = (0.0, 0.0)  # (dt_frames, d_value)
    tangent_type: TangentType = TangentType.AUTOMATIC
    is_selected: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyframe_id": self.keyframe_id,
            "property_id": self.property_id,
            "frame": self.frame,
            "value": self.value,
            "interpolation": self.interpolation.value,
            "in_tangent": list(self.in_tangent),
            "out_tangent": list(self.out_tangent),
            "tangent_type": self.tangent_type.value,
            "is_selected": self.is_selected,
            "metadata": self.metadata,
        }

@dataclass
class AnimatableProperty:
    """Canonical container representing an animatable property on an item or effect."""
    property_id: str
    owner_id: str
    name: str
    value_type: PropertyValueType
    default_value: Any
    current_value: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: str = ""
    is_animated: bool = True
    keyframes: List[KeyframeModel] = field(default_factory=list)
    revision: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property_id": self.property_id,
            "owner_id": self.owner_id,
            "name": self.name,
            "value_type": self.value_type.value,
            "default_value": self.default_value,
            "current_value": self.current_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "unit": self.unit,
            "is_animated": self.is_animated,
            "keyframes": [kf.to_dict() for kf in self.keyframes],
            "revision": self.revision,
        }

    def sort_keyframes(self) -> None:
        self.keyframes.sort(key=lambda k: k.frame)

@dataclass
class TransformAnimation:
    """Standard transform animation bundle for timeline items."""
    owner_id: str
    position_x: AnimatableProperty = field(init=False)
    position_y: AnimatableProperty = field(init=False)
    scale_x: AnimatableProperty = field(init=False)
    scale_y: AnimatableProperty = field(init=False)
    rotation: AnimatableProperty = field(init=False)
    opacity: AnimatableProperty = field(init=False)

    def __post_init__(self):
        self.position_x = AnimatableProperty(
            property_id=f"{self.owner_id}_pos_x",
            owner_id=self.owner_id,
            name="Position X",
            value_type=PropertyValueType.SCALAR,
            default_value=0.0,
            current_value=0.0,
            unit="px",
        )
        self.position_y = AnimatableProperty(
            property_id=f"{self.owner_id}_pos_y",
            owner_id=self.owner_id,
            name="Position Y",
            value_type=PropertyValueType.SCALAR,
            default_value=0.0,
            current_value=0.0,
            unit="px",
        )
        self.scale_x = AnimatableProperty(
            property_id=f"{self.owner_id}_scale_x",
            owner_id=self.owner_id,
            name="Scale X",
            value_type=PropertyValueType.SCALAR,
            default_value=1.0,
            current_value=1.0,
            unit="ratio",
        )
        self.scale_y = AnimatableProperty(
            property_id=f"{self.owner_id}_scale_y",
            owner_id=self.owner_id,
            name="Scale Y",
            value_type=PropertyValueType.SCALAR,
            default_value=1.0,
            current_value=1.0,
            unit="ratio",
        )
        self.rotation = AnimatableProperty(
            property_id=f"{self.owner_id}_rotation",
            owner_id=self.owner_id,
            name="Rotation",
            value_type=PropertyValueType.ANGLE,
            default_value=0.0,
            current_value=0.0,
            unit="deg",
        )
        self.opacity = AnimatableProperty(
            property_id=f"{self.owner_id}_opacity",
            owner_id=self.owner_id,
            name="Opacity",
            value_type=PropertyValueType.SCALAR,
            default_value=1.0,
            current_value=1.0,
            min_value=0.0,
            max_value=1.0,
            unit="ratio",
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "position_x": self.position_x.to_dict(),
            "position_y": self.position_y.to_dict(),
            "scale_x": self.scale_x.to_dict(),
            "scale_y": self.scale_y.to_dict(),
            "rotation": self.rotation.to_dict(),
            "opacity": self.opacity.to_dict(),
        }
