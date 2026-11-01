"""OMNIA Video Studio — Depth Processing & 2.5D Effect Processor (Module 32).

Integrates the VideoDepthEngine directly into the Module 10 video effects pipeline:
- Inherits from IVideoEffectProcessor.
- Registers parameter schemas for depth slicing, DoF focus blur, 2.5D parallax, and occlusion.
- Exposes non-destructive depth-aware compositing to clip effect stacks.
"""

from typing import Dict, Any, List, Optional
import numpy as np

from video_studio.effects_models import (
    VideoFrameBuffer,
    EffectParameterSchema,
    ParameterType,
    EffectCategory,
    ProcessingBackend,
)
from video_studio.effects_processors import IVideoEffectProcessor
from video_studio.depth_models import (
    DepthEffectConfig,
    DepthMap,
    DepthEdgeMode,
)
from video_studio.depth_engine import VideoDepthEngine


class VideoDepthEffectProcessor(IVideoEffectProcessor):
    """Production-grade depth processing and 2.5D compositing processor in Module 10 effects pipeline."""

    def __init__(self, engine: Optional[VideoDepthEngine] = None):
        super().__init__(
            effect_id="depth_compositing_25d",
            name="Depth & 2.5D Compositing",
            category=EffectCategory.COMPOSITING,
        )
        self.engine = engine or VideoDepthEngine()
        self.backend = ProcessingBackend.CPU
        self._current_depth_map: Optional[DepthMap] = None
        self._init_schemas()

    def set_depth_map(self, depth_map: Optional[DepthMap]) -> None:
        """Bind an active depth map sequence/frame to this processor."""
        self._current_depth_map = depth_map

    def _init_schemas(self) -> None:
        self.parameter_schemas = {
            "invert_depth": EffectParameterSchema(
                parameter_id="invert_depth",
                name="Invert Depth",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Reverse depth polarity (0=far, 1=near).",
            ),
            "depth_scale": EffectParameterSchema(
                parameter_id="depth_scale",
                name="Depth Scale",
                parameter_type=ParameterType.FLOAT,
                default_value=1.0,
                min_value=0.1,
                max_value=10.0,
                is_animatable=True,
                description="Depth map contrast / scale multiplier.",
            ),
            "depth_offset": EffectParameterSchema(
                parameter_id="depth_offset",
                name="Depth Offset",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-1.0,
                max_value=1.0,
                is_animatable=True,
                description="Depth map offset / baseline bias.",
            ),
            "enable_depth_slice": EffectParameterSchema(
                parameter_id="enable_depth_slice",
                name="Enable Depth Slicing",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Isolate a specific depth slice as an alpha matte.",
            ),
            "slice_near": EffectParameterSchema(
                parameter_id="slice_near",
                name="Slice Near Cutoff",
                parameter_type=ParameterType.FLOAT,
                default_value=0.2,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Near cutoff distance for depth slice isolation.",
            ),
            "slice_far": EffectParameterSchema(
                parameter_id="slice_far",
                name="Slice Far Cutoff",
                parameter_type=ParameterType.FLOAT,
                default_value=0.6,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Far cutoff distance for depth slice isolation.",
            ),
            "slice_feather": EffectParameterSchema(
                parameter_id="slice_feather",
                name="Slice Edge Softness",
                parameter_type=ParameterType.FLOAT,
                default_value=0.05,
                min_value=0.0,
                max_value=0.5,
                is_animatable=True,
                description="Feather boundary softness for slice matte.",
            ),
            "enable_dof": EffectParameterSchema(
                parameter_id="enable_dof",
                name="Enable Depth of Field",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Simulate optical lens defocus based on depth.",
            ),
            "dof_focus_distance": EffectParameterSchema(
                parameter_id="dof_focus_distance",
                name="DoF Focus Plane",
                parameter_type=ParameterType.FLOAT,
                default_value=0.4,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Normalized depth plane of sharpest optical focus.",
            ),
            "dof_max_blur": EffectParameterSchema(
                parameter_id="dof_max_blur",
                name="DoF Max Defocus Blur",
                parameter_type=ParameterType.FLOAT,
                default_value=15.0,
                min_value=0.0,
                max_value=60.0,
                is_animatable=True,
                description="Maximum radius of defocus blur kernel.",
            ),
            "enable_parallax": EffectParameterSchema(
                parameter_id="enable_parallax",
                name="Enable 2.5D Parallax",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Simulate camera movement using depth displacement warping.",
            ),
            "parallax_shift_x": EffectParameterSchema(
                parameter_id="parallax_shift_x",
                name="Parallax X Shift",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="Horizontal camera displacement in pixels.",
            ),
            "parallax_shift_y": EffectParameterSchema(
                parameter_id="parallax_shift_y",
                name="Parallax Y Shift",
                parameter_type=ParameterType.FLOAT,
                default_value=0.0,
                min_value=-100.0,
                max_value=100.0,
                is_animatable=True,
                description="Vertical camera displacement in pixels.",
            ),
            "parallax_edge_mode": EffectParameterSchema(
                parameter_id="parallax_edge_mode",
                name="Parallax Edge Mode",
                parameter_type=ParameterType.ENUM,
                default_value="REPLICATE",
                options=["REPLICATE", "CLAMP", "TRANSPARENT"],
                description="Edge fill mode: REPLICATE, CLAMP, or TRANSPARENT.",
            ),
            "enable_occlusion": EffectParameterSchema(
                parameter_id="enable_occlusion",
                name="Enable Depth Occlusion",
                parameter_type=ParameterType.BOOLEAN,
                default_value=False,
                description="Mask out foreground elements behind virtual plane.",
            ),
            "occlusion_layer_depth": EffectParameterSchema(
                parameter_id="occlusion_layer_depth",
                name="Occlusion Layer Plane",
                parameter_type=ParameterType.FLOAT,
                default_value=0.5,
                min_value=0.0,
                max_value=1.0,
                is_animatable=True,
                description="Depth plane where virtual layer intersects.",
            ),
        }

    def process_frame(
        self,
        frame: VideoFrameBuffer,
        parameters: Dict[str, Any],
        render_width: int,
        render_height: int,
    ) -> VideoFrameBuffer:
        """Apply depth-based transformations to the input frame."""
        p = self.validate_parameters(parameters)

        edge_mode_str = p.get("parallax_edge_mode", "REPLICATE")
        try:
            edge_mode = DepthEdgeMode(edge_mode_str)
        except ValueError:
            edge_mode = DepthEdgeMode.REPLICATE

        config = DepthEffectConfig(
            enabled=True,
            invert_depth=bool(p.get("invert_depth", False)),
            depth_scale=float(p.get("depth_scale", 1.0)),
            depth_offset=float(p.get("depth_offset", 0.0)),
            clamp_min=float(p.get("clamp_min", 0.0)),
            clamp_max=float(p.get("clamp_max", 1.0)),
            enable_depth_slice=bool(p.get("enable_depth_slice", False)),
            slice_near=float(p.get("slice_near", 0.2)),
            slice_far=float(p.get("slice_far", 0.6)),
            slice_feather=float(p.get("slice_feather", 0.05)),
            enable_dof=bool(p.get("enable_dof", False)),
            dof_focus_distance=float(p.get("dof_focus_distance", 0.4)),
            dof_focal_range=float(p.get("dof_focal_range", 0.1)),
            dof_max_blur=float(p.get("dof_max_blur", 15.0)),
            dof_feather=float(p.get("dof_feather", 0.1)),
            enable_parallax=bool(p.get("enable_parallax", False)),
            parallax_shift_x=float(p.get("parallax_shift_x", 0.0)),
            parallax_shift_y=float(p.get("parallax_shift_y", 0.0)),
            parallax_edge_mode=edge_mode,
            parallax_focal_plane=float(p.get("parallax_focal_plane", 0.5)),
            enable_occlusion=bool(p.get("enable_occlusion", False)),
            occlusion_layer_depth=float(p.get("occlusion_layer_depth", 0.5)),
            occlusion_softness=float(p.get("occlusion_softness", 0.02)),
        )

        processed_data, _ = self.engine.process_frame(
            frame_rgba=frame.data,
            depth_map=self._current_depth_map,
            config=config,
        )

        return VideoFrameBuffer(
            width=frame.width,
            height=frame.height,
            data=processed_data,
            pixel_format=frame.pixel_format,
            timeline_frame=frame.timeline_frame,
            color_space=frame.color_space,
        )
