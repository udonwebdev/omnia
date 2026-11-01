"""OMNIA Video Studio — Media Ingest Pipeline Service (Module 2).

Orchestrates media validation, binary probing, metadata extraction, content hashing,
duplicate detection, offline media detection, and project library registration.
Ensures failed/corrupt media never crashes the host application or corrupts the project.
"""

import os
import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from video_studio.media_models import (
    MediaAsset,
    AssetMediaType,
    AssetLifecycleStatus,
    RationalTime,
    SMPTETimecode,
    ProxyDescriptor,
    ProxyStatus,
    GeneratedMediaDescriptor,
)
from video_studio.media_storage import (
    media_storage_manager,
    StorageSecurityViolation,
)
from video_studio.media_probe import (
    media_probe_service,
    ProbeResult,
)
from video_studio.media_library import (
    media_library_registry,
    ProjectMediaLibrary,
)
from video_studio.media_preview import (
    media_preview_manager,
)

logger = logging.getLogger("Omnia.VideoStudio.Ingest")

class IngestError(Exception):
    """Raised when media ingest cannot proceed due to critical validation error."""
    pass

class MediaIngestService:
    """Coordinates the full ingestion pipeline for incoming assets."""

    def __init__(self):
        self._storage = media_storage_manager
        self._probe = media_probe_service
        self._libraries = media_library_registry
        self._previews = media_preview_manager

    def ingest_file(
        self,
        project_id: str,
        source_file_path: str,
        display_name: Optional[str] = None,
        target_bin_id: Optional[str] = None,
        allow_duplicates: bool = False,
        tags: Optional[List[str]] = None,
    ) -> Tuple[bool, Optional[MediaAsset], str]:
        """Ingests a media file through the safe validation pipeline.
        
        Returns: (success: bool, asset: Optional[MediaAsset], message: str)
        """
        # Step 1: Path security validation & sandbox check
        try:
            safe_source = self._storage.validate_safe_path(source_file_path, allow_external_read=True)
        except StorageSecurityViolation as e:
            logger.warning(f"Storage security violation during ingest: {e}")
            return (False, None, f"Security sandbox rejection: {e}")

        # Step 2: Basic existence & readability check
        if not os.path.exists(safe_source):
            return (False, None, f"Source file does not exist: {safe_source}")

        if not os.path.isfile(safe_source):
            return (False, None, f"Source path is a directory, not a file: {safe_source}")

        file_size = os.path.getsize(safe_source)
        if file_size == 0:
            return (False, None, "File is zero bytes (empty).")

        # Step 3: Compute content fingerprint for duplicate detection
        full_hash, partial_hash = self._probe.compute_file_fingerprint(safe_source)
        lib = self._libraries.get_or_create(project_id)

        if not allow_duplicates:
            dup = lib.find_duplicate_asset(full_hash)
            if dup:
                return (True, dup, f"Duplicate asset detected; referencing existing asset {dup.asset_id}")

        # Step 4: Media Probing (Magic bytes, container & stream discovery)
        probe_res: ProbeResult = self._probe.probe_file(safe_source)
        if not probe_res.is_valid:
            # We still register a failed asset record if desired, or return failure cleanly
            return (False, None, f"Probe validation failed: {probe_res.error_message}")

        # Step 5: Derive asset names and types
        original_name = os.path.basename(safe_source)
        name = display_name.strip() if display_name else original_name
        ext = os.path.splitext(original_name)[1].lower().lstrip(".")

        # Step 6: Construct Normalized MediaAsset
        asset_id = f"asset_{uuid.uuid4().hex[:12]}"
        
        # Calculate rational time duration
        fps = probe_res.frame_rate or 24.0
        dur_sec = probe_res.duration_seconds or 0.0
        total_frames = int(round(dur_sec * fps))
        rational_dur = RationalTime.from_seconds(dur_sec)
        start_tc = SMPTETimecode(fps=fps)

        asset = MediaAsset(
            asset_id=asset_id,
            project_id=project_id,
            name=name,
            original_name=original_name,
            media_type=probe_res.media_type,
            mime_type=probe_res.mime_type,
            extension=ext,
            size_bytes=file_size,
            status=AssetLifecycleStatus.READY,
            file_location=safe_source,
            storage_kind="LOCAL",
            duration_seconds=dur_sec,
            total_frames=total_frames,
            frame_rate=fps,
            frame_rate_mode=probe_res.frame_rate_mode,
            rational_duration=rational_dur,
            start_timecode=start_tc,
            width=probe_res.width,
            height=probe_res.height,
            aspect_ratio=f"{probe_res.width}:{probe_res.height}" if probe_res.width and probe_res.height else None,
            audio_channels=probe_res.audio_channels,
            sample_rate=probe_res.sample_rate,
            container=probe_res.container,
            video_codec=probe_res.video_codec,
            audio_codec=probe_res.audio_codec,
            color_space=probe_res.color_space,
            video_streams=probe_res.video_streams,
            audio_streams=probe_res.audio_streams,
            content_hash_sha256=full_hash,
            partial_hash=partial_hash,
            bin_id=target_bin_id,
            tags=tags or [],
            metadata_technical=probe_res.metadata,
        )

        # Step 7: Initialize preview stubs
        is_audio = probe_res.media_type in (AssetMediaType.AUDIO, AssetMediaType.VIDEO)
        is_visual = probe_res.media_type in (AssetMediaType.VIDEO, AssetMediaType.IMAGE, AssetMediaType.TRANSPARENT_ASSET)
        self._previews.create_stub_preview(asset_id, is_audio=is_audio, is_visual=is_visual)

        # Step 8: Register asset into project library
        lib.add_asset(asset)

        return (True, asset, f"Asset {asset_id} imported successfully into project {project_id}.")

    def check_asset_health(self, project_id: str, asset_id: str) -> Tuple[AssetLifecycleStatus, str]:
        """Checks if the underlying source file is still reachable and intact."""
        lib = self._libraries.get_or_create(project_id)
        asset = lib.get_asset(asset_id)
        if not asset:
            return (AssetLifecycleStatus.FAILED, f"Asset {asset_id} not found in project library.")

        if not os.path.exists(asset.file_location):
            asset.mark_offline("Source media file was moved or deleted from disk.")
            return (AssetLifecycleStatus.OFFLINE, "Source media file is offline / missing.")

        current_size = os.path.getsize(asset.file_location)
        if current_size != asset.size_bytes:
            asset.status = AssetLifecycleStatus.CORRUPTED
            asset.status_reason = f"File size mismatch (expected {asset.size_bytes}, got {current_size})"
            return (AssetLifecycleStatus.CORRUPTED, asset.status_reason)

        asset.mark_ready()
        return (AssetLifecycleStatus.READY, "Asset source file is intact.")

    def relink_asset(self, project_id: str, asset_id: str, new_file_path: str) -> Tuple[bool, str]:
        """Relinks an offline or moved asset to a new filesystem path."""
        lib = self._libraries.get_or_create(project_id)
        asset = lib.get_asset(asset_id)
        if not asset:
            return (False, f"Asset {asset_id} not found.")

        try:
            safe_new = self._storage.validate_safe_path(new_file_path)
        except StorageSecurityViolation as e:
            return (False, f"Relink destination rejected: {e}")

        if not os.path.exists(safe_new):
            return (False, f"New path does not exist: {safe_new}")

        # Quick probe to ensure compatibility
        probe = self._probe.probe_file(safe_new)
        if not probe.is_valid:
            return (False, f"Relink file failed probe: {probe.error_message}")

        asset.file_location = safe_new
        asset.size_bytes = os.path.getsize(safe_new)
        asset.mark_ready()
        return (True, f"Asset {asset_id} relinked to {safe_new}")

# Global singleton
media_ingest_service = MediaIngestService()
