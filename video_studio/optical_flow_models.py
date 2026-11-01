"""OMNIA Video Studio — Optical Flow, Motion Vectors & Motion Analysis Models (Module 33).

Defines authoritative domain models for:
- MotionVectorFieldType: DENSE, SPARSE, BLOCK_MATCHED
- FlowAlgorithmType: FARNEBACK_DENSE, PYRAMIDAL_LK_SPARSE, BLOCK_MATCHING, DIS_DENSE
- FlowQualityPreset: FAST_PREVIEW, BALANCED, STUDIO_HIGH_QUALITY
- FlowVectorCoordinateSystem: IMAGE_PIXELS_CARTESIAN (dx rightwards, dy downwards)
- FlowDirection: FORWARD (source_frame -> target_frame), BACKWARD (target_frame -> source_frame)
- FlowFieldStatus: VALID, SCENE_CUT_DETECTED, ESTIMATION_FAILED, DEGRADED
- MotionVector2D: Representation for sparse vector samples
- MotionFieldMetadata: Complete provenance, source assets, timestamps, frame dims, algorithm settings
- MotionVectorField: Complete versioned serializable motion container:
  * Dense vector tensor (H, W, 2) float32 (dx, dy)
  * Confidence map (H, W) float32 [0.0, 1.0]
  * Occlusion / disocclusion mask (H, W) uint8 (0=valid, 255=occluded)
  * Invalid-region mask (H, W) bool
  * Forward/backward consistency error map (H, W) float32
- MotionAnalysisConfig: Quality, algorithm selection, pyramid scales, consistency check threshold
- MotionDiagnostics: Processing latency, mean flow magnitude, scene cut flag, valid pixel percentage
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


class MotionVectorFieldType(str, Enum):
    """Density and coverage category of the motion field."""
    DENSE = "DENSE"                     # Pixel-dense (H, W, 2) flow field
    SPARSE = "SPARSE"                   # Sparse feature points with explicit coordinates
    BLOCK_MATCHED = "BLOCK_MATCHED"     # Regular grid / macroblock motion vectors


class FlowAlgorithmType(str, Enum):
    """Computer vision optical flow algorithm family."""
    FARNEBACK_DENSE = "FARNEBACK_DENSE"         # Polynomial expansion dense flow (OpenCV calcOpticalFlowFarneback)
    DIS_DENSE = "DIS_DENSE"                     # Dense Inverse Search (Fast / High Accuracy DIS flow)
    PYRAMIDAL_LK_SPARSE = "PYRAMIDAL_LK_SPARSE" # Sparse Lucas-Kanade with pyramidal feature tracking
    BLOCK_MATCHING = "BLOCK_MATCHING"           # Diamond / full-search macroblock correlation


class FlowQualityPreset(str, Enum):
    """Quality and performance tuning profiles."""
    FAST_PREVIEW = "FAST_PREVIEW"               # Downscaled / low-iteration for real-time playback
    BALANCED = "BALANCED"                       # Standard production editing balance
    STUDIO_HIGH_QUALITY = "STUDIO_HIGH_QUALITY" # Multi-scale fine pyramid, max iterations for rendering & export


class FlowVectorCoordinateSystem(str, Enum):
    """Coordinate system conventions."""
    IMAGE_PIXELS_CARTESIAN = "IMAGE_PIXELS_CARTESIAN" # dx points rightwards, dy points downwards in pixels


class FlowDirection(str, Enum):
    """Temporal direction of the motion estimation."""
    FORWARD = "FORWARD"     # Motion from frame T to frame T+1
    BACKWARD = "BACKWARD"   # Motion from frame T+1 to frame T
    BIDIRECTIONAL = "BIDIRECTIONAL" # Both directions evaluated and consistency-checked


class FlowFieldStatus(str, Enum):
    """Integrity and validity status of the motion field."""
    VALID = "VALID"
    SCENE_CUT_DETECTED = "SCENE_CUT_DETECTED" # Large discontinuity / cut detected; vectors zeroed/invalidated
    ESTIMATION_FAILED = "ESTIMATION_FAILED"   # Severe texture loss or dimension mismatch
    DEGRADED = "DEGRADED"                     # Low confidence / partial texture tracking


@dataclass
class MotionVector2D:
    """Individual sparse motion vector."""
    x: float
    y: float
    dx: float
    dy: float
    confidence: float = 1.0
    status: str = "TRACKED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": round(float(self.x), 2),
            "y": round(float(self.y), 2),
            "dx": round(float(self.dx), 3),
            "dy": round(float(self.dy), 3),
            "confidence": round(float(self.confidence), 3),
            "status": self.status,
        }


@dataclass
class MotionDiagnostics:
    """Execution telemetry and motion statistics."""
    execution_time_ms: float = 0.0
    mean_flow_magnitude: float = 0.0
    max_flow_magnitude: float = 0.0
    valid_vector_percentage: float = 100.0
    scene_cut_detected: bool = False
    occlusion_percentage: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_time_ms": round(float(self.execution_time_ms), 2),
            "mean_flow_magnitude": round(float(self.mean_flow_magnitude), 3),
            "max_flow_magnitude": round(float(self.max_flow_magnitude), 3),
            "valid_vector_percentage": round(float(self.valid_vector_percentage), 2),
            "scene_cut_detected": self.scene_cut_detected,
            "occlusion_percentage": round(float(self.occlusion_percentage), 2),
            "warnings": list(self.warnings),
        }


@dataclass
class MotionAnalysisConfig:
    """Configuration parameters for optical flow estimation."""
    algorithm: FlowAlgorithmType = FlowAlgorithmType.FARNEBACK_DENSE
    quality_preset: FlowQualityPreset = FlowQualityPreset.BALANCED
    direction: FlowDirection = FlowDirection.BIDIRECTIONAL

    # Farneback specific parameters
    pyr_scale: float = 0.5
    levels: int = 3
    win_size: int = 15
    iterations: int = 3
    poly_n: int = 5
    poly_sigma: float = 1.2

    # Verification & scene-cut thresholds
    scene_cut_threshold: float = 35.0         # Mean pixel luma difference triggering cut invalidation
    consistency_threshold: float = 1.5         # Forward-backward Euclidean consistency limit (pixels)
    min_confidence_cutoff: float = 0.2         # Vectors below this are flagged as invalid

    # Performance limits
    downscale_factor: float = 1.0              # 1.0 = native resolution; 0.5 = half-res preview
    max_resolution_width: int = 3840
    max_resolution_height: int = 2160

    def to_dict(self) -> Dict[str, Any]:
        return {
            "algorithm": self.algorithm.value,
            "quality_preset": self.quality_preset.value,
            "direction": self.direction.value,
            "pyr_scale": self.pyr_scale,
            "levels": self.levels,
            "win_size": self.win_size,
            "iterations": self.iterations,
            "poly_n": self.poly_n,
            "poly_sigma": self.poly_sigma,
            "scene_cut_threshold": self.scene_cut_threshold,
            "consistency_threshold": self.consistency_threshold,
            "min_confidence_cutoff": self.min_confidence_cutoff,
            "downscale_factor": self.downscale_factor,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MotionAnalysisConfig":
        return cls(
            algorithm=FlowAlgorithmType(data.get("algorithm", FlowAlgorithmType.FARNEBACK_DENSE.value)),
            quality_preset=FlowQualityPreset(data.get("quality_preset", FlowQualityPreset.BALANCED.value)),
            direction=FlowDirection(data.get("direction", FlowDirection.BIDIRECTIONAL.value)),
            pyr_scale=float(data.get("pyr_scale", 0.5)),
            levels=int(data.get("levels", 3)),
            win_size=int(data.get("win_size", 15)),
            iterations=int(data.get("iterations", 3)),
            poly_n=int(data.get("poly_n", 5)),
            poly_sigma=float(data.get("poly_sigma", 1.2)),
            scene_cut_threshold=float(data.get("scene_cut_threshold", 35.0)),
            consistency_threshold=float(data.get("consistency_threshold", 1.5)),
            min_confidence_cutoff=float(data.get("min_confidence_cutoff", 0.2)),
            downscale_factor=float(data.get("downscale_factor", 1.0)),
        )


@dataclass
class MotionVectorField:
    """First-class serializable container storing estimated motion between two video frames."""
    field_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str = "default_asset"
    source_frame_index: int = 0
    target_frame_index: int = 1
    source_pts_seconds: float = 0.0
    target_pts_seconds: float = 0.04
    width: int = 1920
    height: int = 1080
    field_type: MotionVectorFieldType = MotionVectorFieldType.DENSE
    coordinate_system: FlowVectorCoordinateSystem = FlowVectorCoordinateSystem.IMAGE_PIXELS_CARTESIAN
    direction: FlowDirection = FlowDirection.FORWARD
    status: FlowFieldStatus = FlowFieldStatus.VALID

    # Dense vectors: (height, width, 2) float32 array where channel 0 is dx, channel 1 is dy
    dense_flow: Optional[np.ndarray] = None
    # Backward flow for bidirectional verification: (height, width, 2) float32
    backward_flow: Optional[np.ndarray] = None

    # Confidence map: (height, width) float32 [0.0, 1.0]
    confidence_map: Optional[np.ndarray] = None
    # Occlusion mask: (height, width) uint8 (255=occluded, 0=valid)
    occlusion_mask: Optional[np.ndarray] = None
    # Invalid region mask: (height, width) bool
    invalid_mask: Optional[np.ndarray] = None

    # Sparse representation (used when field_type == SPARSE)
    sparse_vectors: List[MotionVector2D] = field(default_factory=list)

    diagnostics: MotionDiagnostics = field(default_factory=MotionDiagnostics)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        has_dense = self.dense_flow is not None
        dense_shape = list(self.dense_flow.shape) if has_dense else []
        return {
            "field_id": self.field_id,
            "asset_id": self.asset_id,
            "source_frame_index": self.source_frame_index,
            "target_frame_index": self.target_frame_index,
            "source_pts_seconds": round(float(self.source_pts_seconds), 4),
            "target_pts_seconds": round(float(self.target_pts_seconds), 4),
            "width": self.width,
            "height": self.height,
            "field_type": self.field_type.value,
            "coordinate_system": self.coordinate_system.value,
            "direction": self.direction.value,
            "status": self.status.value,
            "has_dense_flow": has_dense,
            "dense_shape": dense_shape,
            "sparse_count": len(self.sparse_vectors),
            "diagnostics": self.diagnostics.to_dict(),
            "created_at": self.created_at,
        }
