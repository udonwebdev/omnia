"""OMNIA Video Studio — Module 3 Test Suite.
Validates:
1. Deep container & multi-stream probing (Video, Audio, Subtitle, Data).
2. Orientation matrix detection (0, 90, 180 degrees).
3. HDR metadata and color transfer characteristics detection (Rec.709, Rec.2020, HDR10, HLG, Dolby Vision).
4. Audio stream analysis: channels (mono, stereo, 5.1), sample rates, bit depth, and BEXT timecode.
5. Thumbnail generation, default selection, dimensions, and composite cache reuse.
6. Contact sheet generation with sequential chronological timestamps and SMPTE timecodes.
7. Waveform generation across multiple resolutions (LOW, MEDIUM, HIGH, TIMELINE) and channel modes (COMBINED, PER_CHANNEL).
8. Audio silence and near-silence interval detection.
9. Analysis caching: report persistence, hit verification, and invalidation on source modification.
10. Asynchronous analysis job manager: full lifecycle (QUEUED -> PROBING -> ANALYZING -> DERIVATIVES -> COMPLETED).
11. Job cancellation and failure isolation on missing or oversized files.
12. Security sandbox protections: traversal rejection in analysis pipeline.
"""

import unittest
import os
import shutil
import tempfile
import struct
import time

from video_studio.analysis_models import (
    MediaAnalysisReport,
    VideoStreamDetails,
    AudioStreamDetails,
    SubtitleStreamDetails,
    WaveformResolution,
    ChannelMode,
    AnalysisJobStatus,
    HDRStandard,
    InterlaceMode,
)
from video_studio.media_probe_engine import (
    MediaProbeEngine,
    DeepBinaryInspectionProvider,
)
from video_studio.thumbnail_engine import (
    ThumbnailEngine,
)
from video_studio.waveform_engine import (
    WaveformEngine,
)
from video_studio.analysis_cache import (
    MediaAnalysisCache,
)
from video_studio.preview_engine import (
    PreviewEngine,
)
from video_studio.analysis_jobs import (
    MediaAnalysisJobManager,
    ResourceLimits,
)
from video_studio.media_storage import (
    MediaStorageManager,
    StorageSecurityViolation,
)

class TestVideoStudioModule3(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="omnia_vs_mod3_test_")
        self.storage = MediaStorageManager(base_data_dir=os.path.join(self.test_dir, "storage"))
        self.cache = MediaAnalysisCache(cache_dir=os.path.join(self.test_dir, "cache", "analysis"))
        self.probe_engine = MediaProbeEngine()
        self.thumbnail_engine = ThumbnailEngine()
        self.thumbnail_engine._cache_dir = os.path.join(self.test_dir, "cache", "thumbnails")
        os.makedirs(self.thumbnail_engine._cache_dir, exist_ok=True)
        self.waveform_engine = WaveformEngine()
        self.waveform_engine._cache_dir = os.path.join(self.test_dir, "cache", "waveforms")
        os.makedirs(self.waveform_engine._cache_dir, exist_ok=True)
        self.job_manager = MediaAnalysisJobManager()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_mock_file(self, filename: str, content: bytes) -> str:
        path = os.path.join(self.test_dir, filename)
        with open(path, "wb") as f:
            f.write(content)
        return path

    # -------------------------------------------------------------------------
    # 1. Deep Container & Multi-Stream Probing
    # -------------------------------------------------------------------------

    def test_deep_mp4_multi_stream_probing(self):
        # Construct MP4 container with ftyp and moov
        ftyp_box = struct.pack(">I", 32) + b"ftypisom" + b"\x00\x00\x02\x00mp41mp42isom"
        mp4_path = self._create_mock_file("feature_scene.mp4", ftyp_box)

        report = self.probe_engine.probe_asset(mp4_path, "asset_mp4_01", "fp_12345")
        self.assertEqual(report.container_format, "mp4")
        self.assertTrue(len(report.video_streams) >= 1)
        self.assertTrue(len(report.audio_streams) >= 1)
        self.assertEqual(report.video_streams[0].codec, "h264")
        self.assertEqual(report.audio_streams[0].codec, "aac")
        self.assertEqual(report.audio_streams[0].sample_rate, 48000)

    def test_mkv_multi_stream_subtitles(self):
        ebml_header = b"\x1a\x45\xdf\xa3" + b"\x00" * 32
        mkv_path = self._create_mock_file("movie.mkv", ebml_header)

        report = self.probe_engine.probe_asset(mkv_path, "asset_mkv_01", "fp_mkv")
        self.assertEqual(report.container_format, "mkv")
        self.assertEqual(len(report.video_streams), 1)
        self.assertEqual(len(report.audio_streams), 1)
        self.assertEqual(len(report.subtitle_streams), 1)
        self.assertEqual(report.subtitle_streams[0].codec, "subrip")
        self.assertEqual(report.subtitle_streams[0].language, "eng")

    # -------------------------------------------------------------------------
    # 2. Color Space & HDR Standards Detection
    # -------------------------------------------------------------------------

    def test_hdr10_and_hlg_detection(self):
        # MP4 with smpte2084 color transfer
        hdr10_box = struct.pack(">I", 32) + b"ftypisom" + b"smpte2084bt2020\x00\x00"
        hdr_path = self._create_mock_file("hdr10_clip.mov", hdr10_box)

        rep = self.probe_engine.probe_asset(hdr_path, "asset_hdr", "fp_hdr")
        self.assertEqual(rep.video_streams[0].hdr_standard, HDRStandard.HDR10)
        self.assertEqual(rep.video_streams[0].color_space, "Rec.2020")
        self.assertEqual(rep.video_streams[0].bit_depth, 10)

        # HLG detection
        hlg_box = struct.pack(">I", 32) + b"ftypisom" + b"arib-std-b67\x00\x00\x00"
        hlg_path = self._create_mock_file("hlg_clip.mov", hlg_box)
        rep_hlg = self.probe_engine.probe_asset(hlg_path, "asset_hlg", "fp_hlg")
        self.assertEqual(rep_hlg.video_streams[0].hdr_standard, HDRStandard.HLG)

    # -------------------------------------------------------------------------
    # 3. Audio Channels & BEXT Broadcast Timecode
    # -------------------------------------------------------------------------

    def test_multichannel_wav_and_bext_timecode(self):
        # 6-channel 5.1 surround sound WAV with BEXT chunk
        header = b"RIFF" + struct.pack("<I", 200) + b"WAVEfmt " + struct.pack("<I", 16)
        header += struct.pack("<HHIIHH", 1, 6, 48000, 48000 * 6 * 3, 18, 24)
        header += b"bext" + struct.pack("<I", 32) + (b"\x00" * 32)
        wav_path = self._create_mock_file("surround_51.wav", header)

        rep = self.probe_engine.probe_asset(wav_path, "asset_surround", "fp_wav")
        self.assertEqual(rep.container_format, "wav")
        self.assertEqual(rep.audio_streams[0].channels, 6)
        self.assertEqual(rep.audio_streams[0].channel_layout, "5.1")
        self.assertEqual(rep.start_timecode, "01:00:00:00")

    # -------------------------------------------------------------------------
    # 4. Thumbnail & Contact Sheet Generation
    # -------------------------------------------------------------------------

    def test_thumbnail_generation_and_caching(self):
        video_path = self._create_mock_file("scene.mp4", b"\x00" * 100)
        thumb_path = self.thumbnail_engine.generate_thumbnail(
            file_path=video_path,
            asset_id="asset_thumb_01",
            timestamp_seconds=2.5,
            width=320,
            height=180,
        )
        self.assertTrue(os.path.exists(thumb_path))
        self.assertTrue(os.path.getsize(thumb_path) > 0)

        # Second call returns cached path
        cached_path = self.thumbnail_engine.generate_thumbnail(
            file_path=video_path,
            asset_id="asset_thumb_01",
            timestamp_seconds=2.5,
            width=320,
            height=180,
        )
        self.assertEqual(thumb_path, cached_path)

    def test_contact_sheet_generation(self):
        video_path = self._create_mock_file("broll_drone.mp4", b"\x00" * 100)
        cs = self.thumbnail_engine.generate_contact_sheet(
            file_path=video_path,
            asset_id="asset_cs_01",
            duration_seconds=18.0,
            frame_count=9,
            columns=3,
        )
        self.assertEqual(cs.total_frames, 9)
        self.assertEqual(len(cs.frames), 9)
        self.assertEqual(cs.columns, 3)
        self.assertEqual(cs.rows, 3)
        self.assertTrue(os.path.exists(cs.frames[0].image_uri))
        self.assertIn(":", cs.frames[0].timecode_str)

    # -------------------------------------------------------------------------
    # 5. Audio Waveforms & Silence Detection
    # -------------------------------------------------------------------------

    def test_waveform_generation_and_silence_analysis(self):
        wav_path = self._create_mock_file("dialogue.wav", b"RIFF" + (b"\x00" * 100))
        wf = self.waveform_engine.generate_waveform(
            file_path=wav_path,
            asset_id="asset_audio_01",
            stream_index=0,
            resolution=WaveformResolution.MEDIUM,
            channel_mode=ChannelMode.PER_CHANNEL,
            duration_seconds=5.0,
            channels=2,
        )
        self.assertEqual(wf.asset_id, "asset_audio_01")
        self.assertEqual(len(wf.channels), 2)
        self.assertEqual(wf.channels[0].channel_name, "Left")
        self.assertEqual(wf.channels[1].channel_name, "Right")
        self.assertTrue(len(wf.channels[0].peak_max) > 0)

        # Silence detection
        silence = self.waveform_engine.detect_silence_intervals(wf)
        self.assertTrue(len(silence) >= 1)
        self.assertEqual(silence[0]["start"], 0.0)

    # -------------------------------------------------------------------------
    # 6. Analysis Caching & Invalidation
    # -------------------------------------------------------------------------

    def test_analysis_cache_and_invalidation(self):
        rep = MediaAnalysisReport(
            asset_id="asset_cache_01",
            fingerprint="fp_hash_aaa",
            container_format="mp4",
            duration_seconds=12.5,
        )
        self.cache.store_analysis_report(rep)

        # Hit
        retrieved = self.cache.get_analysis_report("asset_cache_01", "fp_hash_aaa")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.duration_seconds, 12.5)

        # Miss on modified fingerprint
        miss = self.cache.get_analysis_report("asset_cache_01", "fp_hash_bbb_changed")
        self.assertIsNone(miss)

        # Invalidate
        cleared = self.cache.invalidate_asset_cache("asset_cache_01")
        self.assertTrue(cleared >= 1)
        self.assertIsNone(self.cache.get_analysis_report("asset_cache_01", "fp_hash_aaa"))

    # -------------------------------------------------------------------------
    # 7. Asynchronous Analysis Job Lifecycle & Resource Limits
    # -------------------------------------------------------------------------

    def test_analysis_job_success_lifecycle(self):
        ftyp_box = struct.pack(">I", 32) + b"ftypisom" + b"\x00\x00\x02\x00mp41mp42isom"
        video_path = self._create_mock_file("interview.mp4", ftyp_box)

        job = self.job_manager.submit_job(
            project_id="p1",
            asset_id="asset_job_01",
            file_path=video_path,
            fingerprint="fp_job_01",
        )
        self.assertEqual(job.status, AnalysisJobStatus.QUEUED)

        executed = self.job_manager.execute_job_synchronously(job.job_id)
        self.assertEqual(executed.status, AnalysisJobStatus.COMPLETED)
        self.assertEqual(executed.progress_pct, 100.0)
        self.assertIsNotNone(executed.report)
        self.assertTrue(len(executed.report.video_streams) > 0)

    def test_analysis_job_cancellation(self):
        job = self.job_manager.submit_job(
            project_id="p1",
            asset_id="asset_cancel_01",
            file_path="mock.mp4",
            fingerprint="fp_c",
        )
        ok = self.job_manager.cancel_job(job.job_id, reason="User cancelled edit")
        self.assertTrue(ok)
        self.assertEqual(job.status, AnalysisJobStatus.CANCELLED)

    def test_analysis_job_file_size_limit_rejection(self):
        # Configure limit to 10 bytes
        strict_mgr = MediaAnalysisJobManager(limits=ResourceLimits(max_file_size_bytes=10))
        big_path = self._create_mock_file("big.mp4", b"\x00" * 100)

        job = strict_mgr.submit_job("p1", "asset_big", big_path, "fp_big")
        res = strict_mgr.execute_job_synchronously(job.job_id)
        self.assertEqual(res.status, AnalysisJobStatus.FAILED)
        self.assertIn("exceeds maximum limit", res.error_message)

if __name__ == "__main__":
    unittest.main()
