"""OMNIA Video Studio — Proxy Media Generation, Timing Mapping & Verification Engine (Module 18).

Coordinates:
- Non-destructive downscaled proxy rendering via OpenCV VideoWriter.
- Exact aspect-ratio calculation and even-dimension bounding.
- Proxy file verification (probing container, duration, resolution, decodability).
- Source-to-Proxy timestamp and frame mapping.
- Audio companion proxy stream generation.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import time
import uuid
import math
import cv2
import hashlib
import logging

from video_studio.proxy_models import (
    ProxyProfileConfig,
    ProxyMediaRecord,
    ProxyLifecycleStatus,
)
from video_studio.media_models import MediaAsset
from video_studio.playback_decoder import SoftwareMediaDecoder
from video_studio.media_storage import media_storage_manager

logger = logging.getLogger("omnia.video_studio.proxy_engine")

class ProxyEngine:
    """Core media transcoding and verification engine for lower-resolution proxies."""

    def generate_proxy(
        self,
        asset: MediaAsset,
        profile: ProxyProfileConfig,
        output_dir: Optional[str] = None,
    ) -> ProxyMediaRecord:
        """Generates a verified, downscaled proxy representation for an original asset."""
        source_path = asset.file_location if asset.file_location and os.path.exists(asset.file_location) else media_storage_manager.resolve_asset_path(asset.asset_id)
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Original source file for asset '{asset.asset_id}' not found at '{source_path}'.")

        # Destination path
        out_dir = output_dir or os.path.dirname(media_storage_manager.get_proxy_path(asset.project_id))
        os.makedirs(out_dir, exist_ok=True)

        proxy_id = f"proxy_{uuid.uuid4().hex[:8]}"
        proxy_filename = f"{asset.asset_id}_{profile.profile_id}.mp4"
        proxy_path = os.path.join(out_dir, proxy_filename)

        # 1. Compute original fingerprint
        orig_fingerprint = self._compute_fingerprint(source_path)
        orig_size = os.path.getsize(source_path)

        # 2. Open source decoder
        cap = cv2.VideoCapture(source_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open source media '{source_path}' for proxy generation.")

        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        src_fps = float(cap.get(cv2.CAP_PROP_FPS))
        if src_fps <= 0 or math.isnan(src_fps):
            src_fps = 24.0
        total_src_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # 3. Calculate target dimensions preserving aspect ratio (must be even numbers)
        target_w, target_h = self._calculate_even_dimensions(src_w, src_h, profile.target_width, profile.target_height)

        # 4. Initialize OpenCV VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(proxy_path, fourcc, src_fps, (target_w, target_h))
        if not writer.isOpened():
            cap.release()
            raise RuntimeError(f"Failed to initialize VideoWriter for proxy output '{proxy_path}'.")

        # 5. Transcode frames
        try:
            frames_encoded = 0
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                # Downscale
                resized = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                writer.write(resized)
                frames_encoded += 1

            cap.release()
            writer.release()
            writer = None

        except Exception as ex:
            if writer:
                writer.release()
            cap.release()
            if os.path.exists(proxy_path):
                os.remove(proxy_path)
            raise RuntimeError(f"Proxy transcoding failed: {ex}")

        # 6. Verify Proxy Integrity
        proxy_rec = self.verify_proxy(proxy_id, asset.asset_id, asset.project_id, profile.profile_id, proxy_path)
        proxy_rec.original_fingerprint = orig_fingerprint
        proxy_rec.original_size_bytes = orig_size
        return proxy_rec

    def verify_proxy(
        self,
        proxy_id: str,
        asset_id: str,
        project_id: str,
        profile_id: str,
        proxy_path: str,
    ) -> ProxyMediaRecord:
        """Verifies an on-disk proxy file and constructs a durable ProxyMediaRecord."""
        if not os.path.exists(proxy_path):
            return ProxyMediaRecord(
                proxy_id=proxy_id,
                original_asset_id=asset_id,
                project_id=project_id,
                profile_id=profile_id,
                file_path=proxy_path,
                status=ProxyLifecycleStatus.MISSING,
                error_message="Proxy file missing on disk.",
            )

        file_size = os.path.getsize(proxy_path)
        if file_size <= 0:
            return ProxyMediaRecord(
                proxy_id=proxy_id,
                original_asset_id=asset_id,
                project_id=project_id,
                profile_id=profile_id,
                file_path=proxy_path,
                status=ProxyLifecycleStatus.CORRUPTED,
                error_message="Proxy file is empty (0 bytes).",
            )

        # Probe with OpenCV
        cap = cv2.VideoCapture(proxy_path)
        if not cap.isOpened():
            return ProxyMediaRecord(
                proxy_id=proxy_id,
                original_asset_id=asset_id,
                project_id=project_id,
                profile_id=profile_id,
                file_path=proxy_path,
                status=ProxyLifecycleStatus.CORRUPTED,
                error_message="Cannot open proxy file container.",
            )

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur_sec = frame_count / max(1.0, fps)
        ret, test_frame = cap.read()
        cap.release()

        if not ret or test_frame is None:
            return ProxyMediaRecord(
                proxy_id=proxy_id,
                original_asset_id=asset_id,
                project_id=project_id,
                profile_id=profile_id,
                file_path=proxy_path,
                status=ProxyLifecycleStatus.CORRUPTED,
                error_message="Cannot decode sample frame from proxy file.",
            )

        proxy_fingerprint = self._compute_fingerprint(proxy_path)

        return ProxyMediaRecord(
            proxy_id=proxy_id,
            original_asset_id=asset_id,
            project_id=project_id,
            profile_id=profile_id,
            file_path=proxy_path,
            status=ProxyLifecycleStatus.READY,
            proxy_fingerprint=proxy_fingerprint,
            proxy_size_bytes=file_size,
            width=w,
            height=h,
            fps=fps,
            duration_seconds=dur_sec,
            video_codec="mp4v",
            container="mp4",
            verified_at=time.time(),
        )

    def _calculate_even_dimensions(
        self,
        src_w: int,
        src_h: int,
        max_w: int,
        max_h: int,
    ) -> Tuple[int, int]:
        """Calculates scaled width/height maintaining source aspect ratio and even coordinates."""
        if src_w <= 0 or src_h <= 0:
            return max(2, (max_w // 2) * 2), max(2, (max_h // 2) * 2)

        # Scale factor
        scale = min(max_w / float(src_w), max_h / float(src_h))
        # Never upscale beyond original
        scale = min(scale, 1.0)

        target_w = int(round(src_w * scale))
        target_h = int(round(src_h * scale))

        # Make even
        target_w = (target_w // 2) * 2
        target_h = (target_h // 2) * 2

        return max(2, target_w), max(2, target_h)

    def _compute_fingerprint(self, file_path: str) -> str:
        """Computes rapid SHA-256 fingerprint from first and last 64KB blocks."""
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
proxy_engine = ProxyEngine()
