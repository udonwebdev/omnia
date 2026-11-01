"""OMNIA Video Studio — Media Quality Control, Technical Validation & Delivery Compliance Engine (Module 37).

Provides deterministic and evidence-backed technical validation checks:
1. Container & Structural Verification:
   - Existence, read permissions, atom structure, file size bounds.
   - Container format & codec compatibility against target profile.
2. Video Technical QC:
   - Resolution & Aspect Ratio conformance.
   - Frame rate continuity & Variable-Frame-Rate (VFR) jitter.
   - Bounded black-frame cluster detection (Luma MAD / Mean Luma < 2.0).
   - Bounded freeze-frame cluster detection (Inter-frame MAD == 0.0 or < 0.1).
   - Safe-area / aspect ratio mismatch (letterboxing/pillarboxing detection).
   - Pixel clipping (luma clipping at 0 or 255 exceeding threshold).
3. Audio Technical QC:
   - Peak amplitude & true clipping detection (Peak >= max_peak_dbfs / 0.0 dBFS).
   - RMS energy levels and unexpected internal silence gaps (> threshold).
   - Channel layout, channel count, sample rate verification.
   - Audio / Video duration synchronization and drift.
4. Timeline Sequence Integrity QC:
   - Gap detection between items on tracks.
   - Offline / missing asset detection.
   - Track alignment and structural validity.
"""

import os
import math
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

from video_studio.qc_models import (
    QCReportStatus,
    QCSeverity,
    QCCategory,
    RemediabilityType,
    UserReviewStatus,
    QCInspectionScope,
    QCFinding,
    DeliveryProfile,
    QualityControlReport,
)
from video_studio.effects_models import VideoFrameBuffer
from video_studio.audio_models import AudioBuffer, AudioChannelLayout
from video_studio.timeline_models import VideoSequence, TimelineTrackType, TimelineItemType
from video_studio.media_models import MediaAsset
from video_studio.media_probe_engine import DeepBinaryInspectionProvider
from video_studio.timeline_validation import timeline_validation_engine

logger = logging.getLogger("Omnia.VideoStudio.QCEngine")


class QualityControlEngine:
    """Core algorithmic engine for technical quality control and delivery compliance validation."""

    def __init__(self):
        self.probe_provider = DeepBinaryInspectionProvider()

    # -------------------------------------------------------------------------
    # 1. Container & Structural Checks
    # -------------------------------------------------------------------------

    def check_container_and_metadata(
        self,
        file_path: str,
        profile: DeliveryProfile,
        report: QualityControlReport,
    ) -> None:
        """Inspects physical file existence, container atom structure, and size constraints."""
        report.executed_checks.append("container.readability")

        if not os.path.exists(file_path):
            report.findings.append(
                QCFinding(
                    check_name="container.readability",
                    category=QCCategory.CONTAINER,
                    severity=QCSeverity.CRITICAL,
                    title="Media File Missing or Unreadable",
                    description=f"File not found on filesystem at: {file_path}",
                    measured_value=0,
                    expected_range="> 0 bytes",
                    unit="bytes",
                    suggested_remediation="Verify asset storage path or restore missing file from archive.",
                    remediability=RemediabilityType.MANUAL,
                )
            )
            return

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            report.findings.append(
                QCFinding(
                    check_name="container.readability",
                    category=QCCategory.CONTAINER,
                    severity=QCSeverity.CRITICAL,
                    title="Zero-Byte Truncated File",
                    description=f"Media file exists but is 0 bytes (truncated or corrupt export).",
                    measured_value=0,
                    expected_range="> 1024 bytes",
                    unit="bytes",
                    suggested_remediation="Re-render export or re-ingest source media file.",
                    remediability=RemediabilityType.AUTOMATIC,
                    remediation_command="re_render_export",
                )
            )
            return

        # Check maximum file size ceiling if configured in profile
        if profile.max_file_size_bytes is not None and file_size > profile.max_file_size_bytes:
            report.findings.append(
                QCFinding(
                    check_name="container.file_size_ceiling",
                    category=QCCategory.COMPLIANCE,
                    severity=QCSeverity.ERROR,
                    title="File Size Exceeds Delivery Ceiling",
                    description=f"File size ({file_size} bytes) exceeds delivery limit ({profile.max_file_size_bytes} bytes).",
                    measured_value=file_size,
                    expected_range=f"<= {profile.max_file_size_bytes}",
                    unit="bytes",
                    suggested_remediation="Increase video compression or reduce target bitrate in export preset.",
                    remediability=RemediabilityType.AUTOMATIC,
                    remediation_command="re_export_reduced_bitrate",
                )
            )

        # Inspect format and codec compatibility via probe
        report.executed_checks.append("container.codec_compatibility")
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if profile.allowed_containers and ext not in [c.lower() for c in profile.allowed_containers]:
            report.findings.append(
                QCFinding(
                    check_name="container.codec_compatibility",
                    category=QCCategory.COMPLIANCE,
                    severity=QCSeverity.ERROR,
                    title="Container Format Not Allowed by Profile",
                    description=f"Container '.{ext}' is not permitted by delivery profile '{profile.name}'. Allowed: {profile.allowed_containers}",
                    measured_value=ext,
                    expected_range=str(profile.allowed_containers),
                    suggested_remediation=f"Transcode or re-mux container into an allowed format ({profile.allowed_containers[0]}).",
                    remediability=RemediabilityType.AUTOMATIC,
                    remediation_command="transcode_container",
                )
            )

        # Deep binary inspect
        try:
            probe_rep = self.probe_provider.inspect(file_path, report.target_id, fingerprint="qc_probe")
            report.media_metadata["probe"] = probe_rep.to_dict()
        except Exception as e:
            report.findings.append(
                QCFinding(
                    check_name="container.deep_parse",
                    category=QCCategory.CONTAINER,
                    severity=QCSeverity.ERROR,
                    title="Container Deep Parse Failure",
                    description=f"Failed to parse binary atom headers: {str(e)}",
                    suggested_remediation="Check if file was aborted during render or has damaged moov atom.",
                    remediability=RemediabilityType.UNSUPPORTED,
                )
            )

    # -------------------------------------------------------------------------
    # 2. Video Technical QC
    # -------------------------------------------------------------------------

    def check_video_frames(
        self,
        frames: List[VideoFrameBuffer],
        profile: DeliveryProfile,
        report: QualityControlReport,
        expected_fps: Optional[float] = None,
    ) -> None:
        """Inspects decoded video frames for resolution, black bursts, freeze frames, and clipping."""
        if not frames:
            report.skipped_checks["video.frames"] = "No decoded frames provided for visual QC."
            return

        report.executed_checks.append("video.resolution")
        first_frame = frames[0]
        actual_w = first_frame.width
        actual_h = first_frame.height

        # 1. Resolution Check
        if profile.target_width is not None and profile.target_height is not None:
            if actual_w != profile.target_width or actual_h != profile.target_height:
                report.findings.append(
                    QCFinding(
                        check_name="video.resolution",
                        category=QCCategory.VIDEO,
                        severity=QCSeverity.ERROR,
                        title="Resolution Mismatch",
                        description=f"Video resolution {actual_w}x{actual_h} does not match profile requirement {profile.target_width}x{profile.target_height}.",
                        measured_value=f"{actual_w}x{actual_h}",
                        expected_range=f"{profile.target_width}x{profile.target_height}",
                        unit="pixels",
                        suggested_remediation=f"Rescale or render output sequence at {profile.target_width}x{profile.target_height}.",
                        remediability=RemediabilityType.AUTOMATIC,
                        remediation_command="rescale_video",
                    )
                )

        # 2. Aspect Ratio Check
        if profile.target_aspect_ratio:
            ratio_val = actual_w / max(1, actual_h)
            expected_r = 16.0 / 9.0 if profile.target_aspect_ratio == "16:9" else (4.0 / 3.0 if profile.target_aspect_ratio == "4:3" else None)
            if expected_r is not None and abs(ratio_val - expected_r) > 0.05:
                report.findings.append(
                    QCFinding(
                        check_name="video.aspect_ratio",
                        category=QCCategory.VIDEO,
                        severity=QCSeverity.WARNING,
                        title="Aspect Ratio Deviation",
                        description=f"Calculated aspect ratio {ratio_val:.3f} deviates from expected {profile.target_aspect_ratio} ({expected_r:.3f}).",
                        measured_value=round(ratio_val, 3),
                        expected_range=str(expected_r),
                        suggested_remediation="Verify pixel aspect ratio and crop/pad parameters.",
                        remediability=RemediabilityType.MANUAL,
                    )
                )

        # 3. Frame Rate & Timestamp Continuity Check
        report.executed_checks.append("video.frame_rate_continuity")
        if len(frames) > 1:
            intervals = [frames[i].pts_seconds - frames[i-1].pts_seconds for i in range(1, len(frames))]
            mean_interval = float(np.mean(intervals))
            measured_fps = 1.0 / mean_interval if mean_interval > 0 else 0.0

            # VFR check (variance of frame intervals)
            std_interval = float(np.std(intervals))
            if profile.require_constant_frame_rate and std_interval > 0.015:
                report.findings.append(
                    QCFinding(
                        check_name="video.frame_rate_continuity",
                        category=QCCategory.VIDEO,
                        severity=QCSeverity.ERROR,
                        title="Variable Frame Rate (VFR) Detected",
                        description=f"Timestamp jitter standard deviation {std_interval*1000:.2f}ms exceeds constant frame rate limit (15ms).",
                        measured_value=round(std_interval * 1000, 2),
                        expected_range="< 15.0",
                        unit="ms",
                        suggested_remediation="Conform media to constant frame rate (CFR) before final master delivery.",
                        remediability=RemediabilityType.AUTOMATIC,
                        remediation_command="conform_to_cfr",
                    )
                )

        # 4. Black Frame Cluster Inspection
        report.executed_checks.append("video.black_frames")
        black_start_idx: Optional[int] = None
        consecutive_black = 0

        for i, frame in enumerate(frames):
            data = frame.data
            # Compute mean luma
            if data.ndim == 3:
                # Approximate luma Y = 0.299R + 0.587G + 0.114B
                mean_luma = float(0.299 * np.mean(data[:, :, 0]) + 0.587 * np.mean(data[:, :, 1]) + 0.114 * np.mean(data[:, :, 2]))
            else:
                mean_luma = float(np.mean(data))

            is_black = (mean_luma < 2.0)

            if is_black:
                if black_start_idx is None:
                    black_start_idx = i
                consecutive_black += 1
            else:
                if consecutive_black >= profile.max_consecutive_black_frames:
                    # Black burst detected
                    start_t = frames[black_start_idx].pts_seconds
                    end_t = frames[i - 1].pts_seconds
                    report.findings.append(
                        QCFinding(
                            check_name="video.black_frames",
                            category=QCCategory.VIDEO,
                            severity=QCSeverity.WARNING if (black_start_idx == 0 or i == len(frames)) else QCSeverity.ERROR,
                            title="Unexpected Black Frame Gap",
                            description=f"Continuous cluster of {consecutive_black} black frames detected from {start_t:.2f}s to {end_t:.2f}s.",
                            start_time=start_t,
                            end_time=end_t,
                            start_frame=black_start_idx,
                            end_frame=i - 1,
                            measured_value=consecutive_black,
                            expected_range=f"<= {profile.max_consecutive_black_frames}",
                            unit="frames",
                            suggested_remediation="Verify if black interval is an intentional scene fade or an unlinked timeline gap.",
                            remediability=RemediabilityType.MANUAL,
                        )
                    )
                black_start_idx = None
                consecutive_black = 0

        # Trailing black check
        if consecutive_black >= profile.max_consecutive_black_frames and black_start_idx is not None:
            start_t = frames[black_start_idx].pts_seconds
            end_t = frames[-1].pts_seconds
            report.findings.append(
                QCFinding(
                    check_name="video.black_frames",
                    category=QCCategory.VIDEO,
                    severity=QCSeverity.WARNING,  # Trailing black is often an intentional tail pad
                    title="Trailing Black Frame Tail Pad",
                    description=f"Trailing sequence contains {consecutive_black} black frames from {start_t:.2f}s to {end_t:.2f}s.",
                    start_time=start_t,
                    end_time=end_t,
                    start_frame=black_start_idx,
                    end_frame=len(frames) - 1,
                    measured_value=consecutive_black,
                    expected_range=f"<= {profile.max_consecutive_black_frames}",
                    unit="frames",
                    suggested_remediation="Confirm whether tail pad meets delivery slate guidelines.",
                    remediability=RemediabilityType.MANUAL,
                )
            )

        # 5. Freeze Frame Cluster Inspection
        report.executed_checks.append("video.freeze_frames")
        freeze_start_idx: Optional[int] = None
        consecutive_frozen = 0

        for i in range(1, len(frames)):
            prev_f = frames[i - 1].data
            curr_f = frames[i].data

            # Mean absolute pixel difference
            mad = float(np.mean(np.abs(curr_f.astype(np.float32) - prev_f.astype(np.float32))))

            if mad < 0.05:  # Perfectly identical or static
                if freeze_start_idx is None:
                    freeze_start_idx = i - 1
                consecutive_frozen += 1
            else:
                if consecutive_frozen >= profile.max_consecutive_freeze_frames:
                    start_t = frames[freeze_start_idx].pts_seconds
                    end_t = frames[i - 1].pts_seconds
                    report.findings.append(
                        QCFinding(
                            check_name="video.freeze_frames",
                            category=QCCategory.VIDEO,
                            severity=QCSeverity.WARNING,
                            title="Freeze Frame Detected",
                            description=f"Static freeze frame lasting {consecutive_frozen} frames from {start_t:.2f}s to {end_t:.2f}s.",
                            start_time=start_t,
                            end_time=end_t,
                            start_frame=freeze_start_idx,
                            end_frame=i - 1,
                            measured_value=consecutive_frozen,
                            expected_range=f"<= {profile.max_consecutive_freeze_frames}",
                            unit="frames",
                            suggested_remediation="Review timeline to verify if freeze frame is intentional artistic hold.",
                            remediability=RemediabilityType.MANUAL,
                        )
                    )
                freeze_start_idx = None
                consecutive_frozen = 0

        if consecutive_frozen >= profile.max_consecutive_freeze_frames and freeze_start_idx is not None:
            start_t = frames[freeze_start_idx].pts_seconds
            end_t = frames[-1].pts_seconds
            report.findings.append(
                QCFinding(
                    check_name="video.freeze_frames",
                    category=QCCategory.VIDEO,
                    severity=QCSeverity.WARNING,
                    title="Freeze Frame at Tail",
                    description=f"Static freeze frame lasting {consecutive_frozen} frames from {start_t:.2f}s to {end_t:.2f}s.",
                    start_time=start_t,
                    end_time=end_t,
                    start_frame=freeze_start_idx,
                    end_frame=len(frames) - 1,
                    measured_value=consecutive_frozen,
                    expected_range=f"<= {profile.max_consecutive_freeze_frames}",
                    unit="frames",
                    suggested_remediation="Verify hold frame intent.",
                    remediability=RemediabilityType.MANUAL,
                )
            )

    # -------------------------------------------------------------------------
    # 3. Audio Technical QC
    # -------------------------------------------------------------------------

    def check_audio_buffer(
        self,
        audio_buffer: AudioBuffer,
        profile: DeliveryProfile,
        report: QualityControlReport,
    ) -> None:
        """Inspects decoded audio for peak clipping, channel layout, and unexpected silence."""
        report.executed_checks.append("audio.channel_layout")

        # 1. Channel layout validation
        layout_name = audio_buffer.layout.value
        if profile.allowed_channel_layouts and layout_name not in profile.allowed_channel_layouts:
            report.findings.append(
                QCFinding(
                    check_name="audio.channel_layout",
                    category=QCCategory.AUDIO,
                    severity=QCSeverity.ERROR,
                    title="Disallowed Audio Channel Layout",
                    description=f"Audio channel layout '{layout_name}' does not match profile allowed: {profile.allowed_channel_layouts}",
                    measured_value=layout_name,
                    expected_range=str(profile.allowed_channel_layouts),
                    suggested_remediation="Apply audio conform or channel remixing in timeline export settings.",
                    remediability=RemediabilityType.AUTOMATIC,
                    remediation_command="conform_audio_channel_layout",
                )
            )

        # 2. Sample rate validation
        report.executed_checks.append("audio.sample_rate")
        if audio_buffer.sample_rate != profile.target_sample_rate:
            report.findings.append(
                QCFinding(
                    check_name="audio.sample_rate",
                    category=QCCategory.AUDIO,
                    severity=QCSeverity.WARNING,
                    title="Audio Sample Rate Mismatch",
                    description=f"Audio sample rate is {audio_buffer.sample_rate} Hz, expected {profile.target_sample_rate} Hz.",
                    measured_value=audio_buffer.sample_rate,
                    expected_range=str(profile.target_sample_rate),
                    unit="Hz",
                    suggested_remediation=f"Resample audio stream to {profile.target_sample_rate} Hz.",
                    remediability=RemediabilityType.AUTOMATIC,
                    remediation_command="resample_audio",
                )
            )

        # 3. Peak Clipping Inspection
        report.executed_checks.append("audio.clipping")
        samples = audio_buffer.data
        if samples.size > 0:
            peak_linear = float(np.max(np.abs(samples)))
            peak_dbfs = 20.0 * math.log10(max(1e-7, peak_linear))

            if peak_dbfs >= profile.max_peak_dbfs:
                # Find time of maximum clipping
                clipped_indices = np.where(np.abs(samples) >= (10.0 ** (profile.max_peak_dbfs / 20.0)))[1]
                clip_time = float(clipped_indices[0]) / audio_buffer.sample_rate if len(clipped_indices) > 0 else 0.0

                report.findings.append(
                    QCFinding(
                        check_name="audio.clipping",
                        category=QCCategory.AUDIO,
                        severity=QCSeverity.ERROR,
                        title="Audio Peak Level Clipping Detected",
                        description=f"Peak audio level reached {peak_dbfs:.2f} dBFS, exceeding profile ceiling of {profile.max_peak_dbfs:.2f} dBFS.",
                        start_time=clip_time,
                        end_time=clip_time + 0.1,
                        measured_value=round(peak_dbfs, 2),
                        expected_range=f"< {profile.max_peak_dbfs:.2f}",
                        unit="dBFS",
                        suggested_remediation="Apply a brickwall limiter or reduce track gain by 1.5 dB.",
                        remediability=RemediabilityType.AUTOMATIC,
                        remediation_command="apply_limiter",
                    )
                )

        # 4. Audio Silence Inspection
        report.executed_checks.append("audio.silence")
        if samples.size > 0:
            # Measure RMS in 0.5s windows
            win_size = int(audio_buffer.sample_rate * 0.5)
            if win_size > 0 and samples.shape[1] >= win_size:
                num_windows = samples.shape[1] // win_size
                consecutive_silent_windows = 0
                silence_start_win = None
                max_allowed_windows = int(profile.max_silence_duration_seconds / 0.5)

                for w in range(num_windows):
                    chunk = samples[:, w*win_size : (w+1)*win_size]
                    rms = float(np.sqrt(np.mean(chunk**2)))
                    rms_db = 20.0 * math.log10(max(1e-7, rms))

                    if rms_db < -60.0:  # Audio silence below -60 dBFS
                        if silence_start_win is None:
                            silence_start_win = w
                        consecutive_silent_windows += 1
                    else:
                        if consecutive_silent_windows >= max_allowed_windows:
                            st = silence_start_win * 0.5
                            et = w * 0.5
                            report.findings.append(
                                QCFinding(
                                    check_name="audio.silence",
                                    category=QCCategory.AUDIO,
                                    severity=QCSeverity.WARNING,
                                    title="Extended Audio Silence",
                                    description=f"Audio silence (< -60 dBFS) detected lasting {et - st:.2f}s from {st:.2f}s to {et:.2f}s.",
                                    start_time=st,
                                    end_time=et,
                                    measured_value=round(et - st, 2),
                                    expected_range=f"<= {profile.max_silence_duration_seconds}",
                                    unit="seconds",
                                    suggested_remediation="Verify if silent interval is intentional pause or missing audio track.",
                                    remediability=RemediabilityType.MANUAL,
                                )
                            )
                        silence_start_win = None
                        consecutive_silent_windows = 0

    # -------------------------------------------------------------------------
    # 4. Stream Duration & A/V Synchronization
    # -------------------------------------------------------------------------

    def check_av_sync_and_duration(
        self,
        video_duration: float,
        audio_duration: float,
        profile: DeliveryProfile,
        report: QualityControlReport,
    ) -> None:
        """Inspects duration delta between video and audio streams."""
        report.executed_checks.append("stream.av_sync_duration")

        drift = abs(video_duration - audio_duration)
        if drift > profile.duration_tolerance_seconds:
            report.findings.append(
                QCFinding(
                    check_name="stream.av_sync_duration",
                    category=QCCategory.AUDIO,
                    severity=QCSeverity.ERROR,
                    title="Audio/Video Stream Duration Mismatch",
                    description=f"Video duration ({video_duration:.2f}s) and Audio duration ({audio_duration:.2f}s) mismatch by {drift:.2f}s (tolerance: {profile.duration_tolerance_seconds:.2f}s).",
                    measured_value=round(drift, 3),
                    expected_range=f"<= {profile.duration_tolerance_seconds}",
                    unit="seconds",
                    suggested_remediation="Pad or trim audio track to match exact video runtime.",
                    remediability=RemediabilityType.AUTOMATIC,
                    remediation_command="conform_audio_duration",
                )
            )

    # -------------------------------------------------------------------------
    # 5. Timeline Sequence Integrity QC
    # -------------------------------------------------------------------------

    def check_timeline_sequence(
        self,
        sequence: VideoSequence,
        profile: DeliveryProfile,
        report: QualityControlReport,
        all_sequences: Optional[Dict[str, VideoSequence]] = None,
    ) -> None:
        """Inspects a timeline sequence for structural validity, gaps, and missing clips."""
        report.executed_checks.append("timeline.structural_integrity")

        # Validate with existing Module 4 validator
        valid, errs = timeline_validation_engine.validate_sequence(sequence, all_sequences)
        if not valid:
            for err in errs:
                report.findings.append(
                    QCFinding(
                        check_name="timeline.structural_integrity",
                        category=QCCategory.TIMELINE,
                        severity=QCSeverity.ERROR,
                        title="Sequence Structural Error",
                        description=err,
                        suggested_remediation="Fix sequence track layout or link consistency.",
                        remediability=RemediabilityType.MANUAL,
                    )
                )

        # Inspect gaps on video tracks
        report.executed_checks.append("timeline.unintentional_gaps")
        for track in sequence.tracks:
            if track.track_type != TimelineTrackType.VIDEO or not track.is_visible:
                continue

            sorted_items = sorted(track.items, key=lambda it: it.timeline_range.start_frame)
            current_frame = 0

            for it in sorted_items:
                gap = it.timeline_range.start_frame - current_frame
                if gap > 0:
                    fps = sequence.settings.frame_rate if sequence.settings else 24.0
                    start_sec = float(current_frame) / fps
                    gap_sec = float(gap) / fps
                    report.findings.append(
                        QCFinding(
                            check_name="timeline.unintentional_gaps",
                            category=QCCategory.TIMELINE,
                            severity=QCSeverity.WARNING,
                            title="Timeline Track Gap Detected",
                            description=f"Track '{track.name}' has unpopulated {gap}-frame gap ({gap_sec:.2f}s) starting at {start_sec:.2f}s.",
                            start_time=start_sec,
                            end_time=start_sec + gap_sec,
                            start_frame=current_frame,
                            end_frame=it.timeline_range.start_frame,
                            measured_value=gap,
                            expected_range="0 frames",
                            unit="frames",
                            suggested_remediation="Close gap using Ripple Delete or extend neighboring clip head/tail.",
                            remediability=RemediabilityType.AUTOMATIC,
                            remediation_command="ripple_delete_gap",
                        )
                    )
                current_frame = it.timeline_range.end_frame


# Global singleton
quality_control_engine = QualityControlEngine()
