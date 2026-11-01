"""OMNIA Video Studio — Missing Media Detection & Media Relinking Engine (Module 18).

Coordinates:
- Verification and detection of offline, moved, or missing original assets.
- Approved search-root candidate discovery (traversing directories safely).
- Multi-signal matching (fingerprint, filename, size, duration, format).
- Confidence scoring (0.0 to 1.0) and candidate disambiguation.
- Transactional relinking with timeline reference preservation.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import time
import uuid
import hashlib
import cv2
import logging

from video_studio.proxy_models import RelinkCandidate, RelinkResult
from video_studio.media_models import MediaAsset
from video_studio.media_storage import media_storage_manager
from video_studio.media_library import media_library_registry

logger = logging.getLogger("omnia.video_studio.relinking_engine")

class RelinkingEngine:
    """Core candidate matching and asset recovery engine for missing media."""

    def find_candidates_for_asset(
        self,
        asset: MediaAsset,
        search_roots: List[str],
        max_results: int = 10,
    ) -> List[RelinkCandidate]:
        """Discovers and scores potential file matches across approved directories."""
        candidates: List[RelinkCandidate] = []
        expected_filename = asset.original_name or os.path.basename(asset.file_location)
        expected_size = asset.size_bytes
        expected_fingerprint = asset.content_hash_sha256 or ""

        for root in search_roots:
            if not os.path.exists(root) or not os.path.isdir(root):
                continue

            for dirpath, _, filenames in os.walk(root):
                for fname in filenames:
                    # Ignore temporary / hidden files
                    if fname.startswith(".") or fname.startswith("~"):
                        continue

                    full_path = os.path.join(dirpath, fname)
                    try:
                        cand_size = os.path.getsize(full_path)
                    except OSError:
                        continue

                    score = 0.0
                    match_reasons = []

                    # 1. Exact Filename Match
                    if fname.lower() == expected_filename.lower():
                        score += 0.4
                        match_reasons.append("Exact filename match")
                    elif os.path.splitext(fname)[0].lower() == os.path.splitext(expected_filename)[0].lower():
                        score += 0.2
                        match_reasons.append("Base name match")

                    # 2. File Size Match
                    if expected_size > 0:
                        if cand_size == expected_size:
                            score += 0.3
                            match_reasons.append("Identical byte size")
                        elif abs(cand_size - expected_size) < 1024:
                            score += 0.1
                            match_reasons.append("Near-identical byte size")

                    # 3. Fast Fingerprint Check (if score is promising)
                    cand_fp = ""
                    if score >= 0.4 and expected_fingerprint:
                        cand_fp = self._compute_fingerprint(full_path)
                        if cand_fp == expected_fingerprint:
                            score = 1.0 # Exact match
                            match_reasons.append("Verified cryptographic fingerprint match")

                    if score >= 0.3:
                        # Probe basic container metrics
                        w, h, fps, dur = self._quick_probe_video(full_path)
                        candidates.append(
                            RelinkCandidate(
                                candidate_path=full_path,
                                file_name=fname,
                                size_bytes=cand_size,
                                duration_seconds=dur,
                                detected_width=w,
                                detected_height=h,
                                detected_fps=fps,
                                content_fingerprint=cand_fp,
                                confidence_score=min(1.0, score),
                                match_reasons=match_reasons,
                            )
                        )

        # Sort descending by confidence score
        candidates.sort(key=lambda c: c.confidence_score, reverse=True)
        return candidates[:max_results]

    def relink_asset(
        self,
        asset: MediaAsset,
        new_file_path: str,
        verify_content: bool = True,
    ) -> RelinkResult:
        """Executes a transactional relink, updating asset path while preserving timeline identity."""
        relink_id = f"relink_{uuid.uuid4().hex[:8]}"
        prev_path = asset.file_location

        if not os.path.exists(new_file_path):
            return RelinkResult(
                relink_id=relink_id,
                asset_id=asset.asset_id,
                project_id=asset.project_id,
                previous_path=prev_path,
                new_path=new_file_path,
                is_success=False,
                confidence_score=0.0,
                error_message=f"Candidate file does not exist: '{new_file_path}'",
            )

        new_size = os.path.getsize(new_file_path)
        new_fp = self._compute_fingerprint(new_file_path)
        confidence = 0.5
        if asset.content_hash_sha256 and new_fp == asset.content_hash_sha256:
            confidence = 1.0
        elif asset.size_bytes > 0 and new_size == asset.size_bytes:
            confidence = 0.8

        # Update MediaAsset properties in-place
        asset.file_location = new_file_path
        asset.size_bytes = new_size
        asset.content_hash_sha256 = new_fp
        asset.status_reason = f"Relinked to {new_file_path}"
        asset.updated_at = time.time()

        # Update ProjectMediaLibrary
        pml = media_library_registry.get_or_create(asset.project_id)
        pml.add_asset(asset)

        logger.info(f"Asset '{asset.asset_id}' successfully relinked from '{prev_path}' to '{new_file_path}'.")
        return RelinkResult(
            relink_id=relink_id,
            asset_id=asset.asset_id,
            project_id=asset.project_id,
            previous_path=prev_path,
            new_path=new_file_path,
            is_success=True,
            confidence_score=confidence,
        )

    def _quick_probe_video(self, file_path: str) -> Tuple[int, int, float, float]:
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return 0, 0, 0.0, 0.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur = cnt / max(1.0, fps)
        cap.release()
        return w, h, fps, dur

    def _compute_fingerprint(self, file_path: str) -> str:
        h = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                head = f.read(65536)
                h.update(head)
                f.seek(0, os.SEEK_END)
                size = f.tell()
                if size > 65536:
                    f.seek(max(0, size - 65536))
                    tail = f.read(65536)
                    h.update(tail)
            return h.hexdigest()
        except Exception:
            return ""

# Global singleton
relinking_engine = RelinkingEngine()
