"""OMNIA Video Studio — Video Speed Control, Time Remapping & Frame Rate Models (Module 15).

Domain models for non-destructive time remapping:
- RationalTime: Precision rational time representation for non-accumulating frame calculations.
- TimecodeUtils: Precision conversion for 23.976, 24, 25, 29.97 DF/NDF, 30, 50, 59.94 DF/NDF, 60 fps.
- InterpolationMode: Frame interpolation modes (DUPLICATION, BLENDING, OPTICAL_FLOW, AI_INTERPOLATION).
- AudioSpeedMode: Audio behavior during speed remapping (PRESERVE_PITCH, RESAMPLE_PITCH, MUTE, HOLD).
- SpeedCurvePoint: A control point on a variable-speed ramp curve with tangent controls.
- FreezeRegion: Declared freeze intervals holding a specific source frame.
- TimeRemapDocument: Canonical versioned specification of a clip's speed / time-remapping profile.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import math
import fractions
import time
import uuid

# ==============================================================================
# 1. Precise Time Representation & Enums
# ==============================================================================

class FrameRateStandard(str, Enum):
    FPS_23_976 = "23.976"
    FPS_24 = "24"
    FPS_25 = "25"
    FPS_29_97 = "29.97"
    FPS_30 = "30"
    FPS_50 = "50"
    FPS_59_94 = "59.94"
    FPS_60 = "60"

class FrameInterpolationMode(str, Enum):
    """Supported frame interpolation techniques."""
    DUPLICATION = "DUPLICATION"       # Nearest neighbor / hold duplicate frames
    BLENDING = "BLENDING"             # Cross-dissolve alpha blending between adjacent source frames
    OPTICAL_FLOW = "OPTICAL_FLOW"     # Vector-based motion estimation interpolation (where backend is present)
    AI_INTERPOLATION = "AI_INTERPOLATION" # Neural network motion model (optional external backend)

class AudioSpeedMode(str, Enum):
    """Audio handling policy when speed changes."""
    RESAMPLE_PITCH = "RESAMPLE_PITCH"   # Speed changes tape-style with pitch shifting (natural resampling)
    PRESERVE_PITCH = "PRESERVE_PITCH"   # Time-stretch algorithm preserving original pitch (phase vocoder / WSOLA)
    MUTE = "MUTE"                       # Mute audio completely during speed changes or freezes
    HOLD = "HOLD"                       # Micro-looping / hold buffer (for experimental effects)

class SpeedCurveInterpolation(str, Enum):
    """Interpolation between speed ramp control points."""
    LINEAR = "LINEAR"
    BEZIER = "BEZIER"
    HOLD = "HOLD"

# ==============================================================================
# 2. Precision Rational Time & Timecode Utilities
# ==============================================================================

@dataclass(frozen=True)
class RationalTime:
    """Exact rational timestamp avoiding floating-point drift over long timelines."""
    numerator: int
    denominator: int

    def __post_init__(self):
        if self.denominator == 0:
            raise ValueError("RationalTime denominator cannot be zero.")

    @property
    def seconds(self) -> float:
        return float(self.numerator) / float(self.denominator)

    @classmethod
    def from_frames(cls, frame: int, frame_rate: float) -> "RationalTime":
        # Handle fractional rates with exact rational approximations
        if abs(frame_rate - 23.976) < 0.01:
            return cls(frame * 1001, 24000)
        elif abs(frame_rate - 29.97) < 0.01:
            return cls(frame * 1001, 30000)
        elif abs(frame_rate - 59.94) < 0.01:
            return cls(frame * 1001, 60000)
        else:
            frac = fractions.Fraction(frame_rate).limit_denominator(100000)
            # frame / (num/den) = frame * den / num
            return cls(frame * frac.denominator, frac.numerator)

    def to_frame(self, target_rate: float) -> int:
        if abs(target_rate - 23.976) < 0.01:
            # seconds * 24000 / 1001
            return int(round((self.numerator * 24000) / (self.denominator * 1001)))
        elif abs(target_rate - 29.97) < 0.01:
            return int(round((self.numerator * 30000) / (self.denominator * 1001)))
        elif abs(target_rate - 59.94) < 0.01:
            return int(round((self.numerator * 60000) / (self.denominator * 1001)))
        else:
            return int(round(self.seconds * target_rate))


class TimecodeConverter:
    """Accurate SMPTE timecode parser and formatter supporting Drop-Frame and Non-Drop-Frame."""

    @staticmethod
    def frames_to_timecode(frame: int, frame_rate: float, is_drop_frame: bool = False) -> str:
        if frame < 0:
            frame = 0

        if is_drop_frame and (abs(frame_rate - 29.97) < 0.01 or abs(frame_rate - 59.94) < 0.01):
            # SMPTE standard drop frame: drop 2 frames every minute except tens of minutes (at 29.97)
            drop_frames = 2 if abs(frame_rate - 29.97) < 0.01 else 4
            frames_per_minute = int(round(frame_rate * 60))
            frames_per_10minutes = int(round(frame_rate * 600))
            nominal_fps = int(math.ceil(frame_rate))

            d = frame // frames_per_10minutes
            m = frame % frames_per_10minutes
            if m > drop_frames:
                frame_adj = frame + (drop_frames * 9 * d) + drop_frames * ((m - drop_frames) // (frames_per_minute - drop_frames))
            else:
                frame_adj = frame + (drop_frames * 9 * d)

            ff = frame_adj % nominal_fps
            ss = (frame_adj // nominal_fps) % 60
            mm = (frame_adj // (nominal_fps * 60)) % 60
            hh = (frame_adj // (nominal_fps * 3600))
            return f"{hh:02d}:{mm:02d}:{ss:02d};{ff:02d}"
        else:
            # Non-drop frame
            nominal_fps = max(1, int(round(frame_rate)))
            ff = frame % nominal_fps
            ss = (frame // nominal_fps) % 60
            mm = (frame // (nominal_fps * 60)) % 60
            hh = (frame // (nominal_fps * 3600))
            return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

    @staticmethod
    def timecode_to_frames(timecode: str, frame_rate: float, is_drop_frame: bool = False) -> int:
        clean = timecode.strip()
        sep = ";" if ";" in clean else ":"
        parts = clean.split(sep)
        if len(parts) != 4:
            raise ValueError(f"Invalid SMPTE timecode format: '{timecode}'. Expected HH:MM:SS:FF or HH:MM:SS;FF")

        hh, mm, ss, ff = (int(p) for p in parts)
        nominal_fps = max(1, int(round(frame_rate)))

        if is_drop_frame and (";" in clean or is_drop_frame):
            drop_frames = 2 if abs(frame_rate - 29.97) < 0.01 else 4
            total_minutes = 60 * hh + mm
            frames = (nominal_fps * 3600 * hh) + (nominal_fps * 60 * mm) + (nominal_fps * ss) + ff
            frames -= drop_frames * (total_minutes - (total_minutes // 10))
            return max(0, frames)
        else:
            return (nominal_fps * 3600 * hh) + (nominal_fps * 60 * mm) + (nominal_fps * ss) + ff

# ==============================================================================
# 3. Time Remap Models & Control Points
# ==============================================================================

@dataclass
class SpeedCurvePoint:
    """A control point on a variable speed ramp curve."""
    point_id: str
    sequence_frame: int       # Timeline frame offset relative to item start
    speed: float              # Speed multiplier (e.g. 0.5 = 50%, 2.0 = 200%)
    interpolation: SpeedCurveInterpolation = SpeedCurveInterpolation.LINEAR
    handle_left_x: float = 0.0
    handle_left_y: float = 0.0
    handle_right_x: float = 0.0
    handle_right_y: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "point_id": self.point_id,
            "sequence_frame": self.sequence_frame,
            "speed": self.speed,
            "interpolation": self.interpolation.value,
            "handle_left_x": self.handle_left_x,
            "handle_left_y": self.handle_left_y,
            "handle_right_x": self.handle_right_x,
            "handle_right_y": self.handle_right_y,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SpeedCurvePoint":
        return cls(
            point_id=data.get("point_id", f"sp_{uuid.uuid4().hex[:8]}"),
            sequence_frame=int(data.get("sequence_frame", 0)),
            speed=float(data.get("speed", 1.0)),
            interpolation=SpeedCurveInterpolation(data.get("interpolation", "LINEAR")),
            handle_left_x=float(data.get("handle_left_x", 0.0)),
            handle_left_y=float(data.get("handle_left_y", 0.0)),
            handle_right_x=float(data.get("handle_right_x", 0.0)),
            handle_right_y=float(data.get("handle_right_y", 0.0)),
        )

@dataclass
class FreezeRegion:
    """A freeze-frame interval holding a specific source frame."""
    region_id: str
    timeline_start_frame: int   # Relative to timeline item start
    duration_frames: int        # Timeline duration of the hold
    frozen_source_frame: int    # Exact source frame to hold

    @property
    def timeline_end_frame(self) -> int:
        return self.timeline_start_frame + self.duration_frames

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "timeline_start_frame": self.timeline_start_frame,
            "duration_frames": self.duration_frames,
            "frozen_source_frame": self.frozen_source_frame,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FreezeRegion":
        return cls(
            region_id=data.get("region_id", f"fr_{uuid.uuid4().hex[:8]}"),
            timeline_start_frame=int(data.get("timeline_start_frame", 0)),
            duration_frames=int(data.get("duration_frames", 24)),
            frozen_source_frame=int(data.get("frozen_source_frame", 0)),
        )

# ==============================================================================
# 4. Canonical Time Remap Document
# ==============================================================================

@dataclass
class TimeRemapDocument:
    """Canonical versioned document specifying time remapping for a timeline clip."""
    remap_id: str
    item_id: str
    source_reference_id: str
    constant_speed: float = 1.0
    is_reverse: bool = False
    is_variable: bool = False
    speed_points: List[SpeedCurvePoint] = field(default_factory=list)
    freeze_regions: List[FreezeRegion] = field(default_factory=list)
    interpolation_mode: FrameInterpolationMode = FrameInterpolationMode.DUPLICATION
    audio_speed_mode: AudioSpeedMode = AudioSpeedMode.RESAMPLE_PITCH
    min_speed: float = 0.01
    max_speed: float = 100.0
    version: int = 1
    revision: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "remap_id": self.remap_id,
            "item_id": self.item_id,
            "source_reference_id": self.source_reference_id,
            "constant_speed": self.constant_speed,
            "is_reverse": self.is_reverse,
            "is_variable": self.is_variable,
            "speed_points": [p.to_dict() for p in self.speed_points],
            "freeze_regions": [r.to_dict() for r in self.freeze_regions],
            "interpolation_mode": self.interpolation_mode.value,
            "audio_speed_mode": self.audio_speed_mode.value,
            "min_speed": self.min_speed,
            "max_speed": self.max_speed,
            "version": self.version,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeRemapDocument":
        return cls(
            remap_id=data.get("remap_id", f"remap_{uuid.uuid4().hex[:8]}"),
            item_id=data["item_id"],
            source_reference_id=data.get("source_reference_id", ""),
            constant_speed=float(data.get("constant_speed", 1.0)),
            is_reverse=bool(data.get("is_reverse", False)),
            is_variable=bool(data.get("is_variable", False)),
            speed_points=[SpeedCurvePoint.from_dict(p) for p in data.get("speed_points", [])],
            freeze_regions=[FreezeRegion.from_dict(r) for r in data.get("freeze_regions", [])],
            interpolation_mode=FrameInterpolationMode(data.get("interpolation_mode", "DUPLICATION")),
            audio_speed_mode=AudioSpeedMode(data.get("audio_speed_mode", "RESAMPLE_PITCH")),
            min_speed=float(data.get("min_speed", 0.01)),
            max_speed=float(data.get("max_speed", 100.0)),
            version=int(data.get("version", 1)),
            revision=int(data.get("revision", 1)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )
