"""OMNIA Video Studio — Film Grain & Video Texture Effect Processor (Module 31).

Integrates the VideoGrainEngine directly into the Module 10 video effects pipeline:
- Inherits from IVideoEffectProcessor.
- Registers standard parameter schemas (grain_type, intensity, scale, luma_weight, chroma_weight,
  shadow_weight, midtone_weight, highlight_weight, temporal_mode, base_seed, enable_gate_weave,
  halation_mode, enable_film_wear).
- Exposes non-destructive procedural film grain and texture synthesis to clip effect stacks.
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
from video_studio.grain_models import (
    FilmGrainConfig,
    GrainType,
    TemporalGrainMode,
    HalationMode,
    AnalogTextureConfig,
)
from video_studio.grain_engine import video_grain_engine, VideoGrainEngine


class VideoGrainEffectProcessor(IVideoEffectProcessor):
    """Production-grade film grain and analog texture processor in Module 10 effects stack."""

    def __init__(self, engine: Optional[VideoGrainEngine] = None):
        super().__init__(
            effect_id="film_grain_texture",
            name="Film Grain & Analog Texture",
            category=EffectCategory.FILTER,
        )
        self.engine = engine or video_grain_engine
        self.backend = ProcessingBackend.CPU
        self._init_schemas()

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "intensity": EffectParameterSchema(
                parameter_id="intensity",
                name="Grain Intensity",
                parameter_type=ParameterType.FLOAT,
                default_value=0.25,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Overall film grain amplitude.",
            ),
            "scale": EffectParameterSchema(
                parameter_id="scale",
                name="Grain Size / Scale",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.5,
                max_value=4.0,
                is_animatable=True,
                description="Spatial grain cluster size (1.0 = 35mm micro-grain, 2.5 = 16mm coarse).",
            ),
            "grain_type": EffectParameterSchema(
                parameter_id="grain_type",
                name="Grain Distribution Type",
                parameter_type=ParameterType.ENUM,
                default_value="GAUSSIAN",
                options=["GAUSSIAN", "COARSE", "FINE", "ORGANIC"],
                description="Statistical noise distribution model.",
            ),
            "luma_weight": EffectParameterSchema(
                parameter_id="luma_weight",
                name="Luma Grain Weight",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Monochromatic silver halide grain contribution.",
            ),
            "chroma_weight": EffectParameterSchema(
                parameter_id="chroma_weight",
                name="Chroma Grain Weight",
                parameter_type=ParameterType.FLOAT,
                default_value=0.25,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Color dye cloud variation contribution.",
            ),
            "shadow_weight": EffectParameterSchema(
                parameter_id="shadow_weight",
                name="Shadow Grain Weight",
                parameter_type=ParameterType.FLOAT,
                default_value=0.85,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Grain visibility in low shadows.",
            ),
            "midtone_weight": EffectParameterSchema(
                parameter_id="midtone_weight",
                name="Midtone Grain Weight",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Grain visibility in midtone exposures.",
            ),
            "highlight_weight": EffectParameterSchema(
                parameter_id="highlight_weight",
                name="Highlight Grain Weight",
                parameter_type=ParameterType.FLOAT,
                default_value=0.35,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Grain visibility in bright highlights.",
            ),
            "temporal_mode": EffectParameterSchema(
                parameter_id="temporal_mode",
                name="Temporal Behavior Mode",
                parameter_type=ParameterType.ENUM,
                default_value="FRAME_VARYING",
                options=["FRAME_VARYING", "FIXED", "TEMPORALLY_COHERENT"],
                description="Grain animation policy across frames.",
            ),
            "base_seed": EffectParameterSchema(
                parameter_id="base_seed",
                name="PRNG Base Seed",
                parameter_type=ParameterType.INTEGER,
                default_value=1337,
                min_value=1,
                max_value=999999,
                description="Deterministic pseudo-random seed.",
            ),
            "enable_gate_weave": EffectParameterSchema(
                parameter_id="enable_gate_weave",
                name="Enable Gate Weave Jitter",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Simulate subtle mechanical projector/camera gate jitter.",
            ),
            "halation_mode": EffectParameterSchema(
                parameter_id="halation_mode",
                name="Halation Mode",
                parameter_type=ParameterType.ENUM,
                default_value="OFF",
                options=["OFF", "RED_ORANGE", "DIFFUSE_WHITE"],
                description="Emulsion highlight glow bloom.",
            ),
            "enable_film_wear": EffectParameterSchema(
                parameter_id="enable_film_wear",
                name="Enable Dust & Scratches",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Procedural dust specks and vertical scratches.",
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

        config = FilmGrainConfig(
            is_enabled=True,
            grain_type=GrainType(p["grain_type"]),
            intensity=float(p["intensity"]),
            scale=float(p["scale"]),
            luma_weight=float(p["luma_weight"]),
            chroma_weight=float(p["chroma_weight"]),
            shadow_weight=float(p["shadow_weight"]),
            midtone_weight=float(p["midtone_weight"]),
            highlight_weight=float(p["highlight_weight"]),
            temporal_mode=TemporalGrainMode(p["temporal_mode"]),
            base_seed=int(p["base_seed"]),
            texture=AnalogTextureConfig(
                enable_gate_weave=bool(p["enable_gate_weave"]),
                weave_amplitude_x=0.5 if bool(p["enable_gate_weave"]) else 0.0,
                weave_amplitude_y=0.5 if bool(p["enable_gate_weave"]) else 0.0,
                halation_mode=HalationMode(p["halation_mode"]),
                enable_film_wear=bool(p["enable_film_wear"]),
                dust_density=0.0003 if bool(p["enable_film_wear"]) else 0.0,
                scratch_intensity=0.5 if bool(p["enable_film_wear"]) else 0.0,
                scratch_count=1 if bool(p["enable_film_wear"]) else 0,
            ),
        )

        out_frame, _ = self.engine.process_frame(frame, config)
        return out_frame
