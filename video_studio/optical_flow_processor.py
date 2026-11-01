"""OMNIA Video Studio — Motion Vector Visualization & Flow Effect Processor (Module 33).

Integrates optical flow visualization and motion vectors into the Module 10 effects stack:
- Inherits from IVideoEffectProcessor.
- Renders motion vectors as HSV direction/magnitude fields or diagnostic vector overlays.
- Category: UTILITY.
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
from video_studio.optical_flow_models import (
    MotionVectorField,
    FlowQualityPreset,
    MotionAnalysisConfig,
    FlowAlgorithmType,
)
from video_studio.optical_flow_engine import OpticalFlowEngine, optical_flow_engine


class VideoMotionFlowEffectProcessor(IVideoEffectProcessor):
    """Processor allowing editors to visualize and inspect optical flow in the timeline effects stack."""

    def __init__(self, engine: Optional[OpticalFlowEngine] = None):
        super().__init__(
            effect_id="motion_optical_flow_viz",
            name="Optical Flow & Motion Vectors",
            category=EffectCategory.UTILITY,
        )
        self.engine = engine or optical_flow_engine
        self.backend = ProcessingBackend.CPU
        self._previous_frame: Optional[VideoFrameBuffer] = None
        self._init_schemas()

    def set_reference_frame(self, frame: Optional[VideoFrameBuffer]) -> None:
        """Bind previous frame buffer for motion estimation."""
        self._previous_frame = frame

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "visualization_mode": EffectParameterSchema(
                parameter_id="visualization_mode",
                name="Visualization Mode",
                parameter_type=ParameterType.ENUM,
                default_value="HSV_COLOR_WHEEL",
                options=["HSV_COLOR_WHEEL", "CONFIDENCE_MAP", "OCCLUSION_MASK", "MOTION_BLEND"],
                description="Visual rendering representation for optical flow.",
            ),
            "max_speed": EffectParameterSchema(
                parameter_id="max_speed",
                name="Max Speed Normalization",
                parameter_type=ParameterType.FLOAT,
                default_value=20.0,
                min_value=1.0,
                max_value=100.0,
                is_animatable=True,
                description="Pixel displacement corresponding to maximum color saturation.",
            ),
            "blend_opacity": EffectParameterSchema(
                parameter_id="blend_opacity",
                name="Overlay Blend Opacity",
                parameter_type=ParameterType.FLOAT,
                default_value=0.7,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Blend factor between source footage and motion visualization.",
            ),
        }

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        """Process frame and overlay optical flow visualization."""
        p = self.validate_parameters(parameters)
        mode = p.get("visualization_mode", "HSV_COLOR_WHEEL")
        max_speed = float(p.get("max_speed", 20.0))
        blend_op = float(p.get("blend_opacity", 0.7))

        if self._previous_frame is None:
            self._previous_frame = frame
            return frame

        cfg = MotionAnalysisConfig(
            algorithm=FlowAlgorithmType.FARNEBACK_DENSE,
            quality_preset=FlowQualityPreset.BALANCED,
        )
        flow_field = self.engine.compute_dense_flow(self._previous_frame, frame, config=cfg)
        self._previous_frame = frame

        if flow_field.dense_flow is None:
            return frame

        h, w = frame.data.shape[:2]

        if mode == "HSV_COLOR_WHEEL":
            viz_bgr = self.engine.visualize_flow_hsv(flow_field, max_speed=max_speed)
            viz_rgb = cv2.cvtColor(viz_bgr, cv2.COLOR_BGR2RGB)
            if frame.data.shape[2] == 4:
                alpha = frame.data[:, :, 3:4]
                out_data = np.concatenate([viz_rgb, alpha], axis=2)
            else:
                out_data = viz_rgb

        elif mode == "CONFIDENCE_MAP":
            if flow_field.confidence_map is not None:
                conf_uint8 = (flow_field.confidence_map * 255.0).astype(np.uint8)
                conf_rgb = cv2.cvtColor(conf_uint8, cv2.COLOR_GRAY2RGB)
            else:
                conf_rgb = np.full((h, w, 3), 255, dtype=np.uint8)

            if frame.data.shape[2] == 4:
                out_data = np.concatenate([conf_rgb, frame.data[:, :, 3:4]], axis=2)
            else:
                out_data = conf_rgb

        elif mode == "OCCLUSION_MASK":
            if flow_field.occlusion_mask is not None:
                occ_rgb = cv2.cvtColor(flow_field.occlusion_mask, cv2.COLOR_GRAY2RGB)
            else:
                occ_rgb = np.zeros((h, w, 3), dtype=np.uint8)

            if frame.data.shape[2] == 4:
                out_data = np.concatenate([occ_rgb, frame.data[:, :, 3:4]], axis=2)
            else:
                out_data = occ_rgb

        else: # MOTION_BLEND
            viz_bgr = self.engine.visualize_flow_hsv(flow_field, max_speed=max_speed)
            viz_rgb = cv2.cvtColor(viz_bgr, cv2.COLOR_BGR2RGB)
            src_rgb = frame.data[:, :, :3]
            blended_rgb = cv2.addWeighted(src_rgb, 1.0 - blend_op, viz_rgb, blend_op, 0)
            if frame.data.shape[2] == 4:
                out_data = np.concatenate([blended_rgb, frame.data[:, :, 3:4]], axis=2)
            else:
                out_data = blended_rgb

        return VideoFrameBuffer(
            width=frame.width,
            height=frame.height,
            data=out_data,
            pixel_format=frame.pixel_format,
            timeline_frame=frame.timeline_frame,
            color_space=frame.color_space,
        )
