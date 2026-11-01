"""OMNIA Video Studio — Media Quality Control, Technical Validation & Delivery Compliance Models (Module 37).

Defines authoritative domain models for:
- QCReportStatus: Overall report health assessment (PASS, PASS_WITH_WARNINGS, FAIL, INCOMPLETE, ERROR)
- QCSeverity: Individual issue severity (INFO, WARNING, ERROR, CRITICAL)
- QCCategory: Problem domain (CONTAINER, VIDEO, AUDIO, TIMELINE, METADATA, COMPLIANCE)
- RemediabilityType: Feasibility and safety of remediation (AUTOMATIC, MANUAL, UNSUPPORTED)
- UserReviewStatus: Human editor disposition (UNREVIEWED, APPROVED_EXCEPTION, FIX_PENDING, RESOLVED, DISMISSED)
- QCInspectionScope: SOURCE_MEDIA, SEQUENCE_TIMELINE, RENDERED_EXPORT, BATCH_MEDIA
- QCFinding: Granular evidence-backed technical defect with exact time range, measured vs expected, and actionable suggested fixes
- DeliveryProfile: Target compliance specification (broadcaster, streaming, archival standards) with strict vs advisory rules
- QualityControlReport: Versioned inspection container with tool/algorithm provenance, timestamps, findings, and review state
- QCJob: Background job descriptor for asynchronous single-asset, sequence, or batch inspection
- QCJobStatus: PENDING, RUNNING, COMPLETED, CANCELLED, FAILED
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


class QCReportStatus(str, Enum):
    """Authoritative outcome status of a Quality Control inspection."""
    PASS = "PASS"                                 # All checks passed with zero errors or warnings
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"     # Non-critical advisory warnings present; meets core requirements
    FAIL = "FAIL"                                 # One or more ERROR or CRITICAL violations found
    INCOMPLETE = "INCOMPLETE"                     # Inspection was interrupted or some required checks were skipped
    ERROR = "ERROR"                               # Inspector suffered an internal execution exception


class QCSeverity(str, Enum):
    """Severity classification of an individual QC finding."""
    INFO = "INFO"                                 # Informational finding (e.g. detected metadata, profile notes)
    WARNING = "WARNING"                           # Minor variance from ideal specification; acceptable for some outputs
    ERROR = "ERROR"                               # Definite compliance failure or noticeable artifact (e.g. black frame cluster, clipping)
    CRITICAL = "CRITICAL"                         # Fatal defect that prevents playback, delivery, or broadcast (e.g. corrupt header, A/V desync)


class QCCategory(str, Enum):
    """Categorical technical domain of an inspection finding."""
    CONTAINER = "CONTAINER"                       # Container integrity, atom structure, muxing, file size
    VIDEO = "VIDEO"                               # Black frames, freeze frames, resolution, frame rate, VFR, clipping, color primaries
    AUDIO = "AUDIO"                               # Clipping, peak/RMS, silence gaps, channel layout, sample rate, phase
    TIMELINE = "TIMELINE"                         # Gap frames, missing clips, unlinked media, offline assets
    METADATA = "METADATA"                         # Orientation, aspect ratio, timecode continuity, language tags
    COMPLIANCE = "COMPLIANCE"                     # Delivery profile specific requirements (max file size, required streams)


class RemediabilityType(str, Enum):
    """Categorizes whether a finding can be safely remediated automatically or requires manual intervention."""
    AUTOMATIC = "AUTOMATIC"                       # Can be fixed safely via existing validated command (e.g., audio gain clamp, relinking)
    MANUAL = "MANUAL"                             # Requires human creative/editorial judgment (e.g., intentional black frame in scene transition)
    UNSUPPORTED = "UNSUPPORTED"                   # No known non-destructive fix exists (e.g., corrupt source video frame)


class UserReviewStatus(str, Enum):
    """Human review disposition for a specific finding."""
    UNREVIEWED = "UNREVIEWED"                     # Awaiting human editor inspection
    APPROVED_EXCEPTION = "APPROVED_EXCEPTION"     # Intentional artistic choice (e.g., intentional freeze frame or fade to black)
    FIX_PENDING = "FIX_PENDING"                   # Remediation approved by user, awaiting re-run
    RESOLVED = "RESOLVED"                         # Remediation successfully applied and verified
    DISMISSED = "DISMISSED"                       # Dismissed as irrelevant by user


class QCInspectionScope(str, Enum):
    """Target entity under inspection."""
    SOURCE_MEDIA = "SOURCE_MEDIA"                 # Raw ingested media asset file
    SEQUENCE_TIMELINE = "SEQUENCE_TIMELINE"       # Active timeline sequence tracks, items, and transitions
    RENDERED_EXPORT = "RENDERED_EXPORT"           # Post-export rendered container output
    BATCH_MEDIA = "BATCH_MEDIA"                   # Multi-asset batch inspection


class QCJobStatus(str, Enum):
    """Asynchronous job processing state."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass
class QCFinding:
    """Individual evidence-backed technical defect or observation."""
    finding_id: str = field(default_factory=lambda: f"fnd_{uuid.uuid4().hex[:10]}")
    check_name: str = ""                          # Identifier of check (e.g., "video.black_frames", "audio.clipping")
    category: QCCategory = QCCategory.VIDEO
    severity: QCSeverity = QCSeverity.WARNING
    title: str = "Quality Issue Detected"
    description: str = ""
    start_time: Optional[float] = None            # Exact timestamp in seconds where defect begins
    end_time: Optional[float] = None              # Exact timestamp in seconds where defect ends
    start_frame: Optional[int] = None
    end_frame: Optional[int] = None
    measured_value: Optional[Any] = None          # Measured metric (e.g. 0.0 dBFS, 14 black frames)
    expected_range: Optional[str] = None          # Expected envelope (e.g. "< -0.5 dBFS", "0 frames")
    unit: Optional[str] = None                    # Unit of measurement ("dBFS", "frames", "seconds", "pixels")
    confidence: float = 1.0                       # Measurement confidence (0.0 to 1.0)
    suggested_remediation: str = ""               # Specific actionable recommendation
    remediability: RemediabilityType = RemediabilityType.MANUAL
    remediation_command: Optional[str] = None     # Optional reference to existing command ID / op
    review_status: UserReviewStatus = UserReviewStatus.UNREVIEWED
    review_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "check_name": self.check_name,
            "category": self.category.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "start_time": round(float(self.start_time), 3) if self.start_time is not None else None,
            "end_time": round(float(self.end_time), 3) if self.end_time is not None else None,
            "duration": round(float(self.end_time - self.start_time), 3) if self.start_time is not None and self.end_time is not None else None,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "measured_value": self.measured_value,
            "expected_range": self.expected_range,
            "unit": self.unit,
            "confidence": round(float(self.confidence), 3),
            "suggested_remediation": self.suggested_remediation,
            "remediability": self.remediability.value,
            "remediation_command": self.remediation_command,
            "review_status": self.review_status.value,
            "review_notes": self.review_notes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QCFinding":
        return cls(
            finding_id=data.get("finding_id", f"fnd_{uuid.uuid4().hex[:10]}"),
            check_name=data.get("check_name", ""),
            category=QCCategory(data.get("category", QCCategory.VIDEO.value)),
            severity=QCSeverity(data.get("severity", QCSeverity.WARNING.value)),
            title=data.get("title", ""),
            description=data.get("description", ""),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            start_frame=data.get("start_frame"),
            end_frame=data.get("end_frame"),
            measured_value=data.get("measured_value"),
            expected_range=data.get("expected_range"),
            unit=data.get("unit"),
            confidence=float(data.get("confidence", 1.0)),
            suggested_remediation=data.get("suggested_remediation", ""),
            remediability=RemediabilityType(data.get("remediability", RemediabilityType.MANUAL.value)),
            remediation_command=data.get("remediation_command"),
            review_status=UserReviewStatus(data.get("review_status", UserReviewStatus.UNREVIEWED.value)),
            review_notes=data.get("review_notes", ""),
        )


@dataclass
class DeliveryProfile:
    """Configurable technical delivery compliance profile defining mandatory requirements and thresholds."""
    profile_id: str = "delivery_standard_web"
    name: str = "Standard Web Delivery (1080p MP4)"
    description: str = "Strict progressive MP4 delivery standard for web and social distribution."
    version: str = "1.0.0"
    is_custom: bool = False
    
    # Container & Format requirements
    allowed_containers: List[str] = field(default_factory=lambda: ["mp4", "mov"])
    allowed_video_codecs: List[str] = field(default_factory=lambda: ["h264", "hevc", "mp4v"])
    allowed_audio_codecs: List[str] = field(default_factory=lambda: ["aac", "pcm", "mp3"])
    
    # Video Technical Requirements
    target_width: Optional[int] = 1920
    target_height: Optional[int] = 1080
    target_aspect_ratio: Optional[str] = "16:9"
    allowed_frame_rates: List[float] = field(default_factory=lambda: [23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0])
    require_constant_frame_rate: bool = True
    max_consecutive_black_frames: int = 15       # Flag unexpected black gaps > 15 frames (~0.5s)
    max_consecutive_freeze_frames: int = 30      # Flag unexpected freeze frames > 30 frames (~1.0s)
    
    # Audio Technical Requirements
    require_audio: bool = True
    allowed_channel_layouts: List[str] = field(default_factory=lambda: ["STEREO", "SURROUND_5_1", "MONO"])
    target_sample_rate: int = 48000
    max_peak_dbfs: float = -0.5                  # Maximum allowable peak audio amplitude before true clipping flag
    max_silence_duration_seconds: float = 4.0    # Flag unexpected internal audio silence > 4.0s
    
    # File & Duration Constraints
    duration_tolerance_seconds: float = 1.0      # Acceptable variance from sequence/expected duration
    max_file_size_bytes: Optional[int] = None    # Optional file size ceiling
    require_captions: bool = False               # Whether subtitle/caption track is strictly required
    
    # Required check identifiers that MUST execute
    required_checks: List[str] = field(default_factory=lambda: [
        "container.readability",
        "container.codec_compatibility",
        "video.resolution",
        "video.frame_rate_continuity",
        "video.black_frames",
        "video.freeze_frames",
        "audio.clipping",
        "audio.channel_layout",
        "audio.silence",
        "stream.av_sync_duration",
    ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "is_custom": self.is_custom,
            "allowed_containers": list(self.allowed_containers),
            "allowed_video_codecs": list(self.allowed_video_codecs),
            "allowed_audio_codecs": list(self.allowed_audio_codecs),
            "target_width": self.target_width,
            "target_height": self.target_height,
            "target_aspect_ratio": self.target_aspect_ratio,
            "allowed_frame_rates": list(self.allowed_frame_rates),
            "require_constant_frame_rate": self.require_constant_frame_rate,
            "max_consecutive_black_frames": self.max_consecutive_black_frames,
            "max_consecutive_freeze_frames": self.max_consecutive_freeze_frames,
            "require_audio": self.require_audio,
            "allowed_channel_layouts": list(self.allowed_channel_layouts),
            "target_sample_rate": self.target_sample_rate,
            "max_peak_dbfs": self.max_peak_dbfs,
            "max_silence_duration_seconds": self.max_silence_duration_seconds,
            "duration_tolerance_seconds": self.duration_tolerance_seconds,
            "max_file_size_bytes": self.max_file_size_bytes,
            "require_captions": self.require_captions,
            "required_checks": list(self.required_checks),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeliveryProfile":
        return cls(
            profile_id=data.get("profile_id", "delivery_standard_web"),
            name=data.get("name", "Standard Web Delivery"),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            is_custom=bool(data.get("is_custom", False)),
            allowed_containers=list(data.get("allowed_containers", ["mp4", "mov"])),
            allowed_video_codecs=list(data.get("allowed_video_codecs", ["h264", "hevc"])),
            allowed_audio_codecs=list(data.get("allowed_audio_codecs", ["aac", "pcm"])),
            target_width=data.get("target_width"),
            target_height=data.get("target_height"),
            target_aspect_ratio=data.get("target_aspect_ratio"),
            allowed_frame_rates=list(data.get("allowed_frame_rates", [24.0, 30.0, 60.0])),
            require_constant_frame_rate=bool(data.get("require_constant_frame_rate", True)),
            max_consecutive_black_frames=int(data.get("max_consecutive_black_frames", 15)),
            max_consecutive_freeze_frames=int(data.get("max_consecutive_freeze_frames", 30)),
            require_audio=bool(data.get("require_audio", True)),
            allowed_channel_layouts=list(data.get("allowed_channel_layouts", ["STEREO"])),
            target_sample_rate=int(data.get("target_sample_rate", 48000)),
            max_peak_dbfs=float(data.get("max_peak_dbfs", -0.5)),
            max_silence_duration_seconds=float(data.get("max_silence_duration_seconds", 4.0)),
            duration_tolerance_seconds=float(data.get("duration_tolerance_seconds", 1.0)),
            max_file_size_bytes=data.get("max_file_size_bytes"),
            require_captions=bool(data.get("require_captions", False)),
            required_checks=list(data.get("required_checks", [])),
        )


@dataclass
class QualityControlReport:
    """Master versioned Quality Control inspection report container."""
    report_id: str = field(default_factory=lambda: f"qcr_{uuid.uuid4().hex[:10]}")
    project_id: str = "default_project"
    scope: QCInspectionScope = QCInspectionScope.SOURCE_MEDIA
    target_id: str = ""                           # asset_id, sequence_id, or export_id
    target_path: Optional[str] = None
    target_revision: int = 1                      # Revision counter of target entity
    profile_id: str = "delivery_standard_web"
    profile_version: str = "1.0.0"
    report_version: int = 1
    status: QCReportStatus = QCReportStatus.PASS
    findings: List[QCFinding] = field(default_factory=list)
    executed_checks: List[str] = field(default_factory=list)
    skipped_checks: Dict[str, str] = field(default_factory=dict) # check_name -> reason_skipped
    start_time: float = field(default_factory=time.time)
    end_time: float = field(default_factory=time.time)
    provenance: Dict[str, Any] = field(default_factory=lambda: {
        "engine": "OMNIA.VideoStudio.QC",
        "engine_version": "1.0.0",
        "module": 37,
    })
    media_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == QCSeverity.CRITICAL)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == QCSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == QCSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == QCSeverity.INFO)

    def compute_overall_status(self) -> QCReportStatus:
        """Computes deterministic overall status based on finding severities and skipped checks."""
        if self.critical_count > 0 or self.error_count > 0:
            self.status = QCReportStatus.FAIL
        elif self.warning_count > 0:
            self.status = QCReportStatus.PASS_WITH_WARNINGS
        else:
            self.status = QCReportStatus.PASS
        return self.status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "scope": self.scope.value,
            "target_id": self.target_id,
            "target_path": self.target_path,
            "target_revision": self.target_revision,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "report_version": self.report_version,
            "status": self.status.value,
            "duration_seconds": round(float(self.duration_seconds), 3),
            "summary": {
                "critical": self.critical_count,
                "errors": self.error_count,
                "warnings": self.warning_count,
                "info": self.info_count,
                "total_findings": len(self.findings),
            },
            "findings": [f.to_dict() for f in self.findings],
            "executed_checks": list(self.executed_checks),
            "skipped_checks": dict(self.skipped_checks),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "provenance": dict(self.provenance),
            "media_metadata": dict(self.media_metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QualityControlReport":
        rep = cls(
            report_id=data.get("report_id", f"qcr_{uuid.uuid4().hex[:10]}"),
            project_id=data.get("project_id", "default_project"),
            scope=QCInspectionScope(data.get("scope", QCInspectionScope.SOURCE_MEDIA.value)),
            target_id=data.get("target_id", ""),
            target_path=data.get("target_path"),
            target_revision=int(data.get("target_revision", 1)),
            profile_id=data.get("profile_id", "delivery_standard_web"),
            profile_version=data.get("profile_version", "1.0.0"),
            report_version=int(data.get("report_version", 1)),
            status=QCReportStatus(data.get("status", QCReportStatus.PASS.value)),
            findings=[QCFinding.from_dict(f) for f in data.get("findings", [])],
            executed_checks=list(data.get("executed_checks", [])),
            skipped_checks=dict(data.get("skipped_checks", {})),
            start_time=float(data.get("start_time", time.time())),
            end_time=float(data.get("end_time", time.time())),
            provenance=dict(data.get("provenance", {})),
            media_metadata=dict(data.get("media_metadata", {})),
        )
        return rep


@dataclass
class QCJob:
    """Asynchronous QC processing task."""
    job_id: str = field(default_factory=lambda: f"qcj_{uuid.uuid4().hex[:10]}")
    project_id: str = "default_project"
    scope: QCInspectionScope = QCInspectionScope.SOURCE_MEDIA
    target_ids: List[str] = field(default_factory=list)
    profile_id: str = "delivery_standard_web"
    status: QCJobStatus = QCJobStatus.PENDING
    progress: float = 0.0                         # 0.0 to 1.0
    current_step: str = "Initialized"
    reports: List[QualityControlReport] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: Optional[str] = None
    is_cancelled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "scope": self.scope.value,
            "target_ids": list(self.target_ids),
            "profile_id": self.profile_id,
            "status": self.status.value,
            "progress": round(float(self.progress), 3),
            "current_step": self.current_step,
            "report_count": len(self.reports),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }
