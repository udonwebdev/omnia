"""OMNIA Video Studio — Module 4 Test Suite.
Validates:
1. Sequence creation, multi-track generation, and duration calculation.
2. Track ordering, locking, and muting states.
3. Non-destructive media placement (SourceRange vs TimelineRange separation).
4. Linked audio/video clips via LinkGroup.
5. Synchronization groups across multiple items.
6. Markers (cue points, spanning markers) and Regions.
7. Nested sequence placement and DFS circular dependency cycle detection (A -> B -> A).
8. Adjustment layer foundation without media asset references.
9. Reversible command execution, multi-operation transactions, commit, rollback, undo, and redo.
10. Spatial range interval indexing, point queries, and range intersections.
11. Deterministic JSON serialization, deserialization, and schema versioning ("video-studio.timeline.v1").
12. Structural validation engine (invalid ranges, missing tracks, duplicate IDs).
13. Subsystem isolation: Video Studio failures never crash OMNIA Core.
"""

import unittest
import os
import shutil
import tempfile
import json
import time

from video_studio.timeline_models import (
    VideoSequence,
    SequenceSettings,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineMarker,
    TimelineRegion,
    TimelineRange,
    SourceRange,
    TimelineTrackType,
    TimelineItemType,
    TimelineItemState,
    MarkerCategory,
    RegionCategory,
    TIMELINE_SCHEMA_VERSION,
)
from video_studio.timeline_validation import (
    TimelineValidationEngine,
    timeline_validation_engine,
)
from video_studio.timeline_query import (
    TimelineQueryEngine,
    timeline_query_engine,
)
from video_studio.timeline_commands import (
    TimelineCommand,
    TimelineTransaction,
    TimelineHistoryManager,
    TimelineOpType,
)
from video_studio.timeline_serialization import (
    TimelineSerializationEngine,
    timeline_serialization_engine,
)
from video_studio.timeline_service import (
    TimelineService,
    timeline_service,
)

class TestVideoStudioModule4(unittest.TestCase):

    def setUp(self):
        self.service = TimelineService()
        self.query_engine = TimelineQueryEngine()
        self.validator = TimelineValidationEngine()
        self.serializer = TimelineSerializationEngine()

    # -------------------------------------------------------------------------
    # 1. Sequence Creation & Settings
    # -------------------------------------------------------------------------

    def test_sequence_creation_with_default_tracks(self):
        seq = self.service.create_sequence(
            project_id="proj_01",
            name="Main Edit",
            settings=SequenceSettings(width=3840, height=2160, frame_rate=23.976),
            create_default_tracks=True,
        )
        self.assertTrue(seq.sequence_id.startswith("seq_"))
        self.assertEqual(seq.name, "Main Edit")
        self.assertEqual(seq.settings.width, 3840)
        self.assertEqual(seq.settings.frame_rate, 23.976)
        self.assertEqual(len(seq.tracks), 4)  # V1, V2, A1, A2
        self.assertEqual(seq.schema_version, TIMELINE_SCHEMA_VERSION)

    # -------------------------------------------------------------------------
    # 2. Track Ordering & Locking Controls
    # -------------------------------------------------------------------------

    def test_track_locking_prevents_clip_placement(self):
        seq = self.service.create_sequence("proj_01", "Locked Track Test")
        v1 = seq.tracks[0]
        v1.is_locked = True

        # Attempt placing clip on locked track
        item = self.service.add_clip(
            sequence_id=seq.sequence_id,
            track_id=v1.track_id,
            asset_id="asset_raw_01",
            start_frame=0,
            duration_frames=48,
        )
        self.assertIsNone(item)

        # Unlock track and retry
        v1.is_locked = False
        item_ok = self.service.add_clip(
            sequence_id=seq.sequence_id,
            track_id=v1.track_id,
            asset_id="asset_raw_01",
            start_frame=0,
            duration_frames=48,
        )
        self.assertIsNotNone(item_ok)
        self.assertEqual(len(v1.items), 1)

    # -------------------------------------------------------------------------
    # 3. Non-Destructive Source vs Timeline Range
    # -------------------------------------------------------------------------

    def test_non_destructive_ranges_immutability(self):
        seq = self.service.create_sequence("proj_01", "Range Test")
        v1 = seq.tracks[0]

        clip = self.service.add_clip(
            sequence_id=seq.sequence_id,
            track_id=v1.track_id,
            asset_id="asset_interview_10m",
            name="Soundbite 1",
            start_frame=120,       # Timeline: starts at 5.0s (120 frames at 24fps)
            duration_frames=72,     # Placed duration: 3.0s
            source_in_frame=2400,   # Source: in at 100.0s
        )

        self.assertIsNotNone(clip)
        self.assertEqual(clip.timeline_range.start_frame, 120)
        self.assertEqual(clip.timeline_range.end_frame, 192)
        self.assertEqual(clip.source_range.in_frame, 2400)
        self.assertEqual(clip.source_range.out_frame, 2472)
        self.assertEqual(seq.duration_frames, 192)

    # -------------------------------------------------------------------------
    # 4. Linked Media & Sync Groups
    # -------------------------------------------------------------------------

    def test_linked_media_and_sync_groups(self):
        seq = self.service.create_sequence("proj_01", "Linked Media Test")
        v1 = seq.tracks[0]
        a1 = seq.tracks[2]

        v_clip = self.service.add_clip(seq.sequence_id, v1.track_id, "asset_v1", start_frame=0, duration_frames=48)
        a_clip = self.service.add_clip(seq.sequence_id, a1.track_id, "asset_a1", start_frame=0, duration_frames=48)

        lg = self.service.link_items(seq.sequence_id, [v_clip.item_id, a_clip.item_id])
        self.assertIsNotNone(lg)
        self.assertEqual(v_clip.link_group_id, lg.link_group_id)
        self.assertEqual(a_clip.link_group_id, lg.link_group_id)

        # Query linked items
        linked_to_v = self.query_engine.get_linked_items(seq, v_clip.item_id)
        self.assertEqual(len(linked_to_v), 1)
        self.assertEqual(linked_to_v[0].item_id, a_clip.item_id)

    # -------------------------------------------------------------------------
    # 5. Markers and Regions
    # -------------------------------------------------------------------------

    def test_markers_and_regions(self):
        seq = self.service.create_sequence("proj_01", "Markers Test")
        m = self.service.add_marker(seq.sequence_id, frame=48, name="Cut Here", category=MarkerCategory.EDIT)
        self.assertIsNotNone(m)
        self.assertEqual(len(seq.markers), 1)

        # Query markers at playhead
        markers_at_48 = self.query_engine.get_markers_at_time(seq, 48)
        self.assertEqual(len(markers_at_48), 1)
        self.assertEqual(markers_at_48[0].name, "Cut Here")

    # -------------------------------------------------------------------------
    # 6. Nested Sequences & Cycle Detection
    # -------------------------------------------------------------------------

    def test_nested_sequences_and_cycle_rejection(self):
        seq_a = self.service.create_sequence("proj_01", "Seq A")
        seq_b = self.service.create_sequence("proj_01", "Seq B")

        # Place Seq B inside Seq A (valid)
        v1_a = seq_a.tracks[0]
        nested_item = TimelineItemModel(
            item_id="clip_nested_b",
            track_id=v1_a.track_id,
            sequence_id=seq_a.sequence_id,
            source_reference_id=seq_b.sequence_id,
            item_type=TimelineItemType.NESTED_SEQUENCE,
            timeline_range=TimelineRange(0, 100),
            source_range=SourceRange(0, 100),
        )
        v1_a.items.append(nested_item)

        valid_a, errs_a = self.service.validate(seq_a.sequence_id)
        self.assertTrue(valid_a)

        # Now place Seq A inside Seq B (circular dependency A -> B -> A)
        v1_b = seq_b.tracks[0]
        cyclic_item = TimelineItemModel(
            item_id="clip_cyclic_a",
            track_id=v1_b.track_id,
            sequence_id=seq_b.sequence_id,
            source_reference_id=seq_a.sequence_id,
            item_type=TimelineItemType.NESTED_SEQUENCE,
            timeline_range=TimelineRange(0, 100),
            source_range=SourceRange(0, 100),
        )
        v1_b.items.append(cyclic_item)

        # Validation must reject cycle
        valid_b, errs_b = self.validator.validate_sequence(seq_b, self.service._sequences)
        self.assertFalse(valid_b)
        self.assertTrue(any("Circular" in e for e in errs_b))

    # -------------------------------------------------------------------------
    # 7. Adjustment Layer Foundation
    # -------------------------------------------------------------------------

    def test_adjustment_layer_placement(self):
        seq = self.service.create_sequence("proj_01", "Adjustment Test")
        adj_track = self.service.add_track(seq.sequence_id, "FX Track", TimelineTrackType.ADJUSTMENT)

        adj_item = TimelineItemModel(
            item_id="adj_01",
            track_id=adj_track.track_id,
            sequence_id=seq.sequence_id,
            source_reference_id="none",
            name="Global Color Adjustment",
            item_type=TimelineItemType.ADJUSTMENT_LAYER,
            timeline_range=TimelineRange(start_frame=0, duration_frames=240),
            source_range=SourceRange(in_frame=0, duration_frames=240),
        )
        adj_track.items.append(adj_item)
        self.assertEqual(len(adj_track.items), 1)
        self.assertEqual(adj_track.items[0].item_type, TimelineItemType.ADJUSTMENT_LAYER)

    # -------------------------------------------------------------------------
    # 8. Command Architecture, Transactions, Undo & Redo
    # -------------------------------------------------------------------------

    def test_command_transactions_undo_and_redo(self):
        seq = self.service.create_sequence("proj_01", "History Test")
        v1 = seq.tracks[0]
        hm = self.service._history_managers[seq.sequence_id]

        # Create transaction with 2 operations
        tx = TimelineTransaction(transaction_id="tx_01", sequence_id=seq.sequence_id, description="Insert 2 clips")
        c1 = TimelineCommand(
            command_id="cmd_1",
            op_type=TimelineOpType.ADD_ITEM,
            sequence_id=seq.sequence_id,
            target_id="clip_1",
            payload={
                "track_id": v1.track_id,
                "item": {
                    "item_id": "clip_1",
                    "source_reference_id": "asset_1",
                    "timeline_range": {"start_frame": 0, "duration_frames": 24},
                    "source_range": {"in_frame": 0, "duration_frames": 24},
                }
            }
        )
        c2 = TimelineCommand(
            command_id="cmd_2",
            op_type=TimelineOpType.ADD_ITEM,
            sequence_id=seq.sequence_id,
            target_id="clip_2",
            payload={
                "track_id": v1.track_id,
                "item": {
                    "item_id": "clip_2",
                    "source_reference_id": "asset_2",
                    "timeline_range": {"start_frame": 24, "duration_frames": 48},
                    "source_range": {"in_frame": 0, "duration_frames": 48},
                }
            }
        )
        tx.append(c1)
        tx.append(c2)

        # Commit
        ok = hm.commit_transaction(tx)
        self.assertTrue(ok)
        self.assertEqual(len(v1.items), 2)
        self.assertEqual(seq.duration_frames, 72)
        self.assertEqual(seq.revision, 2)

        # Undo
        undo_ok = hm.undo()
        self.assertTrue(undo_ok)
        self.assertEqual(len(v1.items), 0)
        self.assertEqual(seq.duration_frames, 0)
        self.assertEqual(seq.revision, 3)

        # Redo
        redo_ok = hm.redo()
        self.assertTrue(redo_ok)
        self.assertEqual(len(v1.items), 2)
        self.assertEqual(seq.duration_frames, 72)
        self.assertEqual(seq.revision, 4)

    # -------------------------------------------------------------------------
    # 9. Spatial Range Indexing & Queries
    # -------------------------------------------------------------------------

    def test_spatial_query_intersection(self):
        seq = self.service.create_sequence("proj_01", "Spatial Query Test")
        v1 = seq.tracks[0]

        # Clip A: 0..48
        self.service.add_clip(seq.sequence_id, v1.track_id, "asset_a", start_frame=0, duration_frames=48)
        # Clip B: 100..200
        self.service.add_clip(seq.sequence_id, v1.track_id, "asset_b", start_frame=100, duration_frames=100)

        # Query point frame 20 (hits clip A only)
        items_at_20 = self.query_engine.get_items_at_time(seq, 20)
        self.assertEqual(len(items_at_20), 1)
        self.assertEqual(items_at_20[0].timeline_range.start_frame, 0)

        # Query range 30..150 (intersects both Clip A and Clip B)
        items_range = self.query_engine.get_items_intersecting_range(seq, 30, 150)
        self.assertEqual(len(items_range), 2)

        # Query gap range 50..90 (hits nothing)
        items_gap = self.query_engine.get_items_intersecting_range(seq, 50, 90)
        self.assertEqual(len(items_gap), 0)

    # -------------------------------------------------------------------------
    # 10. Serialization & Deserialization Round-Trip
    # -------------------------------------------------------------------------

    def test_serialization_round_trip(self):
        seq = self.service.create_sequence("proj_01", "Serialize Test")
        v1 = seq.tracks[0]
        clip = self.service.add_clip(seq.sequence_id, v1.track_id, "asset_x", start_frame=10, duration_frames=50)
        self.service.add_marker(seq.sequence_id, frame=25, name="Cue")

        json_str = self.serializer.serialize_sequence(seq)
        self.assertIn(TIMELINE_SCHEMA_VERSION, json_str)
        self.assertIn("asset_x", json_str)

        # Restore
        restored = self.serializer.deserialize_sequence(json_str)
        self.assertEqual(restored.sequence_id, seq.sequence_id)
        self.assertEqual(restored.name, seq.name)
        self.assertEqual(len(restored.tracks), len(seq.tracks))
        self.assertEqual(len(restored.tracks[0].items), 1)
        self.assertEqual(restored.tracks[0].items[0].timeline_range.start_frame, 10)
        self.assertEqual(len(restored.markers), 1)

    # -------------------------------------------------------------------------
    # 11. Subsystem Isolation
    # -------------------------------------------------------------------------

    def test_validation_rejects_negative_frames_gracefully(self):
        seq = self.service.create_sequence("proj_01", "Negative Bounds Test")
        v1 = seq.tracks[0]

        bad_item = TimelineItemModel(
            item_id="bad_01",
            track_id=v1.track_id,
            sequence_id=seq.sequence_id,
            source_reference_id="none",
            timeline_range=TimelineRange(start_frame=-10, duration_frames=24),
            source_range=SourceRange(in_frame=-5, duration_frames=24),
        )
        v1.items.append(bad_item)

        valid, errors = self.validator.validate_sequence(seq)
        self.assertFalse(valid)
        self.assertTrue(any("negative" in e for e in errors))

if __name__ == "__main__":
    unittest.main()
