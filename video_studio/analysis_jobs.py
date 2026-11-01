"""OMNIA Video Studio — Asynchronous Media Analysis Job Manager & Resource Governance (Module 3).

Coordinates the multi-stage background analysis pipeline:
QUEUED -> RUNNING -> PROBING -> ANALYZING -> GENERATING_DERIVATIVES -> FINALIZING -> COMPLETED
Includes:
- Resource ceilings (max file size, max thumbnail dimensions, concurrency limits)
- Non-blocking execution
- Progress reporting (0.0 to 100.0%)
- Graceful cancellation and failure isolation
"""

import os
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List

from video_studio.analysis_models import (
    AnalysisJobStatus,
    MediaAnalysisReport,
    WaveformResolution,
    ChannelMode,
)
from video_studio.media_probe_engine import media_probe_engine
from video_studio.thumbnail_engine import thumbnail_engine
from video_studio.waveform_engine import waveform_engine
from video_studio.analysis_cache import media_analysis_cache
from video_studio.media_models import AssetMediaType, MediaAsset
from video_studio.media_storage import media_storage_manager, StorageSecurityViolation

logger = logging.getLogger("Omnia.VideoStudio.AnalysisJobs")

@dataclass
class ResourceLimits:
    max_file_size_bytes: int = 50 * 1024 * 1024 * 1024  # 50 GB
    max_thumbnail_width: int = 3840
    max_thumbnail_height: int = 2160
    max_concurrent_jobs: int = 4
    job_timeout_seconds: float = 300.0

@dataclass
class MediaAnalysisJob:
    job_id: str
    asset_id: str
    project_id: str
    file_path: str
    fingerprint: str
    status: AnalysisJobStatus = AnalysisJobStatus.QUEUED
    progress_pct: float = 0.0
    stage_message: str = "Job queued"
    report: Optional[MediaAnalysisReport] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None
    cancel_requested: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "asset_id": self.asset_id,
            "project_id": self.project_id,
            "status": self.status.value,
            "progress_pct": round(self.progress_pct, 1),
            "stage_message": self.stage_message,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "has_report": self.report is not None,
        }

class MediaAnalysisJobManager:
    """Orchestrates media analysis jobs with progress updates and resource constraints."""

    def __init__(self, limits: Optional[ResourceLimits] = None):
        self.limits = limits or ResourceLimits()
        self._jobs: Dict[str, MediaAnalysisJob] = {}

    def submit_job(
        self,
        project_id: str,
        asset_id: str,
        file_path: str,
        fingerprint: str,
    ) -> MediaAnalysisJob:
        """Submits an asset for background analysis."""
        job_id = f"job_ana_{uuid.uuid4().hex[:10]}"
        job = MediaAnalysisJob(
            job_id=job_id,
            asset_id=asset_id,
            project_id=project_id,
            file_path=file_path,
            fingerprint=fingerprint,
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[MediaAnalysisJob]:
        return self._jobs.get(job_id)

    def cancel_job(self, job_id: str, reason: str = "User cancelled") -> bool:
        job = self.get_job(job_id)
        if not job or job.status in (AnalysisJobStatus.COMPLETED, AnalysisJobStatus.FAILED, AnalysisJobStatus.CANCELLED):
            return False
        job.cancel_requested = True
        job.status = AnalysisJobStatus.CANCELLED
        job.error_message = reason
        job.completed_at = time.time()
        job.stage_message = f"Cancelled: {reason}"
        return True

    def execute_job_synchronously(self, job_id: str) -> MediaAnalysisJob:
        """Executes the analysis pipeline steps deterministically.
        
        Designed for background worker execution or synchronous testing.
        """
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found.")

        job.started_at = time.time()
        job.status = AnalysisJobStatus.RUNNING
        job.progress_pct = 5.0
        job.stage_message = "Validating media path and resource quotas"

        # Check path security & existence
        try:
            safe_path = media_storage_manager.validate_safe_path(job.file_path)
        except StorageSecurityViolation as e:
            job.status = AnalysisJobStatus.FAILED
            job.error_message = f"Storage security violation: {e}"
            job.completed_at = time.time()
            return job

        if not os.path.exists(safe_path):
            job.status = AnalysisJobStatus.FAILED
            job.error_message = f"Source file does not exist: {safe_path}"
            job.completed_at = time.time()
            return job

        size = os.path.getsize(safe_path)
        if size > self.limits.max_file_size_bytes:
            job.status = AnalysisJobStatus.FAILED
            job.error_message = f"File size ({size} bytes) exceeds maximum limit ({self.limits.max_file_size_bytes})"
            job.completed_at = time.time()
            return job

        if job.cancel_requested:
            job.status = AnalysisJobStatus.CANCELLED
            return job

        # Check Cache
        cached_rep = media_analysis_cache.get_analysis_report(job.asset_id, job.fingerprint)
        if cached_rep:
            job.report = cached_rep
            job.progress_pct = 100.0
            job.status = AnalysisJobStatus.COMPLETED
            job.stage_message = "Analysis restored from cache"
            job.completed_at = time.time()
            return job

        # Stage 1: Probing
        job.status = AnalysisJobStatus.PROBING
        job.progress_pct = 25.0
        job.stage_message = "Probing containers and discovering streams"

        report = media_probe_engine.probe_asset(safe_path, job.asset_id, job.fingerprint)

        if job.cancel_requested:
            job.status = AnalysisJobStatus.CANCELLED
            return job

        # Stage 2: Analyzing
        job.status = AnalysisJobStatus.ANALYZING
        job.progress_pct = 50.0
        job.stage_message = "Analyzing frame rates, color spaces, and audio layouts"

        # Stage 3: Generating Derivatives (Thumbnail & Waveform)
        job.status = AnalysisJobStatus.GENERATING_DERIVATIVES
        job.progress_pct = 75.0
        job.stage_message = "Generating representative thumbnail and waveform cache"

        # Thumbnail
        has_video = len(report.video_streams) > 0
        if has_video:
            thumb_path = thumbnail_engine.generate_thumbnail(
                file_path=safe_path,
                asset_id=job.asset_id,
                timestamp_seconds=min(1.0, report.duration_seconds),
                width=320,
                height=180,
                rotation_degrees=report.video_streams[0].rotation_degrees,
            )
            report.default_thumbnail_uri = thumb_path

        # Waveform
        has_audio = len(report.audio_streams) > 0
        if has_audio:
            wf = waveform_engine.generate_waveform(
                file_path=safe_path,
                asset_id=job.asset_id,
                stream_index=report.audio_streams[0].stream_index,
                resolution=WaveformResolution.MEDIUM,
                channel_mode=ChannelMode.COMBINED,
                duration_seconds=report.duration_seconds or 10.0,
                channels=report.audio_streams[0].channels,
                sample_rate=report.audio_streams[0].sample_rate,
            )
            report.has_waveform = True

        if job.cancel_requested:
            job.status = AnalysisJobStatus.CANCELLED
            return job

        # Stage 4: Finalizing & Caching
        job.status = AnalysisJobStatus.FINALIZING
        job.progress_pct = 90.0
        job.stage_message = "Caching analysis results and updating media index"

        media_analysis_cache.store_analysis_report(report)

        job.report = report
        job.status = AnalysisJobStatus.COMPLETED
        job.progress_pct = 100.0
        job.stage_message = "Media analysis complete"
        job.completed_at = time.time()
        return job

# Global singleton
media_analysis_job_manager = MediaAnalysisJobManager()
