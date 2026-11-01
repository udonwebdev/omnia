"""OMNIA Video Studio — Module 18: Professional Proxy Media, Playback Source Selection & Media Relinking Tests.

Validates:
1. Proxy profile configurations, dimension calculation, and aspect ratio preservation.
2. Real proxy media generation via OpenCV and verification probing.
3. Missing media detection, audit reporting, and multi-signal candidate scoring.
4. Transactional relinking updating media library and asset paths while keeping identity intact.
5. Playback source switching between original and proxy modes.
6. Strict export source policy enforcement (ORIGINALS_ONLY vs PROXIES_ALLOWED).
7. Module 1 Capability Registry presence.
"""

import os
import shutil
import tempfile
import unittest
import numpy as np
import cv2

from video_studio.proxy_models import (
    ProxyLifecycleStatus,
    ProxyProfileType,
    PlaybackSourceMode,
    ExportSourcePolicy,
    ProxyProfileConfig,
    ProxyMediaRecord,
    RelinkCandidate,
    RelinkResult,
)
from video_studio.proxy_engine import ProxyEngine
from video_studio.relinking_engine import RelinkingEngine
from video_studio.proxy_service import proxy_service, ProxyService
from video_studio.media_models import MediaAsset, AssetMediaType, AssetLifecycleStatus, VideoStreamInfo
from video_studio.media_library import media_library_registry
from video_studio.timeline_models import (
    VideoSequence,
    SequenceSettings,
    TimelineTrackModel,
    TimelineItemModel,
    TimelineTrackType,
    TimelineItemType,
    TimelineRange,
    SourceRange,
)
from video_studio.playback_engine import TimelinePlaybackEngine
from video_studio.playback_models import PlaybackQuality
from video_studio.registry import video_studio_capability_registry


class TestModule18ProxyAndRelinking(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="omnia_m18_test_")
        self.project_id = "test_proj_m18"
        self.media_dir = os.path.join(self.test_dir, "media")
        self.proxy_dir = os.path.join(self.test_dir, "proxies")
        self.relocate_dir = os.path.join(self.test_dir, "relocated")
        os.makedirs(self.media_dir, exist_ok=True)
        os.makedirs(self.proxy_dir, exist_ok=True)
        os.makedirs(self.relocate_dir, exist_ok=True)

        # Create a real test source video: 1920x1080, 24fps, 24 frames
        self.orig_video_path = os.path.join(self.media_dir, "master_footage.mp4")
        writer = cv2.VideoWriter(
            self.orig_video_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            24.0,
            (1920, 1080),
        )
        for i in range(24):
            # Create a frame with distinct color gradient
            frame = np.full((1080, 1920, 3), (i * 10 % 255, 120, 200), dtype=np.uint8)
            cv2.putText(frame, f"Frame {i}", (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 3.0, (255, 255, 255), 4)
            writer.write(frame)
        writer.release()

        # Create MediaAsset instance
        self.asset = MediaAsset(
            asset_id="asset_master_001",
            project_id=self.project_id,
            name="master_footage.mp4",
            original_name="master_footage.mp4",
            file_location=self.orig_video_path,
            media_type=AssetMediaType.VIDEO,
            status=AssetLifecycleStatus.READY,
            size_bytes=os.path.getsize(self.orig_video_path),
            width=1920,
            height=1080,
            frame_rate=24.0,
            total_frames=24,
            duration_seconds=1.0,
            video_codec="mp4v",
        )
        pml = media_library_registry.get_or_create(self.project_id)
        pml.add_asset(self.asset)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_proxy_profiles_and_dimension_calculation(self):
        """Verify profile dimensions maintain aspect ratio and even pixel bounds."""
        engine = ProxyEngine()
        # 16:9 4K downscale to 720p target
        w, h = engine._calculate_even_dimensions(3840, 2160, 1280, 720)
        self.assertEqual((w, h), (1280, 720))
        self.assertEqual(w % 2, 0)
        self.assertEqual(h % 2, 0)

        # Non-standard aspect ratio (e.g. 1920x1200 down to 720 target)
        w, h = engine._calculate_even_dimensions(1920, 1200, 1280, 720)
        self.assertTrue(w <= 1280 and h <= 720)
        self.assertEqual(w % 2, 0)
        self.assertEqual(h % 2, 0)

        # Upscaling prevention: 640x360 source requested at 1080p target remains source size
        w, h = engine._calculate_even_dimensions(640, 360, 1920, 1080)
        self.assertEqual((w, h), (640, 360))

    def test_02_real_proxy_generation_and_probing(self):
        """Generate a real 480p proxy and verify file output, dimensions, and lifecycle status."""
        rec = proxy_service.generate_proxy_for_asset(
            self.asset,
            profile_id="profile_480p",
            output_dir=self.proxy_dir,
        )
        self.assertEqual(rec.status, ProxyLifecycleStatus.READY)
        self.assertTrue(os.path.exists(rec.file_path))
        self.assertEqual(rec.height, 480)
        self.assertEqual(rec.width, 852)
        self.assertEqual(rec.duration_seconds, 1.0)
        self.assertTrue(rec.proxy_size_bytes > 0)
        self.assertTrue(len(rec.proxy_fingerprint) > 0)

        # Asset should now point to proxy location in metadata
        self.assertEqual(self.asset.proxy_location, rec.file_path)
        self.assertIsNotNone(self.asset.proxy_info)

    def test_03_missing_media_audit_and_discovery(self):
        """Simulate missing file and verify project media audit report."""
        audit_before = proxy_service.audit_project_media(self.project_id)
        self.assertEqual(audit_before["missing_assets_count"], 0)

        # Move source file to simulate offline / moved media
        moved_path = os.path.join(self.relocate_dir, "renamed_footage.mp4")
        shutil.move(self.orig_video_path, moved_path)

        audit_after = proxy_service.audit_project_media(self.project_id)
        self.assertEqual(audit_after["missing_assets_count"], 1)
        self.assertEqual(audit_after["missing_assets"][0]["asset_id"], self.asset.asset_id)

    def test_04_multi_signal_relinking(self):
        """Find candidate in search roots and execute transactional relink."""
        # Move original file to relocated directory with a new name
        relocated_file = os.path.join(self.relocate_dir, "vacation_master_v2.mp4")
        if os.path.exists(self.orig_video_path):
            shutil.move(self.orig_video_path, relocated_file)

        # Scan for candidates
        candidates = proxy_service.scan_for_relink_candidates(
            self.asset,
            search_roots=[self.test_dir],
        )
        self.assertTrue(len(candidates) > 0)
        best_candidate = candidates[0]
        self.assertEqual(best_candidate.candidate_path, relocated_file)
        self.assertTrue(best_candidate.confidence_score > 0.0)

        # Relink asset
        relink_res = proxy_service.relink_asset(self.asset, best_candidate.candidate_path)
        self.assertTrue(relink_res.is_success)
        self.assertEqual(self.asset.file_location, relocated_file)

        # Audit should show 0 missing assets now
        audit = proxy_service.audit_project_media(self.project_id)
        self.assertEqual(audit["missing_assets_count"], 0)

    def test_05_playback_source_mode_resolution(self):
        """Verify PlaybackEngine and ProxyService source switching logic."""
        # Generate proxy first
        proxy_service.generate_proxy_for_asset(self.asset, profile_id="profile_720p", output_dir=self.proxy_dir)

        # 1. Force ORIGINAL
        path, is_proxy = proxy_service.resolve_source_for_playback(self.asset, PlaybackSourceMode.ORIGINAL)
        self.assertFalse(is_proxy)
        self.assertEqual(path, self.asset.file_location)

        # 2. Force PROXY
        path, is_proxy = proxy_service.resolve_source_for_playback(self.asset, PlaybackSourceMode.PROXY)
        self.assertTrue(is_proxy)
        self.assertEqual(path, self.asset.proxy_location)

        # 3. PREFER_PROXY
        path, is_proxy = proxy_service.resolve_source_for_playback(self.asset, PlaybackSourceMode.PREFER_PROXY)
        self.assertTrue(is_proxy)

        # Playback session test
        pb_engine = TimelinePlaybackEngine()
        seq = VideoSequence(
            sequence_id="seq_m18_play",
            project_id=self.project_id,
            name="Proxy Playback Seq",
            settings=SequenceSettings(width=1280, height=720, frame_rate=24.0),
            tracks=[
                TimelineTrackModel(
                    track_id="tr_v0",
                    sequence_id="seq_m18_play",
                    name="Video 1",
                    track_type=TimelineTrackType.VIDEO,
                    items=[
                        TimelineItemModel(
                            item_id="item_v0",
                            track_id="tr_v0",
                            sequence_id="seq_m18_play",
                            name="Master Clip",
                            item_type=TimelineItemType.MEDIA_CLIP,
                            source_reference_id=self.asset.asset_id,
                            timeline_range=TimelineRange(start_frame=0, duration_frames=24),
                            source_range=SourceRange(in_frame=0, duration_frames=24),
                        )
                    ],
                )
            ],
        )

        session = pb_engine.create_session(seq, project_id=self.project_id, quality=PlaybackQuality.PROXY_PREFER)
        frame = pb_engine.render_frame(session.session_id, frame=0)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.width, 1280)
        self.assertEqual(frame.height, 720)

    def test_06_strict_export_protection(self):
        """Ensure ORIGINALS_ONLY policy refuses missing original files."""
        # Move original away
        shutil.move(self.orig_video_path, os.path.join(self.relocate_dir, "hidden.mp4"))

        # Under ORIGINALS_ONLY, resolve_source_for_export must raise an error
        with self.assertRaises(RuntimeError):
            proxy_service.resolve_source_for_export(self.asset, ExportSourcePolicy.ORIGINALS_ONLY)

    def test_07_capability_declarations(self):
        """Verify Module 18 capabilities are correctly registered."""
        self.assertIsNotNone(video_studio_capability_registry.get("video.proxy.generation"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.proxy.source_selection"))
        self.assertIsNotNone(video_studio_capability_registry.get("video.media.relinking"))


if __name__ == "__main__":
    unittest.main()
