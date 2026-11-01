"""OMNIA Video Studio — Video Stabilization, Motion Analysis & Camera Correction Models (Module 21).

Defines authoritative domain models for:
- MotionModelType: TRANSLATION (dx, dy), RIGID (dx, dy, da), SIMILARITY (dx, dy, da, scale), AFFINE (2x3).
- StabilizationMode: SMOOTH_MOTION (preserves intentional camera trajectory), LOCK_CAMERA (attempts absolute stillness).
- MotionTransform: 2D affine transform matrix (dx, dy, angle_rad, scale) representing relative inter-frame motion.
- FrameMotionRecord: Frame-indexed motion observation including raw transform, confidence score, feature count, and cut flag.
- MotionAnalysisReport: Persisted motion trajectory of an entire asset/clip, metadata, feature density, and tracking statistics.
- StabilizationConfig: User controls (smoothing radius, crop compensation, zoom mode, motion model, enabled state).
- CorrectiveTransform: Computed smoothed path delta (inverse transform + adaptive zoom) ready for warp application.
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


# ==============================================================================
# 1. Enums & Policies
# ==============================================================================

class MotionModelType(str, Enum):
    TRANSLATION = "TRANSLATION"   # (dx, dy)
    RIGID = "RIGID"               # Translation + Rotation (dx, dy, d_theta)
    SIMILARITY = "SIMILARITY"     # Translation + Rotation + Uniform Scale
    AFFINE = "AFFINE"             # Full 6-DOF 2D Affine


class StabilizationMode(str, Enum):
    SMOOTH_MOTION = "SMOOTH_MOTION" # Preserves pans/tilts, removes high-frequency jitter
    LOCK_CAMERA = "LOCK_CAMERA"     # Locks position to initial frame anchor


class BorderFillMode(str, Enum):
    BLACK_BORDER = "BLACK_BORDER"
    REPLICATE = "REPLICATE"
    REFLECT = "REFLECT"


# ==============================================================================
# 2. Motion Data Models
# ==============================================================================

@dataclass
class MotionTransform:
    """Rigid/Similarity transform parameters between frame t-1 and frame t."""
    dx: float = 0.0
    dy: float = 0.0
    rotation_rad: float = 0.0
    scale: float = 1.0

    def to_matrix(self) -> List[List[float]]:
        """Returns standard 2x3 affine matrix [[a, b, tx], [c, d, ty]]."""
        cos_a = self.scale * (1.0 if abs(self.rotation_rad) < 1e-6 else float(np.cos(self.rotation_rad)))
        sin_a = self.scale * (0.0 if abs(self.rotation_rad) < 1e-6 else float(np.sin(self.rotation_rad)))
        return [
            [cos_a, -sin_a, self.dx],
            [sin_a, cos_a, self.dy],
        ]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dx": round(self.dx, 4),
            "dy": round(self.dy, 4),
            "rotation_rad": round(self.rotation_rad, 5),
            "scale": round(self.scale, 5),
        }


import numpy as np


@dataclass
class FrameMotionRecord:
    """Individual frame's measured inter-frame camera motion and tracking quality."""
    frame_index: int
    transform: MotionTransform
    feature_count: int = 0
    confidence_score: float = 1.0 # 0.0 to 1.0
    is_scene_cut: bool = False
    tracking_lost: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "transform": self.transform.to_dict(),
            "feature_count": self.feature_count,
            "confidence_score": round(self.confidence_score, 3),
            "is_scene_cut": self.is_scene_cut,
            "tracking_lost": self.tracking_lost,
        }


@dataclass
class MotionAnalysisReport:
    """Comprehensive, persistable motion trajectory dataset for a media asset or clip."""
    report_id: str
    asset_id: str
    total_frames: int
    motion_model: MotionModelType
    frame_records: List[FrameMotionRecord] = field(default_factory=list)
    average_confidence: float = 1.0
    scene_cut_frames: List[int] = field(default_factory=list)
    has_tracking_failure: bool = False
    analyzed_width: int = 1280
    analyzed_height: int = 720
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "asset_id": self.asset_id,
            "total_frames": self.total_frames,
            "motion_model": self.motion_model.value,
            "frame_records": [r.to_dict() for r in self.frame_records],
            "average_confidence": round(self.average_confidence, 3),
            "scene_cut_frames": self.scene_cut_frames,
            "has_tracking_failure": self.has_tracking_failure,
            "analyzed_width": self.analyzed_width,
            "analyzed_height": self.analyzed_height,
            "created_at": self.created_at,
        }


# ==============================================================================
# 3. Stabilization Configuration & Corrections
# ==============================================================================

@dataclass
class StabilizationConfig:
    """User-adjustable parameters controlling trajectory smoothing and frame cropping."""
    is_enabled: bool = True
    motion_model: MotionModelType = MotionModelType.SIMILARITY
    mode: StabilizationMode = StabilizationMode.SMOOTH_MOTION
    smoothing_radius: int = 15          # Temporal window in frames for Gaussian/box smoothing
    smooth_translation: bool = True
    smooth_rotation: bool = True
    smooth_scale: bool = True
    auto_crop_zoom: bool = True         # Automatically scales image to hide black boundary borders
    manual_zoom_factor: float = 1.08    # Safety zoom ratio (1.08 = 8% crop zoom)
    border_fill: BorderFillMode = BorderFillMode.REPLICATE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_enabled": self.is_enabled,
            "motion_model": self.motion_model.value,
            "mode": self.mode.value,
            "smoothing_radius": self.smoothing_radius,
            "smooth_translation": self.smooth_translation,
            "smooth_rotation": self.smooth_rotation,
            "smooth_scale": self.smooth_scale,
            "auto_crop_zoom": self.auto_crop_zoom,
            "manual_zoom_factor": self.manual_zoom_factor,
            "border_fill": self.border_fill.value,
        }


@dataclass
class CorrectiveTransform:
    """Exact 2x3 affine matrix to warp source frame into stabilized viewer space."""
    frame_index: int
    matrix_2x3: List[List[float]] = field(default_factory=lambda: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    applied_zoom: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "matrix_2x3": self.matrix_2x3,
            "applied_zoom": round(self.applied_zoom, 4),
        }
