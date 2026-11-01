"""OMNIA Video Studio — Frame Extraction & Lightweight Preview Engine (Module 3).

Provides a centralized abstraction for:
- get_frame(asset, timestamp_seconds)
- get_frames(asset, timestamps_seconds)
Shared frame-decoding service so future timeline, color, and VFX modules do not
reinvent independent frame extraction logic.
"""

import os
import logging
from typing import Dict, Any, List, Optional

from video_studio.thumbnail_engine import thumbnail_engine

logger = logging.getLogger("Omnia.VideoStudio.PreviewEngine")

class PreviewEngine:
    """Provides frame extraction and hover preview generation."""

    def __init__(self):
        self._thumbnail_engine = thumbnail_engine

    def get_frame(
        self,
        file_path: str,
        asset_id: str,
        timestamp_seconds: float,
        width: int = 640,
        height: int = 360,
        rotation_degrees: int = 0,
    ) -> str:
        """Extracts and returns the URI/filepath for a specific frame."""
        return self._thumbnail_engine.generate_thumbnail(
            file_path=file_path,
            asset_id=asset_id,
            timestamp_seconds=timestamp_seconds,
            width=width,
            height=height,
            rotation_degrees=rotation_degrees,
        )

    def get_frames(
        self,
        file_path: str,
        asset_id: str,
        timestamps_seconds: List[float],
        width: int = 320,
        height: int = 180,
    ) -> List[str]:
        """Batch extracts frames across multiple timestamps."""
        results = []
        for ts in timestamps_seconds:
            f = self.get_frame(file_path, asset_id, ts, width, height)
            results.append(f)
        return results

# Global singleton
preview_engine = PreviewEngine()
