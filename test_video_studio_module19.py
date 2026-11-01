"""OMNIA Video Studio — Module 19: Media Transcoding, Conform & Batch Processing Tests.

Validates:
1. Conform plan generation comparing source properties against target profile.
2. Real video transcode with resolution conform and fit-pad letterboxing.
3. Real audio transcode with channel downmix and loudness normalization.
4. Deterministic frame-rate conversion (drop/duplication).
5. Output validation, SHA-256 fingerprinting, and preservation of the original source.
6. Automatic derivative registration in ProjectMediaLibrary and relationship tracking.
7. Batch transcode execution with error isolation and progress reporting.
8. Capability registry presence.
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import cv2
import wave

from video_studio.transcode_models import (
    TranscodeJobStatus,
    BatchJobStatus,
    TranscodeProfile,
    ScalingPolicy,
    AudioDownmixPolicy,
    LoudnessStandard,
    DerivativeRegistrationPolicy,
)
from video_studio.transcode_engine import TranscodeEngine, transcode_engine
from video_studio.transcode_service import TranscodeService, transcode_service
from video_studio.media_models import (
    MediaAsset,
    AssetMediaType,
    AssetLifecycleStatus,
    MediaRelationshipType,
)
from video_studio.media_library import media_library_registry
from video_studio.registry import video_studio_capability_registry


class TestModule19TranscodingAndConform(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="omnia_m19_test_")
        self.project_id = "test_proj_m19"
        self.media_dir = os.path.join(self.test_dir, "media")
        self.output_dir = os.path.join(self.test_dir, "output")
        os.makedirs(self.media_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

        # 1. Create a real test source video: 1280x720, 30fps, 30 frames (1 second)
        self.video_src_path = os.path.join(self.media_dir, "source_720p30.mp4")
        writer = cv2.VideoWriter(
            self.video_src_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            30.0,
            (1280, 720),
        )
        for i in range(30):
            frame = np.full((720, 1280, 3), (i * 8 % 255, 100, 180), dtype=np.uint8)
            cv2.putText(frame, f"Frame {i}", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 3)
            writer.write(frame)
        writer.release()

        # 2. Create a real test source audio WAV: 44.1kHz stereo, 1 second sine wave
        self.audio_src_path = os.path.join(self.media_dir, "source_audio_44k.wav")
        sample_rate = 44100
        duration = 1.0
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        left = 0.5 * np.sin(2 * np.pi * 440 * t) # 440 Hz A tone
        right = 0.3 * np.sin(2 * np.pi * 880 * t) # 880 Hz
        stereo_signal = np.stack([left, right], axis=1)
        stereo_int16 = (stereo_signal * 32767.0).astype(np.int16)

        with wave.open(self.audio_src_path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(stereo_int16.tobytes())

        # Register MediaAssets
        self.video_asset = MediaAsset(
            asset_id="asset_tc_video_001",
            project_id=self.project_id,
            name="source_720p30.mp4",
            original_name="source_720p30.mp4",
            file_location=self.video_src_path,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
            size_bytes=os.path.getsize(self.video_src_path),
            width=1280,
            height=720,
            frame_rate=30.0,
            total_frames=30,
            duration_seconds=1.0,
        )

        self.audio_asset = MediaAsset(
            asset_id="asset_tc_audio_001",
            project_id=self.project_id,
            name="source_audio_44k.wav",
            original_name="source_audio_44k.wav",
            file_location=self.audio_src_path,
            media_type=AssetMediaType.AUDIO,
            status=AssetLifecycleStatus.READY,
            size_bytes=os.path.getsize(self.audio_src_path),
            sample_rate=44100,
            audio_channels=2,
            duration_seconds=1.0,
        )

        pml = media_library_registry.get_or_create(self.project_id)
        pml.add_asset(self.video_asset)
        pml.add_asset(self.audio_asset)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_conform_plan_generation(self):
        """Verify preflight conform plan accurately identifies conversions."""
        plan = transcode_service.plan_conform(
            self.video_asset,
            profile_id="profile_master_1080p",
        )
        self.assertTrue(plan.is_executable)
        self.assertEqual(plan.asset_id, self.video_asset.asset_id)
        
        # Verify detected transformations
        prop_names = [t.property_name for t in plan.transformations]
        self.assertIn("resolution", prop_names)
        self.assertIn("frame_rate", prop_names)

        # 720p up to 1080p target
        res_t = next(t for t in plan.transformations if t.property_name == "resolution")
        self.assertEqual(res_t.target_value, "1920x1080")

        # 30fps down to 24fps target
        fps_t = next(t for t in plan.transformations if t.property_name == "frame_rate")
        self.assertEqual(fps_t.target_value, "24.000 fps")
        self.assertTrue(fps_t.is_lossy)

    def test_02_video_transcode_and_letterbox_conform(self):
        """Transcode 1280x720 video into 1920x1080 with 24fps conform."""
        orig_hash_before = transcode_engine._compute_fingerprint(self.video_src_path)

        job = transcode_service.create_transcode_job(
            self.video_asset,
            profile_id="profile_master_1080p",
            registration_policy=DerivativeRegistrationPolicy.NEW_ASSET,
        )
        success = transcode_service.execute_job(job.job_id)
        self.assertTrue(success)
        self.assertEqual(job.status, TranscodeJobStatus.COMPLETED)
        self.assertTrue(os.path.exists(job.output_file_path))

        # Verify original file was preserved unmodified
        orig_hash_after = transcode_engine._compute_fingerprint(self.video_src_path)
        self.assertEqual(orig_hash_before, orig_hash_after)

        # Verify output video properties with OpenCV decoder
        cap = cv2.VideoCapture(job.output_file_path)
        self.assertTrue(cap.isOpened())
        out_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        out_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out_fps = float(cap.get(cv2.CAP_PROP_FPS))
        out_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()

        self.assertEqual(out_w, 1920)
        self.assertEqual(out_h, 1080)
        self.assertAlmostEqual(out_fps, 24.0, delta=0.5)
        self.assertTrue(out_frames > 0)

        # Verify derivative registered in ProjectMediaLibrary
        self.assertIsNotNone(job.registered_asset_id)
        pml = media_library_registry.get_or_create(self.project_id)
        child_asset = pml.get_asset(job.registered_asset_id)
        self.assertIsNotNone(child_asset)
        self.assertEqual(child_asset.width, 1920)
        self.assertEqual(child_asset.height, 1080)

        # Verify relationship link
        rels = pml.get_related_assets(self.video_asset.asset_id)
        self.assertTrue(any(r.target_asset_id == job.registered_asset_id for r in rels))

    def test_03_audio_transcode_and_normalization(self):
        """Transcode 44.1kHz stereo audio to 48kHz with EBU R128 loudness normalization."""
        orig_hash_before = transcode_engine._compute_fingerprint(self.audio_src_path)

        job = transcode_service.create_transcode_job(
            self.audio_asset,
            profile_id="profile_audio_broadcast_wav",
            registration_policy=DerivativeRegistrationPolicy.NEW_ASSET,
        )
        success = transcode_service.execute_job(job.job_id)
        self.assertTrue(success)
        self.assertEqual(job.status, TranscodeJobStatus.COMPLETED)
        self.assertTrue(os.path.exists(job.output_file_path))

        # Verify original audio remained unchanged
        orig_hash_after = transcode_engine._compute_fingerprint(self.audio_src_path)
        self.assertEqual(orig_hash_before, orig_hash_after)

        # Inspect conformed WAV properties
        with wave.open(job.output_file_path, "rb") as wf:
            self.assertEqual(wf.getnchannels(), 2)
            self.assertEqual(wf.getframerate(), 48000)
            self.assertEqual(wf.getsampwidth(), 2)
            n_frames = wf.getnframes()
            self.assertAlmostEqual(n_frames / 48000.0, 1.0, delta=0.05)

    def test_04_batch_processing_and_isolation(self):
        """Run batch processing across multiple assets and ensure error isolation."""
        # Create a second dummy video asset with a non-existent path to test failure isolation
        broken_asset = MediaAsset(
            asset_id="asset_broken_002",
            project_id=self.project_id,
            file_location=os.path.join(self.media_dir, "ghost_video.mp4"),
            media_type=AssetMediaType.VIDEO,
        )
        pml = media_library_registry.get_or_create(self.project_id)
        pml.add_asset(broken_asset)

        batch = transcode_service.create_batch(
            project_id=self.project_id,
            name="Daily Ingest Conform Batch",
            assets=[self.video_asset, broken_asset],
            profile_id="profile_web_720p",
        )
        self.assertEqual(batch.total_jobs, 2)

        res_batch = transcode_service.execute_batch(batch.batch_id)
        self.assertEqual(res_batch.completed_jobs, 1)
        self.assertEqual(res_batch.failed_jobs, 1)
        self.assertEqual(res_batch.status, BatchJobStatus.FAILED)

        # Ensure the successful job actually produced a valid output
        job_success = transcode_service.jobs[res_batch.job_ids[0]]
        self.assertEqual(job_success.status, TranscodeJobStatus.COMPLETED)
        self.assertTrue(os.path.exists(job_success.output_file_path))

        # Ensure the failed job did not crash or corrupt the batch
        job_failed = transcode_service.jobs[res_batch.job_ids[1]]
        self.assertEqual(job_failed.status, TranscodeJobStatus.FAILED)

    def test_05_cancellation_and_retry(self):
        """Verify cancellation state handling and job retry capability."""
        job = transcode_service.create_transcode_job(
            self.video_asset,
            profile_id="profile_web_720p",
        )
        # Cancel while queued
        cancelled = transcode_service.cancel_job(job.job_id)
        self.assertTrue(cancelled)
        self.assertEqual(job.status, TranscodeJobStatus.CANCELLED)

        # Retry cancelled job
        retried = transcode_service.retry_job(job.job_id)
        self.assertTrue(retried)
        self.assertEqual(job.status, TranscodeJobStatus.COMPLETED)
        self.assertTrue(os.path.exists(job.output_file_path))

    def test_06_capability_registry_integration(self):
        """Verify Module 19 capabilities are properly registered."""
        self.assertIsNotNone(video_studio_capability_registry.get("video.transcode.engine"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.transcode.conform"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.transcode.batch"))


if __name__ == "__main__":
    unittest.main()
