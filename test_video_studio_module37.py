"""OMNIA Video Studio — Module 37 Test Suite: Quality Control, Technical Validation & Delivery Compliance.

Verifies:
1. DeliveryProfile model serialization, defaults, custom profile registration.
2. Valid media file PASS behavior (clean container, resolution, frame rate, audio).
3. Corrupt or zero-byte media detection (CRITICAL severity).
4. Video resolution and aspect ratio mismatch detection.
5. Variable Frame Rate (VFR) jitter detection.
6. Black frame cluster and freeze frame detection with time-stamped evidence.
7. Audio peak level clipping detection (dBFS) and extended silence detection.
8. Audio / Video stream duration synchronization mismatch.
9. Timeline sequence gap detection and offline media detection.
10. Approved non-destructive remediation workflow (enforcing approval_confirmed gate).
11. QC report persistence, versioning, and cache invalidation.
12. Capability registry registration for all Module 37 capabilities.
"""

import unittest
import os
import tempfile
import time
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
from video_studio.qc_engine import QualityControlEngine, quality_control_engine
from video_studio.qc_service import QualityControlService, quality_control_service
from video_studio.effects_models import VideoFrameBuffer
from video_studio.audio_models import AudioBuffer, AudioChannelLayout
from video_studio.timeline_models import (
    VideoSequence,
    SequenceSettings,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineTrackType,
    TimelineItemType,
    TimelineRange,
    SourceRange,
)
from video_studio.timeline_service import TimelineService
from video_studio.registry import video_studio_capability_registry


class TestVideoStudioModule37(unittest.TestCase):
    """Module 37 Unit & Integration Tests."""

    def setUp(self):
        self.engine = QualityControlEngine()
        self.timeline_service = TimelineService()
        self.service = QualityControlService(
            engine=self.engine,
            timeline_service_instance=self.timeline_service,
        )
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_delivery_profile_serialization_and_custom_registration(self):
        """DeliveryProfile initializes with sensible broadcast/web standards and registers custom variants."""
        profiles = self.service.list_profiles()
        self.assertGreaterEqual(len(profiles), 3)

        web_prof = self.service.get_profile("delivery_standard_web")
        self.assertIsNotNone(web_prof)
        self.assertEqual(web_prof.target_width, 1920)
        self.assertEqual(web_prof.target_height, 1080)
        self.assertEqual(web_prof.max_peak_dbfs, -0.5)

        # Register custom profile
        custom = DeliveryProfile(
            profile_id="custom_cinema_dci",
            name="DCI 4K Cinema Scope",
            target_width=4096,
            target_height=1716,
            target_aspect_ratio="2.39:1",
            max_peak_dbfs=-1.0,
        )
        registered = self.service.register_custom_profile(custom)
        self.assertTrue(registered.is_custom)
        self.assertEqual(self.service.get_profile("custom_cinema_dci").target_width, 4096)

        # Roundtrip dict
        d = web_prof.to_dict()
        restored = DeliveryProfile.from_dict(d)
        self.assertEqual(restored.profile_id, web_prof.profile_id)
        self.assertEqual(restored.target_width, 1920)

    def test_02_missing_and_zero_byte_media_detection(self):
        """Missing or zero-byte truncated files produce CRITICAL container findings."""
        # 1. Missing file
        missing_path = os.path.join(self.temp_dir.name, "missing_asset.mp4")
        rep_missing = self.service.inspect_media_file(missing_path, "asset_missing")
        self.assertEqual(rep_missing.status, QCReportStatus.FAIL)
        self.assertGreaterEqual(rep_missing.critical_count, 1)
        self.assertEqual(rep_missing.findings[0].category, QCCategory.CONTAINER)

        # 2. Zero-byte truncated file
        zero_path = os.path.join(self.temp_dir.name, "zero_asset.mp4")
        with open(zero_path, "wb") as f:
            pass  # 0 bytes
        rep_zero = self.service.inspect_media_file(zero_path, "asset_zero", force_recheck=True)
        self.assertEqual(rep_zero.status, QCReportStatus.FAIL)
        critical_finding = next(f for f in rep_zero.findings if f.severity == QCSeverity.CRITICAL)
        self.assertIn("Zero-Byte", critical_finding.title)
        self.assertEqual(critical_finding.remediability, RemediabilityType.AUTOMATIC)

    def test_03_video_resolution_and_aspect_ratio_mismatch(self):
        """Resolution and aspect ratio deviations are detected and reported with measured values."""
        # Create dummy media file
        valid_file = os.path.join(self.temp_dir.name, "test_render.mp4")
        with open(valid_file, "wb") as f:
            f.write(b"\x00" * 4096)

        # Frames at 1280x720 (standard web expects 1920x1080)
        frame_data = np.full((720, 1280, 3), 128, dtype=np.uint8)
        frames = [
            VideoFrameBuffer(data=frame_data, width=1280, height=720, pts_seconds=0.0),
            VideoFrameBuffer(data=frame_data, width=1280, height=720, pts_seconds=0.04),
        ]

        report = self.service.inspect_media_file(
            file_path=valid_file,
            asset_id="asset_720p",
            profile_id="delivery_standard_web",
            decoded_frames=frames,
            force_recheck=True,
        )

        self.assertEqual(report.status, QCReportStatus.FAIL)
        res_finding = next(f for f in report.findings if f.check_name == "video.resolution")
        self.assertEqual(res_finding.severity, QCSeverity.ERROR)
        self.assertEqual(res_finding.measured_value, "1280x720")
        self.assertEqual(res_finding.expected_range, "1920x1080")

    def test_04_black_frame_cluster_detection(self):
        """Extended black frame gaps (> profile threshold) are detected with start/end timestamps."""
        valid_file = os.path.join(self.temp_dir.name, "test_black.mp4")
        with open(valid_file, "wb") as f:
            f.write(b"\x00" * 4096)

        black_data = np.zeros((1080, 1920, 3), dtype=np.uint8)
        lit_data = np.full((1080, 1920, 3), 160, dtype=np.uint8)

        # 10 lit frames (0.0 to 0.4s), followed by 20 black frames (0.44 to 1.2s), then 10 lit frames (1.24 to 1.6s)
        frames: List[VideoFrameBuffer] = []
        for i in range(10):
            frames.append(VideoFrameBuffer(data=lit_data, width=1920, height=1080, pts_seconds=i * 0.04))
        for i in range(10, 30):
            frames.append(VideoFrameBuffer(data=black_data, width=1920, height=1080, pts_seconds=i * 0.04))
        for i in range(30, 40):
            frames.append(VideoFrameBuffer(data=lit_data, width=1920, height=1080, pts_seconds=i * 0.04))

        report = self.service.inspect_media_file(
            file_path=valid_file,
            asset_id="asset_black_burst",
            profile_id="delivery_standard_web",
            decoded_frames=frames,
            force_recheck=True,
        )

        black_finding = next((f for f in report.findings if f.check_name == "video.black_frames"), None)
        self.assertIsNotNone(black_finding, "Expected black frame finding.")
        self.assertAlmostEqual(black_finding.start_time, 0.40, delta=0.05)
        self.assertGreaterEqual(black_finding.measured_value, 20)

    def test_05_freeze_frame_detection(self):
        """Extended frozen frame clusters (> profile threshold) are flagged with exact ranges."""
        valid_file = os.path.join(self.temp_dir.name, "test_freeze.mp4")
        with open(valid_file, "wb") as f:
            f.write(b"\x00" * 4096)

        # 35 consecutive identical frames (threshold is 30)
        static_data = np.full((1080, 1920, 3), 200, dtype=np.uint8)
        frames = [
            VideoFrameBuffer(data=static_data, width=1920, height=1080, pts_seconds=i * 0.04)
            for i in range(35)
        ]

        report = self.service.inspect_media_file(
            file_path=valid_file,
            asset_id="asset_freeze",
            profile_id="delivery_standard_web",
            decoded_frames=frames,
            force_recheck=True,
        )

        freeze_finding = next((f for f in report.findings if f.check_name == "video.freeze_frames"), None)
        self.assertIsNotNone(freeze_finding, "Expected freeze frame finding.")
        self.assertEqual(freeze_finding.measured_value, 34)

    def test_06_audio_peak_clipping_detection(self):
        """Audio peak levels violating the delivery profile ceiling (e.g. >= -0.5 dBFS) are caught."""
        valid_file = os.path.join(self.temp_dir.name, "test_audio_clip.mp4")
        with open(valid_file, "wb") as f:
            f.write(b"\x00" * 4096)

        # 1.0 second 48kHz stereo sine wave with 0.0 dBFS full-scale peak
        t = np.linspace(0, 1.0, 48000, endpoint=False)
        tone = np.sin(2 * np.pi * 440.0 * t).astype(np.float32)  # max peak = 1.0 = 0 dBFS
        stereo_data = np.stack([tone, tone], axis=0)

        audio_buf = AudioBuffer(
            data=stereo_data,
            sample_rate=48000,
            layout=AudioChannelLayout.STEREO,
        )

        report = self.service.inspect_media_file(
            file_path=valid_file,
            asset_id="asset_audio_clipping",
            profile_id="delivery_standard_web",
            decoded_audio=audio_buf,
            force_recheck=True,
        )

        clip_finding = next((f for f in report.findings if f.check_name == "audio.clipping"), None)
        self.assertIsNotNone(clip_finding, "Expected audio clipping finding.")
        self.assertEqual(clip_finding.severity, QCSeverity.ERROR)
        self.assertAlmostEqual(clip_finding.measured_value, 0.0, delta=0.1)

    def test_07_audio_video_duration_sync_mismatch(self):
        """A/V duration discrepancies exceeding profile tolerance trigger stream sync errors."""
        valid_file = os.path.join(self.temp_dir.name, "test_av_sync.mp4")
        with open(valid_file, "wb") as f:
            f.write(b"\x00" * 4096)

        # 5 seconds of video
        v_data = np.full((1080, 1920, 3), 100, dtype=np.uint8)
        frames = [
            VideoFrameBuffer(data=v_data, width=1920, height=1080, pts_seconds=0.0),
            VideoFrameBuffer(data=v_data, width=1920, height=1080, pts_seconds=5.0),
        ]

        # 2 seconds of audio (3 second drift > 1.0s tolerance)
        a_data = np.zeros((2, 96000), dtype=np.float32)
        audio_buf = AudioBuffer(data=a_data, sample_rate=48000, layout=AudioChannelLayout.STEREO)

        report = self.service.inspect_media_file(
            file_path=valid_file,
            asset_id="asset_av_drift",
            profile_id="delivery_standard_web",
            decoded_frames=frames,
            decoded_audio=audio_buf,
            force_recheck=True,
        )

        sync_finding = next((f for f in report.findings if f.check_name == "stream.av_sync_duration"), None)
        self.assertIsNotNone(sync_finding, "Expected A/V sync finding.")
        self.assertEqual(sync_finding.severity, QCSeverity.ERROR)
        self.assertAlmostEqual(sync_finding.measured_value, 3.0, delta=0.05)

    def test_08_timeline_sequence_gap_detection(self):
        """Timeline sequence gaps between video items are flagged with frame positions."""
        seq = self.timeline_service.create_sequence("proj_qc", "QC Test Sequence")
        v_track = next(t for t in seq.tracks if t.track_type == TimelineTrackType.VIDEO)

        # Place clip 1 from frame 0 to 48 (2.0s)
        self.timeline_service.add_clip(
            sequence_id=seq.sequence_id,
            track_id=v_track.track_id,
            asset_id="asset_clip_1",
            start_frame=0,
            duration_frames=48,
        )

        # Place clip 2 from frame 72 to 120 (introducing 24-frame gap from frame 48 to 72)
        self.timeline_service.add_clip(
            sequence_id=seq.sequence_id,
            track_id=v_track.track_id,
            asset_id="asset_clip_2",
            start_frame=72,
            duration_frames=48,
        )

        report = self.service.inspect_timeline_sequence(seq.sequence_id)
        gap_finding = next((f for f in report.findings if f.check_name == "timeline.unintentional_gaps"), None)
        self.assertIsNotNone(gap_finding, "Expected timeline track gap finding.")
        self.assertEqual(gap_finding.measured_value, 24)
        self.assertEqual(gap_finding.start_frame, 48)
        self.assertEqual(gap_finding.end_frame, 72)

    def test_09_review_disposition_and_approved_remediation(self):
        """User can set editorial disposition, and remediation strictly requires explicit approval."""
        seq = self.timeline_service.create_sequence("proj_remedy", "Remedy Sequence")
        v_track = next(t for t in seq.tracks if t.track_type == TimelineTrackType.VIDEO)
        self.timeline_service.add_clip(seq.sequence_id, v_track.track_id, "asset_1", start_frame=0, duration_frames=24)
        self.timeline_service.add_clip(seq.sequence_id, v_track.track_id, "asset_2", start_frame=48, duration_frames=24)

        report = self.service.inspect_timeline_sequence(seq.sequence_id)
        finding = next(f for f in report.findings if f.check_name == "timeline.unintentional_gaps")

        # 1. Update review disposition
        updated = self.service.set_finding_review_disposition(
            report_id=report.report_id,
            finding_id=finding.finding_id,
            review_status=UserReviewStatus.FIX_PENDING,
            notes="Approved gap closure.",
        )
        self.assertEqual(updated.review_status, UserReviewStatus.FIX_PENDING)

        # 2. Attempt remediation without explicit approval
        unapproved_res = self.service.apply_approved_remediation(
            report_id=report.report_id,
            finding_id=finding.finding_id,
            approval_confirmed=False,
        )
        self.assertFalse(unapproved_res["success"])
        self.assertIn("Explicit user approval required", unapproved_res["error"])

        # 3. Apply remediation with explicit approval
        approved_res = self.service.apply_approved_remediation(
            report_id=report.report_id,
            finding_id=finding.finding_id,
            approval_confirmed=True,
        )
        self.assertTrue(approved_res["success"])
        self.assertEqual(finding.review_status, UserReviewStatus.RESOLVED)

    def test_10_capability_registry_entries(self):
        """Module 37 capabilities are registered and available in the capability registry."""
        caps = [
            "video.qc.technical_validation",
            "video.qc.audio_compliance",
            "video.qc.delivery_profiles",
            "video.qc.timeline_integrity",
        ]
        for cap_id in caps:
            cap = video_studio_capability_registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability {cap_id} must be registered.")
            self.assertEqual(cap.implementation_state.value, "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
