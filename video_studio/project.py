"""OMNIA Video Studio — Project Model Foundation (Module 0).

Establishes the minimal contracts and typed hierarchy for a future Video Studio project:
Project -> Bins -> Sequences -> Tracks -> Clips -> Effects -> Markers -> Version History.
Establishes data models only; does not construct an active timeline engine.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time
from video_studio.media import Timecode, ColorSpace

class TrackKind(str, Enum):
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    GRAPHICS = "GRAPHICS"
    SUBTITLE = "SUBTITLE"
    ADJUSTMENT = "ADJUSTMENT"

@dataclass
class Keyframe:
    time_offset_frames: int
    value: Any
    interpolation: str = "LINEAR"  # "LINEAR", "BEZIER", "HOLD"
    in_handle: Optional[List[float]] = None
    out_handle: Optional[List[float]] = None

@dataclass
class ClipEffect:
    effect_id: str
    effect_type: str  # e.g. "color_wheel", "chroma_key", "transform"
    is_enabled: bool = True
    parameters: Dict[str, Any] = field(default_factory=dict)
    keyframes: Dict[str, List[Keyframe]] = field(default_factory=dict)

@dataclass
class TimelineClip:
    clip_id: str
    asset_id: str
    name: str
    start_frame_timeline: int
    duration_frames: int
    source_in_frame: int
    source_out_frame: int
    speed: float = 1.0
    is_muted: bool = False
    is_locked: bool = False
    effects: List[ClipEffect] = field(default_factory=list)

@dataclass
class TimelineTrack:
    track_id: str
    name: str
    kind: TrackKind
    index: int
    is_muted: bool = False
    is_solo: bool = False
    is_locked: bool = False
    clips: List[TimelineClip] = field(default_factory=list)

@dataclass
class SequenceMarker:
    marker_id: str
    frame: int
    name: str
    comment: str = ""
    color_hex: str = "#00f0ff"

@dataclass
class Sequence:
    sequence_id: str
    name: str
    frame_rate: float = 24.0
    width: int = 1920
    height: int = 1080
    color_space: ColorSpace = ColorSpace.REC709
    start_timecode: Timecode = field(default_factory=Timecode)
    tracks: List[TimelineTrack] = field(default_factory=list)
    markers: List[SequenceMarker] = field(default_factory=list)

@dataclass
class MediaBin:
    bin_id: str
    name: str
    parent_bin_id: Optional[str] = None
    asset_ids: List[str] = field(default_factory=list)

@dataclass
class ProjectVersionSnapshot:
    version_num: int
    timestamp: float
    description: str
    author: str
    snapshot_hash: str

@dataclass
class VideoProject:
    """Canonical model for a Video Studio Project."""
    project_id: str
    name: str
    version: str = "1.0.0"
    author: str = "omnia"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    master_settings: Dict[str, Any] = field(default_factory=lambda: {
        "default_fps": 24.0,
        "default_width": 1920,
        "default_height": 1080,
        "audio_sample_rate": 48000,
        "color_space": "REC709",
    })
    bins: List[MediaBin] = field(default_factory=list)
    sequences: List[Sequence] = field(default_factory=list)
    active_sequence_id: Optional[str] = None
    history: List[ProjectVersionSnapshot] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
