"""OMNIA Video Studio — Video Upscale & Super-Resolution Effect Processor (Module 26).

Integrates the VideoUpscaleEngine directly into the Module 10 video effects pipeline:
- Inherits from IVideoEffectProcessor.
- Registers standard parameter schemas (algorithm, sizing_policy, scale_factor, sharpen_amount, pre_denoise, etc.).
- Allows clips to upscale and enhance within timeline effect stacks and final rendering.
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
from video_studio.upscale_models import (
    UpscaleConfig,
    UpscaleAlgorithm,
    SizingPolicy,
    AspectRatioMode,
    UpscaleQualityMode,
)
from video_studio.upscale_engine import video_upscale_engine, VideoUpscaleEngine


class VideoUpscaleEffectProcessor(IVideoEffectProcessor):
    """Production-grade video upscaling and detail enhancement processor in Module 10 effects stack."""

    def __init__(self, engine: Optional[VideoUpscaleEngine] = None):
        super().__init__(
            effect_id="upscale_enhancement",
            name="Video Upscale & Super-Resolution",
            category=EffectCategory.TRANSFORM,
        )
        self.engine = engine or video_upscale_engine
        self.backend = ProcessingBackend.CPU
        self._init_schemas()

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "algorithm": EffectParameterSchema(
                parameter_id="algorithm",
                name="Resampling Algorithm",
                parameter_type=ParameterType.ENUM,
                default_value="LANCZOS4",
                options=["NEAREST_NEIGHBOR", "BILINEAR", "BICUBIC", "LANCZOS4", "LEARNED_SUPER_RES"],
                description="Spatial interpolation or model-backed reconstruction algorithm.",
            ),
            "sizing_policy": EffectParameterSchema(
                parameter_id="sizing_policy",
                name="Sizing Policy",
                parameter_type=ParameterType.ENUM,
                default_value="SCALE_FACTOR",
                options=["SCALE_FACTOR", "FIT_CANVAS", "FILL_CANVAS", "CUSTOM_DIMENSIONS"],
                description="Output sizing calculation mode.",
            ),
            "scale_factor": EffectParameterSchema(
                parameter_id="scale_factor",
                name="Scale Multiplier",
                parameter_type=ParameterType.FLOAT,
                default_value=2.0,
                min_value=1.0,
                max_value=8.0,
                is_animatable=True,
                description="Spatial magnification multiplier (e.g. 2.0x, 4.0x).",
            ),
            "target_width": EffectParameterSchema(
                parameter_id="target_width",
                name="Target Width",
                parameter_type=ParameterType.INTEGER,
                default_value=1920,
                min_value=64,
                max_value=7680,
                description="Target output horizontal resolution.",
            ),
            "target_height": EffectParameterSchema(
                parameter_id="target_height",
                name="Target Height",
                parameter_type=ParameterType.INTEGER,
                default_value=1080,
                min_value=64,
                max_value=4320,
                description="Target output vertical resolution.",
            ),
            "detail_enhancement": EffectParameterSchema(
                parameter_id="detail_enhancement",
                name="Enable Detail Enhancement",
                parameter_type=ParameterType.BOOLEAN,
                default_value=True,
                description="Post-upscale unsharp edge sharpening.",
            ),
            "sharpen_amount": EffectParameterSchema(
                parameter_id="sharpen_amount",
                name="Sharpen Amount",
                parameter_type=ParameterType.FLOAT,
                default_value=0.25,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Intensity of edge detail recovery.",
            ),
            "pre_denoise": EffectParameterSchema(
                parameter_id="pre_denoise",
                name="Pre-upscale Denoising",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Clean sensor grain before enlarging.",
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

        config = UpscaleConfig(
            algorithm=UpscaleAlgorithm(p["algorithm"]),
            sizing_policy=SizingPolicy(p["sizing_policy"]),
            scale_factor=float(p["scale_factor"]),
            target_width=int(p["target_width"]),
            target_height=int(p["target_height"]),
            detail_enhancement=bool(p["detail_enhancement"]),
            sharpen_amount=float(p["sharpen_amount"]),
            pre_denoise=bool(p["pre_denoise"]),
            is_enabled=True,
        )

        out_frame, _ = self.engine.process_frame(frame, config)
        return out_frame
