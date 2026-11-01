"""OMNIA Video Studio — Proxy Media, Source Selection & Media Relinking Models (Module 18).

Domain models for production-grade proxy media management and asset relinking:
- ProxyLifecycleStatus: Detailed states (NOT_REQUESTED, QUEUED, GENERATING, VERIFYING, READY, STALE, MISSING, CORRUPTED, FAILED, DELETED).
- ProxyProfileType: Profiles (LIGHTWEIGHT_480P, STANDARD_720P, HIGH_1080P, CUSTOM).
- PlaybackSourceMode: Viewer decoding policy (ORIGINAL, PROXY, AUTOMATIC, PREFER_PROXY).
- ExportSourcePolicy: Final render source policy (ORIGINALS_ONLY, PROXIES_ALLOWED, AUTOMATIC).
- ProxyProfileConfig: Detailed configuration per profile (dimensions, codec, container, bitrate, audio settings).
- ProxyMediaRecord: Durable record of a generated proxy, its relationship to the original, and verification fingerprint.
- RelinkCandidate: Match analysis for missing media recovery (fingerprint, filename, size, duration, confidence score).
- RelinkResult: Audit log of a relink transaction.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import time
import uuid

# ==============================================================================
# 1. Lifecycle Enums & Source Modes
# ==============================================================================

class ProxyLifecycleStatus(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    QUEUED = "QUEUED"
    VALIDATING_SOURCE = "VALIDATING_SOURCE"
    GENERATING = "GENERATING"
    VERIFYING = "VERIFYING"
    READY = "READY"
    STALE = "STALE"
    MISSING = "MISSING"
    CORRUPTED = "CORRUPTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DELETED = "DELETED"

class ProxyProfileType(str, Enum):
    LIGHTWEIGHT_480P = "LIGHTWEIGHT_480P"
    STANDARD_720P = "STANDARD_720P"
    HIGH_1080P = "HIGH_1080P"
    CUSTOM = "CUSTOM"

class PlaybackSourceMode(str, Enum):
    ORIGINAL = "ORIGINAL"           # Always decode original media
    PROXY = "PROXY"                 # Decode proxy media
    AUTOMATIC = "AUTOMATIC"         # Adaptive selection based on resolution & performance
    PREFER_PROXY = "PREFER_PROXY"   # Use proxy if ready, otherwise fallback to original

class ExportSourcePolicy(str, Enum):
    ORIGINALS_ONLY = "ORIGINALS_ONLY"       # Strict production default (never silently use proxy)
    PROXIES_ALLOWED = "PROXIES_ALLOWED"     # Explicit draft/review export allowed with proxies
    AUTOMATIC = "AUTOMATIC"                 # Automatic policy based on export preset

# ==============================================================================
# 2. Proxy Profile & Record
# ==============================================================================

@dataclass
class ProxyProfileConfig:
    profile_id: str
    name: str
    profile_type: ProxyProfileType
    target_width: int
    target_height: int
    video_codec: str = "mp4v"
    container: str = "mp4"
    bitrate_kbps: int = 4000
    fps: Optional[float] = None # None = preserve source fps
    audio_sample_rate: int = 48000
    audio_channels: int = 2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "profile_type": self.profile_type.value,
            "target_width": self.target_width,
            "target_height": self.target_height,
            "video_codec": self.video_codec,
            "container": self.container,
            "bitrate_kbps": self.bitrate_kbps,
            "fps": self.fps,
            "audio_sample_rate": self.audio_sample_rate,
            "audio_channels": self.audio_channels,
        }

@dataclass
class ProxyMediaRecord:
    """Durable identity and verification record for a generated proxy media asset."""
    proxy_id: str
    original_asset_id: str
    project_id: str
    profile_id: str
    file_path: str
    status: ProxyLifecycleStatus = ProxyLifecycleStatus.NOT_REQUESTED
    original_fingerprint: str = ""
    original_size_bytes: int = 0
    proxy_fingerprint: str = ""
    proxy_size_bytes: int = 0
    width: int = 1280
    height: int = 720
    fps: float = 24.0
    duration_seconds: float = 0.0
    video_codec: str = "mp4v"
    audio_codec: str = "pcm"
    container: str = "mp4"
    audio_channels: int = 2
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    verified_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proxy_id": self.proxy_id,
            "original_asset_id": self.original_asset_id,
            "project_id": self.project_id,
            "profile_id": self.profile_id,
            "file_path": self.file_path,
            "status": self.status.value,
            "original_fingerprint": self.original_fingerprint,
            "original_size_bytes": self.original_size_bytes,
            "proxy_fingerprint": self.proxy_fingerprint,
            "proxy_size_bytes": self.proxy_size_bytes,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration_seconds": self.duration_seconds,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "container": self.container,
            "audio_channels": self.audio_channels,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "verified_at": self.verified_at,
            "metadata": self.metadata,
        }

# ==============================================================================
# 3. Media Relinking Models
# ==============================================================================

@dataclass
class RelinkCandidate:
    """Potential file match discovered during missing media relinking."""
    candidate_path: str
    file_name: str
    size_bytes: int
    duration_seconds: float = 0.0
    detected_width: int = 0
    detected_height: int = 0
    detected_fps: float = 0.0
    content_fingerprint: str = ""
    confidence_score: float = 0.0 # 0.0 to 1.0 (1.0 = exact sha256 match)
    match_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_path": self.candidate_path,
            "file_name": self.file_name,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "detected_width": self.detected_width,
            "detected_height": self.detected_height,
            "detected_fps": self.detected_fps,
            "content_fingerprint": self.content_fingerprint,
            "confidence_score": round(self.confidence_score, 3),
            "match_reasons": self.match_reasons,
        }

@dataclass
class RelinkResult:
    """Audit log of a completed or failed relink transaction."""
    relink_id: str
    asset_id: str
    project_id: str
    previous_path: str
    new_path: str
    is_success: bool
    confidence_score: float
    error_message: Optional[str] = None
    relinked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relink_id": self.relink_id,
            "asset_id": self.asset_id,
            "project_id": self.project_id,
            "previous_path": self.previous_path,
            "new_path": self.new_path,
            "is_success": self.is_success,
            "confidence_score": self.confidence_score,
            "error_message": self.error_message,
            "relinked_at": self.relinked_at,
        }
