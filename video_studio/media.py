"""OMNIA Video Studio — Media Engine Boundary & Metadata Foundation (Module 0).

Establishes the structural domain models, timecode representations, and media descriptors
for future professional workflows (video, audio, transparent assets, color spaces, proxies).
Does not invoke or require FFmpeg or any low-level media library at this stage.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time

class MediaType(str, Enum):
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"
    GRAPHIC = "GRAPHIC"
    SUBTITLE = "SUBTITLE"
    COMPOUND = "COMPOUND"

class ColorSpace(str, Enum):
    REC709 = "REC709"
    REC2020 = "REC2020"
    SRGB = "SRGB"
    DISPLAY_P3 = "DISPLAY_P3"
    ACESCG = "ACESCG"
    ACESCC = "ACESCC"
    LINEAR = "LINEAR"

@dataclass
class Timecode:
    """Frame-accurate SMPTE timecode representation."""
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    frames: int = 0
    fps: float = 24.0
    is_drop_frame: bool = False

    def to_frames(self) -> int:
        total_seconds = (self.hours * 3600) + (self.minutes * 60) + self.seconds
        return int(total_seconds * self.fps) + self.frames

    def __str__(self) -> str:
        delim = ";" if self.is_drop_frame else ":"
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}{delim}{self.frames:02d}"

@dataclass
class AudioStreamDescriptor:
    stream_index: int = 0
    codec: str = "pcm_s16le"
    sample_rate: int = 48000
    channels: int = 2
    channel_layout: str = "stereo"
    bit_depth: int = 16
    bitrate_kbps: Optional[int] = None

@dataclass
class VideoStreamDescriptor:
    stream_index: int = 0
    codec: str = "h264"
    width: int = 1920
    height: int = 1080
    pixel_aspect_ratio: str = "1:1"
    frame_rate: float = 24.0
    color_space: ColorSpace = ColorSpace.REC709
    bit_depth: int = 8
    has_alpha: bool = False
    duration_sec: float = 0.0
    total_frames: int = 0
    bitrate_kbps: Optional[int] = None

@dataclass
class MediaAssetDescriptor:
    """Authoritative metadata descriptor for any ingested media item."""
    asset_id: str
    file_path: str
    media_type: MediaType
    container_format: str = "mp4"
    duration_seconds: float = 0.0
    start_timecode: Timecode = field(default_factory=Timecode)
    video_streams: List[VideoStreamDescriptor] = field(default_factory=list)
    audio_streams: List[AudioStreamDescriptor] = field(default_factory=list)
    has_proxy: bool = False
    proxy_file_path: Optional[str] = None
    has_waveform: bool = False
    waveform_data_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    file_size_bytes: int = 0
    content_hash_sha256: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
