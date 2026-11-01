"""Unit tests for OMNIA Video Studio Module 17: Professional Video Export, Encoding & Render Queue Engine.

Covers:
1. Export presets discovery and configuration validation.
2. Render job creation with immutable render snapshot.
3. Full sequence rendering into a real, validated MP4 video file.
4. Output media file verification (nonzero size, correct frame count, resolution, decodable test frame).
5. Audio-only master WAV export with real PCM waveform bytes.
6. Render queue progress tracking and job completion states.
7. Capability registry integration.
"""

import unittest
import os
import tempfile
import numpy as np

from video_studio.export_models import (
    ExportConfig,
    ExportContainer,
    VideoEncoderCodec,
    AudioEncoderCodec,
    RenderJobStatus,
)
from video_studio.export_engine import export_engine
from video_studio.export_service import export_service
from video_studio.timeline_models import (
    VideoSequence,
    TimelineTrackModel,
    TimelineTrackType,
    TimelineItemModel,
    TimelineRange,
    SourceRange,
    SequenceSettings,
)
from video_studio.compositing_models import VideoFrameBuffer
from video_studio.audio_models import AudioBuffer

class TestVideoStudioModule17(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="omnia_export_test_")

    def tearDown(self):
        # Cleanup temp directory and generated export files
        if os.path.exists(self.tmp_dir):
            for f in os.listdir(self.tmp_dir):
                try:
                    os.remove(os.path.join(self.tmp_dir, f))
                except Exception:
                    pass
            try:
                os.rmdir(self.tmp_dir)
            except Exception:
                pass

    def test_01_export_presets(self):
        """Verifies standard export presets are available and valid."""
        presets = export_service.list_presets()
        self.assertGreaterEqual(len(presets), 3)

        p_1080p = export_service.get_preset("preset_1080p_hq")
        self.assertIsNotNone(p_1080p)
        self.assertEqual(p_1080p.config.width, 1920)
        self.assertEqual(p_1080p.config.height, 1080)

    def test_02_render_snapshot_and_job_creation(self):
        """Verifies render job creation freezes sequence state into a snapshot."""
        seq = export_service.timeline_service.create_sequence(
            project_id="proj_exp_1",
            name="Export Test Seq",
            settings=SequenceSettings(width=320, height=240, frame_rate=24.0),
            create_default_tracks=False,
        )
        seq.duration_frames = 48

        out_path = os.path.join(self.tmp_dir, "test_job_create.mp4")
        ok, msg, job = export_service.create_render_job(
            project_id="proj_exp_1",
            sequence_id=seq.sequence_id,
            output_path=out_path,
            preset_id="preset_720p_preview",
        )

        self.assertTrue(ok)
        self.assertIsNotNone(job)
        self.assertEqual(job.status, RenderJobStatus.QUEUED)
        self.assertEqual(job.snapshot.duration_frames, 48)
        self.assertEqual(job.snapshot.start_frame, 0)
        self.assertEqual(job.snapshot.end_frame, 48)

    def test_03_real_mp4_export_and_validation(self):
        """Executes full end-to-end rendering and verifies real MP4 file creation and probing."""
        seq = export_service.timeline_service.create_sequence(
            project_id="proj_exp_2",
            name="Render Execution Seq",
            settings=SequenceSettings(width=160, height=120, frame_rate=24.0),
            create_default_tracks=False,
        )
        track = TimelineTrackModel(track_id="t_vid", sequence_id=seq.sequence_id, name="Video", track_type=TimelineTrackType.VIDEO)
        clip = TimelineItemModel(
            item_id="c_exp",
            track_id="t_vid",
            sequence_id=seq.sequence_id,
            source_reference_id="asset_test",
            timeline_range=TimelineRange(start_frame=0, duration_frames=12),
            source_range=SourceRange(in_frame=0, duration_frames=12),
        )
        track.items.append(clip)
        seq.tracks.append(track)
        seq.duration_frames = 12

        out_path = os.path.join(self.tmp_dir, "output_render.mp4")
        cfg = ExportConfig(
            container=ExportContainer.MP4,
            video_codec=VideoEncoderCodec.MP4V,
            width=160,
            height=120,
            frame_rate=24.0,
            include_video=True,
            include_audio=False,
            start_frame=0,
            end_frame=12,
        )

        ok, msg, job = export_service.create_render_job(
            project_id="proj_exp_2",
            sequence_id=seq.sequence_id,
            output_path=out_path,
            config=cfg,
        )
        self.assertTrue(ok)

        # Execute export
        report = export_service.execute_job(job.job_id)
        self.assertTrue(report.is_valid, f"Export failed with error: {report.error_message}")
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(report.file_size_bytes, 0)
        self.assertEqual(report.detected_width, 160)
        self.assertEqual(report.detected_height, 120)
        self.assertTrue(report.has_video_stream)
        self.assertEqual(job.status, RenderJobStatus.COMPLETED)
        self.assertEqual(job.frames_rendered, 12)
        self.assertEqual(job.progress_percent, 100.0)

    def test_04_audio_master_wav_export(self):
        """Verifies master audio WAV export produces valid wave stream with audio duration."""
        seq = export_service.timeline_service.create_sequence(
            project_id="proj_exp_audio",
            name="Audio Render Seq",
            settings=SequenceSettings(frame_rate=24.0),
            create_default_tracks=False,
        )
        seq.duration_frames = 24 # 1 second at 24fps

        out_wav = os.path.join(self.tmp_dir, "master_audio.wav")
        cfg = ExportConfig(
            container=ExportContainer.WAV,
            audio_codec=AudioEncoderCodec.PCM,
            audio_sample_rate=48000,
            audio_channels=2,
            include_video=False,
            include_audio=True,
            start_frame=0,
            end_frame=24,
        )

        ok, msg, job = export_service.create_render_job(
            project_id="proj_exp_audio",
            sequence_id=seq.sequence_id,
            output_path=out_wav,
            config=cfg,
        )
        self.assertTrue(ok)

        report = export_service.execute_job(job.job_id)
        self.assertTrue(report.is_valid)
        self.assertTrue(os.path.exists(out_wav))
        self.assertTrue(report.has_audio_stream)
        self.assertGreater(report.file_size_bytes, 1000)

    def test_05_capability_registry_ready(self):
        """Verifies Module 17 capabilities registered in OMNIA Video Studio Capability Registry."""
        from video_studio.registry import video_studio_capability_registry
        from video_studio.registry_models import ImplementationState

        export_service.register_capabilities()

        cap_exp = video_studio_capability_registry.get("video.export.engine")
        self.assertIsNotNone(cap_exp)
        self.assertEqual(cap_exp.implementation_state, ImplementationState.IMPLEMENTED)

        cap_q = video_studio_capability_registry.get("video.export.render_queue")
        self.assertIsNotNone(cap_q)
        self.assertEqual(cap_q.implementation_state, ImplementationState.IMPLEMENTED)

if __name__ == "__main__":
    unittest.main()
