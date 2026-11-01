"""OMNIA Video Studio — Lens Distortion & Optical Correction Effect Processor (Module 30).

Integrates the VideoLensEngine directly into the Module 10 video effects pipeline:
- Inherits from IVideoEffectProcessor.
- Registers standard parameter schemas (k1, k2, k3, p1, p2, center_x, center_y, ca_red, ca_blue,
  vignette_gain, border_mode, auto_crop_scale).
- Exposes non-destructive geometric distortion and optical correction to clip effect stacks.
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
from video_studio.lens_models import (
    LensCorrectionConfig,
    LensModelType,
    BorderHandlingMode,
)
from video_studio.lens_engine import video_lens_engine, VideoLensEngine


class VideoLensEffectProcessor(IVideoEffectProcessor):
    """Production-grade optical lens correction processor in Module 10 effects stack."""

    def __init__(self, engine: Optional[VideoLensEngine] = None):
        super().__init__(
            effect_id="lens_distortion_correction",
            name="Lens Distortion & Optical Correction",
            category=EffectCategory.TRANSFORM,
        )
        self.engine = engine or video_lens_engine
        self.backend = ProcessingBackend.CPU
        self._init_schemas()

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "strength": EffectParameterSchema(
                parameter_id="strength",
                name="Correction Strength",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.0,
                max_value=2.0,
                is_animatable=True,
                description="Overall distortion correction intensity.",
            ),
            "k1": EffectParameterSchema(
                parameter_id="k1",
                name="Radial Distortion k1",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-1.0,
                max_value=1.0,
                is_animatable=True,
                description="Primary radial coefficient (barrel < 0, pincushion > 0).",
            ),
            "k2": EffectParameterSchema(
                parameter_id="k2",
                name="Radial Distortion k2",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-1.0,
                max_value=1.0,
                is_animatable=True,
                description="Secondary radial coefficient.",
            ),
            "k3": EffectParameterSchema(
                parameter_id="k3",
                name="Radial Distortion k3",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-1.0,
                max_value=1.0,
                is_animatable=True,
                description="Tertiary radial coefficient.",
            ),
            "p1": EffectParameterSchema(
                parameter_id="p1",
                name="Tangential Distortion p1",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-0.2,
                max_value=0.2,
                is_animatable=True,
                description="Tangential decentering coefficient x.",
            ),
            "p2": EffectParameterSchema(
                parameter_id="p2",
                name="Tangential Distortion p2",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-0.2,
                max_value=0.2,
                is_animatable=True,
                description="Tangential decentering coefficient y.",
            ),
            "center_x": EffectParameterSchema(
                parameter_id="center_x",
                name="Optical Center X",
                parameter_type=ParameterType.FLOAT,
                default_value=0.5,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Principal point horizontal coordinate.",
            ),
            "center_y": EffectParameterSchema(
                parameter_id="center_y",
                name="Optical Center Y",
                parameter_type=ParameterType.FLOAT,
                default_value=0.5,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Principal point vertical coordinate.",
            ),
            "enable_ca_correction": EffectParameterSchema(
                parameter_id="enable_ca_correction",
                name="Enable Chromatic Aberration Correction",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Correct lateral chromatic color fringing.",
            ),
            "ca_red_displacement": EffectParameterSchema(
                parameter_id="ca_red_displacement",
                name="CA Red Radial Shift (%)",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-5.0,
                max_value=5.0,
                is_animatable=True,
                description="Radial warp scale for red channel relative to green.",
            ),
            "ca_blue_displacement": EffectParameterSchema(
                parameter_id="ca_blue_displacement",
                name="CA Blue Radial Shift (%)",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-5.0,
                max_value=5.0,
                is_animatable=True,
                description="Radial warp scale for blue channel relative to green.",
            ),
            "enable_vignette_correction": EffectParameterSchema(
                parameter_id="enable_vignette_correction",
                name="Enable Vignetting Correction",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Brighten optical corner light falloff.",
            ),
            "vignette_gain": EffectParameterSchema(
                parameter_id="vignette_gain",
                name="Vignette Gain",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=0.0,
                max_value=3.0,
                is_animatable=True,
                description="Exposure boost applied at image corners.",
            ),
            "border_mode": EffectParameterSchema(
                parameter_id="border_mode",
                name="Border Handling Mode",
                parameter_type=ParameterType.ENUM,
                default_value="CLAMP_EDGE",
                options=["CLAMP_EDGE", "TRANSPARENT", "REFLECT", "CROP_TO_VALID"],
                description="Border fill behavior for unmapped pixels.",
            ),
            "auto_crop_scale": EffectParameterSchema(
                parameter_id="auto_crop_scale",
                name="Auto Crop Scale",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=1.0,
                max_value=2.0,
                is_animatable=True,
                description="Uniform scale to eliminate black border fringes when CROP_TO_VALID.",
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

        config = LensCorrectionConfig(
            is_enabled=True,
            model_type=LensModelType.BROWN_CONRADY,
            strength=float(p["strength"]),
            k1=float(p["k1"]),
            k2=float(p["k2"]),
            k3=float(p["k3"]),
            p1=float(p["p1"]),
            p2=float(p["p2"]),
            center_x=float(p["center_x"]),
            center_y=float(p["center_y"]),
            enable_ca_correction=bool(p["enable_ca_correction"]),
            ca_red_displacement=float(p["ca_red_displacement"]),
            ca_blue_displacement=float(p["ca_blue_displacement"]),
            enable_vignette_correction=bool(p["enable_vignette_correction"]),
            vignette_gain=float(p["vignette_gain"]),
            border_mode=BorderHandlingMode(p["border_mode"]),
            auto_crop_scale=float(p["auto_crop_scale"]),
        )

        out_frame, _ = self.engine.process_frame(frame, config)
        return out_frame
