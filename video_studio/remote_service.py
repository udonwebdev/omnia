"""OMNIA Video Studio — Module 45: Remote Worker Coordinator & Distributed Rendering Service.

Enterprise service coordinating:
- Remote worker registration, authentication, revocation, and heartbeat tracking.
- Secure job dispatch with fencing tokens, lease duration, and scoped asset manifests.
- Multi-worker load-balanced scheduling.
- Worker heartbeat monitoring, timeout detection, and automatic job recovery/reassignment.
- Stale completion rejection using monotonic fencing tokens.
- Chunked artifact transfer verification and publication via Module 44 Orchestration.
- Capability registration in VideoStudioCapabilityRegistry.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from video_studio.export_models import ExportConfig
from video_studio.orchestration_models import (
    FailureClassification,
    OrchestratedRenderState,
    OrchestrationProgress,
    RenderOrchestrationJob,
)
from video_studio.orchestration_service import RenderOrchestrationService, render_orchestration_service
from video_studio.registry import VideoStudioCapabilityRegistry, video_studio_capability_registry
from video_studio.registry_models import (
    ImplementationState,
    VideoStudioCategory,
    VideoStudioCapabilityDescriptor,
)
from video_studio.remote_engine import RemoteWorkerEngine, hash_secret_token
from video_studio.remote_models import (
    ChunkedAssetTransferEnvelope,
    REMOTE_WORKER_PROTOCOL_VERSION,
    RemoteJobAssignment,
    RemoteMessageType,
    RemoteWorkerMessage,
    RemoteWorkerRegistration,
    WorkerHealthStatus,
)

logger = logging.getLogger("omnia.video_studio.remote_coordinator")


class RemoteWorkerCoordinatorService:
    """Enterprise Coordinator for Remote Render Workers & Secure Distributed Rendering."""

    def __init__(
        self,
        capability_registry: Optional[VideoStudioCapabilityRegistry] = None,
        orch_service: Optional[RenderOrchestrationService] = None,
        audit_log_path: str = "omnia_audit.jsonl",
        default_lease_seconds: float = 300.0,
    ) -> None:
        self.registry = capability_registry or video_studio_capability_registry
        self.orchestration_service = orch_service or render_orchestration_service
        self.audit_log_path = audit_log_path
        self.default_lease_seconds = default_lease_seconds
        self.engine = RemoteWorkerEngine()

        # In-memory registry:
        # worker_id -> RemoteWorkerRegistration
        self._workers: Dict[str, RemoteWorkerRegistration] = {}
        # job_id -> RemoteJobAssignment
        self._assignments: Dict[str, RemoteJobAssignment] = {}
        # Monotonically increasing fencing counter per job_id
        self._fencing_counters: Dict[str, int] = {}

        if self.registry:
            self.register_capabilities()

    def register_capabilities(self) -> None:
        """Registers Module 45 Remote Worker capabilities into the registry."""
        capabilities = [
            VideoStudioCapabilityDescriptor(
                id="video.render.remote_worker_protocol",
                name="Remote Render Worker Protocol & Verification",
                description="Secure versioned protocol for remote worker registration, heartbeat tracking, and job dispatch.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["remote", "render_farm", "protocol", "distributed"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.distributed_job_dispatch",
                name="Distributed Job Dispatch & Fencing Leases",
                description="Secure job assignment with monotonic fencing tokens and scoped asset transfer boundaries.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["dispatch", "fencing_token", "leases", "security"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.worker_fault_recovery",
                name="Worker Disconnection Detection & Auto-Recovery",
                description="Heartbeat timeout tracking, zombie task recovery, and automatic job reassignment.",
                category=VideoStudioCategory.RENDERING,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["fault_tolerance", "recovery", "heartbeat", "zombie_cleanup"],
            ),
            VideoStudioCapabilityDescriptor(
                id="video.render.chunked_artifact_transfer",
                name="Chunked Media Transfer & Ingest Verification",
                description="Streaming chunked media artifact transfer with SHA-256 verification and atomic ingest.",
                category=VideoStudioCategory.EXPORT,
                implementation_state=ImplementationState.IMPLEMENTED,
                tags=["transfer", "chunking", "artifact", "integrity"],
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
    # 1. Worker Registration & Identity
    # =========================================================================

    def register_worker(
        self,
        worker_id: str,
        name: str,
        secret_token: str,
        supported_containers: Optional[List[str]] = None,
        supported_codecs: Optional[List[str]] = None,
        has_gpu: bool = False,
        max_concurrent_jobs: int = 2,
        protocol_version: str = REMOTE_WORKER_PROTOCOL_VERSION,
    ) -> RemoteWorkerRegistration:
        """Authenticates and registers a remote worker node into the coordinator pool."""
        if protocol_version != REMOTE_WORKER_PROTOCOL_VERSION:
            raise ValueError(f"Incompatible protocol version '{protocol_version}'. Expected '{REMOTE_WORKER_PROTOCOL_VERSION}'.")

        if not worker_id or not secret_token:
            raise ValueError("worker_id and secret_token are required.")

        token_hash = hash_secret_token(secret_token)
        containers = supported_containers or ["mp4", "mov", "webm", "mkv", "wav"]
        codecs = supported_codecs or ["h264", "mp4v", "aac", "pcm"]

        worker = RemoteWorkerRegistration(
            worker_id=worker_id,
            name=name,
            auth_token_hash=token_hash,
            protocol_version=protocol_version,
            supported_containers=containers,
            supported_codecs=codecs,
            has_gpu_acceleration=has_gpu,
            max_concurrent_jobs=max_concurrent_jobs,
            status=WorkerHealthStatus.ONLINE,
        )

        self._workers[worker_id] = worker
        self._log_audit_event("REMOTE_WORKER_REGISTERED", worker.to_dict())
        return worker

    def get_worker(self, worker_id: str) -> Optional[RemoteWorkerRegistration]:
        return self._workers.get(worker_id)

    def list_workers(self) -> List[RemoteWorkerRegistration]:
        return list(self._workers.values())

    def get_all_workers(self) -> List[RemoteWorkerRegistration]:
        return list(self._workers.values())

    def revoke_worker(self, worker_id: str, reason: str = "") -> bool:
        """Revokes a worker's authorization, immediately banning it from receiving or completing jobs."""
        worker = self.get_worker(worker_id)
        if not worker:
            return False

        worker.is_revoked = True
        worker.status = WorkerHealthStatus.REVOKED
        self._log_audit_event("REMOTE_WORKER_REVOKED", {"worker_id": worker_id, "reason": reason})
        return True

    def process_heartbeat(
        self,
        worker_id: str,
        secret_token: str,
        active_jobs: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Processes worker periodic heartbeat and confirms operational health."""
        worker = self.get_worker(worker_id)
        if not worker:
            return False, f"Worker '{worker_id}' not found."

        if not self.engine.verify_worker_auth(worker, secret_token):
            return False, "Authentication failure: invalid token."

        worker.last_heartbeat = time.time()
        if active_jobs is not None:
            worker.active_job_ids = list(active_jobs)

        if len(worker.active_job_ids) >= worker.max_concurrent_jobs:
            worker.status = WorkerHealthStatus.BUSY
        else:
            worker.status = WorkerHealthStatus.ONLINE

        return True, None

    # =========================================================================
    # 2. Remote Job Dispatch & Fencing
    # =========================================================================

    def assign_job_to_worker(
        self,
        job_id: str,
        worker_id: str,
        scoped_assets: Optional[List[str]] = None,
    ) -> RemoteJobAssignment:
        """Assigns an orchestrated render job to a remote worker with lease and fencing token."""
        worker = self.get_worker(worker_id)
        if not worker or worker.is_revoked:
            raise KeyError(f"Eligible worker '{worker_id}' not available.")

        job = self.orchestration_service.get_job(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found in orchestration queue.")

        if not worker.can_accept_job(job.config):
            raise ValueError(f"Worker '{worker_id}' cannot accept job with current config or capacity.")

        # Increment fencing counter for this job to prevent stale worker completions
        token = self._fencing_counters.get(job_id, 0) + 1
        self._fencing_counters[job_id] = token

        lease_exp = time.time() + self.default_lease_seconds
        assignment = RemoteJobAssignment(
            job_id=job_id,
            worker_id=worker_id,
            fencing_token=token,
            lease_expires_at=lease_exp,
            scoped_asset_paths=list(scoped_assets or []),
        )

        self._assignments[job_id] = assignment
        worker.active_job_ids.append(job_id)
        job.assigned_worker_id = worker_id
        if job.state == OrchestratedRenderState.QUEUED:
            job.transition_to(OrchestratedRenderState.SCHEDULED)

        self._log_audit_event("REMOTE_JOB_ASSIGNED", assignment.to_dict())
        return assignment

    def get_assignment(self, job_id: str) -> Optional[RemoteJobAssignment]:
        return self._assignments.get(job_id)

    # =========================================================================
    # 3. Remote Progress & Completion Verification
    # =========================================================================

    def report_progress(
        self,
        worker_id: str,
        secret_token: str,
        job_id: str,
        fencing_token: int,
        progress_percent: float,
        frames_rendered: int,
        total_frames: int,
        stage: str = "Rendering",
    ) -> Tuple[bool, Optional[str]]:
        """Validates worker and fencing lease, then updates live job progress."""
        worker = self.get_worker(worker_id)
        if not self.engine.verify_worker_auth(worker, secret_token):
            return False, "Unauthorized worker."

        assignment = self.get_assignment(job_id)
        if not assignment:
            return False, f"No active assignment for job '{job_id}'."

        ok_token, err_token = self.engine.validate_fencing_token(assignment, fencing_token)
        if not ok_token:
            return False, err_token

        job = self.orchestration_service.get_job(job_id)
        if not job:
            return False, f"Job '{job_id}' not found."

        if job.state == OrchestratedRenderState.SCHEDULED:
            job.transition_to(OrchestratedRenderState.PREPARING)
            job.transition_to(OrchestratedRenderState.RENDERING)

        job.progress = OrchestrationProgress(
            frames_rendered=frames_rendered,
            total_frames=total_frames,
            progress_percent=progress_percent,
            current_stage=stage,
        )
        return True, None

    def complete_remote_job(
        self,
        worker_id: str,
        secret_token: str,
        job_id: str,
        fencing_token: int,
        returned_artifact_chunks: List[ChunkedAssetTransferEnvelope],
    ) -> Tuple[bool, Optional[str]]:
        """Receives rendered artifact chunks, validates fencing lease, verifies hash, and finalizes."""
        worker = self.get_worker(worker_id)
        if not self.engine.verify_worker_auth(worker, secret_token):
            return False, "Unauthorized worker."

        assignment = self.get_assignment(job_id)
        if not assignment:
            return False, f"No active assignment for job '{job_id}'."

        ok_token, err_token = self.engine.validate_fencing_token(assignment, fencing_token)
        if not ok_token:
            return False, err_token

        job = self.orchestration_service.get_job(job_id)
        if not job:
            return False, f"Job '{job_id}' not found."

        # Progress job state to intermediate stages if needed prior to completion
        if job.state in (OrchestratedRenderState.CREATED, OrchestratedRenderState.VALIDATING):
            job.state = OrchestratedRenderState.SCHEDULED
        if job.state == OrchestratedRenderState.SCHEDULED:
            job.transition_to(OrchestratedRenderState.PREPARING)
            job.transition_to(OrchestratedRenderState.RENDERING)
        elif job.state == OrchestratedRenderState.PREPARING:
            job.transition_to(OrchestratedRenderState.RENDERING)

        # Assemble chunks into job's temp_output_path
        ok_assemble, err_assemble, file_sha = self.engine.assemble_chunked_file(
            returned_artifact_chunks, job.temp_output_path
        )
        if not ok_assemble:
            job.transition_to(OrchestratedRenderState.FAILED)
            job.error_message = f"Failed assembling returned artifact: {err_assemble}"
            job.failure_type = FailureClassification.TRANSIENT
            return False, job.error_message

        if job.state == OrchestratedRenderState.RENDERING:
            job.transition_to(OrchestratedRenderState.FINALIZING)
        if job.state == OrchestratedRenderState.FINALIZING:
            job.transition_to(OrchestratedRenderState.VERIFYING)

        # Output verification
        ok_ver, err_ver, sha, size = self.orchestration_service.engine.verify_output_artifact(job.temp_output_path)
        if not ok_ver:
            job.transition_to(OrchestratedRenderState.FAILED)
            job.error_message = f"Returned artifact verification failed: {err_ver}"
            return False, job.error_message

        job.output_sha256 = sha
        job.output_size_bytes = size
        job.is_verified = True

        # Atomic publish
        ok_pub, err_pub = self.orchestration_service.engine.publish_output_atomically(
            job.temp_output_path, job.output_path
        )
        if not ok_pub:
            job.transition_to(OrchestratedRenderState.FAILED)
            job.error_message = f"Atomic publish failed: {err_pub}"
            return False, job.error_message

        job.transition_to(OrchestratedRenderState.COMPLETED)
        assignment.is_active = False
        if job_id in worker.active_job_ids:
            worker.active_job_ids.remove(job_id)
        worker.total_completed_jobs += 1

        self._log_audit_event("REMOTE_JOB_COMPLETED_AND_PUBLISHED", {
            "job_id": job_id,
            "worker_id": worker_id,
            "output_sha256": sha,
            "size_bytes": size,
        })
        return True, None

    # =========================================================================
    # 4. Heartbeat Sweeping & Fault Recovery
    # =========================================================================

    def check_worker_health_and_recover(self, current_time: Optional[float] = None) -> List[str]:
        """Audits all worker heartbeats, detects timeouts, and requeues orphan jobs."""
        timed_out = self.engine.audit_worker_health(list(self._workers.values()), current_time)
        recovered_jobs: List[str] = []

        for worker in timed_out:
            # Reclaim active jobs assigned to timed out worker
            for jid in list(worker.active_job_ids):
                assignment = self.get_assignment(jid)
                if assignment:
                    assignment.is_active = False
                job = self.orchestration_service.get_job(jid)
                if job and job.state in (OrchestratedRenderState.SCHEDULED, OrchestratedRenderState.RENDERING):
                    job.transition_to(OrchestratedRenderState.FAILED)
                    job.failure_type = FailureClassification.TRANSIENT
                    job.error_message = f"Assigned remote worker '{worker.worker_id}' heartbeat timed out."
                    # Auto retry if attempts remaining
                    self.orchestration_service.retry_job(jid)
                    recovered_jobs.append(jid)
            worker.active_job_ids.clear()

        return recovered_jobs


# Global singleton
remote_worker_coordinator_service = RemoteWorkerCoordinatorService()
