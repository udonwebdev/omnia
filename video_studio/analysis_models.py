"""OMNIA Video Studio — Media Analysis, Stream & Preview Domain Models (Module 3).

Establishes normalized models for:
- Multi-stream representations (Video, Audio, Subtitle, Data)
- Detailed technical parameters (VFR/CFR, Interlacing, Rotation, Color/HDR, Timecodes)
- Audio peak waveforms and silence detection intervals
- Thumbnails, contact sheets, and preview frame requests
- Analysis job state machines and progress tracking
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time
import uuid

# ==============================================================================
# 1. Stream Types & Detailed Enums
# ==============================================================================

class StreamKind(str, Enum):
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    SUBTITLE = "SUBTITLE"
    METADATA = "METADATA"

class InterlaceMode(str, Enum):
    PROGRESSIVE = "PROGRESSIVE"
    INTERLACED_TFF = "INTERLACED_TFF"  # Top Field First
    INTERLACED_BFF = "INTERLACED_BFF"  # Bottom Field First
    UNKNOWN = "UNKNOWN"

class HDRStandard(str, Enum):
    SDR = "SDR"
    HDR10 = "HDR10"
    HDR10_PLUS = "HDR10_PLUS"
    HLG = "HLG"
    DOLBY_VISION = "DOLBY_VISION"
    UNKNOWN = "UNKNOWN"

class WaveformResolution(str, Enum):
    LOW = "LOW"            # 16 samples per sec
    MEDIUM = "MEDIUM"      # 64 samples per sec
    HIGH = "HIGH"          # 256 samples per sec
    TIMELINE = "TIMELINE"  # 1024 samples per sec

class ChannelMode(str, Enum):
    COMBINED = "COMBINED"
    PER_CHANNEL = "PER_CHANNEL"

class AnalysisJobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PROBING = "PROBING"
    ANALYZING = "ANALYZING"
    GENERATING_DERIVATIVES = "GENERATING_DERIVATIVES"
    FINALIZING = "FINALIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

# ==============================================================================
# 2. Granular Stream Descriptors
# ==============================================================================

@dataclass
class VideoStreamDetails:
    """Detailed technical profile for an individual video stream."""
    stream_id: str
    stream_index: int = 0
    codec: str = "h264"
    codec_profile: Optional[str] = "High"
    codec_level: Optional[str] = "4.1"
    width: int = 1920
    height: int = 1080
    display_width: int = 1920
    display_height: int = 1080
    pixel_aspect_ratio: str = "1:1"
    frame_rate: float = 24.0
    average_frame_rate: float = 24.0
    time_base: str = "1/24"
    bit_depth: int = 8
    pixel_format: str = "yuv420p"
    color_space: str = "Rec.709"
    transfer_characteristics: str = "bt709"
    color_primaries: str = "bt709"
    hdr_standard: HDRStandard = HDRStandard.SDR
    rotation_degrees: int = 0
    interlace_mode: InterlaceMode = InterlaceMode.PROGRESSIVE
    is_vfr: bool = False
    bitrate_kbps: Optional[int] = None
    duration_seconds: float = 0.0
    total_frames: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "stream_index": self.stream_index,
            "codec": self.codec,
            "codec_profile": self.codec_profile,
            "codec_level": self.codec_level,
            "width": self.width,
            "height": self.height,
            "display_width": self.display_width,
            "display_height": self.display_height,
            "pixel_aspect_ratio": self.pixel_aspect_ratio,
            "frame_rate": self.frame_rate,
            "average_frame_rate": self.average_frame_rate,
            "time_base": self.time_base,
            "bit_depth": self.bit_depth,
            "pixel_format": self.pixel_format,
            "color_space": self.color_space,
            "transfer_characteristics": self.transfer_characteristics,
            "color_primaries": self.color_primaries,
            "hdr_standard": self.hdr_standard.value,
            "rotation_degrees": self.rotation_degrees,
            "interlace_mode": self.interlace_mode.value,
            "is_vfr": self.is_vfr,
            "bitrate_kbps": self.bitrate_kbps,
            "duration_seconds": self.duration_seconds,
            "total_frames": self.total_frames,
        }

@dataclass
class AudioStreamDetails:
    """Detailed technical profile for an individual audio stream."""
    stream_id: str
    stream_index: int = 0
    codec: str = "aac"
    sample_rate: int = 48000
    channels: int = 2
    channel_layout: str = "stereo"
    bit_depth: int = 16
    bitrate_kbps: Optional[int] = None
    language: Optional[str] = None
    title: Optional[str] = None
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "stream_index": self.stream_index,
            "codec": self.codec,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "channel_layout": self.channel_layout,
            "bit_depth": self.bit_depth,
            "bitrate_kbps": self.bitrate_kbps,
            "language": self.language,
            "title": self.title,
            "duration_seconds": self.duration_seconds,
        }

@dataclass
class SubtitleStreamDetails:
    """Detailed profile for an embedded or sidecar subtitle track."""
    stream_id: str
    stream_index: int = 0
    codec: str = "srt"
    language: Optional[str] = "en"
    title: Optional[str] = None
    is_forced: bool = False
    is_default: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "stream_index": self.stream_index,
            "codec": self.codec,
            "language": self.language,
            "title": self.title,
            "is_forced": self.is_forced,
            "is_default": self.is_default,
        }

# ==============================================================================
# 3. Waveform & Silence Models
# ==============================================================================

@dataclass
class ChannelWaveform:
    """Normalized min/max audio peaks for a single audio channel."""
    channel_index: int
    channel_name: str  # e.g., "Left", "Right", "Center"
    sample_count: int
    peak_min: List[float] = field(default_factory=list)  # -1.0 to 0.0
    peak_max: List[float] = field(default_factory=list)  # 0.0 to 1.0

@dataclass
class AudioPeakAnalysis:
    """Comprehensive peak, RMS, and silence evaluation for an audio stream."""
    stream_index: int
    channels: int
    max_peak_db: float = -0.1
    overall_rms_db: float = -18.0
    has_clipping: bool = False
    silence_intervals: List[Dict[str, float]] = field(default_factory=list)  # [{"start": 0.0, "end": 2.5}]

@dataclass
class WaveformDataset:
    """Authoritative waveform output generated for an asset."""
    asset_id: str
    stream_index: int
    resolution: WaveformResolution
    channel_mode: ChannelMode
    channels: List[ChannelWaveform] = field(default_factory=list)
    combined_waveform: Optional[ChannelWaveform] = None
    peak_analysis: Optional[AudioPeakAnalysis] = None
    analysis_version: str = "1.0.0"
    created_at: float = field(default_factory=time.time)

# ==============================================================================
# 4. Thumbnail & Preview Models
# ==============================================================================

@dataclass
class ThumbnailRequest:
    asset_id: str
    timestamp_seconds: float = 1.0
    width: int = 320
    height: int = 180
    format: str = "jpeg"
    quality: int = 85

@dataclass
class ContactSheetRequest:
    asset_id: str
    duration_seconds: float = 10.0
    frame_count: int = 9
    columns: int = 3
    fps: float = 24.0

@dataclass
class ContactSheetFrame:
    frame_index: int
    timestamp_seconds: float
    timecode_str: str
    image_uri: str

@dataclass
class ContactSheetResult:
    asset_id: str
    columns: int = 3
    rows: int = 3
    total_frames: int = 9
    frames: List[ContactSheetFrame] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

# ==============================================================================
# 5. Comprehensive Analysis Report
# ==============================================================================

@dataclass
class MediaAnalysisReport:
    """Authoritative output of the Media Analysis Pipeline."""
    asset_id: str
    fingerprint: str
    analysis_version: str = "1.0.0"
    container_format: str = "unknown"
    overall_bitrate_kbps: Optional[int] = None
    duration_seconds: float = 0.0
    start_timecode: str = "00:00:00:00"
    is_drop_frame: bool = False
    stream_count: int = 0
    video_streams: List[VideoStreamDetails] = field(default_factory=list)
    audio_streams: List[AudioStreamDetails] = field(default_factory=list)
    subtitle_streams: List[SubtitleStreamDetails] = field(default_factory=list)
    default_thumbnail_uri: Optional[str] = None
    has_waveform: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    analyzed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "fingerprint": self.fingerprint,
            "analysis_version": self.analysis_version,
            "container_format": self.container_format,
            "overall_bitrate_kbps": self.overall_bitrate_kbps,
            "duration_seconds": self.duration_seconds,
            "start_timecode": self.start_timecode,
            "is_drop_frame": self.is_drop_frame,
            "stream_count": self.stream_count,
            "video_streams": [v.to_dict() for v in self.video_streams],
            "audio_streams": [a.to_dict() for a in self.audio_streams],
            "subtitle_streams": [s.to_dict() for s in self.subtitle_streams],
            "default_thumbnail_uri": self.default_thumbnail_uri,
            "has_waveform": self.has_waveform,
            "analyzed_at": self.analyzed_at,
        }
