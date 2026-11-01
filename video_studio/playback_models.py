"""OMNIA Video Studio — Playback Engine & Real-Time Viewer Models (Module 7).

Defines the domain models for timeline playback:
- PlaybackState machine (IDLE, INITIALIZING, READY, PLAYING, PAUSED, SEEKING, BUFFERING, STOPPING, STOPPED, DEGRADED, FAILED)
- PlaybackQuality (FULL, HALF, QUARTER, AUTO, PROXY_PREFER)
- DecodedVideoFrame representation
- DecodedAudioBlock representation
- PlaybackSession configuration and runtime state
- Sync clock models and A/V drift telemetry
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import time
import uuid

class PlaybackState(str, Enum):
    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    SEEKING = "SEEKING"
    BUFFERING = "BUFFERING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"

class PlaybackQuality(str, Enum):
    FULL = "FULL"
    HALF = "HALF"
    QUARTER = "QUARTER"
    AUTO = "AUTO"
    PROXY_PREFER = "PROXY_PREFER"

@dataclass
class DecodedVideoFrame:
    """Canonical in-memory representation of a decoded video frame."""
    frame_id: str
    asset_id: str
    timeline_frame: int
    source_frame: int
    pts_seconds: float
    duration_seconds: float
    width: int
    height: int
    pixel_format: str = "RGBA"
    color_space: str = "Rec.709"
    rotation_degrees: int = 0
    is_offline: bool = False
    is_gap: bool = False
    buffer_bytes: Optional[bytes] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "asset_id": self.asset_id,
            "timeline_frame": self.timeline_frame,
            "source_frame": self.source_frame,
            "pts_seconds": self.pts_seconds,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "pixel_format": self.pixel_format,
            "color_space": self.color_space,
            "rotation_degrees": self.rotation_degrees,
            "is_offline": self.is_offline,
            "is_gap": self.is_gap,
            "buffer_size_bytes": len(self.buffer_bytes) if self.buffer_bytes else 0,
        }

@dataclass
class DecodedAudioBlock:
    """Canonical block of decoded PCM audio data."""
    block_id: str
    asset_id: str
    timeline_frame: int
    pts_seconds: float
    sample_rate: int = 48000
    channels: int = 2
    samples_count: int = 1024
    peak_level_db: float = 0.0
    buffer_bytes: Optional[bytes] = None
    is_muted: bool = False
    is_offline: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "asset_id": self.asset_id,
            "timeline_frame": self.timeline_frame,
            "pts_seconds": self.pts_seconds,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "samples_count": self.samples_count,
            "peak_level_db": self.peak_level_db,
            "is_muted": self.is_muted,
            "is_offline": self.is_offline,
        }

@dataclass
class PlaybackMetrics:
    """Operational telemetry for a playback session."""
    frames_rendered: int = 0
    frames_dropped: int = 0
    seek_count: int = 0
    last_seek_latency_ms: float = 0.0
    average_decode_time_ms: float = 0.0
    av_drift_ms: float = 0.0
    buffer_underruns: int = 0
    active_decoders_count: int = 0
    is_hardware_accelerated: bool = False
    acceleration_backend: str = "SOFTWARE_CPU"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frames_rendered": self.frames_rendered,
            "frames_dropped": self.frames_dropped,
            "seek_count": self.seek_count,
            "last_seek_latency_ms": round(self.last_seek_latency_ms, 2),
            "average_decode_time_ms": round(self.average_decode_time_ms, 2),
            "av_drift_ms": round(self.av_drift_ms, 2),
            "buffer_underruns": self.buffer_underruns,
            "active_decoders_count": self.active_decoders_count,
            "is_hardware_accelerated": self.is_hardware_accelerated,
            "acceleration_backend": self.acceleration_backend,
        }

@dataclass
class PlaybackSession:
    """Authoritative session coordinating playback state for a sequence."""
    session_id: str
    project_id: str
    sequence_id: str
    state: PlaybackState = PlaybackState.IDLE
    current_frame: int = 0
    playback_rate: float = 1.0  # 1.0 normal, 2.0 fast forward, -1.0 reverse
    quality: PlaybackQuality = PlaybackQuality.FULL
    loop: bool = False
    volume: float = 1.0
    is_muted: bool = False
    source_mode: str = "AUTOMATIC"  # ORIGINAL, PROXY, AUTOMATIC, PREFER_PROXY
    metrics: PlaybackMetrics = field(default_factory=PlaybackMetrics)
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "state": self.state.value,
            "current_frame": self.current_frame,
            "playback_rate": self.playback_rate,
            "quality": self.quality.value,
            "loop": self.loop,
            "volume": self.volume,
            "is_muted": self.is_muted,
            "source_mode": self.source_mode,
            "metrics": self.metrics.to_dict(),
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
