"""OMNIA Video Studio — Media Transcoding, Conform & Batch Processing Models (Module 19).

Defines authoritative domain models for:
- TranscodeJobStatus & BatchJobStatus lifecycle states
- Supported container formats, video codecs, audio codecs, and rate modes
- TranscodeProfile & ConformProfile specifications
- ConformPlan: Detailed comparison between source and target requirements with transformation audit
- ScalingPolicy & LetterboxMode (FIT_PAD, CROP_FILL, STRETCH, ANAMORPHIC)
- AudioDownmixPolicy (STEREO_TO_MONO, 5_1_TO_STEREO, PASS_THROUGH)
- LoudnessStandard & LoudnessTarget (EBU_R128, ITU_BS1770, TARGET_LUFS)
- TranscodeJob: Individual transcode task tracking
- TranscodeBatchJob: Multi-item batch coordination with bounded concurrency and failure isolation
- DerivativeRegistrationPolicy (NEW_ASSET, ATTACH_DERIVATIVE, PROXY_CANDIDATE)
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


# ==============================================================================
# 1. Status & Lifecycle Enums
# ==============================================================================

class TranscodeJobStatus(str, Enum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    CONFORMING = "CONFORMING"
    TRANSCODING = "TRANSCODING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class BatchJobStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TranscodeContainer(str, Enum):
    MP4 = "mp4"
    MOV = "mov"
    MKV = "mkv"
    AVI = "avi"
    WAV = "wav"


class VideoCodec(str, Enum):
    MP4V = "mp4v"
    MJPG = "mjpg"
    H264 = "h264"
    RAW = "raw"
    NONE = "none"


class AudioCodec(str, Enum):
    PCM_S16LE = "pcm_s16le"
    PCM_S24LE = "pcm_s24le"
    PCM_F32LE = "pcm_f32le"
    AAC = "aac"
    NONE = "none"


class ScalingPolicy(str, Enum):
    FIT_PAD = "FIT_PAD"           # Preserves aspect ratio, adds letterbox/pillarbox
    CROP_FILL = "CROP_FILL"       # Preserves aspect ratio, crops overflow
    STRETCH = "STRETCH"           # Stretches to fit exact target dimensions
    PRESERVE = "PRESERVE"         # Retains original dimensions without resizing


class AudioDownmixPolicy(str, Enum):
    PASS_THROUGH = "PASS_THROUGH"
    STEREO_TO_MONO = "STEREO_TO_MONO"
    MULTICHANNEL_TO_STEREO = "MULTICHANNEL_TO_STEREO"
    MONO_TO_STEREO = "MONO_TO_STEREO"


class LoudnessStandard(str, Enum):
    NONE = "NONE"
    EBU_R128 = "EBU_R128"       # Target -23.0 LUFS
    ITU_R_BS1770 = "ITU_R_BS1770" # Target -24.0 LUFS
    PEAK_NORMALIZATION = "PEAK_NORMALIZATION" # Target -1.0 dBFS Peak


class DerivativeRegistrationPolicy(str, Enum):
    NEW_ASSET = "NEW_ASSET"
    ATTACH_DERIVATIVE = "ATTACH_DERIVATIVE"
    PROXY_CANDIDATE = "PROXY_CANDIDATE"
    NONE = "NONE"


# ==============================================================================
# 2. Profiles & Specifications
# ==============================================================================

@dataclass
class TranscodeProfile:
    """Comprehensive specification for a media transcoding / conform operation."""
    profile_id: str
    name: str
    description: str = ""
    container: TranscodeContainer = TranscodeContainer.MP4
    video_codec: VideoCodec = VideoCodec.MP4V
    audio_codec: AudioCodec = AudioCodec.PCM_S16LE
    target_width: Optional[int] = None       # None = preserve source
    target_height: Optional[int] = None      # None = preserve source
    scaling_policy: ScalingPolicy = ScalingPolicy.FIT_PAD
    target_fps: Optional[float] = None       # None = preserve source
    bitrate_kbps: int = 8000
    audio_sample_rate: int = 48000
    audio_channels: int = 2
    downmix_policy: AudioDownmixPolicy = AudioDownmixPolicy.PASS_THROUGH
    loudness_standard: LoudnessStandard = LoudnessStandard.NONE
    target_lufs: float = -23.0
    preserve_color_metadata: bool = True
    color_space: str = "Rec.709"
    is_built_in: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "description": self.description,
            "container": self.container.value,
            "video_codec": self.video_codec.value,
            "audio_codec": self.audio_codec.value,
            "target_width": self.target_width,
            "target_height": self.target_height,
            "scaling_policy": self.scaling_policy.value,
            "target_fps": self.target_fps,
            "bitrate_kbps": self.bitrate_kbps,
            "audio_sample_rate": self.audio_sample_rate,
            "audio_channels": self.audio_channels,
            "downmix_policy": self.downmix_policy.value,
            "loudness_standard": self.loudness_standard.value,
            "target_lufs": self.target_lufs,
            "preserve_color_metadata": self.preserve_color_metadata,
            "color_space": self.color_space,
            "is_built_in": self.is_built_in,
        }


@dataclass
class ConformTransformation:
    """Detailed audit of a planned transformation between source and conform target."""
    property_name: str
    source_value: Any
    target_value: Any
    action_type: str # "PRESERVE", "CONVERT", "RESAMPLE", "LETTERBOX", "DOWNMIX", "NORMALIZE"
    is_lossy: bool = False
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property_name": self.property_name,
            "source_value": self.source_value,
            "target_value": self.target_value,
            "action_type": self.action_type,
            "is_lossy": self.is_lossy,
            "details": self.details,
        }


@dataclass
class ConformPlan:
    """Preflight plan comparing source properties against target profile requirements."""
    plan_id: str
    asset_id: str
    profile_id: str
    source_path: str
    destination_path: str
    transformations: List[ConformTransformation] = field(default_factory=list)
    has_lossy_operations: bool = False
    warnings: List[str] = field(default_factory=list)
    is_executable: bool = True
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "asset_id": self.asset_id,
            "profile_id": self.profile_id,
            "source_path": self.source_path,
            "destination_path": self.destination_path,
            "transformations": [t.to_dict() for t in self.transformations],
            "has_lossy_operations": self.has_lossy_operations,
            "warnings": self.warnings,
            "is_executable": self.is_executable,
            "created_at": self.created_at,
        }


# ==============================================================================
# 3. Job Tracking Models
# ==============================================================================

@dataclass
class TranscodeJob:
    """Authoritative representation of a single media transcoding or conform operation."""
    job_id: str
    project_id: str
    asset_id: str
    source_file_path: str
    output_file_path: str
    profile: TranscodeProfile
    conform_plan: Optional[ConformPlan] = None
    batch_id: Optional[str] = None
    status: TranscodeJobStatus = TranscodeJobStatus.QUEUED
    progress_percent: float = 0.0
    stage_message: str = "Job queued"
    frames_processed: int = 0
    total_frames: int = 0
    elapsed_time_seconds: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    output_size_bytes: int = 0
    output_fingerprint: str = ""
    error_message: Optional[str] = None
    registered_asset_id: Optional[str] = None
    registration_policy: DerivativeRegistrationPolicy = DerivativeRegistrationPolicy.NEW_ASSET

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "asset_id": self.asset_id,
            "source_file_path": self.source_file_path,
            "output_file_path": self.output_file_path,
            "profile": self.profile.to_dict(),
            "conform_plan": self.conform_plan.to_dict() if self.conform_plan else None,
            "batch_id": self.batch_id,
            "status": self.status.value,
            "progress_percent": round(self.progress_percent, 2),
            "stage_message": self.stage_message,
            "frames_processed": self.frames_processed,
            "total_frames": self.total_frames,
            "elapsed_time_seconds": round(self.elapsed_time_seconds, 2),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output_size_bytes": self.output_size_bytes,
            "output_fingerprint": self.output_fingerprint,
            "error_message": self.error_message,
            "registered_asset_id": self.registered_asset_id,
            "registration_policy": self.registration_policy.value,
        }


@dataclass
class TranscodeBatchJob:
    """Coordinates batch processing across multiple assets with isolated error handling."""
    batch_id: str
    project_id: str
    name: str
    job_ids: List[str] = field(default_factory=list)
    status: BatchJobStatus = BatchJobStatus.IDLE
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    cancelled_jobs: int = 0
    overall_progress_percent: float = 0.0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "project_id": self.project_id,
            "name": self.name,
            "job_ids": self.job_ids,
            "status": self.status.value,
            "total_jobs": self.total_jobs,
            "completed_jobs": self.completed_jobs,
            "failed_jobs": self.failed_jobs,
            "cancelled_jobs": self.cancelled_jobs,
            "overall_progress_percent": round(self.overall_progress_percent, 2),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
        }
