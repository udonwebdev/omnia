"""OMNIA Video Studio — Normalized Media Asset Models & Types (Module 2).

Defines the normalized domain models for all media types, containers, codecs,
color spaces, time representations, proxy relationships, generated media derivations,
and asset lifecycle states.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time
import uuid

# ==============================================================================
# 1. Media Types & Classification
# ==============================================================================

class AssetMediaType(str, Enum):
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    IMAGE = "IMAGE"
    GRAPHIC = "GRAPHIC"
    TRANSPARENT_ASSET = "TRANSPARENT_ASSET"
    SUBTITLE = "SUBTITLE"
    CAPTION = "CAPTION"
    LUT = "LUT"
    FONT = "FONT"
    TEMPLATE = "TEMPLATE"
    PROJECT = "PROJECT"
    PROXY = "PROXY"
    GENERATED = "GENERATED"
    RECORDING = "RECORDING"
    OTHER = "OTHER"

class AssetLifecycleStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    IMPORTING = "IMPORTING"
    VALIDATING = "VALIDATING"
    INDEXING = "INDEXING"
    READY = "READY"
    MISSING = "MISSING"
    OFFLINE = "OFFLINE"
    CORRUPTED = "CORRUPTED"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"

class ContainerFormat(str, Enum):
    MP4 = "mp4"
    MOV = "mov"
    MKV = "mkv"
    WEBM = "webm"
    MXF = "mxf"
    AVI = "avi"
    WAV = "wav"
    AIFF = "aiff"
    MP3 = "mp3"
    FLAC = "flac"
    OGG = "ogg"
    PNG = "png"
    JPEG = "jpeg"
    TIFF = "tiff"
    EXR = "exr"
    SVG = "svg"
    CUBE = "cube"
    SRT = "srt"
    VTT = "vtt"
    TTF = "ttf"
    OTF = "otf"
    WOFF2 = "woff2"
    UNKNOWN = "unknown"

class VideoCodec(str, Enum):
    H264 = "h264"
    HEVC = "hevc"
    PRORES = "prores"
    DNXHD = "dnxhd"
    DNXHR = "dnxhr"
    AV1 = "av1"
    VP9 = "vp9"
    VP8 = "vp8"
    RAW = "raw"
    PNG_IMAGE = "png"
    JPEG_IMAGE = "jpeg"
    UNKNOWN = "unknown"

class AudioCodec(str, Enum):
    AAC = "aac"
    PCM_S16LE = "pcm_s16le"
    PCM_S24LE = "pcm_s24le"
    PCM_FLOAT = "pcm_f32le"
    OPUS = "opus"
    MP3 = "mp3"
    FLAC = "flac"
    VORBIS = "vorbis"
    UNKNOWN = "unknown"

class FrameRateMode(str, Enum):
    CFR = "CFR"        # Constant Frame Rate
    VFR = "VFR"        # Variable Frame Rate
    UNKNOWN = "UNKNOWN"

class MediaRelationshipType(str, Enum):
    ORIGINAL_TO_PROXY = "ORIGINAL_TO_PROXY"
    ORIGINAL_TO_PROCESSED = "ORIGINAL_TO_PROCESSED"
    ORIGINAL_TO_GENERATED_DERIVATIVE = "ORIGINAL_TO_GENERATED_DERIVATIVE"
    SOURCE_TO_CLEANED_AUDIO = "SOURCE_TO_CLEANED_AUDIO"
    SOURCE_TO_STABILIZED_VIDEO = "SOURCE_TO_STABILIZED_VIDEO"
    SOURCE_TO_COLOR_GRADED = "SOURCE_TO_COLOR_GRADED"
    SOURCE_TO_TRANSCRIPTION = "SOURCE_TO_TRANSCRIPTION"

class ProxyStatus(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    READY = "READY"
    FAILED = "FAILED"
    STALE = "STALE"

# ==============================================================================
# 2. Timing & Frame Rate Abstraction
# ==============================================================================

@dataclass
class RationalTime:
    """Frame-accurate rational time representation (numerator / denominator).
    Prevents IEEE 754 floating-point drift over long timelines.
    """
    numerator: int = 0
    denominator: int = 1

    def to_seconds(self) -> float:
        if self.denominator == 0:
            return 0.0
        return self.numerator / self.denominator

    def to_frames(self, fps: float) -> int:
        return int(round(self.to_seconds() * fps))

    @classmethod
    def from_seconds(cls, seconds: float, base: int = 1000000) -> "RationalTime":
        return cls(numerator=int(round(seconds * base)), denominator=base)

    @classmethod
    def from_frames(cls, frames: int, fps: float) -> "RationalTime":
        # Handle fractional broadcast rates (23.976 -> 24000/1001, 29.97 -> 30000/1001)
        if abs(fps - 23.976) < 0.01:
            return cls(numerator=frames * 1001, denominator=24000)
        elif abs(fps - 29.97) < 0.01:
            return cls(numerator=frames * 1001, denominator=30000)
        elif abs(fps - 59.94) < 0.01:
            return cls(numerator=frames * 1001, denominator=60000)
        else:
            denom = int(round(fps * 1000))
            num = frames * 1000
            return cls(numerator=num, denominator=denom)

@dataclass
class SMPTETimecode:
    """SMPTE timecode representation with drop-frame and non-drop-frame support."""
    hours: int = 0
    minutes: int = 0
    seconds: int = 0
    frames: int = 0
    fps: float = 24.0
    is_drop_frame: bool = False

    def to_total_frames(self) -> int:
        if not self.is_drop_frame:
            total_sec = (self.hours * 3600) + (self.minutes * 60) + self.seconds
            return int(round(total_sec * self.fps)) + self.frames
        # SMPTE Drop Frame Calculation for 29.97 fps (drops 2 frames every min except 10th min)
        total_minutes = (self.hours * 60) + self.minutes
        frame_number = (
            (self.hours * 3600 * 30)
            + (self.minutes * 60 * 30)
            + (self.seconds * 30)
            + self.frames
        )
        drop_frames = 2 * (total_minutes - (total_minutes // 10))
        return frame_number - drop_frames

    @classmethod
    def from_frames(cls, total_frames: int, fps: float = 24.0, is_drop_frame: bool = False) -> "SMPTETimecode":
        if not is_drop_frame:
            int_fps = max(1, int(round(fps)))
            total_seconds = total_frames // int_fps
            frames = total_frames % int_fps
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return cls(hours=hours, minutes=minutes, seconds=seconds, frames=frames, fps=fps, is_drop_frame=False)
        else:
            # Drop frame logic
            total_minutes = total_frames // 17982  # frames per 10 minutes at 29.97
            remaining = total_frames % 17982
            if remaining >= 2:
                adjusted = total_frames + 2 * ((remaining - 2) // 1798 + 1)
            else:
                adjusted = total_frames
            int_fps = 30
            total_seconds = adjusted // int_fps
            frames = adjusted % int_fps
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            return cls(hours=hours, minutes=minutes, seconds=seconds, frames=frames, fps=fps, is_drop_frame=True)

    def to_string(self) -> str:
        delim = ";" if self.is_drop_frame else ":"
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}{delim}{self.frames:02d}"

    def __str__(self) -> str:
        return self.to_string()

# ==============================================================================
# 3. Stream & Track Descriptors
# ==============================================================================

@dataclass
class AudioStreamInfo:
    stream_index: int = 0
    codec: str = "pcm_s16le"
    sample_rate: int = 48000
    channels: int = 2
    channel_layout: str = "stereo"
    bit_depth: int = 16
    bitrate_kbps: Optional[int] = None
    language: Optional[str] = None
    title: Optional[str] = None

@dataclass
class VideoStreamInfo:
    stream_index: int = 0
    codec: str = "h264"
    width: int = 1920
    height: int = 1080
    pixel_aspect_ratio: str = "1:1"
    display_aspect_ratio: str = "16:9"
    frame_rate: float = 24.0
    frame_rate_mode: FrameRateMode = FrameRateMode.CFR
    color_space: str = "Rec.709"
    color_primaries: Optional[str] = "bt709"
    transfer_function: Optional[str] = "bt709"
    matrix_coefficients: Optional[str] = "bt709"
    bit_depth: int = 8
    has_alpha: bool = False
    duration_seconds: float = 0.0
    total_frames: int = 0
    bitrate_kbps: Optional[int] = None

# ==============================================================================
# 4. Proxy & Derivation Descriptors
# ==============================================================================

@dataclass
class ProxyDescriptor:
    proxy_id: str
    original_asset_id: str
    status: ProxyStatus = ProxyStatus.NOT_REQUESTED
    file_path: Optional[str] = None
    width: int = 960
    height: int = 540
    codec: str = "prores_proxy"
    container: str = "mov"
    size_bytes: int = 0
    created_at: Optional[float] = None
    error_message: Optional[str] = None

@dataclass
class GeneratedMediaDescriptor:
    generated_id: str
    asset_id: str
    generated_by: str  # e.g., "ai.transcription", "audio.denoiser", "vfx.chroma_key"
    generation_type: str  # e.g., "DERIVATIVE", "PROCESSED_AUDIO", "SYNTHESIZED_VOICE"
    source_asset_ids: List[str] = field(default_factory=list)
    parent_asset_id: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

@dataclass
class MediaRelationship:
    relationship_id: str
    source_asset_id: str
    target_asset_id: str
    relationship_type: MediaRelationshipType
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

# ==============================================================================
# 5. Authoritative Media Asset Model
# ==============================================================================

@dataclass
class MediaAsset:
    """Canonical model for a media asset managed within OMNIA Video Studio.
    
    Provides strict decoupling between internal identity (asset_id), filesystem
    location (file_path), and user-facing name.
    """
    asset_id: str = field(default_factory=lambda: f"asset_{uuid.uuid4().hex[:12]}")
    project_id: str = "default"
    name: str = "Untitled"
    original_name: str = "Untitled"
    media_type: AssetMediaType = AssetMediaType.OTHER
    mime_type: str = "application/octet-stream"
    extension: str = ""
    size_bytes: int = 0
    status: AssetLifecycleStatus = AssetLifecycleStatus.DISCOVERED
    status_reason: Optional[str] = None

    # Storage paths
    file_location: str = ""
    storage_kind: str = "LOCAL"  # LOCAL, PROJECT, EXTERNAL, ARCHIVE
    thumbnail_location: Optional[str] = None
    proxy_location: Optional[str] = None
    waveform_location: Optional[str] = None

    # Timing & Video Dimensions
    duration_seconds: float = 0.0
    total_frames: int = 0
    frame_rate: float = 24.0
    frame_rate_mode: FrameRateMode = FrameRateMode.CFR
    rational_duration: RationalTime = field(default_factory=RationalTime)
    start_timecode: SMPTETimecode = field(default_factory=SMPTETimecode)
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[str] = None

    # Audio details
    audio_channels: Optional[int] = None
    sample_rate: Optional[int] = None
    audio_bit_depth: Optional[int] = None

    # Format / Codecs
    container: str = "unknown"
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    color_space: Optional[str] = None
    transfer_function: Optional[str] = None

    # Detailed Stream descriptors
    video_streams: List[VideoStreamInfo] = field(default_factory=list)
    audio_streams: List[AudioStreamInfo] = field(default_factory=list)

    # Identifiers & Integrity
    content_hash_sha256: Optional[str] = None
    partial_hash: Optional[str] = None

    # Proxies & Relationships
    proxy_info: Optional[ProxyDescriptor] = None
    generated_info: Optional[GeneratedMediaDescriptor] = None

    # Organization
    bin_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Timestamps
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Structured metadata categories
    metadata_technical: Dict[str, Any] = field(default_factory=dict)
    metadata_camera: Dict[str, Any] = field(default_factory=dict)
    metadata_lens: Dict[str, Any] = field(default_factory=dict)
    metadata_custom: Dict[str, Any] = field(default_factory=dict)

    def mark_offline(self, reason: str = "Source file unreachable") -> None:
        """Transitions asset to OFFLINE state without destroying project metadata."""
        self.status = AssetLifecycleStatus.OFFLINE
        self.status_reason = reason
        self.updated_at = time.time()

    def mark_ready(self) -> None:
        self.status = AssetLifecycleStatus.READY
        self.status_reason = None
        self.updated_at = time.time()

    def mark_failed(self, reason: str) -> None:
        self.status = AssetLifecycleStatus.FAILED
        self.status_reason = reason
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes media asset to dictionary for bus and client telemetry."""
        return {
            "asset_id": self.asset_id,
            "project_id": self.project_id,
            "name": self.name,
            "original_name": self.original_name,
            "media_type": self.media_type.value,
            "mime_type": self.mime_type,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "file_location": self.file_location,
            "storage_kind": self.storage_kind,
            "thumbnail_location": self.thumbnail_location,
            "proxy_location": self.proxy_location,
            "waveform_location": self.waveform_location,
            "duration_seconds": self.duration_seconds,
            "total_frames": self.total_frames,
            "frame_rate": self.frame_rate,
            "frame_rate_mode": self.frame_rate_mode.value,
            "start_timecode": str(self.start_timecode),
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "audio_channels": self.audio_channels,
            "sample_rate": self.sample_rate,
            "container": self.container,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "color_space": self.color_space,
            "content_hash_sha256": self.content_hash_sha256,
            "bin_id": self.bin_id,
            "tags": list(self.tags),
            "has_proxy": self.proxy_info.status == ProxyStatus.READY if self.proxy_info else False,
            "is_generated": self.generated_info is not None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
