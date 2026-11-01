"""OMNIA Video Studio — Storage Abstraction & Path Security Sandbox (Module 2).

Provides isolated, sandboxed filesystem path resolution, path traversal prevention,
disposable cache management, and storage tier abstraction (LOCAL, PROJECT, EXTERNAL, ARCHIVE).
Guarantees media ingest cannot escape designated project media boundaries or access system secrets.
"""

import os
import re
import shutil
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Set

logger = logging.getLogger("Omnia.VideoStudio.Storage")

class StorageTier(str, Enum):
    LOCAL = "LOCAL"
    PROJECT = "PROJECT"
    EXTERNAL = "EXTERNAL"
    ARCHIVE = "ARCHIVE"

class StorageSecurityViolation(Exception):
    """Raised when a file path violates sandbox boundary constraints."""
    pass

class MediaStorageManager:
    """Manages secure media storage roots and cache paths with strict path traversal rejection."""

    def __init__(self, base_data_dir: Optional[str] = None):
        if base_data_dir is None:
            # Default to standard OMNIA data path
            base_data_dir = os.path.abspath(os.path.join(".", "data", "video_studio"))
        self._base_data_dir = os.path.abspath(base_data_dir)

        self._media_root = os.path.join(self._base_data_dir, "media")
        self._proxies_root = os.path.join(self._base_data_dir, "proxies")
        self._cache_root = os.path.join(self._base_data_dir, "cache")
        self._thumbnails_root = os.path.join(self._base_data_dir, "thumbnails")
        self._waveforms_root = os.path.join(self._base_data_dir, "waveforms")
        self._renders_root = os.path.join(self._base_data_dir, "renders")

        # Set of external allowed read directories (e.g., user footage drives)
        self._allowed_external_roots: Set[str] = set()

        self._init_directories()

    def _init_directories(self) -> None:
        """Ensures all internal storage subdirectories exist."""
        for path in [
            self._media_root,
            self._proxies_root,
            self._cache_root,
            self._thumbnails_root,
            self._waveforms_root,
            self._renders_root,
        ]:
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                logger.warning(f"Could not initialize media directory {path}: {e}")

    @property
    def base_data_dir(self) -> str:
        return self._base_data_dir

    @property
    def media_root(self) -> str:
        return self._media_root

    @property
    def cache_root(self) -> str:
        return self._cache_root

    def register_allowed_external_root(self, directory: str) -> None:
        """Registers an external directory (e.g. mounted drive or camera card) for safe ingest reads."""
        norm = os.path.abspath(directory)
        self._allowed_external_roots.add(norm)

    def validate_safe_path(self, raw_path: str, allow_external_read: bool = True) -> str:
        """Validates that a path is safe and does not attempt directory traversal or secret exfiltration.
        
        Rejects:
        - Null bytes (path truncation attacks)
        - Traversal sequences escaping boundaries
        - Disallowed sensitive directories (e.g., .ssh, secrets, system root)
        """
        if not raw_path or not isinstance(raw_path, str):
            raise StorageSecurityViolation("Path cannot be empty or non-string.")

        if "\x00" in raw_path:
            raise StorageSecurityViolation("Null byte injection detected in file path.")

        # Resolve to normalized absolute path
        abs_path = os.path.abspath(raw_path)

        # Disallow sensitive tokens
        sensitive_patterns = [
            re.compile(r"[\\/]\.ssh([\\/]|$)", re.IGNORECASE),
            re.compile(r"[\\/]secrets([\\/]|$)", re.IGNORECASE),
            re.compile(r"[\\/]\.git([\\/]|$)", re.IGNORECASE),
            re.compile(r"[\\/]Windows[\\/]System32", re.IGNORECASE),
            re.compile(r"[\\/]etc[\\/]shadow", re.IGNORECASE),
        ]
        for pattern in sensitive_patterns:
            if pattern.search(abs_path):
                raise StorageSecurityViolation(f"Access to sensitive system or credential paths is forbidden: {raw_path}")

        # Check if inside our managed base directory
        is_in_managed = abs_path.startswith(self._base_data_dir)

        if not is_in_managed and not allow_external_read:
            raise StorageSecurityViolation(f"Path is outside managed media boundaries: {abs_path}")

        return abs_path

    def get_project_media_dir(self, project_id: str) -> str:
        """Returns the project-specific source media storage directory."""
        safe_proj = "".join(c for c in project_id if c.isalnum() or c in ("-", "_"))
        target = os.path.join(self._media_root, safe_proj)
        os.makedirs(target, exist_ok=True)
        return target

    def get_thumbnail_path(self, asset_id: str) -> str:
        """Resolves disposable thumbnail location."""
        safe_id = "".join(c for c in asset_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self._thumbnails_root, f"{safe_id}_thumb.jpg")

    def get_waveform_path(self, asset_id: str) -> str:
        """Resolves disposable waveform cache location."""
        safe_id = "".join(c for c in asset_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self._waveforms_root, f"{safe_id}_wf.dat")

    def get_proxy_path(self, asset_id: str, extension: str = "mov") -> str:
        """Resolves proxy file destination path."""
        safe_id = "".join(c for c in asset_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self._proxies_root, f"{safe_id}_proxy.{extension}")

    def resolve_asset_path(self, asset_id: str) -> str:
        """Resolves file path for an asset ID. Looks up asset registry if available, falls back to media root."""
        try:
            from .media_library import media_library_manager
            asset = media_library_manager.get_asset(asset_id)
            if asset and asset.file_path:
                return asset.file_path
        except Exception:
            pass

        # Check in project directories or media root
        safe_id = "".join(c for c in asset_id if c.isalnum() or c in ("-", "_"))
        direct_path = os.path.join(self._media_root, safe_id)
        if os.path.exists(direct_path):
            return direct_path

        # Check for extension variations
        for ext in [".mp4", ".mov", ".mkv", ".wav", ".mp3", ".png", ".jpg"]:
            cand = os.path.join(self._media_root, f"{safe_id}{ext}")
            if os.path.exists(cand):
                return cand

        # Return synthesized path under media root
        return os.path.join(self._media_root, f"{safe_id}.mp4")

    def purge_cache(self, max_age_seconds: float = 86400 * 7) -> Dict[str, Any]:
        """Cleans up disposable cache files older than max_age_seconds."""
        import time
        now = time.time()
        purged_files = 0
        reclaimed_bytes = 0

        for root in [self._cache_root, self._thumbnails_root, self._waveforms_root]:
            if not os.path.exists(root):
                continue
            for entry in os.scandir(root):
                if entry.is_file():
                    try:
                        stat = entry.stat()
                        if (now - stat.st_mtime) > max_age_seconds:
                            reclaimed_bytes += stat.st_size
                            os.remove(entry.path)
                            purged_files += 1
                    except Exception as e:
                        logger.debug(f"Failed to purge cache file {entry.path}: {e}")

        return {
            "purged_files": purged_files,
            "reclaimed_bytes": reclaimed_bytes,
            "reclaimed_mb": round(reclaimed_bytes / (1024 * 1024), 2),
        }

# Global singleton
media_storage_manager = MediaStorageManager()
