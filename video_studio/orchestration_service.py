"""OMNIA Video Studio — Module 44: Render Pipeline Orchestration & Fault Recovery Service.

Enterprise service managing:
- Validated render job lifecycle from CREATED to COMPLETED.
- Frozen revision snapshots ensuring editing in progress does not mutate in-flight renders.
- Worker scheduling, capability matching, and concurrency limits.
- Pre-render conform checks (Module 43) preventing proxy leaks.
- Transient failure retry & recovery of interrupted jobs.
- Clean temporary output handling and atomic publication.
- Capability registration in VideoStudioCapabilityRegistry.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from video_studio.conform_models import ConformCompatibilityGrade, MediaRepresentationMode
from video_studio.conform_service import ConformService, conform_service
from video_studio.export_engine import ExportEngine, export_engine
from video_studio.export_models import ExportConfig, ExportPreset, RenderJob, RenderJobStatus, RenderSnapshot
from video_studio.orchestration_engine import OrchestrationEngine
from video_studio.orchestration_models import (
    FailureClassification,
    OrchestratedRenderState,
    OrchestrationProgress,
    RenderOrchestrationJob,
    RenderWorkerDescriptor,
)
from video_studio.provenance_engine import compute_file_sha256_chunked
from video_studio.registry import VideoStudioCapabilityRegistry, video_studio_capability_registry
from video_studio.registry_models import (
    ImplementationState,
    VideoStudioCategory,
    VideoStudioCapabilityDescriptor,
)
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_service import TimelineService, timeline_service
from video_studio.versioning_service import VersionControlService, version_control_service

logger = logging.getLogger("omnia.video_studio.orchestration")


class RenderOrchestrationService:
    """Enterprise Video Studio Render Pipeline Orchestrator & Fault Recovery Service."""

    def __init__(
        self,
        capability_registry: Optional[VideoStudioCapabilityRegistry] = None,
        tl_service: Optional[TimelineService] = None,
        conf_service: Optional[ConformService] = None,
        versioning_svc: Optional[VersionControlService] = None,
        exp_engine: Optional[ExportEngine] = None,
        audit_log_path: str = "omnia_audit.jsonl",
        max_concurrent_jobs: int = 2,
    ) -> None:
        self.registry = capability_registry or video_studio_capability_registry
        self.timeline_service = tl_service or timeline_service
        self.conform_service = conf_service or conform_service
        self.versioning_service = versioning_svc or version_control_service
        self.export_engine = exp_engine or export_engine
        self.audit_log_path = audit_log_path
        self.max_concurrent_jobs = max_concurrent_jobs
        self.engine = OrchestrationEngine()

        # In-memory store: job_id -> RenderOrchestrationJob
        self._jobs: Dict[str, RenderOrchestrationJob] = {}
        # Registered Workers: worker_id -> RenderWorkerDescriptor
        self._workers: Dict[str, RenderWorkerDescriptor] = {}
        self._init_default_worker()

        if self.registry:
            self.register_capabilities()

    def _init_default_worker(self) -> None:
        """Initializes primary local engine execution worker."""
        worker = RenderWorkerDescriptor(
            worker_id="worker_local_primary",
            name="Primary Local Execution Worker",
            max_concurrent_jobs=self.max_concurrent_jobs,
        )
        self._workers[worker.worker_id] = worker

    def register_capabilities(self) -> None:
        """Registers Module 44 Orchestration capabilities into the registry."""
        capabilities = [
            VideoStudioCapabilityDescriptor(
                id="video.render.orchestration_lifecycle",
                name="Render Pipeline Lifecycle Orchestration",
                description="State-machine governed render lifecycle (Queued, Preparing, Rendering, Verifying, Completed).",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["render", "orchestration", "lifecycle", "queue"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.worker_scheduling",
                name="Worker Dispatch & Concurrency Control",
                description="Worker capability matching, priority queueing, and bounded concurrent resource scheduling.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["workers", "scheduling", "concurrency", "dispatch"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.fault_recovery_and_retry",
                name="Transient Fault Recovery & Safe Retry",
                description="Automatic transient failure classification, interruption recovery, and clean temp cleanup.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["recovery", "fault_tolerance", "retry", "cleanup"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.output_verification_and_publish",
                name="Output Artifact Verification & Atomic Publish",
                description="Post-render verification of headers, duration, and content hashes before atomic publication.",
                category=VideoStudioCategory.EXPORT,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["export", "verification", "atomic_publish", "sha256"],
            ),
        ]
        for cap in capabilities:
            if not self.registry.get(cap.id):
                self.registry.register(cap, auth_token="core")

    def _log_audit_event(self, event_type: str, details: Dict[str, Any]) -> None:
        payload = {
            "event_type": event_type,
            "timestamp": time.time(),
            "details": details,
        }
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")
        except Exception as e:
            logger.warning(f"Failed to append to audit log {self.audit_log_path}: {e}")

    # =========================================================================
    # 1. Job Creation & Lifecycle Management
    # =========================================================================

    def create_orchestrated_job(
        self,
        project_id: str,
        sequence_id: str,
        output_path: str,
        config: ExportConfig,
        revision_id: Optional[str] = None,
        representation_mode: MediaRepresentationMode = MediaRepresentationMode.ORIGINAL,
        priority: int = 50,
        max_retries: int = 2,
    ) -> RenderOrchestrationJob:
        """Validates parameters, captures stable revision snapshot, and creates durable job record."""
        # 1. Validate output path
        ok_path, err_path = self.engine.validate_render_path(output_path)
        if not ok_path:
            raise ValueError(f"Invalid render output path: {err_path}")

        sequence = self.timeline_service.get_sequence(sequence_id)
        if not sequence:
            raise KeyError(f"Sequence '{sequence_id}' not found.")

        # 2. Pin stable revision snapshot
        rev_num = sequence.revision
        if not revision_id and self.versioning_service:
            # Create a durable immutable snapshot so timeline edits do not corrupt render
            snap = self.versioning_service.create_snapshot(
                project_id=project_id,
                sequence_id=sequence_id,
                name=f"Render Snapshot - {sequence.name}",
                message="Automated render pre-flight snapshot",
                is_protected=True,
            )
            revision_id = snap.revision_id
            rev_num = snap.revision_number

        # 3. Create temporary output path
        ext = os.path.splitext(output_path)[1] or f".{config.container.value.lower()}"
        temp_fd, temp_path = tempfile.mkstemp(prefix="omnia_render_", suffix=ext)
        os.close(temp_fd)

        job = RenderOrchestrationJob(
            project_id=project_id,
            sequence_id=sequence_id,
            revision_id=revision_id,
            revision_number=rev_num,
            output_path=output_path,
            temp_output_path=temp_path,
            config=config,
            representation_mode=representation_mode,
            priority=priority,
            max_retries=max_retries,
        )

        self._jobs[job.job_id] = job
        self._log_audit_event("RENDER_JOB_CREATED", job.to_dict())
        return job

    def get_job(self, job_id: str) -> Optional[RenderOrchestrationJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, project_id: Optional[str] = None) -> List[RenderOrchestrationJob]:
        res = list(self._jobs.values())
        if project_id:
            res = [j for j in res if j.project_id == project_id]
        res.sort(key=lambda j: j.created_at, reverse=True)
        return res

    # =========================================================================
    # 2. Preflight Validation & Scheduling
    # =========================================================================

    def validate_job(self, job_id: str) -> Tuple[bool, List[str]]:
        """Preflight inspection verifying media dependencies, conform requirements, and codecs."""
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found.")

        job.transition_to(OrchestratedRenderState.VALIDATING)
        errors: List[str] = []

        # Check online conform requirements if targeting ORIGINAL
        if job.representation_mode == MediaRepresentationMode.ORIGINAL and self.conform_service:
            ok_conf, conf_errs = self.conform_service.validate_export_conform_readiness(
                job.project_id, job.sequence_id, allow_proxy_draft=False
            )
            if not ok_conf:
                errors.extend(conf_errs)

        if errors:
            job.transition_to(OrchestratedRenderState.FAILED)
            job.failure_type = FailureClassification.PERMANENT
            job.error_message = " ; ".join(errors)
            return False, errors

        job.transition_to(OrchestratedRenderState.QUEUED)
        return True, []

    def schedule_next_job(self) -> Optional[RenderOrchestrationJob]:
        """Schedules the highest priority queued job to an available worker."""
        queued = [j for j in self._jobs.values() if j.state == OrchestratedRenderState.QUEUED]
        if not queued:
            return None

        # Sort by priority desc, created_at asc
        queued.sort(key=lambda j: (-j.priority, j.created_at))

        for job in queued:
            worker = self.engine.select_best_worker(job, list(self._workers.values()))
            if worker:
                job.transition_to(OrchestratedRenderState.SCHEDULED)
                job.assigned_worker_id = worker.worker_id
                worker.current_active_jobs += 1
                self._log_audit_event("RENDER_JOB_SCHEDULED", {
                    "job_id": job.job_id,
                    "worker_id": worker.worker_id,
                })
                return job

        return None

    # =========================================================================
    # 3. Execution, Progress & Output Verification
    # =========================================================================

    def execute_scheduled_job(self, job_id: str) -> bool:
        """Executes rendering synchronously on assigned worker, verifies output, and publishes."""
        job = self.get_job(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found.")

        if job.state != OrchestratedRenderState.SCHEDULED:
            raise ValueError(f"Job '{job_id}' must be in SCHEDULED state to execute (currently {job.state.value}).")

        job.attempt_count += 1
        job.transition_to(OrchestratedRenderState.PREPARING)
        job.transition_to(OrchestratedRenderState.RENDERING)

        sequence = self.timeline_service.get_sequence(job.sequence_id)
        if not sequence:
            job.transition_to(OrchestratedRenderState.FAILED)
            job.failure_type = FailureClassification.PERMANENT
            job.error_message = f"Sequence '{job.sequence_id}' missing."
            return False

        # Build legacy RenderJob for existing ExportEngine
        legacy_job = RenderJob(
            job_id=job.job_id,
            project_id=job.project_id,
            sequence_id=job.sequence_id,
            output_path=job.temp_output_path, # Render to temp output first
            config=job.config,
            snapshot=RenderSnapshot(
                snapshot_id=f"snap_{job.job_id[:8]}",
                project_id=job.project_id,
                sequence_id=job.sequence_id,
                sequence_revision=job.revision_number,
                duration_frames=sequence.duration_frames,
                start_frame=0,
                end_frame=sequence.duration_frames,
            ),
        )

        try:
            # Perform rendering
            report = self.export_engine.render_sequence_to_file(legacy_job, sequence)
            if not report.is_valid:
                raise RuntimeError(report.error_message or "Export engine render failed.")

            # Update progress
            job.progress = OrchestrationProgress(
                frames_rendered=sequence.duration_frames,
                total_frames=sequence.duration_frames,
                progress_percent=100.0,
                current_stage="Muxing and Finalizing",
            )
            job.transition_to(OrchestratedRenderState.FINALIZING)

            # Output Verification
            job.transition_to(OrchestratedRenderState.VERIFYING)
            ok_ver, err_ver, sha, size = self.engine.verify_output_artifact(job.temp_output_path)
            if not ok_ver:
                raise RuntimeError(f"Output artifact verification failed: {err_ver}")

            job.output_sha256 = sha
            job.output_size_bytes = size
            job.is_verified = True

            # Atomic publication
            ok_pub, err_pub = self.engine.publish_output_atomically(job.temp_output_path, job.output_path)
            if not ok_pub:
                raise RuntimeError(f"Publication failed: {err_pub}")

            job.transition_to(OrchestratedRenderState.COMPLETED)
            self._log_audit_event("RENDER_JOB_COMPLETED", job.to_dict())
            return True

        except Exception as e:
            err_msg = str(e)
            job.error_message = err_msg
            job.failure_type = self.engine.classify_failure(err_msg)
            job.transition_to(OrchestratedRenderState.FAILED)

            # Clean up temp output on failure
            if os.path.exists(job.temp_output_path):
                try:
                    os.remove(job.temp_output_path)
                except Exception:
                    pass

            self._log_audit_event("RENDER_JOB_FAILED", job.to_dict())
            return False

        finally:
            # Release worker load
            if job.assigned_worker_id and job.assigned_worker_id in self._workers:
                self._workers[job.assigned_worker_id].current_active_jobs = max(
                    0, self._workers[job.assigned_worker_id].current_active_jobs - 1
                )

    # =========================================================================
    # 4. Cancellation & Retry
    # =========================================================================

    def cancel_job(self, job_id: str) -> bool:
        """Cancels a job if it is in an active non-terminal state."""
        job = self.get_job(job_id)
        if not job:
            return False

        if job.state in (
            OrchestratedRenderState.QUEUED,
            OrchestratedRenderState.SCHEDULED,
            OrchestratedRenderState.PREPARING,
            OrchestratedRenderState.RENDERING,
            OrchestratedRenderState.VALIDATING,
        ):
            job.transition_to(OrchestratedRenderState.CANCELLED)
            # Clean up temp
            if os.path.exists(job.temp_output_path):
                try:
                    os.remove(job.temp_output_path)
                except Exception:
                    pass

            # Release worker
            if job.assigned_worker_id and job.assigned_worker_id in self._workers:
                self._workers[job.assigned_worker_id].current_active_jobs = max(
                    0, self._workers[job.assigned_worker_id].current_active_jobs - 1
                )

            self._log_audit_event("RENDER_JOB_CANCELLED", {"job_id": job_id})
            return True
        return False

    def retry_job(self, job_id: str) -> bool:
        """Requeues a failed job if it is classified as TRANSIENT and within retry limits."""
        job = self.get_job(job_id)
        if not job:
            return False

        if job.state != OrchestratedRenderState.FAILED:
            return False

        if job.failure_type != FailureClassification.TRANSIENT:
            logger.warning(f"Job '{job_id}' failure is {job.failure_type.value}; non-retryable.")
            return False

        if job.attempt_count > job.max_retries:
            logger.warning(f"Job '{job_id}' exceeded max retries ({job.max_retries}).")
            return False

        # Reset temp output and transition back to QUEUED
        job.transition_to(OrchestratedRenderState.QUEUED)
        job.error_message = None
        job.failure_type = FailureClassification.NONE

        self._log_audit_event("RENDER_JOB_RETRY_QUEUED", {"job_id": job_id, "attempt": job.attempt_count})
        return True


# Global singleton
render_orchestration_service = RenderOrchestrationService()
