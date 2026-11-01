"""OMNIA Video Studio — Watch Folder Ingestion Foundation (Module 2).

Defines architectural models, configuration contracts, and registration endpoints
for automated directory monitoring and auto-ingest into specific project bins.
Does not start persistent unmonitored OS threads; establishes the controlled service boundary.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import os
import time

@dataclass
class WatchFolderConfig:
    watch_folder_id: str
    project_id: str
    folder_path: str
    target_bin_id: Optional[str] = None
    is_enabled: bool = True
    recursive: bool = False
    supported_extensions: List[str] = field(default_factory=lambda: [
        "mp4", "mov", "mkv", "webm", "wav", "mp3", "png", "jpg", "jpeg", "exr", "cube", "srt"
    ])
    poll_interval_seconds: int = 10
    last_scan_timestamp: Optional[float] = None
    created_at: float = field(default_factory=time.time)

class WatchFolderManager:
    """Manages active watch folder configurations."""

    def __init__(self):
        self._configs: Dict[str, WatchFolderConfig] = {}

    def register_watch_folder(self, config: WatchFolderConfig) -> None:
        if not os.path.exists(config.folder_path):
            raise FileNotFoundError(f"Watch folder path does not exist: {config.folder_path}")
        self._configs[config.watch_folder_id] = config

    def unregister_watch_folder(self, watch_folder_id: str) -> bool:
        if watch_folder_id in self._configs:
            del self._configs[watch_folder_id]
            return True
        return False

    def get_config(self, watch_folder_id: str) -> Optional[WatchFolderConfig]:
        return self._configs.get(watch_folder_id)

    def list_configs(self, project_id: Optional[str] = None) -> List[WatchFolderConfig]:
        if project_id:
            return [c for c in self._configs.values() if c.project_id == project_id]
        return list(self._configs.values())

    def scan_for_new_files(self, watch_folder_id: str) -> List[str]:
        """Performs a synchronous scan and returns candidate file paths."""
        cfg = self.get_config(watch_folder_id)
        if not cfg or not cfg.is_enabled or not os.path.exists(cfg.folder_path):
            return []

        candidates = []
        ext_set = {f".{ext.lower().lstrip('.')}" for ext in cfg.supported_extensions}

        if cfg.recursive:
            for root, _, files in os.walk(cfg.folder_path):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in ext_set:
                        candidates.append(os.path.join(root, f))
        else:
            with os.scandir(cfg.folder_path) as entries:
                for entry in entries:
                    if entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in ext_set:
                            candidates.append(entry.path)

        cfg.last_scan_timestamp = time.time()
        return candidates

# Global singleton
watch_folder_manager = WatchFolderManager()
