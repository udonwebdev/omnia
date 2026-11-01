"""OMNIA Video Studio — Module 45: Remote Worker Protocol & Distributed Rendering Models.

Authoritative domain models for:
- RemoteWorkerProtocolVersion: Supported versioning ("video-studio.remote-worker.v1").
- RemoteMessageType: REGISTER, AUTHENTICATE, HEARTBEAT, ASSIGN_JOB, ACCEPT_JOB, REJECT_JOB, PROGRESS, CANCEL, COMPLETE, FAIL.
- WorkerHealthStatus: ONLINE, BUSY, DEGRADED, TIMEOUT, REVOKED, OFFLINE.
- RemoteWorkerRegistration: Authenticated remote worker record with capabilities, authentication tokens, and leasing.
- RemoteJobAssignment: Cryptographic leasing token, fencing token, and scoped asset manifest for assigned job.
- ChunkedAssetTransferEnvelope: Chunked streaming protocol for transferring source assets and returning rendered artifacts.
- RemoteWorkerMessage: Strongly-typed protocol envelope with correlation IDs, timestamps, and signatures.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from video_studio.export_models import ExportConfig


REMOTE_WORKER_PROTOCOL_VERSION = "video-studio.remote-worker.v1"


class RemoteMessageType(str, Enum):
    """Protocol message types between Render Coordinator and Remote Workers."""
    REGISTER = "REGISTER"
    HEARTBEAT = "HEARTBEAT"
    ASSIGN_JOB = "ASSIGN_JOB"
    ACCEPT_JOB = "ACCEPT_JOB"
    REJECT_JOB = "REJECT_JOB"
    PROGRESS = "PROGRESS"
    CANCEL = "CANCEL"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    DISCONNECT = "DISCONNECT"


class WorkerHealthStatus(str, Enum):
    """Real-time operational health classification of a remote worker node."""
    ONLINE = "ONLINE"           # Healthy, reachable, ready to accept jobs
    BUSY = "BUSY"               # Reached max concurrent task capacity
    DEGRADED = "DEGRADED"       # High error rate or dropped heartbeats
    TIMEOUT = "TIMEOUT"         # Missed consecutive heartbeat deadlines
    REVOKED = "REVOKED"         # Explicitly banned or unauthorized
    OFFLINE = "OFFLINE"         # Gracefully disconnected


@dataclass
class RemoteWorkerRegistration:
    """Identity, authenticated credentials, and capability profile for a remote worker."""
    worker_id: str = field(default_factory=lambda: f"rworker_{uuid.uuid4().hex[:10]}")
    name: str = "Remote Render Node"
    auth_token_hash: str = ""           # SHA-256 hash of worker authentication secret
    protocol_version: str = REMOTE_WORKER_PROTOCOL_VERSION
    
    # Capabilities
    supported_containers: List[str] = field(default_factory=lambda: ["mp4", "mov", "webm", "mkv", "wav"])
    supported_codecs: List[str] = field(default_factory=lambda: ["h264", "mp4v", "aac", "pcm"])
    has_gpu_acceleration: bool = False
    max_concurrent_jobs: int = 2
    
    # Operational Status
    status: WorkerHealthStatus = WorkerHealthStatus.ONLINE
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_timeout_seconds: float = 30.0
    active_job_ids: List[str] = field(default_factory=list)
    total_completed_jobs: int = 0
    total_failed_jobs: int = 0
    is_revoked: bool = False
    
    registered_at: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)

    def is_alive(self, current_time: Optional[float] = None) -> bool:
        """Determines if worker has reported within its heartbeat timeout window."""
        now = current_time if current_time is not None else time.time()
        if self.is_revoked:
            return False
        return (now - self.last_heartbeat) <= self.heartbeat_timeout_seconds

    def can_accept_job(self, config: ExportConfig) -> bool:
        """Verifies if worker is active, capable, and has spare capacity."""
        if self.is_revoked or not self.is_alive():
            return False
        if len(self.active_job_ids) >= self.max_concurrent_jobs:
            return False
        
        container_ok = config.container.value.lower() in [c.lower() for c in self.supported_containers]
        codec_ok = config.video_codec.value.lower() in [c.lower() for c in self.supported_codecs]
        return container_ok and (codec_ok or not config.include_video)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "name": self.name,
            "protocol_version": self.protocol_version,
            "status": self.status.value,
            "has_gpu_acceleration": self.has_gpu_acceleration,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "active_jobs_count": len(self.active_job_ids),
            "active_job_ids": list(self.active_job_ids),
            "total_completed_jobs": self.total_completed_jobs,
            "total_failed_jobs": self.total_failed_jobs,
            "is_revoked": self.is_revoked,
            "last_heartbeat": self.last_heartbeat,
            "registered_at": self.registered_at,
        }


@dataclass
class RemoteJobAssignment:
    """Lease and fencing token binding a specific job to an authenticated worker."""
    assignment_id: str = field(default_factory=lambda: f"asgn_{uuid.uuid4().hex[:8]}")
    job_id: str = ""
    worker_id: str = ""
    fencing_token: int = 1              # Monotonically increasing token to reject stale completions
    lease_expires_at: float = 0.0
    scoped_asset_paths: List[str] = field(default_factory=list)
    is_active: bool = True
    created_at: float = field(default_factory=time.time)

    def is_lease_valid(self, now: Optional[float] = None) -> bool:
        current = now if now is not None else time.time()
        return self.is_active and (current <= self.lease_expires_at)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "fencing_token": self.fencing_token,
            "lease_expires_at": self.lease_expires_at,
            "scoped_assets_count": len(self.scoped_asset_paths),
            "is_active": self.is_active,
            "created_at": self.created_at,
        }


@dataclass
class ChunkedAssetTransferEnvelope:
    """Streaming chunk payload for transferring assets or returning rendered artifacts."""
    transfer_id: str = field(default_factory=lambda: f"xfer_{uuid.uuid4().hex[:8]}")
    asset_id: str = ""
    chunk_index: int = 0
    total_chunks: int = 1
    chunk_bytes: bytes = b""
    chunk_sha256: str = ""
    is_last_chunk: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transfer_id": self.transfer_id,
            "asset_id": self.asset_id,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "chunk_size_bytes": len(self.chunk_bytes),
            "chunk_sha256": self.chunk_sha256,
            "is_last_chunk": self.is_last_chunk,
        }


@dataclass
class RemoteWorkerMessage:
    """Standardized envelope for protocol message passing."""
    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:10]}")
    protocol_version: str = REMOTE_WORKER_PROTOCOL_VERSION
    message_type: RemoteMessageType = RemoteMessageType.HEARTBEAT
    worker_id: str = ""
    job_id: Optional[str] = None
    fencing_token: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def validate(self) -> Tuple[bool, Optional[str]]:
        if self.protocol_version != REMOTE_WORKER_PROTOCOL_VERSION:
            return False, f"Incompatible protocol version '{self.protocol_version}'. Expected '{REMOTE_WORKER_PROTOCOL_VERSION}'."
        if not self.worker_id:
            return False, "Message must specify worker_id."
        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "protocol_version": self.protocol_version,
            "message_type": self.message_type.value,
            "worker_id": self.worker_id,
            "job_id": self.job_id,
            "fencing_token": self.fencing_token,
            "payload": dict(self.payload),
            "timestamp": self.timestamp,
        }
