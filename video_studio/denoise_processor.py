"""OMNIA Video Studio — Video Denoising Effect Processor (Module 25).

Integrates the VideoDenoiseEngine directly into the Module 10 video effects pipeline:
- Inherits from IVideoEffectProcessor.
- Registers standard parameter schemas (method, strength, luma/chroma, radius, dead pixels, sharpening, etc.).
- Exposes non-destructive denoising to clip effect stacks and timeline evaluation.
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
from video_studio.denoise_models import (
    DenoiseConfig,
    DenoiseMethod,
    DenoiseQualityMode,
    DenoiseChannelScope,
)
from video_studio.denoise_engine import video_denoise_engine, VideoDenoiseEngine


class VideoDenoiseEffectProcessor(IVideoEffectProcessor):
    """Production-grade video denoising and restoration processor in Module 10 effects stack."""

    def __init__(self, engine: Optional[VideoDenoiseEngine] = None):
        super().__init__(
            effect_id="denoise_restoration",
            name="Video Denoise & Restoration",
            category=EffectCategory.FILTER,
        )
        self.engine = engine or video_denoise_engine
        self.backend = ProcessingBackend.CPU
        self._init_schemas()

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "method": EffectParameterSchema(
                parameter_id="method",
                name="Denoising Method",
                parameter_type=ParameterType.ENUM,
                default_value="BILATERAL_SPATIAL",
                options=["BILATERAL_SPATIAL", "FAST_NL_MEANS", "GUIDED_FILTER"],
                description="Spatial filtering algorithm.",
            ),
            "quality_mode": EffectParameterSchema(
                parameter_id="quality_mode",
                name="Quality Mode",
                parameter_type=ParameterType.ENUM,
                default_value="BALANCED",
                options=["FAST", "BALANCED", "HIGH_QUALITY"],
                description="Quality vs performance tradeoff.",
            ),
            "channel_scope": EffectParameterSchema(
                parameter_id="channel_scope",
                name="Channel Scope",
                parameter_type=ParameterType.ENUM,
                default_value="LUMA_AND_CHROMA",
                options=["LUMA_AND_CHROMA", "LUMA_ONLY", "CHROMA_ONLY"],
                description="Channels to target for filtering.",
            ),
            "strength": EffectParameterSchema(
                parameter_id="strength",
                name="Filtering Strength",
                parameter_type=ParameterType.FLOAT,
                default_value=15.0,
                min_value=1.0,
                max_value=100.0,
                is_animatable=True,
                description="Primary noise reduction intensity.",
            ),
            "luma_strength": EffectParameterSchema(
                parameter_id="luma_strength",
                name="Luminance Strength",
                parameter_type=ParameterType.FLOAT,
                default_value=15.0,
                min_value=1.0,
                max_value=100.0,
                is_animatable=True,
                description="Luminance grain suppression intensity.",
            ),
            "chroma_strength": EffectParameterSchema(
                parameter_id="chroma_strength",
                name="Chrominance Strength",
                parameter_type=ParameterType.FLOAT,
                default_value=15.0,
                min_value=1.0,
                max_value=100.0,
                is_animatable=True,
                description="Chroma blotchiness suppression intensity.",
            ),
            "spatial_radius": EffectParameterSchema(
                parameter_id="spatial_radius",
                name="Spatial Radius",
                parameter_type=ParameterType.INTEGER,
                default_value=5,
                min_value=1,
                max_value=15,
                is_animatable=True,
                description="Neighborhood radius for noise analysis.",
            ),
            "dead_pixel_correction": EffectParameterSchema(
                parameter_id="dead_pixel_correction",
                name="Dead Pixel Correction",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Detect and eliminate isolated sensor defects.",
            ),
            "post_sharpening": EffectParameterSchema(
                parameter_id="post_sharpening",
                name="Post-Denoise Sharpening",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Unsharp mask edge detail recovery.",
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

        config = DenoiseConfig(
            method=DenoiseMethod(p["method"]),
            quality_mode=DenoiseQualityMode(p["quality_mode"]),
            channel_scope=DenoiseChannelScope(p["channel_scope"]),
            strength=float(p["strength"]),
            luma_strength=float(p["luma_strength"]),
            chroma_strength=float(p["chroma_strength"]),
            spatial_radius=int(p["spatial_radius"]),
            dead_pixel_correction=bool(p["dead_pixel_correction"]),
            post_sharpening=float(p["post_sharpening"]),
            is_enabled=True,
        )

        out_frame, _ = self.engine.process_frame(frame, config)
        return out_frame
