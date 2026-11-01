"""OMNIA Video Studio — Module 44: Render Pipeline Orchestration & Fault Recovery Models.

Defines authoritative domain models for:
- OrchestratedRenderState: Validated lifecycle states (CREATED, VALIDATING, QUEUED, SCHEDULED, PREPARING, RENDERING, FINALIZING, VERIFYING, COMPLETED, FAILED, CANCELLED, INTERRUPTED).
- FailureClassification: TRANSIENT (retryable e.g. worker timeout/concurrency) vs PERMANENT (unrecoverable e.g. missing asset, invalid codec).
- RenderWorkerDescriptor: Hardware & format capabilities of local/distributed execution workers.
- RenderOrchestrationJob: Extended render job capturing revision snapshot, conform mode, attempt counts, temporary output, checksums, and worker assignment.
- OrchestrationProgress: Fine-grained frame, percentage, elapsed time, and ETA tracking.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from video_studio.conform_models import MediaRepresentationMode
from video_studio.export_models import ExportConfig


ORCHESTRATION_SCHEMA_VERSION = "video-studio.render-orchestration.v1"


class OrchestratedRenderState(str, Enum):
    """Rigorous state machine for orchestrated render execution."""
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    SCHEDULED = "SCHEDULED"
    PREPARING = "PREPARING"
    RENDERING = "RENDERING"
    FINALIZING = "FINALIZING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


# Validated state transition mapping
VALID_STATE_TRANSITIONS: Dict[OrchestratedRenderState, Set[OrchestratedRenderState]] = {
    OrchestratedRenderState.CREATED: {OrchestratedRenderState.VALIDATING, OrchestratedRenderState.CANCELLED, OrchestratedRenderState.FAILED},
    OrchestratedRenderState.VALIDATING: {OrchestratedRenderState.QUEUED, OrchestratedRenderState.FAILED, OrchestratedRenderState.CANCELLED},
    OrchestratedRenderState.QUEUED: {OrchestratedRenderState.SCHEDULED, OrchestratedRenderState.CANCELLED, OrchestratedRenderState.INTERRUPTED},
    OrchestratedRenderState.SCHEDULED: {OrchestratedRenderState.PREPARING, OrchestratedRenderState.CANCELLED, OrchestratedRenderState.INTERRUPTED, OrchestratedRenderState.QUEUED},
    OrchestratedRenderState.PREPARING: {OrchestratedRenderState.RENDERING, OrchestratedRenderState.FAILED, OrchestratedRenderState.CANCELLED, OrchestratedRenderState.INTERRUPTED},
    OrchestratedRenderState.RENDERING: {OrchestratedRenderState.FINALIZING, OrchestratedRenderState.FAILED, OrchestratedRenderState.CANCELLED, OrchestratedRenderState.INTERRUPTED},
    OrchestratedRenderState.FINALIZING: {OrchestratedRenderState.VERIFYING, OrchestratedRenderState.FAILED, OrchestratedRenderState.CANCELLED},
    OrchestratedRenderState.VERIFYING: {OrchestratedRenderState.COMPLETED, OrchestratedRenderState.FAILED, OrchestratedRenderState.CANCELLED},
    OrchestratedRenderState.COMPLETED: set(),  # Terminal
    OrchestratedRenderState.FAILED: {OrchestratedRenderState.QUEUED},  # Requeue on retry
    OrchestratedRenderState.CANCELLED: set(), # Terminal
    OrchestratedRenderState.INTERRUPTED: {OrchestratedRenderState.QUEUED, OrchestratedRenderState.FAILED}, # Recoverable
}


class FailureClassification(str, Enum):
    """Categorization determining retry eligibility."""
    TRANSIENT = "TRANSIENT"         # Worker disconnect, process killed, temporary storage lock -> Safe to retry
    PERMANENT = "PERMANENT"         # Missing media asset, broken syntax, invalid resolution -> Do NOT retry
    NONE = "NONE"


@dataclass
class RenderWorkerDescriptor:
    """Advertised capabilities and health of a render execution worker."""
    worker_id: str = field(default_factory=lambda: f"worker_{uuid.uuid4().hex[:8]}")
    name: str = "Local Engine Worker"
    max_concurrent_jobs: int = 1
    supported_containers: List[str] = field(default_factory=lambda: ["mp4", "mov", "webm", "mkv", "wav"])
    supported_codecs: List[str] = field(default_factory=lambda: ["h264", "mp4v", "aac", "pcm"])
    is_available: bool = True
    last_heartbeat: float = field(default_factory=time.time)
    current_active_jobs: int = 0

    def can_handle(self, config: ExportConfig) -> bool:
        """Verifies if worker supports container and codec."""
        container_ok = config.container.value.lower() in [c.lower() for c in self.supported_containers]
        codec_ok = config.video_codec.value.lower() in [c.lower() for c in self.supported_codecs]
        return container_ok and (codec_ok or not config.include_video)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "supported_containers": list(self.supported_containers),
            "supported_codecs": list(self.supported_codecs),
            "is_available": self.is_available,
            "current_active_jobs": self.current_active_jobs,
            "last_heartbeat": self.last_heartbeat,
        }


@dataclass
class OrchestrationProgress:
    """Progress metrics for active render execution."""
    frames_rendered: int = 0
    total_frames: int = 0
    progress_percent: float = 0.0
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: Optional[float] = None
    fps: float = 0.0
    current_stage: str = "Idle"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frames_rendered": self.frames_rendered,
            "total_frames": self.total_frames,
            "progress_percent": round(self.progress_percent, 2),
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "estimated_remaining_seconds": round(self.estimated_remaining_seconds, 2) if self.estimated_remaining_seconds is not None else None,
            "fps": round(self.fps, 2),
            "current_stage": self.current_stage,
        }


@dataclass
class RenderOrchestrationJob:
    """Comprehensive render job with durability, fault tracking, and artifact verification."""
    job_id: str = field(default_factory=lambda: f"orch_job_{uuid.uuid4().hex[:10]}")
    project_id: str = ""
    sequence_id: str = ""
    revision_id: Optional[str] = None
    revision_number: int = 1
    output_path: str = ""
    temp_output_path: str = ""
    config: ExportConfig = field(default_factory=ExportConfig)
    representation_mode: MediaRepresentationMode = MediaRepresentationMode.ORIGINAL
    
    # Lifecycle
    state: OrchestratedRenderState = OrchestratedRenderState.CREATED
    progress: OrchestrationProgress = field(default_factory=OrchestrationProgress)
    priority: int = 50                  # 0 (lowest) to 100 (highest)
    assigned_worker_id: Optional[str] = None
    
    # Retry & Faults
    max_retries: int = 2
    attempt_count: int = 0
    failure_type: FailureClassification = FailureClassification.NONE
    error_message: Optional[str] = None
    
    # Output Verification
    output_sha256: Optional[str] = None
    output_size_bytes: int = 0
    is_verified: bool = False
    
    # Timestamps
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    updated_at: float = field(default_factory=time.time)

    def can_transition_to(self, new_state: OrchestratedRenderState) -> bool:
        """Enforces valid state machine transitions."""
        valid_next = VALID_STATE_TRANSITIONS.get(self.state, set())
        return new_state in valid_next

    def transition_to(self, new_state: OrchestratedRenderState, reason: str = "") -> None:
        """Applies state transition or raises ValueError on illegal jump."""
        if not self.can_transition_to(new_state):
            raise ValueError(
                f"Illegal render state transition: cannot jump from '{self.state.value}' to '{new_state.value}'. "
                f"Valid next states: {[s.value for s in VALID_STATE_TRANSITIONS.get(self.state, set())]}"
            )
        self.state = new_state
        self.updated_at = time.time()
        if new_state == OrchestratedRenderState.RENDERING and self.started_at is None:
            self.started_at = time.time()
        elif new_state in (OrchestratedRenderState.COMPLETED, OrchestratedRenderState.FAILED, OrchestratedRenderState.CANCELLED):
            self.completed_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_id": self.project_id,
            "sequence_id": self.sequence_id,
            "revision_id": self.revision_id,
            "revision_number": self.revision_number,
            "output_path": self.output_path,
            "temp_output_path": self.temp_output_path,
            "representation_mode": self.representation_mode.value,
            "state": self.state.value,
            "priority": self.priority,
            "assigned_worker_id": self.assigned_worker_id,
            "attempt_count": self.attempt_count,
            "max_retries": self.max_retries,
            "failure_type": self.failure_type.value,
            "error_message": self.error_message,
            "output_sha256": self.output_sha256,
            "output_size_bytes": self.output_size_bytes,
            "is_verified": self.is_verified,
            "progress": self.progress.to_dict(),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "updated_at": self.updated_at,
        }
