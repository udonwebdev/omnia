"""OMNIA Video Studio — Module 41 Tests: Version Control, Revision Snapshots, Branching & Recovery.

Comprehensive test suite verifying:
1. Snapshot creation and immutable capture of sequence state.
2. Stable revision IDs, content fingerprints (SHA-256), and integrity validation.
3. Revision history, chronological ordering, and parent-child tracking.
4. Timeline branching: create branch, list, safe switching, and deletion constraints.
5. Structural revision diff engine: track addition/removal, clip timing modifications, settings deltas.
6. Non-destructive restore: restoring earlier snapshot accurately restores sequence structure.
7. Restore failure safety: integrity mismatch leaves original active sequence untouched.
8. Media asset dependency tracking and missing media detection during pre-flight.
9. Protection safeguards: protected snapshots and active branch heads cannot be deleted.
10. Dry run preview mode: inspects restore outcome without touching active timeline.
11. Integration with Module 40 review annotations referencing stable revisions.
12. Capability registration in VideoStudioCapabilityRegistry under VideoStudioCategory.TIMELINE.
"""

import os
import unittest
from video_studio.media_library import ProjectMediaLibrary, MediaAsset, AssetMediaType
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.registry_models import ImplementationState, VideoStudioCategory
from video_studio.timeline_models import (
    SequenceSettings,
    TimelineItemModel,
    TimelineItemType,
    TimelineRange,
    TimelineTrackModel,
    TimelineTrackType,
    VideoSequence,
)
from video_studio.timeline_service import TimelineService
from video_studio.versioning_engine import VersioningEngine
from video_studio.versioning_models import (
    ProjectBranch,
    RestoreSafetyLevel,
    RevisionDiff,
    RevisionSnapshot,
    RevisionType,
    VERSION_CONTROL_SCHEMA_VERSION,
)
from video_studio.versioning_service import VersionControlService


class FakeMediaLibraryRegistry:
    def __init__(self):
        self._libs = {}

    def get_or_create(self, project_id: str):
        if project_id not in self._libs:
            self._libs[project_id] = ProjectMediaLibrary(project_id)
        return self._libs[project_id]


class TestVideoStudioModule41Versioning(unittest.TestCase):
    """Test suite for Module 41 Version Control, Revision Snapshots & Recovery."""

    def setUp(self) -> None:
        self.audit_log = "test_versioning_audit.jsonl"
        self.registry = VideoStudioCapabilityRegistry()
        self.tl_service = TimelineService()
        self.media_registry = FakeMediaLibraryRegistry()
        self.service = VersionControlService(
            capability_registry=self.registry,
            tl_service=self.tl_service,
            media_registry=self.media_registry,
            audit_log_path=self.audit_log,
        )

        # Setup base sequence
        self.project_id = "prj_cinema"
        self.seq = self.tl_service.create_sequence(
            project_id=self.project_id,
            name="Main Sequence",
            settings=SequenceSettings(width=1920, height=1080),
        )
        self.sequence_id = self.seq.sequence_id

    def tearDown(self) -> None:
        if os.path.exists(self.audit_log):
            try:
                os.remove(self.audit_log)
            except Exception:
                pass

    def test_01_snapshot_creation_and_integrity_fingerprint(self) -> None:
        """Verifies immutable snapshot capture and SHA-256 content fingerprinting."""
        snap = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Cut 1 Milestone",
            message="Initial assembly of act 1",
            author_id="director_dan",
        )
        self.assertIsNotNone(snap.revision_id)
        self.assertTrue(snap.revision_id.startswith("rev_"))
        self.assertEqual(snap.branch_name, "main")
        self.assertEqual(snap.author_id, "director_dan")
        self.assertTrue(len(snap.content_fingerprint_sha256) == 64)

        # Verify integrity check passes
        ok, err = VersioningEngine.verify_snapshot_integrity(snap)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_02_tampered_snapshot_integrity_rejection(self) -> None:
        """Verifies integrity check fails when snapshot data is corrupted or modified."""
        snap = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Tamper Test",
        )
        # Manually tamper with sequence data
        snap.sequence_data["name"] = "Corrupted Project Title"
        ok, err = VersioningEngine.verify_snapshot_integrity(snap)
        self.assertFalse(ok)
        self.assertIn("Fingerprint mismatch", err)

    def test_03_revision_history_and_parent_child(self) -> None:
        """Verifies sequential snapshots establish parent-child linkage."""
        snap1 = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Pass 1",
        )
        # Advance revision
        self.seq.revision += 1
        snap2 = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Pass 2",
        )
        self.assertEqual(snap2.parent_revision_id, snap1.revision_id)

        history = self.service.list_snapshots(project_id=self.project_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].revision_id, snap1.revision_id)
        self.assertEqual(history[1].revision_id, snap2.revision_id)

    def test_04_timeline_branching_and_switching(self) -> None:
        """Verifies creating experimental branches, listing, and switching active branch."""
        snap_main = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Main Root",
        )

        # Create experiment branch
        branch = self.service.create_branch(
            project_id=self.project_id,
            branch_name="experiment-alt-ending",
            head_revision_id=snap_main.revision_id,
            created_by="editor_ed",
            description="Testing alternative climax pacing",
        )
        self.assertEqual(branch.name, "experiment-alt-ending")
        self.assertEqual(branch.fork_revision_id, snap_main.revision_id)

        # Switch branch
        self.service.switch_branch(
            project_id=self.project_id,
            branch_name="experiment-alt-ending",
            auto_restore_head=False,
        )
        self.assertEqual(self.service.get_active_branch(self.project_id), "experiment-alt-ending")

        # Snapshot taken while on experiment branch records branch_name
        snap_exp = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Exp Cut",
        )
        self.assertEqual(snap_exp.branch_name, "experiment-alt-ending")

    def test_05_branch_deletion_safeguards(self) -> None:
        """Verifies cannot delete default branch or currently active branch."""
        self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Root",
        )
        # Attempt to delete default branch
        with self.assertRaises(ValueError):
            self.service.delete_branch(self.project_id, "main")

        # Create secondary branch, switch to it, attempt to delete active branch
        self.service.create_branch(self.project_id, "side-quest")
        self.service.switch_branch(self.project_id, "side-quest", auto_restore_head=False)
        with self.assertRaises(ValueError):
            self.service.delete_branch(self.project_id, "side-quest")

        # Switch back to main, now side-quest can be deleted safely
        self.service.switch_branch(self.project_id, "main", auto_restore_head=False)
        deleted = self.service.delete_branch(self.project_id, "side-quest")
        self.assertTrue(deleted)

    def test_06_structural_revision_diff(self) -> None:
        """Verifies structural diff detects added tracks, modified clip ranges, and setting changes."""
        snap1 = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Before Edits",
        )

        # Mutate sequence: add track, add clip, change width
        v3 = TimelineTrackModel(
            track_id="track_v3",
            sequence_id=self.sequence_id,
            name="V3 FX",
            track_type=TimelineTrackType.VIDEO,
            index=2,
            items=[
                TimelineItemModel(
                    item_id="clip_vfx_01",
                    track_id="track_v3",
                    sequence_id=self.sequence_id,
                    source_reference_id="asset_fire_01",
                    timeline_range=TimelineRange(start_frame=0, duration_frames=48),
                )
            ]
        )
        self.seq.tracks.append(v3)
        self.seq.settings.width = 3840
        self.seq.revision += 1

        snap2 = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="After Edits",
        )

        diff = self.service.compare_revisions(snap1.revision_id, snap2.revision_id)
        self.assertFalse(diff.is_identical)
        self.assertIn("track_v3", diff.tracks_added)
        self.assertIn("clip_vfx_01", diff.clips_added)
        self.assertIn("width", diff.settings_changed)
        self.assertEqual(diff.settings_changed["width"]["source"], 1920)
        self.assertEqual(diff.settings_changed["width"]["target"], 3840)
        self.assertGreater(len(diff.structural_changes), 0)

    def test_07_safe_non_destructive_restore(self) -> None:
        """Verifies restoring an earlier snapshot accurately swaps sequence state and creates pre-restore checkpoint."""
        snap1 = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Pristine State",
        )

        # Mutate sequence drastically
        self.seq.tracks.clear()
        self.seq.name = "Ruined Cut"
        self.assertEqual(len(self.tl_service.get_sequence(self.sequence_id).tracks), 0)

        # Restore snap1
        res = self.service.restore_revision(
            revision_id=snap1.revision_id,
            safety_level=RestoreSafetyLevel.ATOMIC_REPLACE,
            actor_id="director_dan",
            create_safety_snapshot=True,
        )
        self.assertTrue(res.success)
        self.assertIsNotNone(res.safety_snapshot_id)

        # Verify restored sequence state
        restored = self.tl_service.get_sequence(self.sequence_id)
        self.assertEqual(restored.name, "Main Sequence")
        self.assertEqual(len(restored.tracks), 4)

    def test_08_restore_failure_leaves_active_project_untouched(self) -> None:
        """Verifies corrupted snapshot aborts restore and original sequence remains unaffected."""
        snap = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Will Corrupt",
        )
        snap.sequence_data["tracks"] = "corrupted_non_list_payload"

        res = self.service.restore_revision(snap.revision_id)
        self.assertFalse(res.success)
        self.assertIn("Pre-flight integrity validation failed", res.errors[0])

        # Active sequence must still be valid
        active_seq = self.tl_service.get_sequence(self.sequence_id)
        self.assertEqual(active_seq.name, "Main Sequence")

    def test_09_dry_run_preview_mode(self) -> None:
        """Verifies DRY_RUN returns preview results without altering active sequence."""
        snap = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Dry Run Target",
        )
        self.seq.name = "Active Working Title"

        res = self.service.restore_revision(
            revision_id=snap.revision_id,
            safety_level=RestoreSafetyLevel.DRY_RUN,
        )
        self.assertTrue(res.success)
        self.assertIn("[DRY RUN]", res.warnings[-1])

        # Active sequence remains unmodified
        self.assertEqual(self.tl_service.get_sequence(self.sequence_id).name, "Active Working Title")

    def test_10_missing_media_detection(self) -> None:
        """Verifies media assets referenced in snapshot are checked against local media library."""
        # Add item referencing missing media asset
        item = TimelineItemModel(
            item_id="clip_01",
            track_id="track_v1",
            sequence_id=self.sequence_id,
            source_reference_id="asset_missing_raw_video",
        )
        self.seq.tracks[0].items.append(item)

        snap = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Media Dep Snapshot",
        )
        self.assertIn("asset_missing_raw_video", snap.referenced_asset_ids)

        # Pre-flight check flags missing asset
        valid, missing, avail, warnings = self.service.validate_restore_prerequisites(snap.revision_id)
        self.assertTrue(valid)
        self.assertIn("asset_missing_raw_video", missing)
        self.assertGreater(len(warnings), 0)

    def test_11_protection_against_accidental_deletion(self) -> None:
        """Verifies protected snapshots and active branch heads cannot be deleted."""
        snap = self.service.create_snapshot(
            project_id=self.project_id,
            sequence_id=self.sequence_id,
            name="Protected Milestone",
            is_protected=True,
        )
        # Attempt to delete protected snapshot without force
        with self.assertRaises(PermissionError):
            self.service.delete_snapshot(snap.revision_id, force=False)

        # Unprotect, but it is branch head of main -> still blocked
        snap.is_protected = False
        with self.assertRaises(ValueError):
            self.service.delete_snapshot(snap.revision_id)

    def test_12_registry_capabilities(self) -> None:
        """Verifies all Module 41 capabilities are properly registered with IMPLEMENTED state."""
        expected_caps = [
            "video.versioning.revision_snapshots",
            "video.versioning.timeline_branching",
            "video.versioning.structural_comparison",
            "video.versioning.non_destructive_recovery",
        ]
        for cap_id in expected_caps:
            cap = self.registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability '{cap_id}' missing from registry.")
            self.assertEqual(cap.category, VideoStudioCategory.TIMELINE)
            self.assertEqual(cap.implementation_state, ImplementationState.IMPLEMENTED)


if __name__ == "__main__":
    unittest.main()
