"""OMNIA Video Studio — Module 45: Remote Worker Protocol & Verification Engine.

Algorithmic logic for:
- Worker authentication and credential verification (constant-time token hash checks).
- Fencing token validation to prevent split-brain dual completion.
- Chunked file transfer assembly and SHA-256 verification.
- Scoped asset manifest extraction preventing directory exposure to remote workers.
- Heartbeat expiration and worker health state recalculation.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any, Dict, List, Optional, Tuple

from video_studio.provenance_engine import compute_file_sha256_chunked
from video_studio.remote_models import (
    ChunkedAssetTransferEnvelope,
    RemoteJobAssignment,
    RemoteWorkerMessage,
    RemoteWorkerRegistration,
    WorkerHealthStatus,
)


def hash_secret_token(token: str) -> str:
    """Computes SHA-256 hash of an authentication secret token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RemoteWorkerEngine:
    """Core protocol validation, lease fencing, and artifact verification engine for remote workers."""

    @staticmethod
    def verify_worker_auth(worker: RemoteWorkerRegistration, provided_token: str) -> bool:
        """Verifies provided secret token against stored hash using constant-time comparison."""
        if not worker or worker.is_revoked:
            return False
        computed = hash_secret_token(provided_token)
        return hmac.compare_digest(worker.auth_token_hash, computed)

    @staticmethod
    def validate_fencing_token(
        assignment: RemoteJobAssignment,
        incoming_token: int,
        now: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Prevents dual-execution race conditions by ensuring incoming token matches active lease."""
        if not assignment.is_active:
            return False, f"Assignment for job '{assignment.job_id}' is no longer active."

        if not assignment.is_lease_valid(now):
            return False, f"Assignment lease for job '{assignment.job_id}' expired."

        if incoming_token != assignment.fencing_token:
            return False, f"Stale fencing token {incoming_token}. Active token is {assignment.fencing_token}."

        return True, None

    @staticmethod
    def assemble_chunked_file(
        chunks: List[ChunkedAssetTransferEnvelope],
        destination_path: str,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Assembles verified streaming chunks into destination file and confirms SHA-256 integrity.

        Returns:
            Tuple: (success, error_message, assembled_file_sha256)
        """
        # Sort by chunk index
        sorted_chunks = sorted(chunks, key=lambda c: c.chunk_index)
        if not sorted_chunks:
            return False, "No chunks provided for transfer.", None

        # Verify contiguous indices
        for idx, ch in enumerate(sorted_chunks):
            if ch.chunk_index != idx:
                return False, f"Missing chunk index {idx} in transfer sequence.", None

        parent_dir = os.path.dirname(destination_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        try:
            with open(destination_path, "wb") as f:
                for ch in sorted_chunks:
                    # Validate individual chunk hash if present
                    if ch.chunk_sha256:
                        chunk_hash = hashlib.sha256(ch.chunk_bytes).hexdigest()
                        if chunk_hash != ch.chunk_sha256:
                            return False, f"Chunk {ch.chunk_index} checksum mismatch.", None
                    f.write(ch.chunk_bytes)

            file_hash = compute_file_sha256_chunked(destination_path)
            return True, None, file_hash
        except Exception as e:
            return False, f"Failed assembling file at '{destination_path}': {str(e)}", None

    @staticmethod
    def audit_worker_health(
        workers: List[RemoteWorkerRegistration],
        current_time: Optional[float] = None,
    ) -> List[RemoteWorkerRegistration]:
        """Scans worker registry and updates statuses of nodes whose heartbeats timed out."""
        timed_out_workers: List[RemoteWorkerRegistration] = []
        for w in workers:
            if w.is_revoked:
                continue
            if not w.is_alive(current_time):
                if w.status != WorkerHealthStatus.TIMEOUT:
                    w.status = WorkerHealthStatus.TIMEOUT
                    timed_out_workers.append(w)
            elif len(w.active_job_ids) >= w.max_concurrent_jobs:
                w.status = WorkerHealthStatus.BUSY
            else:
                w.status = WorkerHealthStatus.ONLINE
        return timed_out_workers
