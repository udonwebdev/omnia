"""OMNIA Video Studio — Lighting & Relighting Effect Processor (Module 29).

Integrates the VideoLightingEngine directly into the Module 10 video effects pipeline:
- Inherits from IVideoEffectProcessor.
- Registers standard parameter schemas (exposure_stops, brightness, contrast, highlights, shadows,
  whites, blacks, gamma, light_region_count, etc.).
- Exposes non-destructive lighting and relighting to clip-level effect stacks and timeline compositing.
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
from video_studio.lighting_models import (
    LightingEngineDocument,
    GlobalExposureTonalConfig,
    LocalLightRegion,
    LightType,
    LightBlendMode,
    RelightingEngineMode,
)
from video_studio.lighting_engine import video_lighting_engine, VideoLightingEngine


class VideoLightingEffectProcessor(IVideoEffectProcessor):
    """Production-grade lighting, exposure, and relighting processor in Module 10 effects stack."""

    def __init__(self, engine: Optional[VideoLightingEngine] = None):
        super().__init__(
            effect_id="lighting_relighting",
            name="Lighting, Exposure & Relighting",
            category=EffectCategory.FILTER,
        )
        self.engine = engine or video_lighting_engine
        self.backend = ProcessingBackend.CPU
        self._init_schemas()

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "exposure_stops": EffectParameterSchema(
                parameter_id="exposure_stops",
                name="Exposure (EV Stops)",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-5.0,
                max_value=5.0,
                is_animatable=True,
                description="Exposure compensation in photographic stops (2^EV multiplier).",
            ),
            "brightness": EffectParameterSchema(
                parameter_id="brightness",
                name="Brightness",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="Linear brightness offset.",
            ),
            "contrast": EffectParameterSchema(
                parameter_id="contrast",
                name="Contrast",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.1,
                max_value=3.0,
                is_animatable=True,
                description="Contrast adjustment around pivot.",
            ),
            "contrast_pivot": EffectParameterSchema(
                parameter_id="contrast_pivot",
                name="Contrast Pivot",
                parameter_type=ParameterType.FLOAT,
                default_value=0.435,
                min_value=0.0,
                max_value=1.0,
                description="Pivot center point for contrast expansion.",
            ),
            "highlights": EffectParameterSchema(
                parameter_id="highlights",
                name="Highlights",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="High tonal region boost or recovery.",
            ),
            "shadows": EffectParameterSchema(
                parameter_id="shadows",
                name="Shadows",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="Low tonal region lift or compression.",
            ),
            "whites": EffectParameterSchema(
                parameter_id="whites",
                name="Whites",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="Peak white point expansion or clamping.",
            ),
            "blacks": EffectParameterSchema(
                parameter_id="blacks",
                name="Blacks",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="Deep black level crushing or lifting.",
            ),
            "gamma": EffectParameterSchema(
                parameter_id="gamma",
                name="Gamma / Midtones",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.2,
                max_value=3.0,
                is_animatable=True,
                description="Midtone gamma power curve.",
            ),
            "temperature": EffectParameterSchema(
                parameter_id="temperature",
                name="Color Temperature",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="Warmth / Coolness color balance.",
            ),
            "tint": EffectParameterSchema(
                parameter_id="tint",
                name="Tint",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="Green vs Magenta color balance.",
            ),
            # Primary localized spotlight / point light quick controls
            "enable_local_light": EffectParameterSchema(
                parameter_id="enable_local_light",
                name="Enable Local Light",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Enable localized 2D light source.",
            ),
            "local_light_x": EffectParameterSchema(
                parameter_id="local_light_x",
                name="Local Light X",
                parameter_type=ParameterType.FLOAT,
                default_value=0.5,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Normalized X position (0=left, 1=right).",
            ),
            "local_light_y": EffectParameterSchema(
                parameter_id="local_light_y",
                name="Local Light Y",
                parameter_type=ParameterType.FLOAT,
                default_value=0.5,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Normalized Y position (0=top, 1=bottom).",
            ),
            "local_light_radius": EffectParameterSchema(
                parameter_id="local_light_radius",
                name="Local Light Radius",
                parameter_type=ParameterType.FLOAT,
                default_value=0.3,
                min_value=0.01,
                max_value=1.0,
                is_animatable=True,
                description="Light spread radius.",
            ),
            "local_light_intensity": EffectParameterSchema(
                parameter_id="local_light_intensity",
                name="Local Light Intensity",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=-2.0,
                max_value=3.0,
                is_animatable=True,
                description="Light intensity multiplier.",
            ),
            "local_light_feather": EffectParameterSchema(
                parameter_id="local_light_feather",
                name="Local Light Feather",
                parameter_type=ParameterType.FLOAT,
                default_value=0.5,
                min_value=0.01,
                max_value=1.0,
                is_animatable=True,
                description="Edge softness / falloff gradient.",
            ),
            "local_light_blend": EffectParameterSchema(
                parameter_id="local_light_blend",
                name="Local Light Blend Mode",
                parameter_type=ParameterType.ENUM,
                default_value="ADD",
                options=["ADD", "SCREEN", "SOFT_LIGHT", "OVERLAY", "MULTIPLY", "COLOR_DODGE"],
                description="Blend mode for light transfer.",
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

        doc = LightingEngineDocument(
            is_enabled=True,
            engine_mode=RelightingEngineMode.DETERMINISTIC_2D,
            global_tone=GlobalExposureTonalConfig(
                exposure_stops=float(p["exposure_stops"]),
                brightness=float(p["brightness"]),
                contrast=float(p["contrast"]),
                contrast_pivot=float(p["contrast_pivot"]),
                highlights=float(p["highlights"]),
                shadows=float(p["shadows"]),
                whites=float(p["whites"]),
                blacks=float(p["blacks"]),
                gamma=float(p["gamma"]),
                temperature=float(p["temperature"]),
                tint=float(p["tint"]),
            ),
        )

        if bool(p["enable_local_light"]):
            region = LocalLightRegion(
                name="Parametric Spot",
                is_enabled=True,
                light_type=LightType.POINT_RADIAL,
                pos_x=float(p["local_light_x"]),
                pos_y=float(p["local_light_y"]),
                radius_x=float(p["local_light_radius"]),
                radius_y=float(p["local_light_radius"]),
                feather=float(p["local_light_feather"]),
                intensity=float(p["local_light_intensity"]),
                blend_mode=LightBlendMode(p["local_light_blend"]),
            )
            doc.light_regions.append(region)

        out_frame, _ = self.engine.process_frame(frame, doc)
        return out_frame
