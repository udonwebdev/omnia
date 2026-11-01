"""OMNIA Video Studio — Video Export & Render Queue Service (Module 17).

Manages:
- Render job creation, queue scheduling, and execution.
- Preset management (1080p Web, 4K Master, Audio Master).
- Job progress polling and cancellation.
- Integration with OMNIA Video Studio Capability Registry.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import uuid
import time
import os

from video_studio.export_models import (
    ExportConfig,
    ExportPreset,
    ExportContainer,
    VideoEncoderCodec,
    AudioEncoderCodec,
    RenderJob,
    RenderJobStatus,
    RenderSnapshot,
    ExportValidationReport,
)
from video_studio.export_engine import export_engine, ExportEngine
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_service import timeline_service, TimelineService

logger = logging.getLogger("omnia.video_studio.export_service")

class ExportService:
    """Central service managing video rendering queue and export configurations."""

    def __init__(
        self,
        engine: Optional[ExportEngine] = None,
        tl_service: Optional[TimelineService] = None,
    ):
        self.engine = engine or export_engine
        self.timeline_service = tl_service or timeline_service
        # In-memory render queue: {job_id: RenderJob}
        self._jobs: Dict[str, RenderJob] = {}
        # Reusable export presets: {preset_id: ExportPreset}
        self._presets: Dict[str, ExportPreset] = {}
        self._init_built_in_presets()

    def _init_built_in_presets(self) -> None:
        """Populates standard broadcast & web export presets."""
        # 1. 1080p H.264 High Quality
        p_1080p = ExportPreset(
            preset_id="preset_1080p_hq",
            name="1080p High Quality MP4",
            description="Full HD 1920x1080 at 24fps high bitrate MP4 delivery.",
            config=ExportConfig(
                container=ExportContainer.MP4,
                video_codec=VideoEncoderCodec.H264,
                audio_codec=AudioEncoderCodec.PCM,
                width=1920,
                height=1080,
                frame_rate=24.0,
                bitrate_kbps=16000,
            ),
            is_built_in=True,
        )
        self._presets[p_1080p.preset_id] = p_1080p

        # 2. 720p Fast Preview
        p_720p = ExportPreset(
            preset_id="preset_720p_preview",
            name="720p Fast Proxy/Preview",
            description="Fast rendering 1280x720 24fps preview file.",
            config=ExportConfig(
                container=ExportContainer.MP4,
                video_codec=VideoEncoderCodec.MP4V,
                audio_codec=AudioEncoderCodec.PCM,
                width=1280,
                height=720,
                frame_rate=24.0,
                bitrate_kbps=6000,
            ),
            is_built_in=True,
        )
        self._presets[p_720p.preset_id] = p_720p

        # 3. Master Audio Only (WAV)
        p_audio = ExportPreset(
            preset_id="preset_audio_master",
            name="Master Audio WAV",
            description="Lossless 48kHz 24-bit/16-bit PCM Stereo Master.",
            config=ExportConfig(
                container=ExportContainer.WAV,
                audio_codec=AudioEncoderCodec.PCM,
                include_video=False,
                include_audio=True,
            ),
            is_built_in=True,
        )
        self._presets[p_audio.preset_id] = p_audio

    # ==========================================================================
    # 1. Preset Management
    # ==========================================================================

    def list_presets(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._presets.values()]

    def get_preset(self, preset_id: str) -> Optional[ExportPreset]:
        return self._presets.get(preset_id)

    # ==========================================================================
    # 2. Job Creation & Queue Management
    # ==========================================================================

    def create_render_job(
        self,
        project_id: str,
        sequence_id: str,
        output_path: str,
        config: Optional[ExportConfig] = None,
        preset_id: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[RenderJob]]:
        """Creates an immutable render snapshot and registers a job in the queue."""
        sequence = self.timeline_service.get_sequence(sequence_id)
        if not sequence:
            return False, f"Sequence '{sequence_id}' not found.", None

        if preset_id and preset_id in self._presets:
            cfg = self._presets[preset_id].config
        elif config:
            cfg = config
        else:
            cfg = self._presets["preset_1080p_hq"].config

        # Frame boundaries
        start_frame = cfg.start_frame if cfg.start_frame is not None else 0
        end_frame = cfg.end_frame if cfg.end_frame is not None else sequence.duration_frames
        if end_frame <= start_frame:
            end_frame = start_frame + 24 # Fallback minimum duration

        snapshot = RenderSnapshot(
            snapshot_id=f"snap_{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            sequence_id=sequence_id,
            sequence_revision=sequence.revision,
            duration_frames=end_frame - start_frame,
            start_frame=start_frame,
            end_frame=end_frame,
        )

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job = RenderJob(
            job_id=job_id,
            project_id=project_id,
            sequence_id=sequence_id,
            output_path=output_path,
            config=cfg,
            snapshot=snapshot,
            status=RenderJobStatus.QUEUED,
        )

        self._jobs[job_id] = job
        return True, "Render job queued.", job

    def execute_job(self, job_id: str) -> ExportValidationReport:
        """Executes a queued render job synchronously."""
        job = self._jobs.get(job_id)
        if not job:
            return ExportValidationReport(is_valid=False, file_path="", error_message=f"Job '{job_id}' not found.")

        sequence = self.timeline_service.get_sequence(job.sequence_id)
        if not sequence:
            job.status = RenderJobStatus.FAILED
            job.error_message = f"Sequence '{job.sequence_id}' not found."
            return ExportValidationReport(is_valid=False, file_path=job.output_path, error_message=job.error_message)

        report = self.engine.render_sequence_to_file(job, sequence)
        return report

    def get_job(self, job_id: str) -> Optional[RenderJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[Dict[str, Any]]:
        return [j.to_dict() for j in self._jobs.values()]

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        if job.status in (RenderJobStatus.QUEUED, RenderJobStatus.PREPARING, RenderJobStatus.RENDERING):
            job.status = RenderJobStatus.CANCELLED
            return True
        return False

    # ==========================================================================
    # 3. Capability Registry Integration
    # ==========================================================================

    def register_capabilities(self) -> None:
        """Registers Module 17 export capabilities into OMNIA Video Studio registry."""
        try:
            from video_studio.registry import video_studio_capability_registry
            from video_studio.registry_models import (
                VideoStudioCapabilityDescriptor,
                VideoStudioCategory,
                ImplementationState,
            )
            caps = [
                VideoStudioCapabilityDescriptor(
                    id="video.export.engine",
                    name="Video Export & Encoding Pipeline",
                    description="Full timeline rendering to MP4, AVI, WebM and WAV files.",
                    category=VideoStudioCategory.EXPORT,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["export", "encoding", "mp4", "wav"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.export.render_queue",
                    name="Render Queue Manager",
                    description="Render snapshots, job prioritization, and execution tracking.",
                    category=VideoStudioCategory.RENDERING,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["render_queue", "batch"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.export.validation",
                    name="Export Output Verification",
                    description="Decoded frame integrity and media probing verification.",
                    category=VideoStudioCategory.EXPORT,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["validation", "probing"],
                ),
            ]
            for c in caps:
                try:
                    video_studio_capability_registry.register(c, auth_token="core")
                except Exception as e:
                    logger.debug(f"Capability '{c.id}' registration note: {e}")
        except Exception as ex:
            logger.debug(f"Capabilities registry not available: {ex}")

# Global singleton
export_service = ExportService()
export_service.register_capabilities()
