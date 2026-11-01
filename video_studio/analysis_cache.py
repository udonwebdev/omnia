"""OMNIA Video Studio — Media Analysis Cache & Invalidation Engine (Module 3).

Stores, indexes, and invalidates derived media analysis data:
- Media probe reports
- Waveform datasets
- Thumbnails and contact sheets
- Frame preview references
Uses composite cache keys: (asset_id, file_fingerprint, analysis_version).
Automatically invalidates stale cached data when source files change.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional

from video_studio.analysis_models import MediaAnalysisReport, WaveformDataset
from video_studio.media_storage import media_storage_manager

logger = logging.getLogger("Omnia.VideoStudio.AnalysisCache")

class MediaAnalysisCache:
    """Manages disk-backed and memory-backed invalidatable analysis results."""

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = os.path.join(media_storage_manager.cache_root, "analysis")
        self._cache_dir = os.path.abspath(cache_dir)
        os.makedirs(self._cache_dir, exist_ok=True)
        self._memory_cache: Dict[str, Any] = {}

    def _make_key(self, asset_id: str, fingerprint: str, version: str = "1.0.0") -> str:
        clean_fp = "".join(c for c in fingerprint if c.isalnum() or c in ("-", "_"))[:16]
        return f"{asset_id}_{clean_fp}_v{version}"

    def get_analysis_report(self, asset_id: str, fingerprint: str, version: str = "1.0.0") -> Optional[MediaAnalysisReport]:
        """Retrieves cached analysis report if fingerprint matches."""
        key = self._make_key(asset_id, fingerprint, version)
        if key in self._memory_cache:
            return self._memory_cache[key]

        disk_file = os.path.join(self._cache_dir, f"{key}_report.json")
        if os.path.exists(disk_file):
            try:
                with open(disk_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Reconstruct report
                from video_studio.analysis_models import VideoStreamDetails, AudioStreamDetails, SubtitleStreamDetails, HDRStandard, InterlaceMode
                rep = MediaAnalysisReport(
                    asset_id=data["asset_id"],
                    fingerprint=data["fingerprint"],
                    analysis_version=data.get("analysis_version", "1.0.0"),
                    container_format=data.get("container_format", "unknown"),
                    overall_bitrate_kbps=data.get("overall_bitrate_kbps"),
                    duration_seconds=data.get("duration_seconds", 0.0),
                    start_timecode=data.get("start_timecode", "00:00:00:00"),
                    is_drop_frame=data.get("is_drop_frame", False),
                    stream_count=data.get("stream_count", 0),
                    default_thumbnail_uri=data.get("default_thumbnail_uri"),
                    has_waveform=data.get("has_waveform", False),
                    analyzed_at=data.get("analyzed_at", time.time()),
                )
                for v in data.get("video_streams", []):
                    rep.video_streams.append(VideoStreamDetails(
                        stream_id=v["stream_id"],
                        stream_index=v.get("stream_index", 0),
                        codec=v.get("codec", "h264"),
                        codec_profile=v.get("codec_profile"),
                        codec_level=v.get("codec_level"),
                        width=v.get("width", 1920),
                        height=v.get("height", 1080),
                        display_width=v.get("display_width", 1920),
                        display_height=v.get("display_height", 1080),
                        pixel_aspect_ratio=v.get("pixel_aspect_ratio", "1:1"),
                        frame_rate=v.get("frame_rate", 24.0),
                        average_frame_rate=v.get("average_frame_rate", 24.0),
                        bit_depth=v.get("bit_depth", 8),
                        pixel_format=v.get("pixel_format", "yuv420p"),
                        color_space=v.get("color_space", "Rec.709"),
                        transfer_characteristics=v.get("transfer_characteristics", "bt709"),
                        color_primaries=v.get("color_primaries", "bt709"),
                        hdr_standard=HDRStandard(v.get("hdr_standard", "SDR")),
                        rotation_degrees=v.get("rotation_degrees", 0),
                        interlace_mode=InterlaceMode(v.get("interlace_mode", "PROGRESSIVE")),
                        is_vfr=v.get("is_vfr", False),
                        duration_seconds=v.get("duration_seconds", 0.0),
                        total_frames=v.get("total_frames", 0),
                    ))
                for a in data.get("audio_streams", []):
                    rep.audio_streams.append(AudioStreamDetails(
                        stream_id=a["stream_id"],
                        stream_index=a.get("stream_index", 0),
                        codec=a.get("codec", "aac"),
                        sample_rate=a.get("sample_rate", 48000),
                        channels=a.get("channels", 2),
                        channel_layout=a.get("channel_layout", "stereo"),
                        bit_depth=a.get("bit_depth", 16),
                        duration_seconds=a.get("duration_seconds", 0.0),
                    ))
                for s in data.get("subtitle_streams", []):
                    rep.subtitle_streams.append(SubtitleStreamDetails(
                        stream_id=s["stream_id"],
                        stream_index=s.get("stream_index", 0),
                        codec=s.get("codec", "srt"),
                        language=s.get("language"),
                    ))
                self._memory_cache[key] = rep
                return rep
            except Exception as e:
                logger.warning(f"Failed to read cached analysis report {disk_file}: {e}")
        return None

    def store_analysis_report(self, report: MediaAnalysisReport) -> None:
        """Saves analysis report to memory and disk cache."""
        key = self._make_key(report.asset_id, report.fingerprint, report.analysis_version)
        self._memory_cache[key] = report

        disk_file = os.path.join(self._cache_dir, f"{key}_report.json")
        try:
            with open(disk_file, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write analysis report to disk: {e}")

    def invalidate_asset_cache(self, asset_id: str) -> int:
        """Removes all cached analysis and derivatives for a given asset ID."""
        invalidated_count = 0
        # Memory
        keys_to_del = [k for k in self._memory_cache if k.startswith(f"{asset_id}_")]
        for k in keys_to_del:
            del self._memory_cache[k]
            invalidated_count += 1

        # Disk
        if os.path.exists(self._cache_dir):
            for entry in os.scandir(self._cache_dir):
                if entry.is_file() and entry.name.startswith(f"{asset_id}_"):
                    try:
                        os.remove(entry.path)
                        invalidated_count += 1
                    except Exception:
                        pass
        return invalidated_count

# Global singleton
media_analysis_cache = MediaAnalysisCache()
