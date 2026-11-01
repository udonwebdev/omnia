"""OMNIA Video Studio — Motion Tracking, Object Tracking & Track-to-Effects Models (Module 22).

Defines authoritative domain models for:
- TrackingMethodType: POINT_OPTICAL_FLOW, REGION_TEMPLATE_MATCH, PLANAR_FEATURE_CLUSTER.
- TrackingStatus: IDLE, TRACKING, PAUSED, COMPLETED, TRACK_LOST, FAILED, CANCELLED.
- TrackTargetType: POINT, BOUNDING_BOX, PLANAR_REGION.
- TrackSample: Timestamped motion point (frame, x, y, width, height, angle_rad, scale, confidence, status).
- TrackingSession: Persistent tracking session associated with project, clip, asset, and tracking target.
- TrackApplicationTarget: TRANSFORM_POSITION, TRANSFORM_ROTATION, TRANSFORM_SCALE, MASK_POSITION, EFFECT_PARAM.
- TrackToEffectBinding: Rule mapping tracking samples to animatable properties or effect inputs with offset & smoothing.
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


# ==============================================================================
# 1. Enums & Policies
# ==============================================================================

class TrackingMethodType(str, Enum):
    POINT_OPTICAL_FLOW = "POINT_OPTICAL_FLOW"       # Lucas-Kanade forward/backward validated point tracking
    REGION_TEMPLATE_MATCH = "REGION_TEMPLATE_MATCH" # Normalized cross-correlation template matching
    PLANAR_FEATURE_CLUSTER = "PLANAR_FEATURE_CLUSTER" # RANSAC cluster tracking with rotation and scale


class TrackingStatus(str, Enum):
    IDLE = "IDLE"
    TRACKING = "TRACKING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    TRACK_LOST = "TRACK_LOST"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TrackTargetType(str, Enum):
    POINT = "POINT"
    BOUNDING_BOX = "BOUNDING_BOX"
    PLANAR_REGION = "PLANAR_REGION"


class TrackApplicationTarget(str, Enum):
    TRANSFORM_POSITION = "TRANSFORM_POSITION"
    TRANSFORM_ROTATION = "TRANSFORM_ROTATION"
    TRANSFORM_SCALE = "TRANSFORM_SCALE"
    TRANSFORM_ALL = "TRANSFORM_ALL"
    MASK_POSITION = "MASK_POSITION"
    EFFECT_PARAMETER = "EFFECT_PARAMETER"


# ==============================================================================
# 2. Tracking Samples & Configuration
# ==============================================================================

@dataclass
class TrackSample:
    """Individual frame's measured tracking sample with coordinate geometry and confidence."""
    frame_index: int
    x: float
    y: float
    width: float = 0.0
    height: float = 0.0
    rotation_rad: float = 0.0
    scale: float = 1.0
    confidence: float = 1.0 # 0.0 to 1.0
    is_valid: bool = True
    tracking_lost: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "width": round(self.width, 3),
            "height": round(self.height, 3),
            "rotation_rad": round(self.rotation_rad, 5),
            "scale": round(self.scale, 5),
            "confidence": round(self.confidence, 3),
            "is_valid": self.is_valid,
            "tracking_lost": self.tracking_lost,
        }


@dataclass
class TrackingSession:
    """Persistent tracking session bound to a timeline clip or media asset."""
    session_id: str
    project_id: str
    clip_id: str
    asset_id: str
    target_name: str
    method: TrackingMethodType = TrackingMethodType.POINT_OPTICAL_FLOW
    target_type: TrackTargetType = TrackTargetType.POINT
    status: TrackingStatus = TrackingStatus.IDLE
    initial_x: float = 0.0
    initial_y: float = 0.0
    initial_width: float = 64.0
    initial_height: float = 64.0
    start_frame: int = 0
    end_frame: int = 0
    samples: Dict[int, TrackSample] = field(default_factory=dict) # frame_index -> TrackSample
    average_confidence: float = 1.0
    lost_track_frames: List[int] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def get_sample_at(self, frame: int) -> Optional[TrackSample]:
        return self.samples.get(frame)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "clip_id": self.clip_id,
            "asset_id": self.asset_id,
            "target_name": self.target_name,
            "method": self.method.value,
            "target_type": self.target_type.value,
            "status": self.status.value,
            "initial_x": round(self.initial_x, 3),
            "initial_y": round(self.initial_y, 3),
            "initial_width": round(self.initial_width, 3),
            "initial_height": round(self.initial_height, 3),
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "total_samples": len(self.samples),
            "average_confidence": round(self.average_confidence, 3),
            "lost_track_frames": self.lost_track_frames,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ==============================================================================
# 3. Track-to-Effects & Keyframe Binding
# ==============================================================================

@dataclass
class TrackToEffectBinding:
    """Configuration linking a tracking session's motion data to a destination property."""
    binding_id: str
    session_id: str
    target_clip_id: str
    application_target: TrackApplicationTarget = TrackApplicationTarget.TRANSFORM_POSITION
    offset_x: float = 0.0
    offset_y: float = 0.0
    invert_motion: bool = False
    relative_to_initial: bool = True
    target_property_id: Optional[str] = None
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "session_id": self.session_id,
            "target_clip_id": self.target_clip_id,
            "application_target": self.application_target.value,
            "offset_x": round(self.offset_x, 3),
            "offset_y": round(self.offset_y, 3),
            "invert_motion": self.invert_motion,
            "relative_to_initial": self.relative_to_initial,
            "target_property_id": self.target_property_id,
            "is_active": self.is_active,
        }
