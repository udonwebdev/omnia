"""OMNIA Video Studio — Multicamera Synchronization Engine (Module 20).

Coordinates:
- Source stream probing and start timecode alignment.
- Audio waveform cross-correlation synchronization using numpy normalized cross-correlation.
- Manual offset adjustment and synchronization point nudging.
- Synchronization confidence scoring and drift analysis.
"""

import os
import wave
import logging
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

from video_studio.multicam_models import (
    CameraAngle,
    SyncMethod,
    SyncConfidence,
    AngleSyncResult,
)
from video_studio.media_models import MediaAsset
from video_studio.media_library import media_library_registry

logger = logging.getLogger("omnia.video_studio.multicam_sync")


class MulticamSyncEngine:
    """Core audio and timecode alignment engine for multicamera sources."""

    def synchronize_angles(
        self,
        project_id: str,
        angles: List[CameraAngle],
        method: SyncMethod = SyncMethod.TIMECODE,
        reference_angle_id: Optional[str] = None,
    ) -> List[AngleSyncResult]:
        """Aligns all angles against a designated reference angle or time zero."""
        pml = media_library_registry.get_or_create(project_id)
        if not angles:
            return []

        ref_angle = angles[0]
        if reference_angle_id:
            found = next((a for a in angles if a.angle_id == reference_angle_id), None)
            if found:
                ref_angle = found

        results: List[AngleSyncResult] = []

        if method == SyncMethod.TIMECODE:
            results = self._sync_by_timecode(pml, angles, ref_angle)
        elif method == SyncMethod.AUDIO_WAVEFORM:
            results = self._sync_by_audio_correlation(pml, angles, ref_angle)
        elif method == SyncMethod.IN_POINT:
            results = self._sync_by_in_points(angles, ref_angle)
        else: # MANUAL_OFFSET
            for a in angles:
                results.append(AngleSyncResult(
                    angle_id=a.angle_id,
                    asset_id=a.asset_id,
                    calculated_offset_frames=a.sync_offset_frames,
                    method_used=SyncMethod.MANUAL_OFFSET,
                    confidence=SyncConfidence.EXACT,
                    confidence_score=1.0,
                ))

        return results

    def _sync_by_timecode(
        self,
        pml: Any,
        angles: List[CameraAngle],
        ref_angle: CameraAngle,
    ) -> List[AngleSyncResult]:
        """Aligns angles based on SMPTE start timecode from media asset metadata."""
        results: List[AngleSyncResult] = []
        ref_asset = pml.get_asset(ref_angle.asset_id)
        ref_tc_frames = self._get_timecode_frames(ref_asset)

        for angle in angles:
            asset = pml.get_asset(angle.asset_id)
            if not asset:
                results.append(AngleSyncResult(
                    angle_id=angle.angle_id,
                    asset_id=angle.asset_id,
                    calculated_offset_frames=0,
                    method_used=SyncMethod.TIMECODE,
                    confidence=SyncConfidence.NONE,
                    confidence_score=0.0,
                    warnings=[f"Media asset '{angle.asset_id}' not found in library."],
                ))
                continue

            tc_frames = self._get_timecode_frames(asset)
            offset = tc_frames - ref_tc_frames

            # High confidence if valid timecode was extracted
            has_tc = bool(asset.start_timecode and (asset.start_timecode.hours or asset.start_timecode.minutes or asset.start_timecode.seconds or asset.start_timecode.frames))
            results.append(AngleSyncResult(
                angle_id=angle.angle_id,
                asset_id=angle.asset_id,
                calculated_offset_frames=offset,
                method_used=SyncMethod.TIMECODE,
                confidence=SyncConfidence.HIGH if has_tc else SyncConfidence.LOW,
                confidence_score=0.9 if has_tc else 0.3,
                warnings=[] if has_tc else ["Asset lacks SMPTE timecode; defaulted to zero offset."],
            ))

        return results

    def _sync_by_audio_correlation(
        self,
        pml: Any,
        angles: List[CameraAngle],
        ref_angle: CameraAngle,
    ) -> List[AngleSyncResult]:
        """Calculates audio peak cross-correlation between angle waveforms."""
        results: List[AngleSyncResult] = []
        ref_asset = pml.get_asset(ref_angle.asset_id)
        ref_audio = self._extract_mono_envelope(ref_asset.file_location if ref_asset else "")

        for angle in angles:
            if angle.angle_id == ref_angle.angle_id or ref_audio is None:
                results.append(AngleSyncResult(
                    angle_id=angle.angle_id,
                    asset_id=angle.asset_id,
                    calculated_offset_frames=0,
                    method_used=SyncMethod.AUDIO_WAVEFORM,
                    confidence=SyncConfidence.EXACT if angle.angle_id == ref_angle.angle_id else SyncConfidence.NONE,
                    confidence_score=1.0 if angle.angle_id == ref_angle.angle_id else 0.0,
                ))
                continue

            asset = pml.get_asset(angle.asset_id)
            cand_audio = self._extract_mono_envelope(asset.file_location if asset else "")
            if cand_audio is None:
                results.append(AngleSyncResult(
                    angle_id=angle.angle_id,
                    asset_id=angle.asset_id,
                    calculated_offset_frames=0,
                    method_used=SyncMethod.AUDIO_WAVEFORM,
                    confidence=SyncConfidence.NONE,
                    confidence_score=0.0,
                    warnings=["No readable audio track found for correlation."],
                ))
                continue

            # Normalized Cross-Correlation
            offset_samples, corr_score = self._cross_correlate_signals(ref_audio, cand_audio)
            fps = asset.frame_rate or 24.0
            # 8000 Hz envelope sample rate
            offset_frames = int(round((offset_samples / 8000.0) * fps))

            confidence = SyncConfidence.HIGH if corr_score > 0.7 else (
                SyncConfidence.MEDIUM if corr_score > 0.4 else SyncConfidence.LOW
            )

            results.append(AngleSyncResult(
                angle_id=angle.angle_id,
                asset_id=angle.asset_id,
                calculated_offset_frames=offset_frames,
                method_used=SyncMethod.AUDIO_WAVEFORM,
                confidence=confidence,
                confidence_score=corr_score,
            ))

        return results

    def _sync_by_in_points(
        self,
        angles: List[CameraAngle],
        ref_angle: CameraAngle,
    ) -> List[AngleSyncResult]:
        """Aligns angles based on user-marked in-points."""
        results: List[AngleSyncResult] = []
        ref_in = ref_angle.in_point_frame

        for a in angles:
            offset = ref_in - a.in_point_frame
            results.append(AngleSyncResult(
                angle_id=a.angle_id,
                asset_id=a.asset_id,
                calculated_offset_frames=offset,
                method_used=SyncMethod.IN_POINT,
                confidence=SyncConfidence.HIGH,
                confidence_score=0.95,
            ))

        return results

    def _get_timecode_frames(self, asset: Optional[MediaAsset]) -> int:
        if not asset or not asset.start_timecode:
            return 0
        tc = asset.start_timecode
        fps = asset.frame_rate or 24.0
        return int(round((tc.hours * 3600 + tc.minutes * 60 + tc.seconds) * fps + tc.frames))

    def _extract_mono_envelope(self, file_path: str, target_sr: int = 8000) -> Optional[np.ndarray]:
        """Extracts a low-rate audio amplitude envelope from a WAV file for efficient correlation."""
        if not file_path or not os.path.exists(file_path) or not file_path.lower().endswith(".wav"):
            return None

        try:
            with wave.open(file_path, "rb") as wf:
                sr = wf.getframerate()
                ch = wf.getnchannels()
                frames_to_read = min(wf.getnframes(), sr * 30) # analyze first 30 seconds
                raw = wf.readframes(frames_to_read)

            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            if ch > 1:
                data = data.reshape(-1, ch).mean(axis=1)

            # Downsample to target_sr
            step = max(1, sr // target_sr)
            envelope = np.abs(data[::step])
            norm = np.linalg.norm(envelope)
            if norm > 0:
                envelope = envelope / norm
            return envelope
        except Exception as e:
            logger.debug(f"Could not extract audio envelope from '{file_path}': {e}")
            return None

    def _cross_correlate_signals(self, sig_ref: np.ndarray, sig_cand: np.ndarray) -> Tuple[int, float]:
        """Calculates lag between two signals using full cross-correlation."""
        if len(sig_ref) == 0 or len(sig_cand) == 0:
            return 0, 0.0

        corr = np.correlate(sig_ref, sig_cand, mode="full")
        lag = int(np.argmax(corr)) - (len(sig_cand) - 1)
        max_corr = float(np.max(corr)) if len(corr) > 0 else 0.0
        return lag, min(1.0, max(0.0, max_corr))


# Global singleton
multicam_sync_engine = MulticamSyncEngine()
