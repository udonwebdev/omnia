"""OMNIA Video Studio — Object Segmentation & Subject Isolation Effect Processor (Module 34).

Integrates subject segmentation masks into the Module 10 effects pipeline:
- Inherits from IVideoEffectProcessor.
- Modulates frame alpha channel using active segmentation masks or visualizes mask overlay.
- Category: COMPOSITING.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import cv2

from video_studio.effects_models import (
    VideoFrameBuffer,
    EffectParameterSchema,
    ParameterType,
    EffectCategory,
    ProcessingBackend,
)
from video_studio.effects_processors import IVideoEffectProcessor
from video_studio.segmentation_models import MaskCombinationMode, MaskRefinementConfig
from video_studio.segmentation_service import VideoSegmentationService, video_segmentation_service


class VideoSegmentationEffectProcessor(IVideoEffectProcessor):
    """Processor applying segmentation masks to frame transparency in the effects stack."""

    def __init__(self, service: Optional[VideoSegmentationService] = None):
        super().__init__(
            effect_id="subject_segmentation_isolation",
            name="Subject Segmentation & Isolation",
            category=EffectCategory.COMPOSITING,
        )
        self.service = service or video_segmentation_service
        self.backend = ProcessingBackend.CPU
        self._init_schemas()

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "clip_id": EffectParameterSchema(
                parameter_id="clip_id",
                name="Clip Identifier",
                parameter_type=ParameterType.ENUM,
                default_value="default_clip",
                options=["default_clip"],
                description="Identifier of clip containing segmentation masks.",
            ),
            "combination_mode": EffectParameterSchema(
                parameter_id="combination_mode",
                name="Mask Combination Mode",
                parameter_type=ParameterType.ENUM,
                default_value="UNION",
                options=["UNION", "INTERSECT", "SUBTRACT", "REPLACE"],
                description="Combination operation for multiple overlapping masks.",
            ),
            "invert_output": EffectParameterSchema(
                parameter_id="invert_output",
                name="Invert Subject Isolation",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Invert mask to isolate background instead of subject.",
            ),
            "mask_opacity": EffectParameterSchema(
                parameter_id="mask_opacity",
                name="Mask Influence Opacity",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Strength of alpha modulation.",
            ),
        }

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        p = self.validate_parameters(parameters)
        clip_id = parameters.get("clip_id", "default_clip")
        mode_str = p.get("combination_mode", "UNION")
        invert = bool(p.get("invert_output", False))
        opacity = float(p.get("mask_opacity", 1.0))

        try:
            mode = MaskCombinationMode(mode_str)
        except ValueError:
            mode = MaskCombinationMode.UNION

        container = self.service.get_or_create_frame_container(clip_id, frame.timeline_frame)
        mask_f32 = container.composite_combined_mask(mode=mode)

        if mask_f32 is None:
            return frame

        h, w = frame.data.shape[:2]
        if mask_f32.shape[:2] != (h, w):
            mask_f32 = cv2.resize(mask_f32, (w, h), interpolation=cv2.INTER_LINEAR)

        if invert:
            mask_f32 = 1.0 - mask_f32

        # Blend mask with opacity
        effective_mask = (1.0 - opacity) + (opacity * mask_f32)

        data = frame.data.copy()
        if data.shape[2] == 4:
            orig_alpha = data[:, :, 3].astype(np.float32)
            new_alpha = np.clip(orig_alpha * effective_mask, 0, 255).astype(np.uint8)
            data[:, :, 3] = new_alpha
        else:
            new_alpha = np.clip(effective_mask * 255.0, 0, 255).astype(np.uint8)
            data = np.concatenate([data, new_alpha[:, :, np.newaxis]], axis=2)

        return VideoFrameBuffer(
            width=w,
            height=h,
            data=data,
            pixel_format=frame.pixel_format,
            timeline_frame=frame.timeline_frame,
            color_space=frame.color_space,
        )
