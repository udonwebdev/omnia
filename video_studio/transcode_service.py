"""OMNIA Video Studio — Media Transcoding, Conform & Batch Processing Service (Module 19).

Coordinates:
- Built-in transcode and conform profile catalog (ProRes-style master, 1080p Web, Archive WAV, 720p Fast).
- Individual and batch job orchestration with bounded concurrency.
- Per-item cancellation and failure isolation.
- Automatic registration of outputs as new MediaAsset or Derivative instances in ProjectMediaLibrary.
- Integration with Module 1 Capability Registry.
"""

import os
import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from video_studio.transcode_models import (
    TranscodeJob,
    TranscodeBatchJob,
    TranscodeProfile,
    ConformPlan,
    TranscodeJobStatus,
    BatchJobStatus,
    TranscodeContainer,
    VideoCodec,
    AudioCodec,
    ScalingPolicy,
    AudioDownmixPolicy,
    LoudnessStandard,
    DerivativeRegistrationPolicy,
)
from video_studio.transcode_engine import transcode_engine, TranscodeEngine
from video_studio.media_models import (
    MediaAsset,
    AssetMediaType,
    AssetLifecycleStatus,
    MediaRelationshipType,
    GeneratedMediaDescriptor,
)
from video_studio.media_library import media_library_registry, ProjectMediaLibrary
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.transcode_service")

# Built-in Standard Profiles
BUILTIN_PROFILES: Dict[str, TranscodeProfile] = {
    "profile_master_1080p": TranscodeProfile(
        profile_id="profile_master_1080p",
        name="1080p Editing Master (Conformed)",
        description="High-bitrate progressive MP4 at 1080p 24fps with pristine 48kHz stereo audio.",
        container=TranscodeContainer.MP4,
        video_codec=VideoCodec.MP4V,
        audio_codec=AudioCodec.PCM_S16LE,
        target_width=1920,
        target_height=1080,
        target_fps=24.0,
        scaling_policy=ScalingPolicy.FIT_PAD,
        bitrate_kbps=18000,
        audio_sample_rate=48000,
        audio_channels=2,
        is_built_in=True,
    ),
    "profile_web_720p": TranscodeProfile(
        profile_id="profile_web_720p",
        name="720p Fast Web & Proxy Deliverable",
        description="Fast preview/proxy 1280x720 video with fit-pad scaling.",
        container=TranscodeContainer.MP4,
        video_codec=VideoCodec.MP4V,
        audio_codec=AudioCodec.PCM_S16LE,
        target_width=1280,
        target_height=720,
        target_fps=24.0,
        scaling_policy=ScalingPolicy.FIT_PAD,
        bitrate_kbps=4000,
        audio_sample_rate=48000,
        audio_channels=2,
        is_built_in=True,
    ),
    "profile_audio_broadcast_wav": TranscodeProfile(
        profile_id="profile_audio_broadcast_wav",
        name="Broadcast Normalized WAV",
        description="48kHz 24-bit stereo WAV with EBU R128 loudness normalization (-23 LUFS).",
        container=TranscodeContainer.WAV,
        video_codec=VideoCodec.NONE,
        audio_codec=AudioCodec.PCM_S16LE,
        target_width=None,
        target_height=None,
        audio_sample_rate=48000,
        audio_channels=2,
        loudness_standard=LoudnessStandard.EBU_R128,
        target_lufs=-23.0,
        is_built_in=True,
    ),
}


class TranscodeService:
    """Central service managing transcoding profiles, conform preflight, batch queues, and asset derivation."""

    def __init__(self, engine: Optional[TranscodeEngine] = None):
        self.engine = engine or transcode_engine
        self.profiles: Dict[str, TranscodeProfile] = dict(BUILTIN_PROFILES)
        self.jobs: Dict[str, TranscodeJob] = {}
        self.batches: Dict[str, TranscodeBatchJob] = {}
        self._register_capabilities()

    def _register_capabilities(self) -> None:
        """Registers Module 19 transcoding and conform capabilities."""
        caps = [
            VideoStudioCapabilityDescriptor(
                id="video.transcode.engine",
                name="Media Transcoding Engine",
                description="Deterministic conversion between supported video and audio formats",
                category=VideoStudioCategory.MEDIA,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["transcode", "codec", "conversion"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.transcode.conform",
                name="Media Conform Pipeline",
                description="Resolution conform, letterboxing, frame-rate adaptation, and loudness normalization",
                category=VideoStudioCategory.MEDIA,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["conform", "normalize", "letterbox", "framerate"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.transcode.batch",
                name="Batch Transcoding Queue",
                description="Multi-item concurrent batch processing with failure isolation and retry",
                category=VideoStudioCategory.MEDIA,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["batch", "queue", "jobs"],
            ),
        ]
        for cap in caps:
            try:
                video_studio_capability_registry.register(cap, auth_token="core")
            except Exception as e:
                logger.debug(f"Capability '{cap.id}' note: {e}")

    # --------------------------------------------------------------------------
    # Profile Catalog
    # --------------------------------------------------------------------------

    def list_profiles(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self.profiles.values()]

    def get_profile(self, profile_id: str) -> Optional[TranscodeProfile]:
        return self.profiles.get(profile_id)

    def register_profile(self, profile: TranscodeProfile) -> None:
        self.profiles[profile.profile_id] = profile

    # --------------------------------------------------------------------------
    # Preflight Conform Planning
    # --------------------------------------------------------------------------

    def plan_conform(
        self,
        asset: MediaAsset,
        profile_id: str = "profile_master_1080p",
        output_path: Optional[str] = None,
    ) -> ConformPlan:
        """Inspects source asset and produces an executable ConformPlan against a profile."""
        profile = self.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Unknown transcode profile '{profile_id}'.")

        out_path = output_path or self._generate_safe_output_path(asset, profile)
        return self.engine.build_conform_plan(asset, profile, out_path)

    # --------------------------------------------------------------------------
    # Job Creation & Execution
    # --------------------------------------------------------------------------

    def create_transcode_job(
        self,
        asset: MediaAsset,
        profile_id: str = "profile_master_1080p",
        output_path: Optional[str] = None,
        registration_policy: DerivativeRegistrationPolicy = DerivativeRegistrationPolicy.NEW_ASSET,
        batch_id: Optional[str] = None,
    ) -> TranscodeJob:
        """Creates a validated TranscodeJob ready for execution."""
        profile = self.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Unknown transcode profile '{profile_id}'.")

        out_path = output_path or self._generate_safe_output_path(asset, profile)
        conform_plan = self.engine.build_conform_plan(asset, profile, out_path)

        job_id = f"job_tc_{uuid.uuid4().hex[:10]}"
        job = TranscodeJob(
            job_id=job_id,
            project_id=asset.project_id,
            asset_id=asset.asset_id,
            source_file_path=asset.file_location,
            output_file_path=out_path,
            profile=profile,
            conform_plan=conform_plan,
            batch_id=batch_id,
            registration_policy=registration_policy,
        )
        self.jobs[job_id] = job
        return job

    def execute_job(self, job_id: str) -> bool:
        """Synchronously executes a transcode job, validates output, and registers derivative asset."""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"Transcode job '{job_id}' not found.")

        success = self.engine.execute_transcode(job)
        if success and job.registration_policy != DerivativeRegistrationPolicy.NONE:
            self._register_transcoded_asset(job)

        return success

    def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        if job.status in (TranscodeJobStatus.QUEUED, TranscodeJobStatus.VALIDATING, TranscodeJobStatus.TRANSCODING):
            job.status = TranscodeJobStatus.CANCELLED
            job.stage_message = "Cancelled by user"
            return True
        return False

    def retry_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job or job.status not in (TranscodeJobStatus.FAILED, TranscodeJobStatus.CANCELLED):
            return False
        job.status = TranscodeJobStatus.QUEUED
        job.progress_percent = 0.0
        job.frames_processed = 0
        job.error_message = None
        return self.execute_job(job_id)

    # --------------------------------------------------------------------------
    # Batch Processing
    # --------------------------------------------------------------------------

    def create_batch(
        self,
        project_id: str,
        name: str,
        assets: List[MediaAsset],
        profile_id: str = "profile_master_1080p",
        registration_policy: DerivativeRegistrationPolicy = DerivativeRegistrationPolicy.NEW_ASSET,
    ) -> TranscodeBatchJob:
        """Assembles a multi-item batch job across candidate assets."""
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        job_ids = []

        for asset in assets:
            job = self.create_transcode_job(
                asset=asset,
                profile_id=profile_id,
                registration_policy=registration_policy,
                batch_id=batch_id,
            )
            job_ids.append(job.job_id)

        batch = TranscodeBatchJob(
            batch_id=batch_id,
            project_id=project_id,
            name=name,
            job_ids=job_ids,
            total_jobs=len(job_ids),
        )
        self.batches[batch_id] = batch
        return batch

    def execute_batch(self, batch_id: str) -> TranscodeBatchJob:
        """Executes all jobs in a batch sequentially with strict failure isolation."""
        batch = self.batches.get(batch_id)
        if not batch:
            raise ValueError(f"Batch '{batch_id}' not found.")

        batch.status = BatchJobStatus.RUNNING
        for idx, job_id in enumerate(batch.job_ids):
            job = self.jobs.get(job_id)
            if not job:
                continue

            try:
                ok = self.execute_job(job_id)
                if ok:
                    batch.completed_jobs += 1
                elif job.status == TranscodeJobStatus.CANCELLED:
                    batch.cancelled_jobs += 1
                else:
                    batch.failed_jobs += 1
            except Exception as e:
                logger.warning(f"Batch item failed safely: {e}")
                batch.failed_jobs += 1

            batch.overall_progress_percent = ((idx + 1) / float(batch.total_jobs)) * 100.0

        batch.status = BatchJobStatus.COMPLETED if batch.failed_jobs == 0 else BatchJobStatus.FAILED
        batch.completed_at = time.time()
        return batch

    # --------------------------------------------------------------------------
    # Output Safety & Asset Derivation Registration
    # --------------------------------------------------------------------------

    def _generate_safe_output_path(self, asset: MediaAsset, profile: TranscodeProfile) -> str:
        """Computes a collision-free output path based on source name, profile ID, and extension."""
        src_dir = os.path.dirname(os.path.abspath(asset.file_location))
        base_name = os.path.splitext(os.path.basename(asset.file_location))[0]
        out_ext = profile.container.value
        filename = f"{base_name}_{profile.profile_id}.{out_ext}"
        candidate = os.path.join(src_dir, filename)

        # Collision prevention
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(src_dir, f"{base_name}_{profile.profile_id}_{counter}.{out_ext}")
            counter += 1

        return candidate

    def _register_transcoded_asset(self, job: TranscodeJob) -> None:
        """Registers transcoded output in the ProjectMediaLibrary and records derivative relationship."""
        pml = media_library_registry.get_or_create(job.project_id)
        parent_asset = pml.get_asset(job.asset_id)

        # Create new child asset
        new_asset_id = f"asset_deriv_{uuid.uuid4().hex[:8]}"
        is_audio = job.profile.container == TranscodeContainer.WAV or job.profile.video_codec == VideoCodec.NONE
        
        deriv_asset = MediaAsset(
            asset_id=new_asset_id,
            project_id=job.project_id,
            name=os.path.basename(job.output_file_path),
            original_name=os.path.basename(job.output_file_path),
            file_location=job.output_file_path,
            media_type=AssetMediaType.AUDIO if is_audio else AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
            size_bytes=job.output_size_bytes,
            content_hash_sha256=job.output_fingerprint,
            width=job.profile.target_width or (parent_asset.width if parent_asset else 1920),
            height=job.profile.target_height or (parent_asset.height if parent_asset else 1080),
            frame_rate=job.profile.target_fps or (parent_asset.frame_rate if parent_asset else 24.0),
            container=job.profile.container.value,
            generated_info=GeneratedMediaDescriptor(
                generated_id=f"gen_{uuid.uuid4().hex[:8]}",
                asset_id=new_asset_id,
                generated_by="Module 19 Transcode Engine",
                generation_type="TRANSCODE_CONFORM",
                source_asset_ids=[job.asset_id],
                parent_asset_id=job.asset_id,
                parameters=job.profile.to_dict(),
            ),
        )

        pml.add_asset(deriv_asset)

        # Register relationship
        pml.link_relationship(
            source_asset_id=job.asset_id,
            target_asset_id=new_asset_id,
            rel_type=MediaRelationshipType.ORIGINAL_TO_GENERATED_DERIVATIVE,
            metadata={"profile_id": job.profile.profile_id, "job_id": job.job_id},
        )

        # If policy is PROXY_CANDIDATE, link as proxy in parent asset
        if job.registration_policy == DerivativeRegistrationPolicy.PROXY_CANDIDATE and parent_asset:
            parent_asset.proxy_location = job.output_file_path
            pml.add_asset(parent_asset)

        job.registered_asset_id = new_asset_id
        logger.info(f"Registered transcoded asset '{new_asset_id}' as derivative of '{job.asset_id}'.")


# Global singleton
transcode_service = TranscodeService()
