"""OMNIA Video Studio — Multicamera Sequence, Angle & Decision Models (Module 20).

Defines authoritative domain models for:
- CameraAngle: A single camera recording with stable ID, asset reference, audio channel map, and sync offset.
- SyncMethod: IN_POINT, OUT_POINT, TIMECODE, AUDIO_WAVEFORM, MANUAL_OFFSET.
- SyncConfidence: NONE, LOW, MEDIUM, HIGH, EXACT.
- AngleSwitchDecision: Recorded editorial cut decision on a shared timeline (start frame, end frame, active angle, audio source).
- MulticamAudioPolicy: LOCKED_MASTER (audio stays on one camera/mix), FOLLOW_VIDEO (audio cuts with video), EXTERNAL_RECORDING.
- MulticamSequence: Persistent multicamera container with synchronized angles, decisions, timeline range, and active audio routing.
- MulticamFlattenResult: Mapping and tracking for flattening multicamera decisions into standard timeline tracks and items.
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


# ==============================================================================
# 1. Enums & Policies
# ==============================================================================

class SyncMethod(str, Enum):
    MANUAL_OFFSET = "MANUAL_OFFSET"
    IN_POINT = "IN_POINT"
    OUT_POINT = "OUT_POINT"
    TIMECODE = "TIMECODE"
    AUDIO_WAVEFORM = "AUDIO_WAVEFORM"


class SyncConfidence(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXACT = "EXACT"


class MulticamAudioPolicy(str, Enum):
    LOCKED_MASTER = "LOCKED_MASTER"          # Audio locked to a primary designated camera
    FOLLOW_VIDEO = "FOLLOW_VIDEO"            # Audio cuts automatically whenever video angle switches
    EXTERNAL_RECORDING = "EXTERNAL_RECORDING"# Audio routed from a dedicated external production track


# ==============================================================================
# 2. Camera Angle Model
# ==============================================================================

@dataclass
class CameraAngle:
    """Individual camera angle/recording within a multicamera sequence."""
    angle_id: str
    asset_id: str
    camera_label: str       # e.g., "CAM A", "Wide Overhead", "Close-up Host"
    display_name: str
    sync_offset_frames: int = 0  # Offset in integer frames relative to multicam sequence frame 0
    in_point_frame: int = 0      # Local source in-point
    out_point_frame: Optional[int] = None # Local source out-point
    audio_track_indices: List[int] = field(default_factory=lambda: [0]) # Audio tracks to mix/monitor
    is_enabled: bool = True
    color: str = "#3B82F6"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "angle_id": self.angle_id,
            "asset_id": self.asset_id,
            "camera_label": self.camera_label,
            "display_name": self.display_name,
            "sync_offset_frames": self.sync_offset_frames,
            "in_point_frame": self.in_point_frame,
            "out_point_frame": self.out_point_frame,
            "audio_track_indices": self.audio_track_indices,
            "is_enabled": self.is_enabled,
            "color": self.color,
            "metadata": self.metadata,
        }


# ==============================================================================
# 3. Angle Switching Decision Model
# ==============================================================================

@dataclass
class AngleSwitchDecision:
    """A persistent editorial cut decision specifying the active camera angle over a timeline range."""
    decision_id: str
    multicam_id: str
    start_frame: int
    end_frame: int
    active_angle_id: str
    audio_angle_id: Optional[str] = None  # None = use sequence audio policy
    revision: int = 1
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "multicam_id": self.multicam_id,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "active_angle_id": self.active_angle_id,
            "audio_angle_id": self.audio_angle_id,
            "revision": self.revision,
            "created_at": self.created_at,
        }


# ==============================================================================
# 4. Synchronization Candidate & Result
# ==============================================================================

@dataclass
class AngleSyncResult:
    """Details and confidence for an individual angle's calculated synchronization alignment."""
    angle_id: str
    asset_id: str
    calculated_offset_frames: int
    method_used: SyncMethod
    confidence: SyncConfidence = SyncConfidence.NONE
    confidence_score: float = 0.0 # 0.0 to 1.0
    drift_detected_frames: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "angle_id": self.angle_id,
            "asset_id": self.asset_id,
            "calculated_offset_frames": self.calculated_offset_frames,
            "method_used": self.method_used.value,
            "confidence": self.confidence.value,
            "confidence_score": round(self.confidence_score, 3),
            "drift_detected_frames": self.drift_detected_frames,
            "warnings": self.warnings,
        }


# ==============================================================================
# 5. Multicamera Sequence Model
# ==============================================================================

@dataclass
class MulticamSequence:
    """Authoritative multicamera container synchronizing multiple angles into an editable whole."""
    multicam_id: str
    project_id: str
    name: str
    angles: List[CameraAngle] = field(default_factory=list)
    decisions: List[AngleSwitchDecision] = field(default_factory=list)
    audio_policy: MulticamAudioPolicy = MulticamAudioPolicy.LOCKED_MASTER
    master_audio_angle_id: Optional[str] = None
    frame_rate: float = 24.0
    duration_frames: int = 0
    width: int = 1920
    height: int = 1080
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1

    def get_angle(self, angle_id: str) -> Optional[CameraAngle]:
        return next((a for a in self.angles if a.angle_id == angle_id), None)

    def get_active_decision_at(self, frame: int) -> Optional[AngleSwitchDecision]:
        for d in self.decisions:
            if d.start_frame <= frame < d.end_frame:
                return d
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "multicam_id": self.multicam_id,
            "project_id": self.project_id,
            "name": self.name,
            "angles": [a.to_dict() for a in self.angles],
            "decisions": [d.to_dict() for d in self.decisions],
            "audio_policy": self.audio_policy.value,
            "master_audio_angle_id": self.master_audio_angle_id,
            "frame_rate": self.frame_rate,
            "duration_frames": self.duration_frames,
            "width": self.width,
            "height": self.height,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }


@dataclass
class MulticamFlattenResult:
    """Report of flattening a multicamera sequence into standard timeline tracks and clips."""
    multicam_id: str
    target_sequence_id: str
    video_track_id: str
    audio_track_id: str
    created_clip_ids: List[str] = field(default_factory=list)
    total_segments_flattened: int = 0
    is_success: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "multicam_id": self.multicam_id,
            "target_sequence_id": self.target_sequence_id,
            "video_track_id": self.video_track_id,
            "audio_track_id": self.audio_track_id,
            "created_clip_ids": self.created_clip_ids,
            "total_segments_flattened": self.total_segments_flattened,
            "is_success": self.is_success,
            "error_message": self.error_message,
        }
