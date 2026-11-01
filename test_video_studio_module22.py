"""OMNIA Video Studio — Module 22 Test Suite.
Tests:
1. Point tracking with Lucas-Kanade and forward-backward consistency.
2. Region tracking with normalized cross-correlation template matching.
3. Tracking quality analysis: confidence degradation and lost-track detection on synthetic occlusions.
4. Track-to-Transform binding: converting tracking samples into Module 8 keyframes in AnimationService.
5. Relative and inverted offset motion options.
6. Capability registration in VideoStudioCapabilityRegistry.
"""

import os
import tempfile
import unittest
import numpy as np
import cv2

from video_studio.tracking_models import (
    TrackingSession,
    TrackSample,
    TrackingMethodType,
    TrackingStatus,
    TrackTargetType,
    TrackApplicationTarget,
    TrackToEffectBinding,
)
from video_studio.tracking_engine import MotionTrackingEngine
from video_studio.tracking_service import TrackingService
from video_studio.animation_service import AnimationService
from video_studio.registry import video_studio_capability_registry
from video_studio.catalog_loader import populate_roadmap_capabilities


def create_synthetic_moving_box_video(
    output_path: str,
    width: int = 320,
    height: int = 240,
    num_frames: int = 30,
    box_start: tuple = (50, 50),
    dx: float = 3.0,
    dy: float = 2.0,
    occlude_frame: int = -1,
) -> str:
    """Generates an MP4 synthetic video with a distinctive white rectangle moving across dark background."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, 25.0, (width, height))

    bx, by = box_start
    bw, bh = 30, 30

    for i in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Draw a moving square target with texture (circle inside)
        if i != occlude_frame:
            x1 = int(bx + i * dx)
            y1 = int(by + i * dy)
            cv2.rectangle(frame, (x1, y1), (x1 + bw, y1 + bh), (220, 220, 220), -1)
            cv2.circle(frame, (x1 + bw // 2, y1 + bh // 2), 6, (40, 40, 240), -1)

        out.write(frame)

    out.release()
    return output_path


class TestModule22Tracking(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.test_video = os.path.join(self.tmp_dir, "test_motion.mp4")
        create_synthetic_moving_box_video(self.test_video, num_frames=20, dx=4.0, dy=2.0)
        self.engine = MotionTrackingEngine()
        self.anim_service = AnimationService()
        self.service = TrackingService(engine=self.engine, animation_service=self.anim_service)

    def tearDown(self):
        if os.path.exists(self.test_video):
            try:
                os.remove(self.test_video)
            except Exception:
                pass
        try:
            os.rmdir(self.tmp_dir)
        except Exception:
            pass

    def test_point_tracking_optical_flow(self):
        """Verifies Lucas-Kanade point tracking with forward-backward error validation."""
        session = self.service.create_session(
            project_id="proj_1",
            clip_id="clip_1",
            asset_id="asset_1",
            target_name="CenterMarker",
            initial_x=65.0, # Center of moving box (50 + 15)
            initial_y=65.0,
            start_frame=0,
            end_frame=20,
            method=TrackingMethodType.POINT_OPTICAL_FLOW,
        )

        res = self.service.start_tracking(session.session_id, self.test_video)
        self.assertEqual(res.status, TrackingStatus.COMPLETED)
        self.assertEqual(len(res.samples), 20)
        self.assertGreater(res.average_confidence, 0.7)

        # Initial point vs frame 19 point: moved ~19*4 = 76 px in X, 19*2 = 38 px in Y
        s0 = res.samples[0]
        s19 = res.samples[19]
        self.assertAlmostEqual(s0.x, 65.0, delta=1.0)
        self.assertAlmostEqual(s0.y, 65.0, delta=1.0)
        self.assertGreater(s19.x, s0.x + 60.0)
        self.assertGreater(s19.y, s0.y + 25.0)

    def test_region_tracking_template_match(self):
        """Verifies template matching tracking over video frames."""
        session = self.service.create_session(
            project_id="proj_1",
            clip_id="clip_1",
            asset_id="asset_1",
            target_name="SquareTarget",
            initial_x=65.0,
            initial_y=65.0,
            initial_width=30.0,
            initial_height=30.0,
            start_frame=0,
            end_frame=20,
            method=TrackingMethodType.REGION_TEMPLATE_MATCH,
        )

        res = self.service.start_tracking(session.session_id, self.test_video)
        self.assertEqual(res.status, TrackingStatus.COMPLETED)
        self.assertEqual(len(res.samples), 20)
        self.assertGreater(res.average_confidence, 0.8)

        s19 = res.samples[19]
        self.assertGreater(s19.x, 120.0)
        self.assertGreater(s19.y, 85.0)

    def test_tracking_loss_detection_on_occlusion(self):
        """Verifies that an occluded or disappeared target triggers lost-track detection."""
        occluded_video = os.path.join(self.tmp_dir, "occluded.mp4")
        create_synthetic_moving_box_video(occluded_video, num_frames=15, dx=2.0, dy=0.0, occlude_frame=10)

        session = self.service.create_session(
            project_id="proj_1",
            clip_id="clip_1",
            asset_id="asset_1",
            target_name="OccludedTarget",
            initial_x=65.0,
            initial_y=65.0,
            start_frame=0,
            end_frame=15,
            method=TrackingMethodType.POINT_OPTICAL_FLOW,
        )

        res = self.service.start_tracking(session.session_id, occluded_video)
        self.assertIn(10, res.lost_track_frames)
        self.assertFalse(res.samples[10].is_valid)
        self.assertTrue(res.samples[10].tracking_lost)

        if os.path.exists(occluded_video):
            os.remove(occluded_video)

    def test_apply_track_to_clip_transform_keyframes(self):
        """Verifies track-to-transform conversion creates keyframes in AnimationService."""
        session = self.service.create_session(
            project_id="proj_1",
            clip_id="src_clip",
            asset_id="asset_1",
            target_name="Feature",
            initial_x=100.0,
            initial_y=100.0,
            start_frame=0,
            end_frame=5,
        )
        # Populate artificial tracked samples
        session.samples = {
            0: TrackSample(0, 100.0, 100.0, confidence=1.0),
            1: TrackSample(1, 105.0, 102.0, confidence=1.0),
            2: TrackSample(2, 110.0, 104.0, confidence=1.0),
            3: TrackSample(3, 115.0, 106.0, confidence=1.0),
            4: TrackSample(4, 120.0, 108.0, confidence=1.0),
        }

        binding = TrackToEffectBinding(
            binding_id="bind_1",
            session_id=session.session_id,
            target_clip_id="dest_clip",
            application_target=TrackApplicationTarget.TRANSFORM_POSITION,
            relative_to_initial=True,
            offset_x=10.0,
            offset_y=5.0,
        )

        counts = self.service.apply_track_to_clip_transform(
            session_id=session.session_id,
            target_clip_id="dest_clip",
            binding=binding,
        )

        self.assertEqual(counts["pos_x"], 5)
        self.assertEqual(counts["pos_y"], 5)

        # Inspect keyframes on destination transform
        transform = self.anim_service.get_or_create_transform("dest_clip")
        self.assertEqual(len(transform.position_x.keyframes), 5)
        self.assertEqual(len(transform.position_y.keyframes), 5)

        # Frame 0: (100-100) + 10 = 10.0
        k0_x = next(k for k in transform.position_x.keyframes if k.frame == 0)
        self.assertEqual(k0_x.value, 10.0)

        # Frame 4: (120-100) + 10 = 30.0
        k4_x = next(k for k in transform.position_x.keyframes if k.frame == 4)
        self.assertEqual(k4_x.value, 30.0)

    def test_manual_sample_correction(self):
        """Verifies manual sample correction updates position and clears lost-track state."""
        session = self.service.create_session(
            project_id="proj_1",
            clip_id="clip_1",
            asset_id="asset_1",
            target_name="ManualTarget",
            initial_x=50.0,
            initial_y=50.0,
        )
        session.lost_track_frames.append(3)

        updated = self.service.update_sample_manually(session.session_id, frame_index=3, x=72.5, y=88.0)
        self.assertEqual(updated.x, 72.5)
        self.assertEqual(updated.y, 88.0)
        self.assertTrue(updated.is_valid)
        self.assertNotIn(3, session.lost_track_frames)

    def test_module22_capabilities_registered(self):
        """Verifies Module 22 tracking capabilities in catalog and registry."""
        populate_roadmap_capabilities(video_studio_capability_registry)
        point_cap = video_studio_capability_registry.get("video.tracking.point")
        region_cap = video_studio_capability_registry.get("video.tracking.region")
        binding_cap = video_studio_capability_registry.get("video.tracking.effects_binding")

        self.assertIsNotNone(point_cap)
        self.assertIsNotNone(region_cap)
        self.assertIsNotNone(binding_cap)


if __name__ == "__main__":
    unittest.main()
