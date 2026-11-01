"""OMNIA Video Studio — Module 43: Media Conform, Offline Editing & High-Resolution Relink Models.

Domain models for:
- ProxyProfile: Presets for lightweight editing proxies (Low 540p, Medium 720p, High 1080p, Audio-Only).
- ProxyMappingRecord: Two-way binding between an authoritative high-resolution source and its proxy representation.
- MediaRepresentationMode: ORIGINAL, PROXY, AUTO.
- ConformCompatibilityGrade: COMPATIBLE, COMPATIBLE_WITH_WARNING, REQUIRES_RESOLUTION, BLOCKING.
- ConformIssue: Individual stream or timing incompatibility item identified during pre-conform inspection.
- ConformPreflightReport: Multi-asset audit report comparing proxy timeline references against original source files.
- ConformTransactionResult: Result of executing an online conform operation with automatic rollback capability.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


CONFORM_SCHEMA_VERSION = "video-studio.conform.v1"


class MediaRepresentationMode(str, Enum):
    """Active playback and editing mode for a timeline sequence or project."""
    ORIGINAL = "ORIGINAL"       # Force high-resolution original source files
    PROXY = "PROXY"             # Force lightweight editing proxies where available
    AUTO = "AUTO"               # Use proxies during timeline scrubbing/playback, conform for export


class ConformCompatibilityGrade(str, Enum):
    """Classification of an asset's compatibility for high-resolution conform."""
    COMPATIBLE = "COMPATIBLE"                               # Perfect match, frame-accurate
    COMPATIBLE_WITH_WARNING = "COMPATIBLE_WITH_WARNING"     # Safe to conform, minor metadata diff
    REQUIRES_RESOLUTION = "REQUIRES_RESOLUTION"             # User intervention needed (e.g. slight timing variance)
    BLOCKING = "BLOCKING"                                   # Cannot conform (missing file, stream missing, broken hash)


@dataclass
class ProxyProfile:
    """Specification profile for generating editing proxies."""
    profile_id: str = field(default_factory=lambda: f"prof_{uuid.uuid4().hex[:8]}")
    name: str = "720p Editing Proxy"
    target_width: int = 1280
    target_height: int = 720
    container: str = "mp4"
    video_codec: str = "h264"
    audio_codec: str = "aac"
    bitrate_kbps: int = 2500
    preserve_audio_channels: bool = True
    audio_sample_rate: int = 48000
    color_space: str = "Rec.709"
    is_built_in: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "target_width": self.target_width,
            "target_height": self.target_height,
            "container": self.container,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "bitrate_kbps": self.bitrate_kbps,
            "preserve_audio_channels": self.preserve_audio_channels,
            "audio_sample_rate": self.audio_sample_rate,
            "color_space": self.color_space,
            "is_built_in": self.is_built_in,
        }


@dataclass
class ProxyMappingRecord:
    """Authoritative mapping connecting an original source asset to its derived proxy."""
    mapping_id: str = field(default_factory=lambda: f"map_{uuid.uuid4().hex[:10]}")
    project_id: str = "default"
    original_asset_id: str = ""
    proxy_asset_id: str = ""
    original_fingerprint_sha256: str = ""
    proxy_fingerprint_sha256: str = ""
    profile_id: str = ""
    
    # Original specs
    original_file_path: str = ""
    original_width: int = 1920
    original_height: int = 1080
    original_fps: float = 24.0
    original_total_frames: int = 0
    original_duration_seconds: float = 0.0
    original_audio_channels: int = 2

    # Proxy specs
    proxy_file_path: str = ""
    proxy_width: int = 1280
    proxy_height: int = 720
    proxy_fps: float = 24.0
    proxy_total_frames: int = 0
    proxy_duration_seconds: float = 0.0

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping_id": self.mapping_id,
            "project_id": self.project_id,
            "original_asset_id": self.original_asset_id,
            "proxy_asset_id": self.proxy_asset_id,
            "original_fingerprint_sha256": self.original_fingerprint_sha256,
            "proxy_fingerprint_sha256": self.proxy_fingerprint_sha256,
            "profile_id": self.profile_id,
            "original_file_path": self.original_file_path,
            "original_dimensions": f"{self.original_width}x{self.original_height}",
            "proxy_dimensions": f"{self.proxy_width}x{self.proxy_height}",
            "original_fps": self.original_fps,
            "proxy_fps": self.proxy_fps,
            "original_duration_seconds": self.original_duration_seconds,
            "proxy_duration_seconds": self.proxy_duration_seconds,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }


@dataclass
class ConformIssue:
    """Individual discrepancy identified during conform preflight validation."""
    asset_id: str
    property_name: str
    grade: ConformCompatibilityGrade
    message: str
    original_value: Any = None
    proxy_value: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "property_name": self.property_name,
            "grade": self.grade.value,
            "message": self.message,
            "original_value": str(self.original_value) if self.original_value is not None else None,
            "proxy_value": str(self.proxy_value) if self.proxy_value is not None else None,
        }


@dataclass
class ConformPreflightReport:
    """Audit report predicting the outcome and safety of an online conform operation."""
    report_id: str = field(default_factory=lambda: f"rep_{uuid.uuid4().hex[:8]}")
    project_id: str = ""
    sequence_id: str = ""
    overall_grade: ConformCompatibilityGrade = ConformCompatibilityGrade.COMPATIBLE
    is_ready_for_online_render: bool = True
    total_clips_inspected: int = 0
    compatible_clips_count: int = 0
    blocking_issues_count: int = 0
    issues: List[ConformIssue] = field(default_factory=list)
    proposed_relinks: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "overall_grade": self.overall_grade.value,
            "is_ready_for_online_render": self.is_ready_for_online_render,
            "total_clips_inspected": self.total_clips_inspected,
            "compatible_clips_count": self.compatible_clips_count,
            "blocking_issues_count": self.blocking_issues_count,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
            "proposed_relinks": list(self.proposed_relinks),
            "created_at": self.created_at,
        }


@dataclass
class ConformTransactionResult:
    """Result of applying an online conform swap to a timeline sequence."""
    success: bool = True
    project_id: str = ""
    sequence_id: str = ""
    target_mode: MediaRepresentationMode = MediaRepresentationMode.ORIGINAL
    conformed_clips_count: int = 0
    rollback_snapshot_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    applied_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "target_mode": self.target_mode.value,
            "conformed_clips_count": self.conformed_clips_count,
            "rollback_snapshot_id": self.rollback_snapshot_id,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "applied_at": self.applied_at,
        }
