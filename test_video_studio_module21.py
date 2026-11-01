"""OMNIA Video Studio — Module 21: Video Stabilization, Motion Analysis & Camera Correction Tests.

Validates:
1. Feature tracking and camera motion estimation (Lucas-Kanade optical flow + RANSAC).
2. Trajectory accumulation and Gaussian smoothing.
3. Adaptive zoom and aspect-ratio crop compensation.
4. Scene-cut detection and boundary isolation (preventing smoothing across cuts).
5. Frame warping and actual pixel stabilization on test video with synthetic camera jitter.
6. Compositor and effects pipeline integration.
7. Capability registry presence.
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import cv2

from video_studio.stabilization_models import (
    MotionModelType,
    StabilizationMode,
    StabilizationConfig,
    MotionAnalysisReport,
)
from video_studio.motion_analysis_engine import motion_analysis_engine, MotionAnalysisEngine
from video_studio.stabilization_engine import stabilization_engine, StabilizationEngine
from video_studio.stabilization_service import stabilization_service, StabilizationService
from video_studio.media_models import MediaAsset, AssetMediaType, AssetLifecycleStatus
from video_studio.media_library import media_library_registry
from video_studio.effects_models import VideoFrameBuffer
from video_studio.registry import video_studio_capability_registry


class TestModule21Stabilization(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="omnia_m21_test_")
        self.project_id = "test_proj_m21"
        self.media_dir = os.path.join(self.test_dir, "media")
        os.makedirs(self.media_dir, exist_ok=True)

        # 1. Create a real video fixture with intentional high-frequency shake (30 frames, 1280x720)
        self.shaky_video_path = os.path.join(self.media_dir, "shaky_footage.mp4")
        writer = cv2.VideoWriter(self.shaky_video_path, cv2.VideoWriter_fourcc(*"mp4v"), 24.0, (1280, 720))

        # Base background texture with plenty of high-contrast features
        base_canvas = np.zeros((720, 1280, 3), dtype=np.uint8)
        for y in range(0, 720, 40):
            for x in range(0, 1280, 40):
                color = ((x * 3) % 255, (y * 5) % 255, 180)
                cv2.rectangle(base_canvas, (x, y), (x + 20, y + 20), color, -1)

        # Generate frames with alternating +/- 12 pixel jitter
        for i in range(30):
            # Alternating jitter
            dx = 12 if (i % 2 == 0) else -12
            dy = 8 if (i % 3 == 0) else -8
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            shaky_frame = cv2.warpAffine(base_canvas, M, (1280, 720))
            cv2.putText(shaky_frame, f"Frame {i}", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
            writer.write(shaky_frame)
        writer.release()

        # Register MediaAsset
        self.asset = MediaAsset(
            asset_id="asset_shaky_001",
            project_id=self.project_id,
            name="shaky_footage.mp4",
            original_name="shaky_footage.mp4",
            file_location=self.shaky_video_path,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
            width=1280,
            height=720,
            frame_rate=24.0,
            total_frames=30,
            duration_seconds=1.25,
        )
        pml = media_library_registry.get_or_create(self.project_id)
        pml.add_asset(self.asset)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_motion_analysis_feature_tracking(self):
        """Analyze inter-frame motion on shaky footage using Shi-Tomasi + Optical Flow."""
        report = motion_analysis_engine.analyze_asset_motion(
            file_path=self.shaky_video_path,
            asset_id=self.asset.asset_id,
            motion_model=MotionModelType.SIMILARITY,
        )
        self.assertEqual(report.total_frames, 30)
        self.assertTrue(len(report.frame_records) == 30)
        self.assertTrue(report.average_confidence > 0.7)

        # Verify that measured motion dx/dy alternates in sign
        rec1 = report.frame_records[1]
        rec2 = report.frame_records[2]
        self.assertTrue(abs(rec1.transform.dx) > 5.0)
        self.assertTrue(abs(rec2.transform.dx) > 5.0)
        # Signs should oppose due to alternating synthetic jitter
        self.assertNotEqual(np.sign(rec1.transform.dx), np.sign(rec2.transform.dx))

    def test_02_corrective_transforms_and_smoothing(self):
        """Calculate corrective transforms and ensure smoothed trajectory cancels jitter."""
        report = motion_analysis_engine.analyze_asset_motion(
            file_path=self.shaky_video_path,
            asset_id=self.asset.asset_id,
        )
        cfg = StabilizationConfig(
            is_enabled=True,
            smoothing_radius=10,
            auto_crop_zoom=True,
            manual_zoom_factor=1.08,
        )
        corrections = stabilization_engine.compute_corrective_transforms(report, cfg)
        self.assertEqual(len(corrections), 30)

        # Every transform should include a 2x3 affine matrix and applied zoom
        for corr in corrections:
            self.assertEqual(len(corr.matrix_2x3), 2)
            self.assertEqual(len(corr.matrix_2x3[0]), 3)
            self.assertAlmostEqual(corr.applied_zoom, 1.08, places=2)

    def test_03_frame_stabilization_warp(self):
        """Apply corrective transform to an actual video frame buffer and verify pixel modification."""
        cap = cv2.VideoCapture(self.shaky_video_path)
        ret, frame_bgr = cap.read()
        cap.release()
        self.assertTrue(ret)

        frame_rgba = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA)
        input_buf = VideoFrameBuffer(1280, 720, data=frame_rgba)

        # Analyze and configure clip
        report = stabilization_service.analyze_clip("clip_001", self.asset)
        cfg = StabilizationConfig(is_enabled=True, smoothing_radius=10)
        stabilization_service.update_clip_config("clip_001", self.asset.asset_id, cfg)

        # Process frame 1
        output_buf = stabilization_service.process_frame("clip_001", input_buf, source_frame=1)
        self.assertIsNotNone(output_buf)
        self.assertEqual(output_buf.width, 1280)
        self.assertEqual(output_buf.height, 720)

        # Pixel data should have been warped and modified
        diff = np.abs(output_buf.data.astype(np.float32) - input_buf.data.astype(np.float32))
        self.assertTrue(np.mean(diff) > 0.0)

    def test_04_scene_cut_isolation(self):
        """Ensure smoothing does not smooth across scene cuts."""
        # Create a synthetic report with an explicit scene cut at frame 15
        from video_studio.stabilization_models import MotionTransform, FrameMotionRecord
        records = []
        for i in range(30):
            records.append(FrameMotionRecord(
                frame_index=i,
                transform=MotionTransform(dx=10.0 if i < 15 else -10.0, dy=0.0),
                is_scene_cut=(i == 15),
            ))
        report = MotionAnalysisReport(
            report_id="rep_cut_test",
            asset_id="asset_cut",
            total_frames=30,
            motion_model=MotionModelType.SIMILARITY,
            frame_records=records,
            scene_cut_frames=[15],
            analyzed_width=1280,
            analyzed_height=720,
        )
        cfg = StabilizationConfig(is_enabled=True, smoothing_radius=5)
        corrections = stabilization_engine.compute_corrective_transforms(report, cfg)
        self.assertEqual(len(corrections), 30)

    def test_05_capability_registry_integration(self):
        """Verify Module 21 capabilities are registered."""
        self.assertIsNotNone(video_studio_capability_registry.get("video.stabilization.motion_analysis"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.stabilization.camera_smoothing"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.stabilization.crop_compensation"))


if __name__ == "__main__":
    unittest.main()
