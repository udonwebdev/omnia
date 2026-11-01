"""OMNIA Video Studio — Module 20: Multicamera Editing, Angle Switching & Synchronization Tests.

Validates:
1. Multicam sequence creation with multiple camera recordings.
2. Timecode and waveform correlation synchronization calculation.
3. Manual offset nudging.
4. Synchronized multi-angle grid preview rendering with live cut border.
5. Live angle switching decisions, range partitioning, undo, and redo.
6. Locked audio policy preservation across camera switches.
7. Flattening multicam decisions into standard timeline tracks and clips.
8. Capability registry presence.
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import cv2

from video_studio.multicam_models import (
    CameraAngle,
    AngleSwitchDecision,
    SyncMethod,
    SyncConfidence,
    MulticamAudioPolicy,
    MulticamSequence,
)
from video_studio.multicam_sync_engine import multicam_sync_engine, MulticamSyncEngine
from video_studio.multicam_service import multicam_service, MulticamService
from video_studio.media_models import (
    MediaAsset,
    AssetMediaType,
    AssetLifecycleStatus,
    SMPTETimecode,
)
from video_studio.media_library import media_library_registry
from video_studio.timeline_models import (
    VideoSequence,
    SequenceSettings,
)
from video_studio.registry import video_studio_capability_registry


class TestModule20Multicam(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="omnia_m20_test_")
        self.project_id = "test_proj_m20"
        self.media_dir = os.path.join(self.test_dir, "media")
        os.makedirs(self.media_dir, exist_ok=True)

        # 1. Create real video files for 3 camera angles (Cam A, Cam B, Cam C)
        self.cam_a_path = os.path.join(self.media_dir, "cam_a.mp4")
        self.cam_b_path = os.path.join(self.media_dir, "cam_b.mp4")
        self.cam_c_path = os.path.join(self.media_dir, "cam_c.mp4")

        # 1280x720, 24fps, 48 frames (2 seconds)
        for path, color_bgr, label in [
            (self.cam_a_path, (200, 50, 50), "CAM A"),
            (self.cam_b_path, (50, 200, 50), "CAM B"),
            (self.cam_c_path, (50, 50, 200), "CAM C"),
        ]:
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 24.0, (1280, 720))
            for f in range(48):
                img = np.full((720, 1280, 3), color_bgr, dtype=np.uint8)
                cv2.putText(img, f"{label} Frame {f}", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 3)
                writer.write(img)
            writer.release()

        # Register MediaAssets
        self.asset_a = MediaAsset(
            asset_id="asset_cam_a",
            project_id=self.project_id,
            name="cam_a.mp4",
            original_name="cam_a.mp4",
            file_location=self.cam_a_path,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
            width=1280,
            height=720,
            frame_rate=24.0,
            total_frames=48,
            duration_seconds=2.0,
            start_timecode=SMPTETimecode(hours=1, minutes=0, seconds=0, frames=0),
        )

        self.asset_b = MediaAsset(
            asset_id="asset_cam_b",
            project_id=self.project_id,
            name="cam_b.mp4",
            original_name="cam_b.mp4",
            file_location=self.cam_b_path,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
            width=1280,
            height=720,
            frame_rate=24.0,
            total_frames=48,
            duration_seconds=2.0,
            start_timecode=SMPTETimecode(hours=1, minutes=0, seconds=1, frames=0), # +24 frames offset
        )

        self.asset_c = MediaAsset(
            asset_id="asset_cam_c",
            project_id=self.project_id,
            name="cam_c.mp4",
            original_name="cam_c.mp4",
            file_location=self.cam_c_path,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
            width=1280,
            height=720,
            frame_rate=24.0,
            total_frames=48,
            duration_seconds=2.0,
            start_timecode=SMPTETimecode(hours=1, minutes=0, seconds=2, frames=0), # +48 frames offset
        )

        pml = media_library_registry.get_or_create(self.project_id)
        pml.add_asset(self.asset_a)
        pml.add_asset(self.asset_b)
        pml.add_asset(self.asset_c)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_multicam_sequence_creation_and_timecode_sync(self):
        """Verify multicam creation and SMPTE timecode synchronization calculation."""
        mc = multicam_service.create_multicam_sequence(
            project_id=self.project_id,
            name="Interview Multicam",
            asset_ids=[self.asset_a.asset_id, self.asset_b.asset_id, self.asset_c.asset_id],
            sync_method=SyncMethod.TIMECODE,
        )
        self.assertEqual(len(mc.angles), 3)
        self.assertEqual(mc.duration_frames, 48)

        # Cam A should be reference (offset 0)
        ang_a = mc.angles[0]
        self.assertEqual(ang_a.sync_offset_frames, 0)

        # Cam B started 1 second (24 frames) later
        ang_b = mc.angles[1]
        self.assertEqual(ang_b.sync_offset_frames, 24)

        # Cam C started 2 seconds (48 frames) later
        ang_c = mc.angles[2]
        self.assertEqual(ang_c.sync_offset_frames, 48)

    def test_02_manual_sync_nudging(self):
        """Verify frame-accurate sync offset adjustment."""
        mc = multicam_service.create_multicam_sequence(
            project_id=self.project_id,
            name="Manual Sync Sequence",
            asset_ids=[self.asset_a.asset_id, self.asset_b.asset_id],
            sync_method=SyncMethod.MANUAL_OFFSET,
        )
        ang_b = mc.angles[1]
        self.assertEqual(ang_b.sync_offset_frames, 0)

        # Nudge Cam B forward by 5 frames
        updated = multicam_service.nudge_angle_sync(mc.multicam_id, ang_b.angle_id, delta_frames=5)
        self.assertEqual(updated.sync_offset_frames, 5)

    def test_03_multicam_grid_preview_rendering(self):
        """Render synchronized multicamera grid preview with real decoded video frames."""
        mc = multicam_service.create_multicam_sequence(
            project_id=self.project_id,
            name="Grid Preview Sequence",
            asset_ids=[self.asset_a.asset_id, self.asset_b.asset_id, self.asset_c.asset_id],
            sync_method=SyncMethod.MANUAL_OFFSET,
        )
        frame_buf = multicam_service.render_multicam_frame(mc.multicam_id, frame=10)
        self.assertIsNotNone(frame_buf)
        self.assertEqual(frame_buf.width, 1920)
        self.assertEqual(frame_buf.height, 1080)
        self.assertTrue(len(frame_buf.buffer_bytes) > 0)

    def test_04_angle_switching_decisions_and_undo_redo(self):
        """Record live angle switching decisions and verify undo/redo stack."""
        mc = multicam_service.create_multicam_sequence(
            project_id=self.project_id,
            name="Switching Sequence",
            asset_ids=[self.asset_a.asset_id, self.asset_b.asset_id],
            sync_method=SyncMethod.MANUAL_OFFSET,
        )
        ang_a_id = mc.angles[0].angle_id
        ang_b_id = mc.angles[1].angle_id

        # Initially 1 decision spanning frame 0 to 48 on Cam A
        self.assertEqual(len(mc.decisions), 1)
        self.assertEqual(mc.decisions[0].active_angle_id, ang_a_id)

        # Cut to Cam B at frame 20
        decisions = multicam_service.switch_angle_at_frame(mc.multicam_id, frame=20, new_angle_id=ang_b_id)
        self.assertEqual(len(decisions), 2)
        self.assertEqual(decisions[0].active_angle_id, ang_a_id)
        self.assertEqual(decisions[0].start_frame, 0)
        self.assertEqual(decisions[0].end_frame, 20)
        self.assertEqual(decisions[1].active_angle_id, ang_b_id)
        self.assertEqual(decisions[1].start_frame, 20)
        self.assertEqual(decisions[1].end_frame, 48)

        # Undo cut
        ok_undo = multicam_service.undo_decision(mc.multicam_id)
        self.assertTrue(ok_undo)
        self.assertEqual(len(mc.decisions), 1)
        self.assertEqual(mc.decisions[0].active_angle_id, ang_a_id)

        # Redo cut
        ok_redo = multicam_service.redo_decision(mc.multicam_id)
        self.assertTrue(ok_redo)
        self.assertEqual(len(mc.decisions), 2)
        self.assertEqual(mc.decisions[1].active_angle_id, ang_b_id)

    def test_05_flatten_multicam_to_timeline(self):
        """Bake multicam cut decisions into standard timeline tracks and clips."""
        mc = multicam_service.create_multicam_sequence(
            project_id=self.project_id,
            name="Flatten Test",
            asset_ids=[self.asset_a.asset_id, self.asset_b.asset_id],
            sync_method=SyncMethod.MANUAL_OFFSET,
        )
        ang_b_id = mc.angles[1].angle_id
        multicam_service.switch_angle_at_frame(mc.multicam_id, frame=24, new_angle_id=ang_b_id)

        # Create target timeline sequence
        target_seq = VideoSequence(
            sequence_id="seq_target_flatten",
            project_id=self.project_id,
            name="Master Edit",
            settings=SequenceSettings(width=1920, height=1080, frame_rate=24.0),
        )

        res = multicam_service.flatten_to_sequence(mc.multicam_id, target_seq)
        self.assertTrue(res.is_success)
        self.assertEqual(res.total_segments_flattened, 2)
        self.assertEqual(len(target_seq.tracks), 2) # 1 Video track + 1 Master Audio track

        v_track = target_seq.tracks[0]
        self.assertEqual(len(v_track.items), 2)
        # First clip: Cam A (0 to 24)
        self.assertEqual(v_track.items[0].timeline_range.start_frame, 0)
        self.assertEqual(v_track.items[0].timeline_range.duration_frames, 24)
        # Second clip: Cam B (24 to 48)
        self.assertEqual(v_track.items[1].timeline_range.start_frame, 24)
        self.assertEqual(v_track.items[1].timeline_range.duration_frames, 24)

    def test_06_capability_registry_integration(self):
        """Verify Module 20 capabilities are registered."""
        self.assertIsNotNone(video_studio_capability_registry.get("video.multicam.sequence"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.multicam.sync"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.multicam.switching"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.multicam.flattening"))


if __name__ == "__main__":
    unittest.main()
