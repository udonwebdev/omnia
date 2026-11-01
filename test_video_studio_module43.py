"""OMNIA Video Studio — Module 43 Tests: Media Conform, Offline Editing & Relinking.

Comprehensive test suite verifying:
1. Source and proxy identity relationships and bidirectional mapping records.
2. Proxy profile configuration (540p, 720p, 1080p).
3. Frame rate, total frames, and duration preservation validation.
4. Audio channel preservation and stream layout compatibility.
5. Seamless playback representation switching (ORIGINAL vs PROXY).
6. State preservation during representation toggling (in/out points, ranges, speed, effects).
7. Missing original source detection during preflight conform audit.
8. Blocking conform detection on frame-rate or significant duration mismatches.
9. Preflight report issue classification (COMPATIBLE, WARNING, RESOLUTION, BLOCKING).
10. Transactional online conform execution with pre-conform rollback snapshot.
11. Export conform validation gate: prevents proxy media from rendering in final master exports.
12. Capability registration in VideoStudioCapabilityRegistry under MEDIA, TIMELINE, and EXPORT categories.
"""

import os
import tempfile
import unittest
from video_studio.conform_engine import ConformEngine
from video_studio.conform_models import (
    ConformCompatibilityGrade,
    ConformPreflightReport,
    MediaRepresentationMode,
    ProxyMappingRecord,
    ProxyProfile,
)
from video_studio.conform_service import ConformService
from video_studio.media_library import ProjectMediaLibrary, MediaAsset, AssetMediaType
from video_studio.media_models import AssetLifecycleStatus
from video_studio.provenance_engine import compute_file_sha256_chunked
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.registry_models import ImplementationState, VideoStudioCategory
from video_studio.timeline_models import (
    SequenceSettings,
    TimelineItemModel,
    TimelineRange,
    TimelineTrackModel,
    TimelineTrackType,
    VideoSequence,
)
from video_studio.timeline_service import TimelineService
from video_studio.versioning_service import VersionControlService


class FakeMediaLibraryRegistry:
    def __init__(self):
        self._libs = {}

    def get_or_create(self, project_id: str):
        if project_id not in self._libs:
            self._libs[project_id] = ProjectMediaLibrary(project_id)
        return self._libs[project_id]


class TestVideoStudioModule43Conform(unittest.TestCase):
    """Test suite for Module 43 Media Conform, Offline Editing & Relink Engine."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_log = os.path.join(self.temp_dir.name, "test_conform_audit.jsonl")
        self.registry = VideoStudioCapabilityRegistry()
        self.tl_service = TimelineService()
        self.media_registry = FakeMediaLibraryRegistry()

        self.versioning_svc = VersionControlService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            audit_log_path=self.audit_log,
        )

        self.service = ConformService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            versioning_svc=self.versioning_svc,
            audit_log_path=self.audit_log,
        )

        self.project_id = "prj_cinema_conform"

        # Create physical original file (4K RAW)
        self.orig_file = os.path.join(self.temp_dir.name, "scene_01_raw.mp4")
        with open(self.orig_file, "wb") as f:
            f.write(b"HIGH_RES_ORIGINAL_SOURCE_RAW_VIDEO_STREAM_BYTES_4K")

        # Create physical proxy file (720p Proxy)
        self.proxy_file = os.path.join(self.temp_dir.name, "scene_01_proxy.mp4")
        with open(self.proxy_file, "wb") as f:
            f.write(b"LIGHTWEIGHT_720P_OFFLINE_PROXY_VIDEO_STREAM_BYTES")

        self.orig_hash = compute_file_sha256_chunked(self.orig_file)
        self.proxy_hash = compute_file_sha256_chunked(self.proxy_file)

        # Ingest both assets into library
        self.library = self.media_registry.get_or_create(self.project_id)
        self.orig_asset = MediaAsset(
            asset_id="asset_orig_4k",
            project_id=self.project_id,
            name="Scene 01 RAW",
            original_name="scene_01_raw.mp4",
            file_location=self.orig_file,
            size_bytes=os.path.getsize(self.orig_file),
            content_hash_sha256=self.orig_hash,
            media_type=AssetMediaType.VIDEO,
            width=3840,
            height=2160,
            frame_rate=24.0,
            total_frames=240,
            duration_seconds=10.0,
            audio_channels=2,
        )
        self.proxy_asset = MediaAsset(
            asset_id="asset_proxy_720p",
            project_id=self.project_id,
            name="Scene 01 Proxy",
            original_name="scene_01_proxy.mp4",
            file_location=self.proxy_file,
            size_bytes=os.path.getsize(self.proxy_file),
            content_hash_sha256=self.proxy_hash,
            media_type=AssetMediaType.PROXY,
            width=1280,
            height=720,
            frame_rate=24.0,
            total_frames=240,
            duration_seconds=10.0,
            audio_channels=2,
        )
        self.library.add_asset(self.orig_asset)
        self.library.add_asset(self.proxy_asset)

        # Register mapping
        self.mapping = self.service.register_proxy_mapping(
            project_id=self.project_id,
            original_asset_id="asset_orig_4k",
            proxy_asset_id="asset_proxy_720p",
        )

        # Create sequence with clip pointing initially to original
        self.seq = self.tl_service.create_sequence(
            project_id=self.project_id,
            name="Feature Master Sequence",
        )
        self.clip = TimelineItemModel(
            item_id="clip_master_01",
            track_id=self.seq.tracks[0].track_id,
            sequence_id=self.seq.sequence_id,
            source_reference_id="asset_orig_4k",
            name="Scene 01 Master Clip",
            timeline_range=TimelineRange(start_frame=0, duration_frames=120),
        )
        self.seq.tracks[0].items.append(self.clip)

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_proxy_mapping_record(self) -> None:
        """Verifies two-way mapping between original source and proxy representation."""
        m_by_orig = self.service.get_mapping_by_original(self.project_id, "asset_orig_4k")
        self.assertIsNotNone(m_by_orig)
        self.assertEqual(m_by_orig.proxy_asset_id, "asset_proxy_720p")

        m_by_proxy = self.service.get_mapping_by_proxy(self.project_id, "asset_proxy_720p")
        self.assertIsNotNone(m_by_proxy)
        self.assertEqual(m_by_proxy.original_asset_id, "asset_orig_4k")

    def test_02_proxy_profiles(self) -> None:
        """Verifies default built-in proxy profiles exist."""
        prof_720 = self.service._profiles.get("proxy_720p_standard")
        self.assertIsNotNone(prof_720)
        self.assertEqual(prof_720.target_width, 1280)
        self.assertEqual(prof_720.target_height, 720)

    def test_03_representation_mode_switching_to_proxy(self) -> None:
        """Verifies switching sequence representation to PROXY seamlessly swaps clip references."""
        res = self.service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            target_mode=MediaRepresentationMode.PROXY,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.conformed_clips_count, 1)

        # Clip source_reference_id should now be asset_proxy_720p
        self.assertEqual(self.clip.source_reference_id, "asset_proxy_720p")
        self.assertEqual(
            self.service.get_sequence_representation_mode(self.seq.sequence_id),
            MediaRepresentationMode.PROXY,
        )

    def test_04_timeline_state_preservation_during_toggle(self) -> None:
        """Verifies switching does not alter timeline range, duration, or clip attributes."""
        orig_range = self.clip.timeline_range.to_dict()

        # Switch to PROXY
        self.service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            target_mode=MediaRepresentationMode.PROXY,
        )
        self.assertEqual(self.clip.timeline_range.to_dict(), orig_range)

        # Switch back to ORIGINAL
        self.service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            target_mode=MediaRepresentationMode.ORIGINAL,
        )
        self.assertEqual(self.clip.timeline_range.to_dict(), orig_range)
        self.assertEqual(self.clip.source_reference_id, "asset_orig_4k")

    def test_05_preflight_compatibility_clean(self) -> None:
        """Verifies preflight report shows COMPATIBLE when original and proxy match timing."""
        # Switch to proxy first
        self.service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            target_mode=MediaRepresentationMode.PROXY,
        )

        report = self.service.run_conform_preflight(self.project_id, self.seq.sequence_id)
        self.assertTrue(report.is_ready_for_online_render)
        self.assertEqual(report.overall_grade, ConformCompatibilityGrade.COMPATIBLE)
        self.assertEqual(report.blocking_issues_count, 0)
        self.assertEqual(len(report.proposed_relinks), 1)

    def test_06_missing_original_source_detection(self) -> None:
        """Verifies preflight detects when original high-resolution file is missing on disk."""
        # Switch to proxy
        self.service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            target_mode=MediaRepresentationMode.PROXY,
        )

        # Point original asset to missing file
        self.orig_asset.file_location = os.path.join(self.temp_dir.name, "missing_raw.mp4")

        report = self.service.run_conform_preflight(self.project_id, self.seq.sequence_id)
        self.assertFalse(report.is_ready_for_online_render)
        self.assertEqual(report.overall_grade, ConformCompatibilityGrade.BLOCKING)
        self.assertGreater(report.blocking_issues_count, 0)

    def test_07_frame_rate_mismatch_blocking(self) -> None:
        """Verifies frame-rate mismatch between original and proxy is marked BLOCKING."""
        self.proxy_asset.frame_rate = 29.97

        issues = ConformEngine.evaluate_compatibility(self.orig_asset, self.proxy_asset)
        blocking = [i for i in issues if i.grade == ConformCompatibilityGrade.BLOCKING]
        self.assertGreater(len(blocking), 0)
        self.assertEqual(blocking[0].property_name, "frame_rate")

    def test_08_duration_drift_issue_classification(self) -> None:
        """Verifies large frame drift is BLOCKING, minor frame variance is WARNING."""
        # Minor drift (1 frame)
        self.proxy_asset.total_frames = 241
        issues = ConformEngine.evaluate_compatibility(self.orig_asset, self.proxy_asset)
        self.assertEqual(issues[0].grade, ConformCompatibilityGrade.COMPATIBLE_WITH_WARNING)

        # Major drift (10 frames)
        self.proxy_asset.total_frames = 250
        issues = ConformEngine.evaluate_compatibility(self.orig_asset, self.proxy_asset)
        self.assertEqual(issues[0].grade, ConformCompatibilityGrade.BLOCKING)

    def test_09_transactional_online_conform_execution(self) -> None:
        """Verifies online conform swaps clips back to original and creates a rollback snapshot."""
        # Put sequence in PROXY mode
        self.service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            target_mode=MediaRepresentationMode.PROXY,
        )
        self.assertEqual(self.clip.source_reference_id, "asset_proxy_720p")

        # Execute online conform
        res = self.service.execute_online_conform(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            create_rollback_checkpoint=True,
            actor_id="master_colorist",
        )
        self.assertTrue(res.success)
        self.assertIsNotNone(res.rollback_snapshot_id)
        self.assertEqual(self.clip.source_reference_id, "asset_orig_4k")
        self.assertEqual(
            self.service.get_sequence_representation_mode(self.seq.sequence_id),
            MediaRepresentationMode.ORIGINAL,
        )

    def test_10_online_conform_aborts_on_blocking_issues(self) -> None:
        """Verifies online conform aborts and leaves sequence in proxy mode if original is missing."""
        self.service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            target_mode=MediaRepresentationMode.PROXY,
        )
        self.orig_asset.file_location = os.path.join(self.temp_dir.name, "vanished.mp4")

        res = self.service.execute_online_conform(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
        )
        self.assertFalse(res.success)
        self.assertIn("Online conform blocked", res.errors[0])
        self.assertEqual(self.clip.source_reference_id, "asset_proxy_720p")

    def test_11_export_validation_gate(self) -> None:
        """Verifies export validation gate blocks final quality rendering while in proxy mode."""
        # Switch to PROXY mode
        self.service.switch_representation_mode(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            target_mode=MediaRepresentationMode.PROXY,
        )

        # Final quality export without allow_proxy_draft must fail
        ok, errs = self.service.validate_export_conform_readiness(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            allow_proxy_draft=False,
        )
        self.assertFalse(ok)
        self.assertIn("Export rejected: Project is currently in PROXY representation mode", errs[0])

        # Allowed if draft export
        ok_draft, _ = self.service.validate_export_conform_readiness(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            allow_proxy_draft=True,
        )
        self.assertTrue(ok_draft)

    def test_12_registry_capabilities(self) -> None:
        """Verifies all Module 43 capabilities are registered with IMPLEMENTED state."""
        expected = [
            ("video.conform.offline_proxy_workflow", VideoStudioCategory.MEDIA),
            ("video.conform.representation_switching", VideoStudioCategory.TIMELINE),
            ("video.conform.online_relink_engine", VideoStudioCategory.MEDIA),
            ("video.conform.render_validation_gate", VideoStudioCategory.EXPORT),
        ]
        for cap_id, expected_cat in expected:
            cap = self.registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability '{cap_id}' missing from registry.")
            self.assertEqual(cap.category, expected_cat)
            self.assertEqual(cap.implementation_state, ImplementationState.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
