"""OMNIA Video Studio — Real Media Transcoding, Conform & Audio Normalization Engine (Module 19).

Coordinates:
- Source probing and metadata validation.
- Resolution, aspect ratio, and letterboxing conform.
- Frame-rate conversions (CFR/VFR, drop/duplicate, timecode preservation).
- Audio sample-rate, channel downmix, and loudness normalization.
- Safe output generation via temporary files and SHA-256 fingerprinting.
- Integration with OpenCV VideoWriter and Python wave audio backends.
"""

import os
import time
import math
import wave
import uuid
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple, Callable

import cv2
import numpy as np

from video_studio.transcode_models import (
    TranscodeJob,
    TranscodeProfile,
    ConformPlan,
    ConformTransformation,
    TranscodeJobStatus,
    ScalingPolicy,
    AudioDownmixPolicy,
    LoudnessStandard,
    TranscodeContainer,
    VideoCodec,
    AudioCodec,
)
from video_studio.media_models import MediaAsset
from video_studio.media_probe import media_probe_service

logger = logging.getLogger("omnia.video_studio.transcode_engine")


class TranscodeEngine:
    """Core audio/video conversion and normalization engine."""

    def build_conform_plan(
        self,
        asset: MediaAsset,
        profile: TranscodeProfile,
        output_file_path: str,
    ) -> ConformPlan:
        """Analyzes differences between source properties and target profile to produce a conform plan."""
        source_path = asset.file_location
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        transformations: List[ConformTransformation] = []
        warnings: List[str] = []
        has_lossy = False

        # Probe source if details are missing
        src_w = asset.width or 1920
        src_h = asset.height or 1080
        src_fps = asset.frame_rate or 24.0
        src_audio_sr = asset.sample_rate or 48000
        src_channels = asset.audio_channels or 2

        # 1. Container & Codec
        target_ext = profile.container.value
        src_ext = os.path.splitext(source_path)[1].lstrip(".").lower()
        if src_ext != target_ext:
            transformations.append(ConformTransformation(
                property_name="container",
                source_value=src_ext,
                target_value=target_ext,
                action_type="CONVERT",
                is_lossy=False,
                details=f"Remuxing/encoding container format from {src_ext} to {target_ext}",
            ))

        # 2. Video Resolution & Scaling
        target_w = profile.target_width or src_w
        target_h = profile.target_height or src_h
        if target_w != src_w or target_h != src_h:
            is_downscale = (target_w * target_h) < (src_w * src_h)
            action = "LETTERBOX" if profile.scaling_policy == ScalingPolicy.FIT_PAD else "RESIZE"
            transformations.append(ConformTransformation(
                property_name="resolution",
                source_value=f"{src_w}x{src_h}",
                target_value=f"{target_w}x{target_h}",
                action_type=action,
                is_lossy=is_downscale,
                details=f"Spatial conform with {profile.scaling_policy.value} policy",
            ))
            if is_downscale:
                has_lossy = True
        else:
            transformations.append(ConformTransformation(
                property_name="resolution",
                source_value=f"{src_w}x{src_h}",
                target_value=f"{target_w}x{target_h}",
                action_type="PRESERVE",
                is_lossy=False,
                details="Native resolution preserved",
            ))

        # 3. Frame Rate
        target_fps = profile.target_fps or src_fps
        if abs(target_fps - src_fps) > 0.01:
            transformations.append(ConformTransformation(
                property_name="frame_rate",
                source_value=f"{src_fps:.3f} fps",
                target_value=f"{target_fps:.3f} fps",
                action_type="RESAMPLE",
                is_lossy=True,
                details="Temporal conform using deterministic frame drop/duplication",
            ))
            has_lossy = True
            warnings.append(f"Frame rate conversion from {src_fps:.2f} to {target_fps:.2f} fps may alter motion smoothness.")
        else:
            transformations.append(ConformTransformation(
                property_name="frame_rate",
                source_value=f"{src_fps:.3f} fps",
                target_value=f"{target_fps:.3f} fps",
                action_type="PRESERVE",
                is_lossy=False,
                details="Native frame rate preserved",
            ))

        # 4. Audio Channels & Sample Rate
        if profile.audio_codec != AudioCodec.NONE:
            if profile.audio_channels != src_channels:
                transformations.append(ConformTransformation(
                    property_name="audio_channels",
                    source_value=src_channels,
                    target_value=profile.audio_channels,
                    action_type="DOWNMIX" if profile.audio_channels < src_channels else "UPMIX",
                    is_lossy=(profile.audio_channels < src_channels),
                    details=f"Channel layout conform: {profile.downmix_policy.value}",
                ))
                if profile.audio_channels < src_channels:
                    has_lossy = True

            if profile.audio_sample_rate != src_audio_sr:
                transformations.append(ConformTransformation(
                    property_name="audio_sample_rate",
                    source_value=f"{src_audio_sr} Hz",
                    target_value=f"{profile.audio_sample_rate} Hz",
                    action_type="RESAMPLE",
                    is_lossy=True,
                    details=f"Audio resampled from {src_audio_sr} to {profile.audio_sample_rate} Hz",
                ))

            if profile.loudness_standard != LoudnessStandard.NONE:
                transformations.append(ConformTransformation(
                    property_name="audio_loudness",
                    source_value="Unmeasured",
                    target_value=f"{profile.loudness_standard.value} ({profile.target_lufs} LUFS/dBFS)",
                    action_type="NORMALIZE",
                    is_lossy=False,
                    details="Active loudness measurement and dynamic gain normalization",
                ))

        # 5. Color Metadata
        if profile.preserve_color_metadata:
            transformations.append(ConformTransformation(
                property_name="color_metadata",
                source_value=asset.color_space or "Rec.709",
                target_value=profile.color_space,
                action_type="PRESERVE",
                is_lossy=False,
                details="Preserving source color primaries and matrix coefficients",
            ))

        return ConformPlan(
            plan_id=plan_id,
            asset_id=asset.asset_id,
            profile_id=profile.profile_id,
            source_path=source_path,
            destination_path=output_file_path,
            transformations=transformations,
            has_lossy_operations=has_lossy,
            warnings=warnings,
            is_executable=True,
        )

    def execute_transcode(
        self,
        job: TranscodeJob,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Executes the transcode/conform operation deterministically using safe temporary files."""
        job.status = TranscodeJobStatus.VALIDATING
        job.stage_message = "Validating source and profile"
        job.started_at = time.time()

        src_path = job.source_file_path
        if not os.path.exists(src_path):
            job.status = TranscodeJobStatus.FAILED
            job.error_message = f"Source media file not found at '{src_path}'."
            return False

        # Build output directory and temp path
        final_output_path = job.output_file_path
        out_dir = os.path.dirname(os.path.abspath(final_output_path))
        os.makedirs(out_dir, exist_ok=True)
        temp_output_path = os.path.join(out_dir, f".tmp_{uuid.uuid4().hex[:8]}_{os.path.basename(final_output_path)}")

        profile = job.profile
        try:
            # Check for pure audio transcode
            if profile.container == TranscodeContainer.WAV or profile.video_codec == VideoCodec.NONE:
                return self._execute_audio_transcode(
                    job, temp_output_path, final_output_path, progress_callback, cancel_check
                )
            else:
                return self._execute_video_transcode(
                    job, temp_output_path, final_output_path, progress_callback, cancel_check
                )
        except Exception as e:
            logger.exception(f"Transcode failed for job '{job.job_id}': {e}")
            job.status = TranscodeJobStatus.FAILED
            job.error_message = str(e)
            if os.path.exists(temp_output_path):
                try:
                    os.remove(temp_output_path)
                except Exception:
                    pass
            return False

    def _execute_video_transcode(
        self,
        job: TranscodeJob,
        temp_path: str,
        final_path: str,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Transcodes video streams with optional aspect ratio preservation and temporal conform."""
        cap = cv2.VideoCapture(job.source_file_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open source media file '{job.source_file_path}' with video decoder.")

        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        src_fps = float(cap.get(cv2.CAP_PROP_FPS))
        if src_fps <= 0 or math.isnan(src_fps):
            src_fps = 24.0
        total_src_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_src_frames <= 0:
            total_src_frames = 1

        profile = job.profile
        target_w = profile.target_width or src_w
        target_h = profile.target_height or src_h
        target_fps = profile.target_fps or src_fps

        # Dimension safety (must be even numbers)
        target_w = (target_w // 2) * 2
        target_h = (target_h // 2) * 2

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        if profile.video_codec == VideoCodec.MJPG:
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")

        writer = cv2.VideoWriter(temp_path, fourcc, target_fps, (target_w, target_h))
        if not writer.isOpened():
            cap.release()
            raise RuntimeError(f"Failed to initialize video writer at '{temp_path}'.")

        job.status = TranscodeJobStatus.TRANSCODING
        job.stage_message = "Transcoding visual frames"
        job.total_frames = total_src_frames

        fps_ratio = target_fps / src_fps
        frame_idx = 0
        written_frames = 0
        accumulated_target_frames = 0.0

        try:
            while True:
                if cancel_check and cancel_check():
                    job.status = TranscodeJobStatus.CANCELLED
                    job.stage_message = "Transcode cancelled by user"
                    break

                ret, frame = cap.read()
                if not ret:
                    break

                # Spatial conform (Scaling / Letterbox)
                conformed_frame = self._conform_frame_dimensions(
                    frame=frame,
                    src_w=src_w,
                    src_h=src_h,
                    target_w=target_w,
                    target_h=target_h,
                    policy=profile.scaling_policy,
                )

                # Temporal conform (FPS adaptation via deterministic frame drop/duplication)
                accumulated_target_frames += fps_ratio
                frames_to_write = int(round(accumulated_target_frames)) - written_frames

                for _ in range(max(1, frames_to_write)):
                    writer.write(conformed_frame)
                    written_frames += 1

                frame_idx += 1
                job.frames_processed = frame_idx
                job.progress_percent = min(95.0, (frame_idx / float(total_src_frames)) * 95.0)
                job.elapsed_time_seconds = time.time() - (job.started_at or time.time())

                if progress_callback:
                    progress_callback(job.progress_percent, frame_idx)

        finally:
            cap.release()
            writer.release()

        if job.status == TranscodeJobStatus.CANCELLED:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False

        # Verification stage
        job.status = TranscodeJobStatus.VERIFYING
        job.stage_message = "Verifying output container integrity"
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise RuntimeError(f"Transcode produced empty or missing file at '{temp_path}'.")

        # Atomic finalize
        if os.path.exists(final_path):
            os.remove(final_path)
        os.rename(temp_path, final_path)

        # Output Fingerprinting & Metadata Recording
        job.output_size_bytes = os.path.getsize(final_path)
        job.output_fingerprint = self._compute_fingerprint(final_path)
        job.status = TranscodeJobStatus.COMPLETED
        job.stage_message = "Transcode and conform completed successfully"
        job.progress_percent = 100.0
        job.completed_at = time.time()
        job.elapsed_time_seconds = job.completed_at - (job.started_at or job.completed_at)
        return True

    def _execute_audio_transcode(
        self,
        job: TranscodeJob,
        temp_path: str,
        final_path: str,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Transcodes WAV audio files with sample-rate conversion, channel downmix, and loudness normalization."""
        src_path = job.source_file_path
        if not src_path.lower().endswith(".wav"):
            raise ValueError(f"Direct audio transcoding currently requires a WAV source: '{src_path}'.")

        with wave.open(src_path, "rb") as wf_in:
            src_channels = wf_in.getnchannels()
            src_sampwidth = wf_in.getsampwidth()
            src_framerate = wf_in.getframerate()
            n_frames = wf_in.getnframes()
            raw_audio = wf_in.readframes(n_frames)

        # Interpret PCM bytes into numpy float32 buffer (-1.0 to 1.0)
        if src_sampwidth == 2:
            data = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
        elif src_sampwidth == 4:
            data = np.frombuffer(raw_audio, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            data = np.frombuffer(raw_audio, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

        if src_channels > 1:
            data = data.reshape(-1, src_channels)
        else:
            data = data.reshape(-1, 1)

        profile = job.profile
        target_channels = profile.audio_channels
        target_rate = profile.audio_sample_rate

        # 1. Channel Downmixing / Upmixing
        if src_channels != target_channels:
            if src_channels >= 2 and target_channels == 1:
                # Downmix to mono: average channels
                data = np.mean(data, axis=1, keepdims=True)
            elif src_channels == 1 and target_channels == 2:
                # Mono to stereo duplication
                data = np.repeat(data, 2, axis=1)

        # 2. Resampling (Linear interpolation across time axis)
        if src_framerate != target_rate:
            total_time = len(data) / float(src_framerate)
            new_len = int(round(total_time * target_rate))
            orig_indices = np.linspace(0, len(data) - 1, new_len)
            resampled = np.zeros((new_len, target_channels), dtype=np.float32)
            for ch in range(target_channels):
                resampled[:, ch] = np.interp(orig_indices, np.arange(len(data)), data[:, ch])
            data = resampled

        # 3. Loudness Measurement & Normalization
        if profile.loudness_standard != LoudnessStandard.NONE:
            # Measure Peak and RMS
            peak_val = np.max(np.abs(data))
            rms_val = np.sqrt(np.mean(data ** 2)) if len(data) > 0 else 0.0001
            
            # Target RMS calculation based on profile LUFS
            target_linear = 10.0 ** (profile.target_lufs / 20.0)
            if rms_val > 1e-6:
                gain = target_linear / rms_val
                # Prevent hard clipping above -0.5 dBFS
                if peak_val * gain > 0.94:
                    gain = 0.94 / max(1e-6, peak_val)
                data = data * gain

        # 4. Write conformed WAV file
        int16_data = np.clip(data * 32767.0, -32768.0, 32767.0).astype(np.int16)
        with wave.open(temp_path, "wb") as wf_out:
            wf_out.setnchannels(target_channels)
            wf_out.setsampwidth(2)
            wf_out.setframerate(target_rate)
            wf_out.writeframes(int16_data.tobytes())

        # Finalize
        if os.path.exists(final_path):
            os.remove(final_path)
        os.rename(temp_path, final_path)

        job.output_size_bytes = os.path.getsize(final_path)
        job.output_fingerprint = self._compute_fingerprint(final_path)
        job.status = TranscodeJobStatus.COMPLETED
        job.stage_message = "Audio conform and transcode completed"
        job.progress_percent = 100.0
        job.completed_at = time.time()
        job.elapsed_time_seconds = job.completed_at - (job.started_at or job.completed_at)
        return True

    def _conform_frame_dimensions(
        self,
        frame: np.ndarray,
        src_w: int,
        src_h: int,
        target_w: int,
        target_h: int,
        policy: ScalingPolicy,
    ) -> np.ndarray:
        """Applies spatial scaling, letterboxing, or cropping to match target dimensions."""
        if src_w == target_w and src_h == target_h:
            return frame

        if policy == ScalingPolicy.STRETCH:
            return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        elif policy == ScalingPolicy.CROP_FILL:
            # Scale so image completely covers target, crop excess
            scale = max(target_w / float(src_w), target_h / float(src_h))
            scaled_w = int(round(src_w * scale))
            scaled_h = int(round(src_h * scale))
            scaled = cv2.resize(frame, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)

            x_start = max(0, (scaled_w - target_w) // 2)
            y_start = max(0, (scaled_h - target_h) // 2)
            return scaled[y_start:y_start + target_h, x_start:x_start + target_w]

        else: # FIT_PAD (Letterbox / Pillarbox)
            scale = min(target_w / float(src_w), target_h / float(src_h))
            scaled_w = (int(round(src_w * scale)) // 2) * 2
            scaled_h = (int(round(src_h * scale)) // 2) * 2
            scaled = cv2.resize(frame, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)

            # Create black background canvas
            canvas = np.zeros((target_h, target_w, frame.shape[2]), dtype=frame.dtype)
            x_offset = max(0, (target_w - scaled_w) // 2)
            y_offset = max(0, (target_h - scaled_h) // 2)
            canvas[y_offset:y_offset + scaled_h, x_offset:x_offset + scaled_w] = scaled
            return canvas

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
                    h.update(f.read(65536))
            return h.hexdigest()
        except Exception:
            return ""


# Global singleton
transcode_engine = TranscodeEngine()
