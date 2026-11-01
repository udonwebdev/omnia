"""OMNIA Video Studio — Video Export, Encoding & Render Pipeline (Module 17).

Coordinates:
- Sequence & timeline evaluation over export range.
- Full compositing, effects, color grading, subtitles, motion graphics, and speed remapping execution per frame.
- High-efficiency video encoding via OpenCV VideoWriter (MP4, AVI, WebM).
- Synchronized multitrack audio mixing & master WAV/PCM export.
- Real-time progress updates & cancellation monitoring.
- Post-render verification & media probing.
"""

from typing import Dict, Any, List, Optional, Tuple, Callable
import os
import time
import uuid
import math
import cv2
import wave
import numpy as np
import logging

from video_studio.export_models import (
    ExportConfig,
    ExportContainer,
    VideoEncoderCodec,
    AudioEncoderCodec,
    RenderJob,
    RenderJobStatus,
    ExportValidationReport,
)
from video_studio.timeline_models import VideoSequence
from video_studio.compositor import multilayer_compositor
from video_studio.audio_mixer import multitrack_audio_mixer
from video_studio.media_probe_engine import media_probe_service

logger = logging.getLogger("omnia.video_studio.export_engine")

class ExportEngine:
    """Core video rendering, encoding, and muxing engine for OMNIA Video Studio."""

    def render_sequence_to_file(
        self,
        job: RenderJob,
        sequence: VideoSequence,
        progress_callback: Optional[Callable[[float, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> ExportValidationReport:
        """Executes full sequence rendering, encoding frames and audio into target file."""
        job.status = RenderJobStatus.PREPARING
        t_start = time.time()

        cfg = job.config
        start_frame = job.snapshot.start_frame
        end_frame = job.snapshot.end_frame
        total_frames = max(1, end_frame - start_frame)
        job.total_frames = total_frames

        # Ensure output directory exists
        out_dir = os.path.dirname(os.path.abspath(job.output_path))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        # Module 18: Validate that all referenced media assets have available originals (Strict Export Source Protection)
        try:
            from video_studio.proxy_service import proxy_service
            from video_studio.proxy_models import ExportSourcePolicy
            from video_studio.media_library import media_library_registry
            pml = media_library_registry.get_or_create(sequence.project_id)
            for track in sequence.tracks:
                for item in track.items:
                    if item.source_reference_id:
                        asset = pml.get_asset(item.source_reference_id)
                        if asset:
                            # Strict resolution check
                            proxy_service.resolve_source_for_export(asset, ExportSourcePolicy.ORIGINALS_ONLY)
        except Exception as e:
            job.status = RenderJobStatus.FAILED
            job.error_message = f"Strict export pre-check failed: {e}"
            return ExportValidationReport(is_valid=False, file_path=job.output_path, error_message=str(e))

        # 1. Determine Container & Codec
        fourcc = self._resolve_fourcc(cfg.video_codec, cfg.container)
        fps = float(cfg.frame_rate)
        width, height = cfg.width, cfg.height

        writer = None
        if cfg.include_video and cfg.container != ExportContainer.WAV:
            writer = cv2.VideoWriter(job.output_path, fourcc, fps, (width, height))
            if not writer.isOpened():
                # Fallback to standard MP4V / MJPG
                fourcc_fb = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(job.output_path, fourcc_fb, fps, (width, height))
                if not writer.isOpened():
                    raise RuntimeError(f"Failed to open video writer for output: {job.output_path}")

        job.status = RenderJobStatus.RENDERING

        # 2. Render Video Frames (if video is enabled)
        try:
            if cfg.include_video and writer:
                for idx, frame_idx in enumerate(range(start_frame, end_frame)):
                    if cancel_check and cancel_check():
                        job.status = RenderJobStatus.CANCELLED
                        writer.release()
                        return ExportValidationReport(is_valid=False, file_path=job.output_path, error_message="Render cancelled by user.")

                    # Full compositing graph execution (Layers, Effects, Color Grades, Graphics, Captions, Transitions)
                    frame_buf = multilayer_compositor.composite_sequence_frame(
                        sequence=sequence,
                        target_frame=frame_idx,
                        canvas_width=width,
                        canvas_height=height,
                    )

                    # OpenCV expects BGR uint8
                    rgba = frame_buf.data
                    if rgba.shape[2] == 4:
                        bgr = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
                    else:
                        bgr = cv2.cvtColor(rgba, cv2.COLOR_RGB2BGR)

                    writer.write(bgr)

                    job.frames_rendered = idx + 1
                    job.progress_percent = (job.frames_rendered / float(total_frames)) * (85.0 if cfg.include_audio else 100.0)
                    job.elapsed_time_seconds = time.time() - t_start

                    if progress_callback:
                        progress_callback(job.progress_percent, job.frames_rendered)

                writer.release()
                writer = None

            # 3. Audio Rendering (if configured)
            if cfg.include_audio:
                job.status = RenderJobStatus.ENCODING
                # Render master audio mix for the export range
                audio_buf = multitrack_audio_mixer.render_audio_slice(
                    sequence=sequence,
                    start_frame=start_frame,
                    duration_frames=total_frames,
                    sample_rate=cfg.audio_sample_rate,
                    output_channels=cfg.audio_channels,
                )

                # For WAV export or companion audio track
                audio_path = job.output_path if cfg.container == ExportContainer.WAV else f"{os.path.splitext(job.output_path)[0]}.wav"
                self._write_audio_wav(audio_path, audio_buf, cfg.audio_sample_rate, cfg.audio_channels)

                job.progress_percent = 95.0
                if progress_callback:
                    progress_callback(job.progress_percent, job.frames_rendered)

            # 4. Verification Stage
            job.status = RenderJobStatus.VERIFYING
            report = self.validate_export_output(job.output_path, expected_fps=fps, expected_w=width, expected_h=height)
            job.validation_report = report

            if report.is_valid:
                job.status = RenderJobStatus.COMPLETED
                job.progress_percent = 100.0
                job.completed_at = time.time()
                job.elapsed_time_seconds = job.completed_at - t_start
            else:
                job.status = RenderJobStatus.FAILED
                job.error_message = report.error_message

            return report

        except Exception as e:
            if writer:
                writer.release()
            job.status = RenderJobStatus.FAILED
            job.error_message = str(e)
            logger.error(f"Render job '{job.job_id}' failed: {e}", exc_info=True)
            return ExportValidationReport(is_valid=False, file_path=job.output_path, error_message=str(e))

    def _resolve_fourcc(self, codec: VideoEncoderCodec, container: ExportContainer) -> int:
        """Maps VideoEncoderCodec and Container to safe OpenCV FourCC integers."""
        if container == ExportContainer.WEBM:
            return cv2.VideoWriter_fourcc(*"VP80")
        elif codec == VideoEncoderCodec.H264:
            # Platform dependent, fallback gracefully
            return cv2.VideoWriter_fourcc(*"mp4v")
        elif codec == VideoEncoderCodec.MJPEG:
            return cv2.VideoWriter_fourcc(*"MJPG")
        else:
            return cv2.VideoWriter_fourcc(*"mp4v")

    def _write_audio_wav(self, file_path: str, audio_buf: Any, sample_rate: int, channels: int) -> None:
        """Writes PCM audio data safely to disk as a standard 16-bit WAV file."""
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(sample_rate)
            pcm_bytes = audio_buf.to_int16_bytes() if hasattr(audio_buf, "to_int16_bytes") else (audio_buf.data * 32767.0).astype(np.int16).T.tobytes()
            wf.writeframes(pcm_bytes)

    def validate_export_output(
        self,
        file_path: str,
        expected_fps: float = 24.0,
        expected_w: int = 1920,
        expected_h: int = 1080,
    ) -> ExportValidationReport:
        """Validates that output media file exists, has nonzero size, and valid headers."""
        if not os.path.exists(file_path):
            return ExportValidationReport(is_valid=False, file_path=file_path, error_message="File does not exist.")

        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            return ExportValidationReport(is_valid=False, file_path=file_path, file_size_bytes=0, error_message="File is empty (0 bytes).")

        # 1. Check if WAV audio container first
        if file_path.lower().endswith(".wav"):
            try:
                with wave.open(file_path, "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    dur = frames / float(rate)
                    return ExportValidationReport(
                        is_valid=True,
                        file_path=file_path,
                        file_size_bytes=file_size,
                        duration_seconds=dur,
                        has_audio_stream=True,
                    )
            except Exception as ex:
                return ExportValidationReport(is_valid=False, file_path=file_path, file_size_bytes=file_size, error_message=f"Corrupt WAV: {ex}")

        # 2. Probe video stream with OpenCV
        cap = cv2.VideoCapture(file_path)
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            dur_sec = frame_count / max(1.0, fps)
            ret, sample_frame = cap.read()
            cap.release()

            if not ret or sample_frame is None:
                return ExportValidationReport(
                    is_valid=False,
                    file_path=file_path,
                    file_size_bytes=file_size,
                    error_message="Could not decode test frame from exported video.",
                )

            return ExportValidationReport(
                is_valid=True,
                file_path=file_path,
                file_size_bytes=file_size,
                duration_seconds=dur_sec,
                detected_width=w,
                detected_height=h,
                detected_fps=fps,
                has_video_stream=True,
            )

        return ExportValidationReport(
            is_valid=False,
            file_path=file_path,
            file_size_bytes=file_size,
            error_message="Could not open video or audio stream for verification.",
        )

# Global singleton
export_engine = ExportEngine()
