"""OMNIA Video Studio — Animation Service & Keyframe Command Management (Module 8).

Coordinates:
- Registering animatable properties on items and effects
- Keyframe mutations (Add, Update, Delete, Move, Copy, Paste, Bulk Edit)
- Reversible transaction and command pattern integration
- Copy-paste with relative frame offsets
- Evaluating properties across playhead frames
"""

from typing import Dict, Any, List, Optional, Tuple
import uuid
import copy
import logging

from video_studio.animation_models import (
    AnimatableProperty,
    KeyframeModel,
    InterpolationMode,
    TangentType,
    PropertyValueType,
    TransformAnimation,
)
from video_studio.animation_evaluator import (
    AnimationEvaluator,
    animation_evaluator,
)

logger = logging.getLogger("Omnia.VideoStudio.AnimationService")

class AnimationService:
    """Central registry and editing orchestrator for animatable parameters."""

    def __init__(self, evaluator: Optional[AnimationEvaluator] = None):
        self.evaluator = evaluator or animation_evaluator
        self._properties: Dict[str, AnimatableProperty] = {}
        self._transforms: Dict[str, TransformAnimation] = {}
        self._clipboard: List[KeyframeModel] = []

    def get_or_create_transform(self, owner_id: str) -> TransformAnimation:
        """Retrieves or instantiates standard transform properties for an item."""
        if owner_id not in self._transforms:
            trans = TransformAnimation(owner_id=owner_id)
            self._transforms[owner_id] = trans
            # Register channels
            self._properties[trans.position_x.property_id] = trans.position_x
            self._properties[trans.position_y.property_id] = trans.position_y
            self._properties[trans.scale_x.property_id] = trans.scale_x
            self._properties[trans.scale_y.property_id] = trans.scale_y
            self._properties[trans.rotation.property_id] = trans.rotation
            self._properties[trans.opacity.property_id] = trans.opacity
        return self._transforms[owner_id]

    def register_property(self, prop: AnimatableProperty) -> None:
        self._properties[prop.property_id] = prop

    def get_property(self, property_id: str) -> Optional[AnimatableProperty]:
        return self._properties.get(property_id)

    # -------------------------------------------------------------------------
    # Keyframe Operations
    # -------------------------------------------------------------------------

    def add_keyframe(
        self,
        property_id: str,
        frame: int,
        value: Any,
        interpolation: InterpolationMode = InterpolationMode.LINEAR,
        tangent_type: TangentType = TangentType.AUTOMATIC,
        in_tangent: Tuple[float, float] = (0.0, 0.0),
        out_tangent: Tuple[float, float] = (0.0, 0.0),
        keyframe_id: Optional[str] = None,
    ) -> KeyframeModel:
        prop = self._properties.get(property_id)
        if not prop:
            raise ValueError(f"Property '{property_id}' not found.")

        # Remove existing keyframe at exact same frame if present
        prop.keyframes = [k for k in prop.keyframes if k.frame != frame]

        kf = KeyframeModel(
            keyframe_id=keyframe_id or str(uuid.uuid4()),
            property_id=property_id,
            frame=frame,
            value=value,
            interpolation=interpolation,
            in_tangent=in_tangent,
            out_tangent=out_tangent,
            tangent_type=tangent_type,
        )
        prop.keyframes.append(kf)
        prop.sort_keyframes()
        prop.revision += 1
        self.evaluator.invalidate_cache(property_id)
        return kf

    def remove_keyframe(self, property_id: str, keyframe_id: str) -> bool:
        prop = self._properties.get(property_id)
        if not prop:
            return False
        before_len = len(prop.keyframes)
        prop.keyframes = [k for k in prop.keyframes if k.keyframe_id != keyframe_id]
        if len(prop.keyframes) != before_len:
            prop.revision += 1
            self.evaluator.invalidate_cache(property_id)
            return True
        return False

    def move_keyframe(self, property_id: str, keyframe_id: str, new_frame: int) -> bool:
        prop = self._properties.get(property_id)
        if not prop:
            return False
        kf = next((k for k in prop.keyframes if k.keyframe_id == keyframe_id), None)
        if not kf:
            return False
        # Remove any other keyframe occupying the target frame
        prop.keyframes = [k for k in prop.keyframes if k.keyframe_id == keyframe_id or k.frame != new_frame]
        kf.frame = new_frame
        prop.sort_keyframes()
        prop.revision += 1
        self.evaluator.invalidate_cache(property_id)
        return True

    def set_keyframe_value(self, property_id: str, keyframe_id: str, new_value: Any) -> bool:
        prop = self._properties.get(property_id)
        if not prop:
            return False
        kf = next((k for k in prop.keyframes if k.keyframe_id == keyframe_id), None)
        if not kf:
            return False
        kf.value = new_value
        prop.revision += 1
        self.evaluator.invalidate_cache(property_id)
        return True

    def set_interpolation(
        self,
        property_id: str,
        keyframe_id: str,
        interpolation: InterpolationMode,
    ) -> bool:
        prop = self._properties.get(property_id)
        if not prop:
            return False
        kf = next((k for k in prop.keyframes if k.keyframe_id == keyframe_id), None)
        if not kf:
            return False
        kf.interpolation = interpolation
        prop.revision += 1
        self.evaluator.invalidate_cache(property_id)
        return True

    # -------------------------------------------------------------------------
    # Bulk & Clipboard Operations
    # -------------------------------------------------------------------------

    def copy_keyframes(self, property_id: str, keyframe_ids: Optional[List[str]] = None) -> int:
        prop = self._properties.get(property_id)
        if not prop:
            return 0
        if keyframe_ids:
            selected = [k for k in prop.keyframes if k.keyframe_id in keyframe_ids]
        else:
            selected = list(prop.keyframes)
        self._clipboard = [copy.deepcopy(k) for k in selected]
        return len(self._clipboard)

    def paste_keyframes(self, target_property_id: str, target_start_frame: int) -> List[KeyframeModel]:
        target_prop = self._properties.get(target_property_id)
        if not target_prop:
            raise ValueError(f"Target property '{target_property_id}' not found.")
        if not self._clipboard:
            return []

        base_frame = min(k.frame for k in self._clipboard)
        pasted = []

        for k in self._clipboard:
            offset = k.frame - base_frame
            new_f = target_start_frame + offset
            new_kf = self.add_keyframe(
                property_id=target_property_id,
                frame=new_f,
                value=k.value,
                interpolation=k.interpolation,
                tangent_type=k.tangent_type,
                in_tangent=k.in_tangent,
                out_tangent=k.out_tangent,
            )
            pasted.append(new_kf)
        return pasted

    def evaluate(self, property_id: str, frame: int) -> Any:
        prop = self._properties.get(property_id)
        if not prop:
            return None
        return self.evaluator.evaluate(prop, frame)

# Global animation service singleton
animation_service = AnimationService()
