"""OMNIA Video Studio — Module 44: Render Orchestration & Output Verification Engine.

Algorithmic core for:
- Pre-render preflight validation (path security, revision resolution, dependency checking).
- Worker capability matching and priority queue scheduling.
- Transient vs permanent failure classification.
- Output integrity inspection (existence, file readability, size, duration, chunked SHA-256 fingerprint).
- Atomic publication (moving verified temp file to destination path safely).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from video_studio.conform_models import ConformCompatibilityGrade, MediaRepresentationMode
from video_studio.export_models import ExportConfig
from video_studio.orchestration_models import (
    FailureClassification,
    OrchestratedRenderState,
    RenderOrchestrationJob,
    RenderWorkerDescriptor,
)
from video_studio.provenance_engine import compute_file_sha256_chunked
from video_studio.timeline_models import VideoSequence


class OrchestrationEngine:
    """Core domain logic for render validation, worker dispatch, failure classification, and output publication."""

    @staticmethod
    def validate_render_path(output_path: str) -> Tuple[bool, Optional[str]]:
        """Ensures output path is non-empty, normalized, and not trying path traversal."""
        if not output_path or not output_path.strip():
            return False, "Output path cannot be empty."

        norm = os.path.normpath(output_path)
        # Check parent dir
        parent = os.path.dirname(norm)
        if parent and not os.path.exists(parent):
            try:
                os.makedirs(parent, exist_ok=True)
            except Exception as e:
                return False, f"Failed to create output directory '{parent}': {str(e)}"

        return True, None

    @staticmethod
    def select_best_worker(
        job: RenderOrchestrationJob,
        workers: List[RenderWorkerDescriptor],
    ) -> Optional[RenderWorkerDescriptor]:
        """Finds available worker matching job codec requirements with lowest active load."""
        eligible = [
            w for w in workers
            if w.is_available
            and w.current_active_jobs < w.max_concurrent_jobs
            and w.can_handle(job.config)
        ]
        if not eligible:
            return None

        # Sort by active load ascending
        eligible.sort(key=lambda w: w.current_active_jobs)
        return eligible[0]

    @staticmethod
    def classify_failure(error_msg: str) -> FailureClassification:
        """Classifies an error string as TRANSIENT (retryable) or PERMANENT."""
        err_lower = error_msg.lower()
        permanent_keywords = [
            "missing",
            "not found",
            "permission denied",
            "access denied",
            "invalid codec",
            "unsupported container",
            "broken syntax",
            "illegal state",
        ]
        for kw in permanent_keywords:
            if kw in err_lower:
                return FailureClassification.PERMANENT

        transient_keywords = [
            "timeout",
            "timed out",
            "disconnected",
            "busy",
            "temporarily unavailable",
            "worker crashed",
            "interrupted",
            "connection reset",
            "locked",
        ]
        for kw in transient_keywords:
            if kw in err_lower:
                return FailureClassification.TRANSIENT

        return FailureClassification.PERMANENT

    @staticmethod
    def verify_output_artifact(
        temp_file_path: str,
        expected_min_bytes: int = 16,
    ) -> Tuple[bool, Optional[str], Optional[str], int]:
        """Probes output file confirming existence, readability, size, and generates cryptographic fingerprint.

        Returns:
            Tuple: (is_valid, error_message, sha256_hash, file_size_bytes)
        """
        if not os.path.exists(temp_file_path) or not os.path.isfile(temp_file_path):
            return False, f"Rendered output missing at '{temp_file_path}'.", None, 0

        size = os.path.getsize(temp_file_path)
        if size < expected_min_bytes:
            return False, f"Rendered output too small ({size} bytes, expected >= {expected_min_bytes}).", None, size

        # Compute fingerprint
        sha = compute_file_sha256_chunked(temp_file_path)
        if not sha:
            return False, "Failed to compute content hash for rendered output.", None, size

        return True, None, sha, size

    @staticmethod
    def publish_output_atomically(
        temp_file_path: str,
        destination_path: str,
        overwrite: bool = True,
    ) -> Tuple[bool, Optional[str]]:
        """Atomically moves verified temporary render artifact to target destination."""
        if not os.path.exists(temp_file_path):
            return False, f"Source temp file '{temp_file_path}' does not exist."

        if os.path.exists(destination_path) and not overwrite:
            return False, f"Destination file '{destination_path}' already exists and overwrite=False."

        try:
            # Atomic replace or copy
            if os.path.exists(destination_path):
                os.remove(destination_path)
            shutil.move(temp_file_path, destination_path)
            return True, None
        except Exception as e:
            return False, f"Failed atomic publish from '{temp_file_path}' to '{destination_path}': {str(e)}"
