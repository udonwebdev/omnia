"""OMNIA Video Studio — Video Export, Encoding & Render Queue Models (Module 17).

Domain models for non-destructive sequence rendering and video encoding:
- ExportContainer: Container formats (MP4, MOV, WEBM, MKV, WAV).
- VideoCodec: Encoders (H264, H265, VP9, AV1, MJPEG, RAW).
- AudioCodec: Encoders (AAC, OPUS, PCM, MP3).
- RateControlMode: Bitrate strategies (CBR, VBR, CRF).
- ExportPreset: Reusable render configurations (e.g. 1080p High Quality, 4K Master, WebM Delivery).
- RenderJobStatus: Comprehensive lifecycle states (QUEUED, PREPARING, RENDERING, ENCODING, MUXING, VERIFYING, COMPLETED, FAILED, CANCELLING, CANCELLED).
- RenderSnapshot: Immutable frozen representation of timeline and asset state at render start.
- RenderJob: Render queue item tracking progress, frames, metrics, and output path.
- ExportValidationReport: Diagnostic result confirming output integrity (file exists, valid headers, streams, duration, decodability).
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import time
import uuid

# ==============================================================================
# 1. Enums & Format Descriptors
# ==============================================================================

class ExportContainer(str, Enum):
    MP4 = "MP4"
    MOV = "MOV"
    WEBM = "WEBM"
    MKV = "MKV"
    WAV = "WAV" # Audio-only export

class VideoEncoderCodec(str, Enum):
    H264 = "H264"
    H265 = "H265"
    VP9 = "VP9"
    AV1 = "AV1"
    MJPEG = "MJPEG"
    MP4V = "MP4V" # Built-in OpenCV native fallback

class AudioEncoderCodec(str, Enum):
    AAC = "AAC"
    OPUS = "OPUS"
    PCM = "PCM"
    MP3 = "MP3"
    NONE = "NONE" # Video only

class RateControlMode(str, Enum):
    CRF = "CRF"       # Constant Rate Factor / Constant Quality
    CBR = "CBR"       # Constant Bitrate
    VBR = "VBR"       # Variable Bitrate

class RenderJobStatus(str, Enum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    RENDERING = "RENDERING"
    ENCODING = "ENCODING"
    MUXING = "MUXING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"

# ==============================================================================
# 2. Export Configuration & Preset
# ==============================================================================

@dataclass
class ExportConfig:
    """Technical specification for an individual render output."""
    container: ExportContainer = ExportContainer.MP4
    video_codec: VideoEncoderCodec = VideoEncoderCodec.MP4V
    audio_codec: AudioEncoderCodec = AudioEncoderCodec.PCM
    width: int = 1920
    height: int = 1080
    frame_rate: float = 24.0
    bitrate_kbps: int = 12000
    crf: int = 20
    keyframe_interval: int = 48
    pixel_format: str = "YUV420P"
    audio_sample_rate: int = 48000
    audio_channels: int = 2
    audio_bitrate_kbps: int = 320
    include_video: bool = True
    include_audio: bool = True
    start_frame: Optional[int] = None # None = entire sequence
    end_frame: Optional[int] = None   # None = entire sequence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "container": self.container.value,
            "video_codec": self.video_codec.value,
            "audio_codec": self.audio_codec.value,
            "width": self.width,
            "height": self.height,
            "frame_rate": self.frame_rate,
            "bitrate_kbps": self.bitrate_kbps,
            "crf": self.crf,
            "keyframe_interval": self.keyframe_interval,
            "pixel_format": self.pixel_format,
            "audio_sample_rate": self.audio_sample_rate,
            "audio_channels": self.audio_channels,
            "audio_bitrate_kbps": self.audio_bitrate_kbps,
            "include_video": self.include_video,
            "include_audio": self.include_audio,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
        }

@dataclass
class ExportPreset:
    """Reusable export template."""
    preset_id: str
    name: str
    description: str
    config: ExportConfig
    is_built_in: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "name": self.name,
            "description": self.description,
            "config": self.config.to_dict(),
            "is_built_in": self.is_built_in,
        }

# ==============================================================================
# 3. Render Snapshot & Render Job
# ==============================================================================

@dataclass
class RenderSnapshot:
    """Frozen state of the project timeline and components at export kickoff."""
    snapshot_id: str
    project_id: str
    sequence_id: str
    sequence_revision: int
    duration_frames: int
    start_frame: int
    end_frame: int
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "sequence_revision": self.sequence_revision,
            "duration_frames": self.duration_frames,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "created_at": self.created_at,
        }

@dataclass
class ExportValidationReport:
    """Post-export verification metrics confirming media validity."""
    is_valid: bool
    file_path: str
    file_size_bytes: int = 0
    duration_seconds: float = 0.0
    detected_width: int = 0
    detected_height: int = 0
    detected_fps: float = 0.0
    has_video_stream: bool = False
    has_audio_stream: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "duration_seconds": self.duration_seconds,
            "detected_width": self.detected_width,
            "detected_height": self.detected_height,
            "detected_fps": self.detected_fps,
            "has_video_stream": self.has_video_stream,
            "has_audio_stream": self.has_audio_stream,
            "error_message": self.error_message,
        }

@dataclass
class RenderJob:
    """An active or completed job in the export queue."""
    job_id: str
    project_id: str
    sequence_id: str
    output_path: str
    config: ExportConfig
    snapshot: RenderSnapshot
    status: RenderJobStatus = RenderJobStatus.QUEUED
    progress_percent: float = 0.0
    frames_rendered: int = 0
    total_frames: int = 0
    elapsed_time_seconds: float = 0.0
    error_message: Optional[str] = None
    validation_report: Optional[ExportValidationReport] = None
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "output_path": self.output_path,
            "config": self.config.to_dict(),
            "snapshot": self.snapshot.to_dict(),
            "status": self.status.value,
            "progress_percent": round(self.progress_percent, 2),
            "frames_rendered": self.frames_rendered,
            "total_frames": self.total_frames,
            "elapsed_time_seconds": round(self.elapsed_time_seconds, 2),
            "error_message": self.error_message,
            "validation_report": self.validation_report.to_dict() if self.validation_report else None,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
