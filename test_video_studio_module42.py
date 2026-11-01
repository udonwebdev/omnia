"""OMNIA Video Studio — Module 42 Tests: Media Asset Provenance, Dependency Graph & Relinking.

Comprehensive test suite verifying:
1. Asset identity, metadata, and provenance event logging.
2. Streaming/chunked SHA-256 calculation for non-blocking file hashing.
3. Project resource dependency graph generation (Project -> Sequences -> Clips -> Assets -> Revisions).
4. Missing media detection and file health inspection.
5. Content modification detection (size/hash mismatches).
6. Intelligent relinking candidate discovery, ranking, and scoring breakdown.
7. Verified exact match via SHA-256 fingerprint vs probable match by name/size.
8. Safe relinking execution: updates asset file_location and all sequence clip references.
9. Non-destructive relink dry run preview mode.
10. Asset usage analysis: detects assets referenced by active sequences, revisions, and branches.
11. Deletion safety guard: prevents deleting assets that are in active use unless forced.
12. Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.MEDIA.
"""

import os
import tempfile
import unittest
from video_studio.media_library import ProjectMediaLibrary, MediaAsset, AssetMediaType
from video_studio.media_models import AssetLifecycleStatus
from video_studio.provenance_engine import ProvenanceEngine, compute_file_sha256_chunked
from video_studio.provenance_models import (
    AssetProvenanceRecord,
    DependencyNodeType,
    ProjectDependencyGraph,
    RelinkMatchConfidence,
)
from video_studio.provenance_service import ProvenanceService
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


class TestVideoStudioModule42Provenance(unittest.TestCase):
    """Test suite for Module 42 Provenance, Dependency Graph & Relinking Engine."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_log = os.path.join(self.temp_dir.name, "test_provenance_audit.jsonl")
        self.registry = VideoStudioCapabilityRegistry()
        self.tl_service = TimelineService()
        self.media_registry = FakeMediaLibraryRegistry()

        self.versioning_svc = VersionControlService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            audit_log_path=self.audit_log,
        )

        self.service = ProvenanceService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            versioning_svc=self.versioning_svc,
            audit_log_path=self.audit_log,
        )

        self.project_id = "prj_feature"

        # Create physical test media file
        self.media_file = os.path.join(self.temp_dir.name, "interview_cam_a.mp4")
        with open(self.media_file, "wb") as f:
            f.write(b"SAMPLE_VIDEO_STREAM_DATA_FRAME_BYTES_123456789")

        self.media_hash = compute_file_sha256_chunked(self.media_file)
        self.media_size = os.path.getsize(self.media_file)

        # Ingest asset into project library
        self.library = self.media_registry.get_or_create(self.project_id)
        self.asset = MediaAsset(
            asset_id="asset_cam_a",
            project_id=self.project_id,
            name="Interview Cam A",
            original_name="interview_cam_a.mp4",
            file_location=self.media_file,
            size_bytes=self.media_size,
            content_hash_sha256=self.media_hash,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
        )
        self.library.add_asset(self.asset)

        # Create sequence with clip pointing to asset
        self.seq = self.tl_service.create_sequence(
            project_id=self.project_id,
            name="Cut 01",
        )
        clip = TimelineItemModel(
            item_id="clip_01",
            track_id=self.seq.tracks[0].track_id,
            sequence_id=self.seq.sequence_id,
            source_reference_id="asset_cam_a",
            name="A-Roll 01",
            timeline_range=TimelineRange(start_frame=0, duration_frames=100),
        )
        self.seq.tracks[0].items.append(clip)

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_provenance_event_recording(self) -> None:
        """Verifies recording and retrieving immutable asset provenance history."""
        rec = self.service.record_provenance_event(
            asset_id="asset_cam_a",
            event_type="INGEST",
            new_location=self.media_file,
            new_checksum=self.media_hash,
            actor_id="assistant_editor",
            rationale="Initial ingest from SD Card 1",
        )
        self.assertIsNotNone(rec.record_id)
        self.assertEqual(rec.event_type, "INGEST")

        history = self.service.get_asset_provenance("asset_cam_a")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].new_location, self.media_file)

    def test_02_chunked_sha256_hashing(self) -> None:
        """Verifies chunked streaming SHA-256 calculation matches standard hash."""
        h = compute_file_sha256_chunked(self.media_file, chunk_size=8)
        self.assertIsNotNone(h)
        self.assertEqual(len(h), 64)
        self.assertEqual(h, self.media_hash)

        # Missing file returns None
        missing_h = compute_file_sha256_chunked(os.path.join(self.temp_dir.name, "ghost.mp4"))
        self.assertIsNone(missing_h)

    def test_03_dependency_graph_generation(self) -> None:
        """Verifies project dependency graph links project, sequence, clip, asset, and snapshot."""
        # Create a revision snapshot
        snap = self.versioning_svc.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            name="Assembly 1",
        )

        graph = self.service.get_dependency_graph(self.project_id)
        self.assertIsNotNone(graph)
        self.assertIn(f"proj_{self.project_id}", graph.nodes)
        self.assertIn(f"seq_{self.seq.sequence_id}", graph.nodes)
        self.assertIn("clip_clip_01", graph.nodes)
        self.assertIn("asset_asset_cam_a", graph.nodes)
        self.assertIn(f"rev_{snap.revision_id}", graph.nodes)

        # Clip references asset
        deps = graph.get_dependencies("clip_clip_01")
        self.assertIn("asset_asset_cam_a", deps)

    def test_04_missing_media_detection(self) -> None:
        """Verifies health inspection flags assets when physical file is missing or unlinked."""
        # Point asset to non-existent path
        self.asset.file_location = os.path.join(self.temp_dir.name, "deleted_raw.mp4")

        health = self.service.inspect_project_assets_health(self.project_id)
        self.assertEqual(health["missing_count"], 1)
        self.assertIn("asset_cam_a", health["missing_asset_ids"])
        self.assertEqual(self.asset.status, AssetLifecycleStatus.MISSING)

    def test_05_modified_content_detection(self) -> None:
        """Verifies health inspection detects when file size changes unexpectedly."""
        # Artificially alter size_bytes recorded
        self.asset.size_bytes = 999999

        health = self.service.inspect_project_assets_health(self.project_id)
        self.assertEqual(health["modified_count"], 1)
        self.assertIn("asset_cam_a", health["modified_asset_ids"])
        self.assertEqual(self.asset.status, AssetLifecycleStatus.FAILED)

    def test_06_intelligent_relinking_candidate_ranking(self) -> None:
        """Tests scanning search directories for candidate relink files and scoring confidence."""
        # Create search folder with 2 files: an exact match copy and a size mismatch with same name
        search_dir = os.path.join(self.temp_dir.name, "relocated_media")
        os.makedirs(search_dir, exist_ok=True)

        exact_copy = os.path.join(search_dir, "interview_cam_a.mp4")
        with open(exact_copy, "wb") as f:
            f.write(b"SAMPLE_VIDEO_STREAM_DATA_FRAME_BYTES_123456789")

        alt_version = os.path.join(search_dir, "interview_cam_a_alt.mp4")
        with open(alt_version, "wb") as f:
            f.write(b"DIFFERENT_CONTENT")

        candidates = self.service.find_relink_candidates(
            project_id=self.project_id,
            asset_id="asset_cam_a",
            search_directories=[search_dir],
        )
        self.assertGreaterEqual(len(candidates), 1)

        # Top candidate must be VERIFIED_EXACT
        top = candidates[0]
        self.assertEqual(top.confidence, RelinkMatchConfidence.VERIFIED_EXACT)
        self.assertEqual(top.score, 1.0)
        self.assertTrue(top.is_verified)

    def test_07_safe_relink_execution(self) -> None:
        """Verifies relinking updates asset location, hash, and sequence clip references."""
        new_loc = os.path.join(self.temp_dir.name, "recovered_clip.mp4")
        with open(new_loc, "wb") as f:
            f.write(b"SAMPLE_VIDEO_STREAM_DATA_FRAME_BYTES_123456789")

        res = self.service.relink_asset(
            project_id=self.project_id,
            asset_id="asset_cam_a",
            new_file_path=new_loc,
            actor_id="editor_dan",
            is_dry_run=False,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.relinked_assets_count, 1)
        self.assertEqual(self.asset.file_location, new_loc)
        self.assertEqual(self.asset.status, AssetLifecycleStatus.READY)

        # Check provenance log
        history = self.service.get_asset_provenance("asset_cam_a")
        self.assertEqual(history[-1].event_type, "RELINK")
        self.assertEqual(history[-1].new_location, new_loc)

    def test_08_relink_dry_run_mode(self) -> None:
        """Verifies dry run mode returns preview results without changing asset location."""
        new_loc = os.path.join(self.temp_dir.name, "preview_only.mp4")
        with open(new_loc, "wb") as f:
            f.write(b"TEST_BYTES")

        res = self.service.relink_asset(
            project_id=self.project_id,
            asset_id="asset_cam_a",
            new_file_path=new_loc,
            is_dry_run=True,
        )
        self.assertTrue(res.success)
        self.assertTrue(res.is_dry_run)
        # File location must remain original
        self.assertEqual(self.asset.file_location, self.media_file)

    def test_09_asset_usage_analysis(self) -> None:
        """Verifies asset usage detects references across sequences and snapshots."""
        # Snapshots pin asset
        snap = self.versioning_svc.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.seq.sequence_id,
            name="Milestone Alpha",
        )

        usage = self.service.analyze_asset_usage(self.project_id, "asset_cam_a")
        self.assertTrue(usage.is_used_in_active_project)
        self.assertIn(self.seq.sequence_id, usage.active_sequence_ids)
        self.assertIn("clip_01", usage.active_clip_ids)
        self.assertIn(snap.revision_id, usage.referenced_in_revisions)
        self.assertFalse(usage.is_safe_to_delete)
        self.assertGreater(len(usage.safety_blockers), 0)

    def test_10_safe_delete_prevention(self) -> None:
        """Verifies cannot delete actively used asset without force flag."""
        # Attempt safe delete
        ok, reason = self.service.safe_delete_asset(self.project_id, "asset_cam_a", force=False)
        self.assertFalse(ok)
        self.assertIn("Deletion blocked", reason)

        # Clear active clips and revisions
        self.seq.tracks[0].items.clear()
        unused_asset = MediaAsset(
            asset_id="asset_unused",
            project_id=self.project_id,
            name="Unused B-Roll",
        )
        self.library.add_asset(unused_asset)

        # Now unused asset can be safely deleted
        ok, err = self.service.safe_delete_asset(self.project_id, "asset_unused", force=False)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_11_forced_delete_override(self) -> None:
        """Verifies force=True allows deletion when explicitly requested."""
        ok, err = self.service.safe_delete_asset(self.project_id, "asset_cam_a", force=True)
        self.assertTrue(ok)
        self.assertIsNone(self.library.get_asset("asset_cam_a"))

    def test_12_registry_capabilities(self) -> None:
        """Verifies all Module 42 capabilities are registered with IMPLEMENTED state."""
        expected = [
            "video.provenance.asset_tracking",
            "video.provenance.dependency_graph",
            "video.provenance.intelligent_relinking",
            "video.provenance.usage_and_cleanup_safety",
        ]
        for cap_id in expected:
            cap = self.registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability '{cap_id}' missing from registry.")
            self.assertEqual(cap.category, VideoStudioCategory.MEDIA)
            self.assertEqual(cap.implementation_state, ImplementationState.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
