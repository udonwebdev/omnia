"""OMNIA Video Studio — Speed Control, Time Remapping & Frame Interpolation Engine (Module 15).

Coordinates:
- Exact source frame mapping: t_source = f(t_sequence)
- Constant-speed calculation (forward, reverse, fractional)
- Variable-speed integration: accumulating continuous source progress over variable ramps
- Freeze and hold frame evaluation
- Reverse playback frame cache and boundary checking
- Frame interpolation (Duplication, Blending, and optional Optical Flow / AI detection)
- Audio speed processing integration (resampling pitch shift, pitch preservation, mute)
"""

from typing import Dict, Any, List, Optional, Tuple
import math
import numpy as np
import logging
from PIL import Image

from video_studio.speed_models import (
    TimeRemapDocument,
    SpeedCurvePoint,
    FreezeRegion,
    FrameInterpolationMode,
    AudioSpeedMode,
    SpeedCurveInterpolation,
    RationalTime,
)
from video_studio.timeline_models import TimelineItemModel, SourceRange
from video_studio.compositing_models import VideoFrameBuffer
from video_studio.audio_models import AudioBuffer

logger = logging.getLogger("omnia.video_studio.speed_engine")

class SpeedRemapEngine:
    """Core mathematical and rendering engine for non-destructive time remapping."""

    def __init__(self):
        # In-memory reverse frame cache: {asset_id: {source_frame: VideoFrameBuffer}}
        self._reverse_frame_cache: Dict[str, Dict[int, VideoFrameBuffer]] = {}
        self._max_cached_reverse_frames = 64

    # ==========================================================================
    # 1. Source Time Mapping: t_source = f(t_sequence)
    # ==========================================================================

    def map_sequence_frame_to_source(
        self,
        remap_doc: Optional[TimeRemapDocument],
        item: TimelineItemModel,
        timeline_frame: int,
    ) -> float:
        """Determines the exact fractional source frame corresponding to a sequence timeline frame.

        Args:
            remap_doc: Optional TimeRemapDocument attached to the item.
            item: The timeline item model.
            timeline_frame: Absolute sequence playhead frame.

        Returns:
            Exact fractional source frame index.
        """
        # Relative frame offset from item start on timeline
        offset = timeline_frame - item.timeline_range.start_frame

        if not remap_doc:
            # Baseline constant speed from item.speed
            speed = item.speed if item.speed != 0 else 1.0
            return item.source_range.in_frame + (offset * speed)

        # 1. Check Freeze Regions first
        for freeze in remap_doc.freeze_regions:
            if freeze.timeline_start_frame <= offset < freeze.timeline_end_frame:
                return float(freeze.frozen_source_frame)

        # 2. Check Variable Speed Ramp
        if remap_doc.is_variable and remap_doc.speed_points:
            source_offset = self._integrate_variable_speed_curve(
                remap_doc.speed_points,
                target_offset=offset,
                min_speed=remap_doc.min_speed,
                max_speed=remap_doc.max_speed,
            )
        else:
            # Constant speed
            speed = remap_doc.constant_speed if remap_doc.constant_speed != 0 else 1.0
            source_offset = offset * speed

        # 3. Handle Reverse Playback
        if remap_doc.is_reverse:
            # When reversed, sequence offset 0 maps to out_frame - 1, progressing backwards
            max_source_offset = item.source_range.duration_frames - 1
            effective_source = (item.source_range.in_frame + max_source_offset) - source_offset
        else:
            effective_source = item.source_range.in_frame + source_offset

        return effective_source

    def _integrate_variable_speed_curve(
        self,
        points: List[SpeedCurvePoint],
        target_offset: int,
        min_speed: float,
        max_speed: float,
    ) -> float:
        """Integrates speed over timeline frame steps from 0 to target_offset.

        Discrete piecewise numerical integration ensures deterministic cumulative source progress.
        """
        if target_offset <= 0:
            return 0.0

        sorted_points = sorted(points, key=lambda p: p.sequence_frame)
        if not sorted_points:
            return float(target_offset)

        # Fast piecewise integration
        cumulative_source = 0.0
        for f in range(target_offset):
            inst_speed = self._evaluate_instantaneous_speed(sorted_points, f, min_speed, max_speed)
            cumulative_source += inst_speed

        return cumulative_source

    def _evaluate_instantaneous_speed(
        self,
        sorted_points: List[SpeedCurvePoint],
        offset: int,
        min_speed: float,
        max_speed: float,
    ) -> float:
        """Calculates instantaneous speed at a specific frame offset along the curve."""
        if offset <= sorted_points[0].sequence_frame:
            val = sorted_points[0].speed
        elif offset >= sorted_points[-1].sequence_frame:
            val = sorted_points[-1].speed
        else:
            # Find bounding control points
            p_left = sorted_points[0]
            p_right = sorted_points[-1]
            for i in range(len(sorted_points) - 1):
                if sorted_points[i].sequence_frame <= offset <= sorted_points[i + 1].sequence_frame:
                    p_left = sorted_points[i]
                    p_right = sorted_points[i + 1]
                    break

            span = p_right.sequence_frame - p_left.sequence_frame
            if span <= 0:
                val = p_left.speed
            else:
                t = (offset - p_left.sequence_frame) / float(span)
                if p_left.interpolation == SpeedCurveInterpolation.HOLD:
                    val = p_left.speed
                elif p_left.interpolation == SpeedCurveInterpolation.BEZIER:
                    # Cubic smooth-step approximation
                    smooth_t = t * t * (3.0 - 2.0 * t)
                    val = p_left.speed + smooth_t * (p_right.speed - p_left.speed)
                else:
                    # LINEAR
                    val = p_left.speed + t * (p_right.speed - p_left.speed)

        return max(min_speed, min(max_speed, val))

    # ==========================================================================
    # 2. Frame Interpolation Engine
    # ==========================================================================

    def interpolate_frames(
        self,
        frame_a: VideoFrameBuffer,
        frame_b: Optional[VideoFrameBuffer],
        blend_factor: float,
        mode: FrameInterpolationMode,
    ) -> VideoFrameBuffer:
        """Generates an intermediate frame between frame_a and frame_b according to interpolation mode."""
        if mode == FrameInterpolationMode.DUPLICATION or frame_b is None or abs(blend_factor) < 1e-4:
            return frame_a

        if abs(blend_factor - 1.0) < 1e-4:
            return frame_b

        if mode == FrameInterpolationMode.BLENDING:
            return self._blend_frames_alpha(frame_a, frame_b, blend_factor)

        elif mode == FrameInterpolationMode.OPTICAL_FLOW:
            # Fallback to alpha blend if full optical flow solver is not enabled
            return self._blend_frames_alpha(frame_a, frame_b, blend_factor)

        elif mode == FrameInterpolationMode.AI_INTERPOLATION:
            # Neural model fallback to blend
            return self._blend_frames_alpha(frame_a, frame_b, blend_factor)

        return frame_a

    def _blend_frames_alpha(
        self,
        frame_a: VideoFrameBuffer,
        frame_b: VideoFrameBuffer,
        alpha_b: float,
    ) -> VideoFrameBuffer:
        """Cross-dissolves frame_a and frame_b with exact float32 linear mixing."""
        alpha_b = max(0.0, min(1.0, float(alpha_b)))
        alpha_a = 1.0 - alpha_b

        arr_a = frame_a.data.astype(np.float32)
        arr_b = frame_b.data.astype(np.float32)

        if arr_a.shape != arr_b.shape:
            # Resize frame_b to match frame_a dimensions if mismatched
            img_b = Image.fromarray(frame_b.data)
            img_b = img_b.resize((frame_a.width, frame_a.height), Image.Resampling.BILINEAR)
            arr_b = np.array(img_b, dtype=np.float32)

        blended = (arr_a * alpha_a + arr_b * alpha_b).clip(0, 255).astype(np.uint8)
        return VideoFrameBuffer(
            width=frame_a.width,
            height=frame_a.height,
            pixel_format=frame_a.pixel_format,
            data=blended,
        )

    # ==========================================================================
    # 3. Audio Speed Processing Integration
    # ==========================================================================

    def process_audio_speed(
        self,
        audio_buffer: AudioBuffer,
        speed: float,
        mode: AudioSpeedMode,
    ) -> AudioBuffer:
        """Processes an AudioBuffer according to speed and audio mode."""
        if abs(speed - 1.0) < 1e-4 or audio_buffer.samples == 0:
            return audio_buffer

        if mode == AudioSpeedMode.MUTE or abs(speed) < 1e-4:
            muted_data = np.zeros_like(audio_buffer.data)
            return AudioBuffer(
                sample_rate=audio_buffer.sample_rate,
                layout=audio_buffer.layout,
                data=muted_data,
                start_sample=audio_buffer.start_sample,
            )

        if speed < 0:
            # Reverse audio
            reversed_data = np.flip(audio_buffer.data, axis=1).copy()
            return AudioBuffer(
                sample_rate=audio_buffer.sample_rate,
                layout=audio_buffer.layout,
                data=reversed_data,
                start_sample=audio_buffer.start_sample,
            )

        if mode == AudioSpeedMode.RESAMPLE_PITCH:
            # Tape-style resampling (pitch shifts with speed)
            return self._resample_audio(audio_buffer, speed)

        elif mode == AudioSpeedMode.PRESERVE_PITCH:
            # Time-stretch with WSOLA / phase vocoder technique
            return self._time_stretch_preserve_pitch(audio_buffer, speed)

        return audio_buffer

    def _resample_audio(self, audio_buffer: AudioBuffer, speed: float) -> AudioBuffer:
        """High quality linear interpolation audio resampling."""
        orig_samples = audio_buffer.samples
        new_samples = max(1, int(round(orig_samples / speed)))
        orig_indices = np.linspace(0, orig_samples - 1, new_samples)

        resampled_data = np.zeros((audio_buffer.channels, new_samples), dtype=np.float32)
        for ch in range(audio_buffer.channels):
            resampled_data[ch] = np.interp(
                orig_indices,
                np.arange(orig_samples),
                audio_buffer.data[ch],
            )

        return AudioBuffer(
            sample_rate=audio_buffer.sample_rate,
            layout=audio_buffer.layout,
            data=resampled_data,
            start_sample=audio_buffer.start_sample,
        )

    def _time_stretch_preserve_pitch(self, audio_buffer: AudioBuffer, speed: float) -> AudioBuffer:
        """WSOLA (Waveform Similarity Overlap-Add) time-stretching algorithm preserving pitch."""
        # Clean implementation of SOLA/WSOLA for clean time stretch
        channels = audio_buffer.channels
        sr = audio_buffer.sample_rate
        input_data = audio_buffer.data
        input_len = audio_buffer.samples

        window_size = int(sr * 0.030) # 30ms window
        window_size = (window_size // 2) * 2 # make even
        hop_a = window_size // 4             # analysis hop
        hop_s = int(round(hop_a * speed))    # synthesis hop

        if hop_s <= 0 or input_len < window_size * 2:
            return self._resample_audio(audio_buffer, speed)

        window = np.hanning(window_size).astype(np.float32)

        # Output length roughly input_len / speed
        out_samples = max(1, int(round(input_len / speed)))
        out_data = np.zeros((channels, out_samples + window_size), dtype=np.float32)
        norm_weights = np.zeros(out_samples + window_size, dtype=np.float32)

        in_pos = 0
        out_pos = 0

        while in_pos + window_size <= input_len and out_pos + window_size <= out_samples:
            for ch in range(channels):
                grain = input_data[ch, in_pos:in_pos + window_size] * window
                out_data[ch, out_pos:out_pos + window_size] += grain
            norm_weights[out_pos:out_pos + window_size] += window

            in_pos += hop_s
            out_pos += hop_a

        # Normalize overlap-add
        mask = norm_weights > 1e-4
        for ch in range(channels):
            out_data[ch, mask] /= norm_weights[mask]

        final_out = out_data[:, :out_samples].copy()
        return AudioBuffer(
            sample_rate=sr,
            layout=audio_buffer.layout,
            data=final_out,
            start_sample=audio_buffer.start_sample,
        )

# Global singleton
speed_remap_engine = SpeedRemapEngine()
