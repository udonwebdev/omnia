"""OMNIA Video Studio — Chroma Key Effect Processor (Module 23).

Integrates the ChromaKeyEngine directly into the Module 10 video effects pipeline:
- Inherits from IVideoEffectProcessor.
- Registers standard parameter schemas (tolerance, softness, feather, choke, spill, etc.).
- Exposes real-time keying to clip-level effect stacks and timeline compositing.
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
from video_studio.chroma_models import (
    ChromaKeyConfig,
    ChromaKeyType,
    ChromaColorSpace,
    MatteDisplayMode,
    KeyColorSample,
)
from video_studio.chroma_engine import chroma_key_engine, ChromaKeyEngine


class ChromaKeyEffectProcessor(IVideoEffectProcessor):
    """Production-grade chroma key effect processor in Module 10 effects stack."""

    def __init__(self, engine: Optional[ChromaKeyEngine] = None):
        super().__init__(
            effect_id="chroma_key",
            name="Chroma Key & Green Screen",
            category=EffectCategory.COMPOSITING,
        )
        self.engine = engine or chroma_key_engine
        self.backend = ProcessingBackend.CPU
        self._init_schemas()

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "key_type": EffectParameterSchema(
                parameter_id="key_type",
                name="Key Type",
                parameter_type=ParameterType.ENUM,
                default_value="GREEN_SCREEN",
                options=["GREEN_SCREEN", "BLUE_SCREEN", "CUSTOM_COLOR"],
                description="Target background color type.",
            ),
            "color_space": EffectParameterSchema(
                parameter_id="color_space",
                name="Color Space",
                parameter_type=ParameterType.ENUM,
                default_value="LAB",
                options=["LAB", "YCBCR", "HSV", "RGB"],
                description="Color representation for chroma distance.",
            ),
            "key_color_r": EffectParameterSchema(
                parameter_id="key_color_r",
                name="Key Color Red",
                parameter_type=ParameterType.INTEGER,
                default_value=0,
                min_value=0,
                max_value=255,
                is_animatable=True,
                description="Red component of custom key color.",
            ),
            "key_color_g": EffectParameterSchema(
                parameter_id="key_color_g",
                name="Key Color Green",
                parameter_type=ParameterType.INTEGER,
                default_value=255,
                min_value=0,
                max_value=255,
                is_animatable=True,
                description="Green component of custom key color.",
            ),
            "key_color_b": EffectParameterSchema(
                parameter_id="key_color_b",
                name="Key Color Blue",
                parameter_type=ParameterType.INTEGER,
                default_value=0,
                min_value=0,
                max_value=255,
                is_animatable=True,
                description="Blue component of custom key color.",
            ),
            "tolerance": EffectParameterSchema(
                parameter_id="tolerance",
                name="Key Tolerance",
                parameter_type=ParameterType.FLOAT,
                default_value=40.0,
                min_value=1.0,
                max_value=150.0,
                is_animatable=True,
                description="Color distance threshold for key transparency.",
            ),
            "softness": EffectParameterSchema(
                parameter_id="softness",
                name="Edge Softness",
                parameter_type=ParameterType.FLOAT,
                default_value=20.0,
                min_value=0.0,
                max_value=100.0,
                is_animatable=True,
                description="Width of the semi-transparent falloff edge.",
            ),
            "feather_radius": EffectParameterSchema(
                parameter_id="feather_radius",
                name="Feather Radius",
                parameter_type=ParameterType.INTEGER,
                default_value=0,
                min_value=0,
                max_value=30,
                is_animatable=True,
                description="Gaussian blur feathering on the alpha matte.",
            ),
            "choke": EffectParameterSchema(
                parameter_id="choke",
                name="Matte Choke / Expand",
                parameter_type=ParameterType.INTEGER,
                default_value=0,
                min_value=-20,
                max_value=20,
                is_animatable=True,
                description="Erosion (negative) or dilation (positive) of the matte edge.",
            ),
            "spill_suppression": EffectParameterSchema(
                parameter_id="spill_suppression",
                name="Enable Spill Suppression",
                parameter_type=ParameterType.BOOLEAN,
                default_value=True,
                description="Suppress key color bounce on foreground edges.",
            ),
            "spill_strength": EffectParameterSchema(
                parameter_id="spill_strength",
                name="Spill Strength",
                parameter_type=ParameterType.FLOAT,
                default_value=0.8,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Intensity of spill neutralization.",
            ),
            "display_mode": EffectParameterSchema(
                parameter_id="display_mode",
                name="Display Mode",
                parameter_type=ParameterType.ENUM,
                default_value="FOREGROUND_KEYED",
                options=["FOREGROUND_KEYED", "MATTE_ONLY", "COMPOSITE", "ORIGINAL", "SPILL_ONLY"],
                description="Output view for viewport inspection.",
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

        key_type = ChromaKeyType(p["key_type"])
        color_space = ChromaColorSpace(p["color_space"])
        disp_mode = MatteDisplayMode(p["display_mode"])

        if key_type == ChromaKeyType.GREEN_SCREEN:
            sample = KeyColorSample(r=0, g=255, b=0)
        elif key_type == ChromaKeyType.BLUE_SCREEN:
            sample = KeyColorSample(r=0, g=0, b=255)
        else:
            sample = KeyColorSample(r=int(p["key_color_r"]), g=int(p["key_color_g"]), b=int(p["key_color_b"]))

        config = ChromaKeyConfig(
            key_type=key_type,
            color_space=color_space,
            key_samples=[sample],
            tolerance=float(p["tolerance"]),
            softness=float(p["softness"]),
            feather_radius=int(p["feather_radius"]),
            choke=int(p["choke"]),
            spill_suppression=bool(p["spill_suppression"]),
            spill_strength=float(p["spill_strength"]),
            display_mode=disp_mode,
        )

        return self.engine.process_frame(frame, config)
