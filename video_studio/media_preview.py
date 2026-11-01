"""OMNIA Video Studio — Preview, Waveform & Thumbnail Foundation (Module 2).

Provides data contracts, caching abstractions, and processing lifecycles for:
- Asset Thumbnails
- Audio Waveforms (multichannel peak data & zoom decimation levels)
- Proxy Generation lifecycle states

Does not invoke ffmpeg or UI canvas rendering yet; establishes the foundational
state machines and cache paths.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import time
import os

from video_studio.media_models import ProxyStatus

class PreviewStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"
    NOT_AVAILABLE = "NOT_AVAILABLE"

@dataclass
class ThumbnailDescriptor:
    asset_id: str
    status: PreviewStatus = PreviewStatus.PENDING
    thumbnail_path: Optional[str] = None
    width: int = 320
    height: int = 180
    timestamp_seconds: float = 0.0
    generated_at: Optional[float] = None
    error_message: Optional[str] = None

@dataclass
class WaveformDescriptor:
    asset_id: str
    status: PreviewStatus = PreviewStatus.PENDING
    cache_file_path: Optional[str] = None
    channels: int = 2
    samples_per_pixel: int = 256
    zoom_levels: List[int] = field(default_factory=lambda: [64, 256, 1024, 4096])
    peak_min_values: List[float] = field(default_factory=list)
    peak_max_values: List[float] = field(default_factory=list)
    generated_at: Optional[float] = None
    error_message: Optional[str] = None

class MediaPreviewManager:
    """Coordinates thumbnail and waveform generation requests and lifecycle states."""

    def __init__(self):
        self._thumbnails: Dict[str, ThumbnailDescriptor] = {}
        self._waveforms: Dict[str, WaveformDescriptor] = {}

    def get_thumbnail(self, asset_id: str) -> Optional[ThumbnailDescriptor]:
        return self._thumbnails.get(asset_id)

    def register_thumbnail(self, descriptor: ThumbnailDescriptor) -> None:
        self._thumbnails[descriptor.asset_id] = descriptor

    def get_waveform(self, asset_id: str) -> Optional[WaveformDescriptor]:
        return self._waveforms.get(asset_id)

    def register_waveform(self, descriptor: WaveformDescriptor) -> None:
        self._waveforms[descriptor.asset_id] = descriptor

    def create_stub_preview(self, asset_id: str, is_audio: bool = False, is_visual: bool = True) -> None:
        """Initializes pending or placeholder preview records during ingest."""
        if is_visual:
            self._thumbnails[asset_id] = ThumbnailDescriptor(
                asset_id=asset_id,
                status=PreviewStatus.PENDING,
            )
        if is_audio:
            self._waveforms[asset_id] = WaveformDescriptor(
                asset_id=asset_id,
                status=PreviewStatus.PENDING,
            )

# Global singleton
media_preview_manager = MediaPreviewManager()
