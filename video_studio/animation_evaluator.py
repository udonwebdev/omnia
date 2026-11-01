"""OMNIA Video Studio — Animation Interpolation & Evaluation Engine (Module 8).

Implements frame-accurate property evaluation:
- Binary search for interval localization: O(log N) lookup
- Constant / Hold interpolation
- Linear interpolation
- Cubic Bezier interpolation with tangent handles
- Ease In / Ease Out / Ease In Out curves
- Component-wise vector and color interpolation
- Cache invalidation on property revision changes
"""

from typing import Dict, Any, List, Optional, Tuple
import math
import bisect
import logging

from video_studio.animation_models import (
    AnimatableProperty,
    KeyframeModel,
    InterpolationMode,
    PropertyValueType,
)

logger = logging.getLogger("Omnia.VideoStudio.AnimationEvaluator")

class AnimationEvaluator:
    """Evaluates animatable properties at exact timeline frame positions."""

    def __init__(self):
        # Cache: (property_id, revision, frame) -> evaluated_value
        self._cache: Dict[Tuple[str, int, int], Any] = {}

    def invalidate_cache(self, property_id: Optional[str] = None) -> None:
        if property_id is None:
            self._cache.clear()
        else:
            self._cache = {k: v for k, v in self._cache.items() if k[0] != property_id}

    def evaluate(self, prop: AnimatableProperty, frame: int) -> Any:
        """Evaluates property value at frame deterministically."""
        if not prop.is_animated or not prop.keyframes:
            return prop.default_value

        cache_key = (prop.property_id, prop.revision, frame)
        if cache_key in self._cache:
            return self._cache[cache_key]

        kfs = prop.keyframes
        # 1. Single keyframe
        if len(kfs) == 1:
            val = kfs[0].value
            self._cache[cache_key] = val
            return val

        # 2. Before first keyframe
        if frame <= kfs[0].frame:
            val = kfs[0].value
            self._cache[cache_key] = val
            return val

        # 3. After last keyframe
        if frame >= kfs[-1].frame:
            val = kfs[-1].value
            self._cache[cache_key] = val
            return val

        # 4. Binary search for segment [k1, k2]
        frames_list = [k.frame for k in kfs]
        idx = bisect.bisect_right(frames_list, frame)
        k1 = kfs[idx - 1]
        k2 = kfs[idx]

        # Exactly at keyframe
        if frame == k1.frame:
            self._cache[cache_key] = k1.value
            return k1.value
        if frame == k2.frame:
            self._cache[cache_key] = k2.value
            return k2.value

        # Progress t in [0.0, 1.0]
        total_dt = max(1, k2.frame - k1.frame)
        t = (frame - k1.frame) / float(total_dt)

        mode = k1.interpolation
        val = self._interpolate_values(k1, k2, t, mode, prop.value_type)

        # Enforce property min/max clamp if applicable
        if isinstance(val, (int, float)):
            if prop.min_value is not None:
                val = max(prop.min_value, val)
            if prop.max_value is not None:
                val = min(prop.max_value, val)

        self._cache[cache_key] = val
        return val

    def _interpolate_values(
        self,
        k1: KeyframeModel,
        k2: KeyframeModel,
        t: float,
        mode: InterpolationMode,
        val_type: PropertyValueType,
    ) -> Any:
        # Non-numeric discrete types (BOOLEAN, ENUM) always hold
        if val_type in (PropertyValueType.BOOLEAN, PropertyValueType.ENUM) or mode in (InterpolationMode.CONSTANT, InterpolationMode.HOLD):
            return k1.value

        # Calculate eased / curved t
        factor = t
        if mode == InterpolationMode.LINEAR:
            factor = t
        elif mode == InterpolationMode.EASE_IN:
            factor = t * t
        elif mode == InterpolationMode.EASE_OUT:
            factor = t * (2.0 - t)
        elif mode == InterpolationMode.EASE_IN_OUT:
            factor = 0.5 * (1.0 - math.cos(math.pi * t))
        elif mode == InterpolationMode.BEZIER:
            factor = self._solve_cubic_bezier(t, k1.out_tangent, k2.in_tangent)

        v1 = k1.value
        v2 = k2.value

        # Scalar / Angle / Integer
        if val_type in (PropertyValueType.SCALAR, PropertyValueType.ANGLE):
            res = float(v1) + factor * (float(v2) - float(v1))
            return res
        elif val_type == PropertyValueType.INTEGER:
            res = float(v1) + factor * (float(v2) - float(v1))
            return int(round(res))
        elif val_type in (PropertyValueType.VECTOR2, PropertyValueType.VECTOR3, PropertyValueType.VECTOR4):
            # List or tuple component-wise
            return [float(a) + factor * (float(b) - float(a)) for a, b in zip(v1, v2)]
        elif val_type == PropertyValueType.COLOR:
            # Normalized or 0-255 RGBA
            return [float(a) + factor * (float(b) - float(a)) for a, b in zip(v1, v2)]

        return v1

    def _solve_cubic_bezier(
        self,
        t: float,
        out_tangent: Tuple[float, float],
        in_tangent: Tuple[float, float],
    ) -> float:
        """Solves 1D Cubic Bezier curve at parametric progress t."""
        # Control points P0=(0,0), P1=(x1, y1), P2=(x2, y2), P3=(1,1)
        # Handle offsets default normalized
        p1_y = max(0.0, min(1.0, 0.0 + out_tangent[1])) if out_tangent[1] != 0.0 else 0.33
        p2_y = max(0.0, min(1.0, 1.0 - in_tangent[1])) if in_tangent[1] != 0.0 else 0.67

        # Standard 1D Bernstein cubic polynomial
        u = 1.0 - t
        y = 3.0 * u * u * t * p1_y + 3.0 * u * t * t * p2_y + t * t * t
        return max(0.0, min(1.0, y))

# Global animation evaluator singleton
animation_evaluator = AnimationEvaluator()
