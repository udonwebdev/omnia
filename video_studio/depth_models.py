"""OMNIA Video Studio — Depth Estimation, Depth Maps & 2.5D Compositing Models (Module 32).

Defines serialization models, enums, parameters, and diagnostics for:
- Depth map representations (METRIC, RELATIVE, NORMALIZED, DISPARITY)
- Inversion and orientation flags (INVERTED, STANDARD)
- Edge handling modes for 2.5D parallax (REPLICATE, CLAMP, TRANSPARENT)
- Depth map containers and provenance tracking
- Depth-driven visual effects:
  * Depth slicing / range isolation with cosine feathering
  * Depth-of-Field (DoF) optical blur simulation
  * 2.5D camera parallax displacement / coordinate warping
  * Depth-aware layer occlusion
- Monocular AI depth estimation extension/adapter interface (stubbed/experimental)
- Depth processing telemetry and diagnostics
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import uuid
import time
import numpy as np


class DepthRepresentationType(str, Enum):
    """Depth data semantics and physical scale representation."""
    NORMALIZED = "NORMALIZED"   # Scaled strictly to [0.0, 1.0], 0.0=near, 1.0=far (or reversed if inverted)
    RELATIVE = "RELATIVE"       # Uncalibrated relative disparity / inverse depth
    METRIC = "METRIC"           # Calibrated physical metric distance in meters (from camera)
    DISPARITY = "DISPARITY"     # Stereo disparity in pixels (1/depth relationship)


class DepthEdgeMode(str, Enum):
    """Border and hole filling behavior for 2.5D parallax camera displacement."""
    REPLICATE = "REPLICATE"         # Clamp/replicate border pixels to prevent dark seams
    CLAMP = "CLAMP"                 # Strict clamp to frame boundaries
    TRANSPARENT = "TRANSPARENT"     # Zero alpha for newly exposed parallax background regions


class DepthMapProvenance(str, Enum):
    """Source origin of the depth data."""
    IMPORTED_FILE = "IMPORTED_FILE"           # User-provided grayscale or EXR depth sequence
    CAMERA_SENSOR = "CAMERA_SENSOR"           # Hardware LiDAR / ToF / structured light sensor
    MONOCULAR_ESTIMATION = "MONOCULAR_ESTIMATION" # AI / deep learning monocular depth prediction
    PROCEDURAL = "PROCEDURAL"                 # Synthesized depth ramp or geometric primitive


@dataclass
class DepthDiagnostics:
    """Telemetry and execution metrics for depth operations."""
    processed_frames: int = 0
    clamped_pixel_count: int = 0
    invalid_nan_inf_count: int = 0
    min_depth_encountered: float = 0.0
    max_depth_encountered: float = 1.0
    average_depth: float = 0.5
    displacement_magnitude_max: float = 0.0
    fallback_used: bool = False
    warning_messages: List[str] = field(default_factory=list)
    last_process_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processed_frames": self.processed_frames,
            "clamped_pixel_count": self.clamped_pixel_count,
            "invalid_nan_inf_count": self.invalid_nan_inf_count,
            "min_depth_encountered": round(float(self.min_depth_encountered), 4),
            "max_depth_encountered": round(float(self.max_depth_encountered), 4),
            "average_depth": round(float(self.average_depth), 4),
            "displacement_magnitude_max": round(float(self.displacement_magnitude_max), 3),
            "fallback_used": self.fallback_used,
            "warning_messages": list(self.warning_messages),
            "last_process_duration_ms": round(float(self.last_process_duration_ms), 3),
        }


@dataclass
class DepthMap:
    """In-memory depth map associated with a video frame or clip."""
    map_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    clip_id: str = "default_clip"
    frame_number: int = 0
    width: int = 1920
    height: int = 1080
    data: Optional[np.ndarray] = None  # 2D float32 array in [0.0, 1.0] or raw metric values
    representation_type: DepthRepresentationType = DepthRepresentationType.NORMALIZED
    is_inverted: bool = False           # If True, 1.0 is near and 0.0 is far
    near_plane: float = 0.1             # Near clipping boundary (in metric units or normalized)
    far_plane: float = 100.0            # Far clipping boundary
    provenance: DepthMapProvenance = DepthMapProvenance.IMPORTED_FILE
    confidence_map: Optional[np.ndarray] = None # Optional 2D float32 [0.0, 1.0] confidence array
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        has_data = self.data is not None
        shape = list(self.data.shape) if has_data else [self.height, self.width]
        return {
            "map_id": self.map_id,
            "clip_id": self.clip_id,
            "frame_number": self.frame_number,
            "width": self.width,
            "height": self.height,
            "has_data": has_data,
            "shape": shape,
            "representation_type": self.representation_type.value,
            "is_inverted": self.is_inverted,
            "near_plane": self.near_plane,
            "far_plane": self.far_plane,
            "provenance": self.provenance.value,
            "has_confidence": self.confidence_map is not None,
            "metadata": dict(self.metadata),
        }


@dataclass
class DepthEffectConfig:
    """Comprehensive parameters for depth-aware compositing and 2.5D operations."""
    config_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    clip_id: str = "default_clip"
    enabled: bool = True

    # Depth Normalization & Remapping
    invert_depth: bool = False
    depth_scale: float = 1.0           # Multiplier applied before clamping
    depth_offset: float = 0.0          # Offset applied before clamping
    clamp_min: float = 0.0
    clamp_max: float = 1.0

    # Depth Slicing / Range Isolation (for creating depth-based mattes)
    enable_depth_slice: bool = False
    slice_near: float = 0.2            # Normalized depth near cutoff
    slice_far: float = 0.6             # Normalized depth far cutoff
    slice_feather: float = 0.05        # Cosine feather softness at slice boundaries

    # Depth-of-Field (DoF) Optical Blur Simulation
    enable_dof: bool = False
    dof_focus_distance: float = 0.4    # Plane of sharpest focus in [0.0, 1.0]
    dof_focal_range: float = 0.1       # Depth of field thickness where image remains sharp
    dof_max_blur: float = 15.0         # Maximum Gaussian blur kernel radius in pixels
    dof_feather: float = 0.1           # Transition falloff between in-focus and out-of-focus

    # 2.5D Parallax Camera Displacement
    enable_parallax: bool = False
    parallax_shift_x: float = 0.0      # Horizontal camera displacement in pixels [-100.0, 100.0]
    parallax_shift_y: float = 0.0      # Vertical camera displacement in pixels [-100.0, 100.0]
    parallax_edge_mode: DepthEdgeMode = DepthEdgeMode.REPLICATE
    parallax_focal_plane: float = 0.5  # Depth plane that experiences zero camera displacement

    # Depth-aware Occlusion Compositing
    enable_occlusion: bool = False
    occlusion_layer_depth: float = 0.5 # Depth plane of intersecting virtual graphic/layer
    occlusion_softness: float = 0.02   # Matte edge feathering at occlusion boundary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_id": self.config_id,
            "clip_id": self.clip_id,
            "enabled": self.enabled,
            "invert_depth": self.invert_depth,
            "depth_scale": self.depth_scale,
            "depth_offset": self.depth_offset,
            "clamp_min": self.clamp_min,
            "clamp_max": self.clamp_max,
            "enable_depth_slice": self.enable_depth_slice,
            "slice_near": self.slice_near,
            "slice_far": self.slice_far,
            "slice_feather": self.slice_feather,
            "enable_dof": self.enable_dof,
            "dof_focus_distance": self.dof_focus_distance,
            "dof_focal_range": self.dof_focal_range,
            "dof_max_blur": self.dof_max_blur,
            "dof_feather": self.dof_feather,
            "enable_parallax": self.enable_parallax,
            "parallax_shift_x": self.parallax_shift_x,
            "parallax_shift_y": self.parallax_shift_y,
            "parallax_edge_mode": self.parallax_edge_mode.value,
            "parallax_focal_plane": self.parallax_focal_plane,
            "enable_occlusion": self.enable_occlusion,
            "occlusion_layer_depth": self.occlusion_layer_depth,
            "occlusion_softness": self.occlusion_softness,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DepthEffectConfig":
        edge_mode_raw = data.get("parallax_edge_mode", "REPLICATE")
        try:
            edge_mode = DepthEdgeMode(edge_mode_raw)
        except ValueError:
            edge_mode = DepthEdgeMode.REPLICATE

        return cls(
            config_id=data.get("config_id", str(uuid.uuid4())),
            clip_id=data.get("clip_id", "default_clip"),
            enabled=data.get("enabled", True),
            invert_depth=data.get("invert_depth", False),
            depth_scale=float(data.get("depth_scale", 1.0)),
            depth_offset=float(data.get("depth_offset", 0.0)),
            clamp_min=float(data.get("clamp_min", 0.0)),
            clamp_max=float(data.get("clamp_max", 1.0)),
            enable_depth_slice=data.get("enable_depth_slice", False),
            slice_near=float(data.get("slice_near", 0.2)),
            slice_far=float(data.get("slice_far", 0.6)),
            slice_feather=float(data.get("slice_feather", 0.05)),
            enable_dof=data.get("enable_dof", False),
            dof_focus_distance=float(data.get("dof_focus_distance", 0.4)),
            dof_focal_range=float(data.get("dof_focal_range", 0.1)),
            dof_max_blur=float(data.get("dof_max_blur", 15.0)),
            dof_feather=float(data.get("dof_feather", 0.1)),
            enable_parallax=data.get("enable_parallax", False),
            parallax_shift_x=float(data.get("parallax_shift_x", 0.0)),
            parallax_shift_y=float(data.get("parallax_shift_y", 0.0)),
            parallax_edge_mode=edge_mode,
            parallax_focal_plane=float(data.get("parallax_focal_plane", 0.5)),
            enable_occlusion=data.get("enable_occlusion", False),
            occlusion_layer_depth=float(data.get("occlusion_layer_depth", 0.5)),
            occlusion_softness=float(data.get("occlusion_softness", 0.02)),
        )


class MonocularEstimationAdapter:
    """Extension/Adapter interface for optional Monocular AI Depth Estimation engines.
    
    Adheres strictly to the architectural rule:
    Never synthesize fake depth maps. In the absence of an explicit neural model runtime,
    this returns is_available=False with transparent capability status.
    """
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.is_available = False
        self.model_name = "None (Adapter Stub)"
        self.status_message = "No local monocular depth neural weights bundled."

    def estimate_depth(self, frame_rgb: np.ndarray) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """Attempt to infer a normalized depth map from RGB frame.
        
        Returns:
            Tuple of (depth_array or None, status_dict)
        """
        if not self.is_available:
            return None, {
                "success": False,
                "error": "Monocular depth estimation is EXPERIMENTAL and requires configured model weights.",
                "model_status": self.status_message,
            }
        
        # Extension point for external deep learning weights (MiDaS / DPT / ZoeDepth)
        return None, {"success": False, "error": "Model runtime not loaded."}
