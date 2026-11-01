"""OMNIA Video Studio — Video Deblur & Motion Blur Effect Processor (Module 28).

Integrates the VideoDeblurEngine directly into the Module 10 video effects pipeline:
- Inherits from IVideoEffectProcessor.
- Registers standard parameter schemas (operation, deblur_method, blur_length, blur_angle_deg, shutter_mode, regularization_k).
- Exposes non-destructive deblurring and shutter motion blur to clip effect stacks.
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from video_studio.effects_models import (
    VideoFrameBuffer,
    EffectParameterSchema,
    ParameterType,
    EffectCategory,
    ProcessingBackend,
)
from video_studio.effects_processors import IVideoEffectProcessor
from video_studio.deblur_models import (
    DeblurConfig,
    BlurOperationType,
    BlurKernelType,
    ShutterAngleMode,
    DeblurMethod,
)
from video_studio.deblur_engine import video_deblur_engine, VideoDeblurEngine


class VideoDeblurEffectProcessor(IVideoEffectProcessor):
    """Production-grade deblurring and motion blur processor in Module 10 effects stack."""

    def __init__(self, engine: Optional[VideoDeblurEngine] = None):
        super().__init__(
            effect_id="deblur_motion_blur",
            name="Video Deblur & Motion Blur",
            category=EffectCategory.FILTER,
        )
        self.engine = engine or video_deblur_engine
        self.backend = ProcessingBackend.CPU
        self._init_schemas()

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "operation": EffectParameterSchema(
                parameter_id="operation",
                name="Operation Type",
                parameter_type=ParameterType.ENUM,
                default_value="MOTION_BLUR_GENERATION",
                options=["DEBLUR_RESTORATION", "MOTION_BLUR_GENERATION", "MOTION_BLUR_REDUCTION"],
                description="Process to perform on the image.",
            ),
            "deblur_method": EffectParameterSchema(
                parameter_id="deblur_method",
                name="Deblur Algorithm",
                parameter_type=ParameterType.ENUM,
                default_value="WIENER_DECONVOLUTION",
                options=["WIENER_DECONVOLUTION", "LUCY_RICHARDSON", "REGULARIZED_INVERSE"],
                description="Deconvolution algorithm used for restoration.",
            ),
            "blur_length": EffectParameterSchema(
                parameter_id="blur_length",
                name="Blur Length / Radius",
                parameter_type=ParameterType.FLOAT,
                default_value=7.0,
                min_value=1.0,
                max_value=45.0,
                is_animatable=True,
                description="Blur path length in pixels.",
            ),
            "blur_angle_deg": EffectParameterSchema(
                parameter_id="blur_angle_deg",
                name="Blur Angle (Deg)",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-180.0,
                max_value=180.0,
                is_animatable=True,
                description="Angle of linear blur trajectory.",
            ),
            "shutter_mode": EffectParameterSchema(
                parameter_id="shutter_mode",
                name="Shutter Angle Mode",
                parameter_type=ParameterType.ENUM,
                default_value="SHUTTER_180",
                options=["SHUTTER_90", "SHUTTER_180", "SHUTTER_270", "SHUTTER_360", "CUSTOM"],
                description="Camera shutter simulation for motion blur.",
            ),
            "regularization_k": EffectParameterSchema(
                parameter_id="regularization_k",
                name="Wiener Regularizer K",
                parameter_type=ParameterType.FLOAT,
                default_value=0.005,
                min_value=0.0001,
                max_value=0.1,
                description="Noise-to-signal ratio to prevent noise explosion.",
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

        config = DeblurConfig(
            operation=BlurOperationType(p["operation"]),
            deblur_method=DeblurMethod(p["deblur_method"]),
            blur_length=float(p["blur_length"]),
            blur_angle_deg=float(p["blur_angle_deg"]),
            shutter_mode=ShutterAngleMode(p["shutter_mode"]),
            regularization_k=float(p["regularization_k"]),
            is_enabled=True,
        )

        out_frame, _ = self.engine.process_frame(frame, config)
        return out_frame
