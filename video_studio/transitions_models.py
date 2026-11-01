"""OMNIA Video Studio — Video & Audio Transition Models (Module 12).

Defines canonical transition entities:
- TransitionType: DISSOLVE, FADE_IN, FADE_OUT, FADE_TO_BLACK, FADE_FROM_BLACK,
                  FADE_TO_TRANSPARENT, FADE_FROM_TRANSPARENT, WIPE, PUSH, SLIDE,
                  AUDIO_FADE_IN, AUDIO_FADE_OUT, AUDIO_CROSSFADE
- TransitionAlignment: START_AT_CUT, CENTER_ON_CUT, END_AT_CUT
- TransitionDirection: LEFT_TO_RIGHT, RIGHT_TO_LEFT, TOP_TO_BOTTOM, BOTTOM_TO_TOP
- VideoTransition: Non-destructive transition model placed at a cut or clip edge
- SourceHandleValidationResult: Verification of source frame availability (head/tail handles)
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import time
import uuid

class TransitionType(str, Enum):
    DISSOLVE = "DISSOLVE"
    CROSS_DISSOLVE = "CROSS_DISSOLVE"
    FADE_IN = "FADE_IN"
    FADE_OUT = "FADE_OUT"
    FADE_TO_BLACK = "FADE_TO_BLACK"
    FADE_FROM_BLACK = "FADE_FROM_BLACK"
    FADE_TO_TRANSPARENT = "FADE_TO_TRANSPARENT"
    FADE_FROM_TRANSPARENT = "FADE_FROM_TRANSPARENT"
    WIPE = "WIPE"
    PUSH = "PUSH"
    SLIDE = "SLIDE"
    AUDIO_FADE_IN = "AUDIO_FADE_IN"
    AUDIO_FADE_OUT = "AUDIO_FADE_OUT"
    AUDIO_CROSSFADE = "AUDIO_CROSSFADE"

class TransitionAlignment(str, Enum):
    START_AT_CUT = "START_AT_CUT"      # Starts at cut, extends forward into incoming clip
    CENTER_ON_CUT = "CENTER_ON_CUT"    # Centered on cut point (requires handles on both clips)
    END_AT_CUT = "END_AT_CUT"          # Ends at cut, extends backward into outgoing clip

class TransitionDirection(str, Enum):
    LEFT_TO_RIGHT = "LEFT_TO_RIGHT"
    RIGHT_TO_LEFT = "RIGHT_TO_LEFT"
    TOP_TO_BOTTOM = "TOP_TO_BOTTOM"
    BOTTOM_TO_TOP = "BOTTOM_TO_TOP"

class CrossfadeCurve(str, Enum):
    LINEAR = "LINEAR"
    EQUAL_POWER = "EQUAL_POWER"
    EXPONENTIAL = "EXPONENTIAL"

@dataclass
class SourceHandleValidationResult:
    """Detailed validation check for media handles on outgoing and incoming clips."""
    is_valid: bool
    reason: str = ""
    outgoing_handle_available: int = 0
    outgoing_handle_required: int = 0
    incoming_handle_available: int = 0
    incoming_handle_required: int = 0
    missing_handle_clip_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "reason": self.reason,
            "outgoing_handle_available": self.outgoing_handle_available,
            "outgoing_handle_required": self.outgoing_handle_required,
            "incoming_handle_available": self.incoming_handle_available,
            "incoming_handle_required": self.incoming_handle_required,
            "missing_handle_clip_id": self.missing_handle_clip_id,
        }

@dataclass
class VideoTransition:
    """Canonical model for a video or audio transition between timeline clips or clip boundaries."""
    transition_id: str
    sequence_id: str
    track_id: str
    transition_type: TransitionType
    start_frame: int
    duration_frames: int
    outgoing_clip_id: Optional[str] = None  # None for standalone fade-in
    incoming_clip_id: Optional[str] = None  # None for standalone fade-out
    alignment: TransitionAlignment = TransitionAlignment.CENTER_ON_CUT
    direction: TransitionDirection = TransitionDirection.LEFT_TO_RIGHT
    is_enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)
    # audio settings if this transition couples or represents audio crossfade
    crossfade_curve: CrossfadeCurve = CrossfadeCurve.EQUAL_POWER
    version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.duration_frames

    def contains_frame(self, frame: int) -> bool:
        return self.start_frame <= frame < self.end_frame

    def get_progress(self, frame: int) -> float:
        """Calculates normalized progress p in [0.0, 1.0]."""
        if self.duration_frames <= 0:
            return 1.0
        if frame <= self.start_frame:
            return 0.0
        if frame >= self.end_frame - 1:
            return 1.0
        return float(frame - self.start_frame) / float(self.duration_frames)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "sequence_id": self.sequence_id,
            "track_id": self.track_id,
            "transition_type": self.transition_type.value,
            "start_frame": self.start_frame,
            "duration_frames": self.duration_frames,
            "end_frame": self.end_frame,
            "outgoing_clip_id": self.outgoing_clip_id,
            "incoming_clip_id": self.incoming_clip_id,
            "alignment": self.alignment.value,
            "direction": self.direction.value,
            "is_enabled": self.is_enabled,
            "parameters": self.parameters,
            "crossfade_curve": self.crossfade_curve.value,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "VideoTransition":
        ttype = TransitionType(d["transition_type"])
        align = TransitionAlignment(d.get("alignment", TransitionAlignment.CENTER_ON_CUT.value))
        direction = TransitionDirection(d.get("direction", TransitionDirection.LEFT_TO_RIGHT.value))
        curve = CrossfadeCurve(d.get("crossfade_curve", CrossfadeCurve.EQUAL_POWER.value))
        return cls(
            transition_id=d["transition_id"],
            sequence_id=d["sequence_id"],
            track_id=d["track_id"],
            transition_type=ttype,
            start_frame=d["start_frame"],
            duration_frames=d["duration_frames"],
            outgoing_clip_id=d.get("outgoing_clip_id"),
            incoming_clip_id=d.get("incoming_clip_id"),
            alignment=align,
            direction=direction,
            is_enabled=d.get("is_enabled", True),
            parameters=d.get("parameters", {}),
            crossfade_curve=curve,
            version=d.get("version", "1.0.0"),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
        )
