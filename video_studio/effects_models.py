"""OMNIA Video Studio — Video Effects & Color Processing Domain Models (Module 10).

Defines:
- ParameterType: FLOAT, INTEGER, BOOLEAN, ENUM, COLOR_RGBA, VECTOR2, ANGLE.
- EffectParameterSchema: Typed schema with defaults, ranges, units, and animatable flags.
- EffectParameterValue: Concrete instance parameter configuration.
- EffectCategory: TRANSFORM, COLOR, COMPOSITING, BLUR, STYLIZATION, UTILITY.
- EffectDescriptor: Specification of an effect processor (ID, name, category, backend, schema).
- EffectInstance: Non-destructive effect assigned to a timeline item/clip with enabled/bypass state.
- VideoEffectStack: Ordered list of effect instances with reordering, enable, bypass, and serialization.
- VideoFrameBuffer: In-memory image buffer (NumPy ndarray in RGBA/RGB uint8/float32) for zero-copy DSP operations.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
import uuid
import time
import numpy as np

# ==============================================================================
# 1. Enums & Schemas
# ==============================================================================

class ParameterType(str, Enum):
    FLOAT = "FLOAT"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"
    COLOR_RGBA = "COLOR_RGBA"
    VECTOR2 = "VECTOR2"
    ANGLE = "ANGLE"

class EffectCategory(str, Enum):
    TRANSFORM = "TRANSFORM"
    COLOR = "COLOR"
    COMPOSITING = "COMPOSITING"
    FILTER = "FILTER"
    UTILITY = "UTILITY"

class ProcessingBackend(str, Enum):
    CPU = "CPU"
    GPU_DIRECTML = "GPU_DIRECTML"
    AUTO = "AUTO"

@dataclass
class EffectParameterSchema:
    """Declares typing, range, defaults, and animation capability for an effect parameter."""
    parameter_id: str
    name: str
    parameter_type: ParameterType
    default_value: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    unit: str = ""
    is_animatable: bool = True
    options: List[str] = field(default_factory=list) # For ENUM
    description: str = ""

    def validate(self, value: Any) -> Tuple[bool, Any, str]:
        """Validates and clamps or normalizes parameter value."""
        if value is None:
            return True, self.default_value, "Default applied"

        if self.parameter_type in (ParameterType.FLOAT, ParameterType.ANGLE):
            try:
                v = float(value)
                if np.isnan(v) or np.isinf(v):
                    return False, self.default_value, "Value is NaN or infinite"
                if self.min_value is not None:
                    v = max(self.min_value, v)
                if self.max_value is not None:
                    v = min(self.max_value, v)
                return True, v, "Valid"
            except (ValueError, TypeError):
                return False, self.default_value, "Expected float"

        elif self.parameter_type == ParameterType.INTEGER:
            try:
                v = int(value)
                if self.min_value is not None:
                    v = max(int(self.min_value), v)
                if self.max_value is not None:
                    v = min(int(self.max_value), v)
                return True, v, "Valid"
            except (ValueError, TypeError):
                return False, self.default_value, "Expected integer"

        elif self.parameter_type == ParameterType.BOOLEAN:
            return True, bool(value), "Valid"

        elif self.parameter_type == ParameterType.ENUM:
            s = str(value)
            if self.options and s not in self.options:
                return False, self.default_value, f"Invalid enum option '{s}'. Allowed: {self.options}"
            return True, s, "Valid"

        elif self.parameter_type == ParameterType.VECTOR2:
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                try:
                    return True, (float(value[0]), float(value[1])), "Valid"
                except (ValueError, TypeError):
                    pass
            return False, self.default_value, "Expected (x, y) float tuple"

        elif self.parameter_type == ParameterType.COLOR_RGBA:
            if isinstance(value, (list, tuple)) and len(value) >= 4:
                try:
                    clamped = [max(0.0, min(1.0, float(c))) for c in value[:4]]
                    return True, tuple(clamped), "Valid"
                except (ValueError, TypeError):
                    pass
            return False, self.default_value, "Expected (r, g, b, a) in [0.0, 1.0]"

        return True, value, "Valid"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter_id": self.parameter_id,
            "name": self.name,
            "type": self.parameter_type.value,
            "default_value": self.default_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step": self.step,
            "unit": self.unit,
            "is_animatable": self.is_animatable,
            "options": self.options,
            "description": self.description,
        }

# ==============================================================================
# 2. Frame Buffer Contract
# ==============================================================================

@dataclass
class VideoFrameBuffer:
    """In-memory multi-channel image buffer (RGBA uint8 or float32 NumPy array).
    Shape: (height, width, 4) for RGBA.
    """
    width: int
    height: int
    pixel_format: str = "RGBA"
    color_space: str = "Rec.709"
    data: np.ndarray = field(default_factory=lambda: np.zeros((1, 1, 4), dtype=np.uint8))
    pts_seconds: float = 0.0
    timeline_frame: int = 0

    def __post_init__(self):
        if not isinstance(self.data, np.ndarray):
            self.data = np.asarray(self.data, dtype=np.uint8)
        if self.data.ndim == 2: # Gray to RGBA
            h, w = self.data.shape
            rgba = np.zeros((h, w, 4), dtype=self.data.dtype)
            rgba[:, :, 0] = self.data
            rgba[:, :, 1] = self.data
            rgba[:, :, 2] = self.data
            rgba[:, :, 3] = 255 if self.data.dtype == np.uint8 else 1.0
            self.data = rgba
        elif self.data.ndim == 3 and self.data.shape[2] == 3: # RGB to RGBA
            h, w, _ = self.data.shape
            rgba = np.zeros((h, w, 4), dtype=self.data.dtype)
            rgba[:, :, :3] = self.data
            rgba[:, :, 3] = 255 if self.data.dtype == np.uint8 else 1.0
            self.data = rgba

    def copy(self) -> "VideoFrameBuffer":
        return VideoFrameBuffer(
            width=self.width,
            height=self.height,
            pixel_format=self.pixel_format,
            color_space=self.color_space,
            data=np.copy(self.data),
            pts_seconds=self.pts_seconds,
            timeline_frame=self.timeline_frame,
        )

    @classmethod
    def blank(cls, width: int, height: int, color: Tuple[int, int, int, int] = (0, 0, 0, 255)) -> "VideoFrameBuffer":
        data = np.zeros((height, width, 4), dtype=np.uint8)
        data[:, :] = color
        return cls(width=width, height=height, data=data)

    @classmethod
    def from_bytes(cls, raw_bytes: bytes, width: int, height: int, pixel_format: str = "RGBA") -> "VideoFrameBuffer":
        if not raw_bytes:
            return cls.blank(width, height)
        expected_len = width * height * 4
        if len(raw_bytes) < expected_len:
            # Pad with black
            padded = raw_bytes + b"\x00\x00\x00\xff" * (width * height - len(raw_bytes) // 4)
            arr = np.frombuffer(padded[:expected_len], dtype=np.uint8).reshape((height, width, 4))
        else:
            arr = np.frombuffer(raw_bytes[:expected_len], dtype=np.uint8).reshape((height, width, 4))
        return cls(width=width, height=height, pixel_format=pixel_format, data=arr)

    def to_bytes(self) -> bytes:
        return self.data.tobytes()

# ==============================================================================
# 3. Effect Instance & Stack Models
# ==============================================================================

@dataclass
class EffectInstance:
    """Non-destructive instance of an effect applied to a clip or track."""
    instance_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    effect_id: str = "effect.unknown"
    name: str = "Effect"
    category: EffectCategory = EffectCategory.FILTER
    is_enabled: bool = True
    is_bypassed: bool = False
    order_index: int = 0
    parameters: Dict[str, Any] = field(default_factory=dict)
    automation_targets: Dict[str, str] = field(default_factory=dict) # param_id -> animatable_property_id
    last_error: Optional[str] = None
    version: str = "1.0.0"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "effect_id": self.effect_id,
            "name": self.name,
            "category": self.category.value,
            "is_enabled": self.is_enabled,
            "is_bypassed": self.is_bypassed,
            "order_index": self.order_index,
            "parameters": dict(self.parameters),
            "automation_targets": dict(self.automation_targets),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EffectInstance":
        cat = EffectCategory(data.get("category", "FILTER"))
        return cls(
            instance_id=data.get("instance_id", str(uuid.uuid4())),
            effect_id=data.get("effect_id", "effect.unknown"),
            name=data.get("name", "Effect"),
            category=cat,
            is_enabled=data.get("is_enabled", True),
            is_bypassed=data.get("is_bypassed", False),
            order_index=data.get("order_index", 0),
            parameters=data.get("parameters", {}),
            automation_targets=data.get("automation_targets", {}),
            version=data.get("version", "1.0.0"),
        )

@dataclass
class VideoEffectStack:
    """Ordered sequence of effect instances attached to a timeline object."""
    owner_id: str # clip_id or track_id
    effects: List[EffectInstance] = field(default_factory=list)

    def add_effect(self, effect: EffectInstance) -> None:
        effect.order_index = len(self.effects)
        self.effects.append(effect)

    def remove_effect(self, instance_id: str) -> bool:
        init_len = len(self.effects)
        self.effects = [e for e in self.effects if e.instance_id != instance_id]
        self._reindex()
        return len(self.effects) < init_len

    def reorder_effect(self, instance_id: str, new_index: int) -> bool:
        found = None
        for e in self.effects:
            if e.instance_id == instance_id:
                found = e
                break
        if not found:
            return False

        self.effects.remove(found)
        clamped_idx = max(0, min(len(self.effects), new_index))
        self.effects.insert(clamped_idx, found)
        self._reindex()
        return True

    def get_effect(self, instance_id: str) -> Optional[EffectInstance]:
        for e in self.effects:
            if e.instance_id == instance_id:
                return e
        return None

    def _reindex(self) -> None:
        for idx, e in enumerate(self.effects):
            e.order_index = idx

    def to_list(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.effects]

    @classmethod
    def from_list(cls, owner_id: str, data_list: List[Dict[str, Any]]) -> "VideoEffectStack":
        stack = cls(owner_id=owner_id)
        for item in data_list:
            stack.effects.append(EffectInstance.from_dict(item))
        stack._reindex()
        return stack
