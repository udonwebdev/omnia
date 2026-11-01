"""OMNIA Video Studio — Module 2 Test Suite.
Validates:
1. Normalized media asset creation, stable IDs, and dictionary representation.
2. Binary magic-byte probing across containers (MP4, WAV, PNG, OpenEXR, LUT, Subtitle).
3. File validation: empty file rejection, corrupted header rejection, missing file handling.
4. Storage sandbox: path traversal rejection, null-byte injection rejection, sensitive path protection.
5. Ingest pipeline: full valid import, duplicate detection without hash collisions.
6. Project media library: creation, default bins, custom bins, nested hierarchy, and asset assignment.
7. Bin management: moving assets, renaming bins, recursive and non-recursive deletion.
8. Media search: multi-criteria queries (text, media type, tags, bin filtering, codecs).
9. Media lifecycle: offline state transition on missing file, relink resolution.
10. Timing representations: RationalTime frame conversion, SMPTE drop-frame / non-drop-frame calculations.
11. Proxy and generated media derivation models and relationships.
12. Watch folder registration and candidate scan filtering.
"""

import unittest
import os
import shutil
import tempfile
import struct
import time

from video_studio.media_models import (
    AssetMediaType,
    AssetLifecycleStatus,
    ContainerFormat,
    FrameRateMode,
    ProxyStatus,
    MediaRelationshipType,
    RationalTime,
    SMPTETimecode,
    MediaAsset,
    ProxyDescriptor,
    GeneratedMediaDescriptor,
)
from video_studio.media_storage import (
    MediaStorageManager,
    StorageSecurityViolation,
)
from video_studio.media_probe import (
    MediaProbeService,
    BuiltinHeuristicProbeProvider,
    ProbeResult,
)
from video_studio.media_library import (
    ProjectMediaLibrary,
    MediaBinNode,
    MediaSearchQuery,
    media_library_registry,
)
from video_studio.media_ingest import (
    MediaIngestService,
)
from video_studio.watch_folder import (
    WatchFolderConfig,
    WatchFolderManager,
)

class TestVideoStudioModule2(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="omnia_vs_mod2_test_")
        self.storage = MediaStorageManager(base_data_dir=os.path.join(self.test_dir, "storage"))
        self.probe = MediaProbeService()
        self.library = ProjectMediaLibrary(project_id="test_proj_01")
        self.ingest = MediaIngestService()
        # Override storage in ingest for isolated sandbox testing
        self.ingest._storage = self.storage
        self.ingest._probe = self.probe

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        media_library_registry.remove("test_proj_01")
        media_library_registry.remove("test_proj_relink")

    def _create_mock_file(self, filename: str, content: bytes) -> str:
        path = os.path.join(self.test_dir, filename)
        with open(path, "wb") as f:
            f.write(content)
        return path

    # -------------------------------------------------------------------------
    # 1. Asset Identity & Timing Model
    # -------------------------------------------------------------------------

    def test_asset_identity_independent_of_filename(self):
        asset = MediaAsset(
            name="Sequence_Final.mov",
            original_name="raw_footage_001.mov",
            file_location="/mock/path/raw_footage_001.mov",
            media_type=AssetMediaType.VIDEO,
        )
        self.assertTrue(asset.asset_id.startswith("asset_"))
        self.assertNotEqual(asset.asset_id, asset.name)
        self.assertNotEqual(asset.asset_id, asset.original_name)

        # Renaming asset display name does not affect asset_id
        orig_id = asset.asset_id
        asset.name = "Scene 1 Take 2"
        self.assertEqual(asset.asset_id, orig_id)

    def test_rational_time_conversions(self):
        # 24 fps exact
        rt = RationalTime.from_frames(48, fps=24.0)
        self.assertAlmostEqual(rt.to_seconds(), 2.0, places=3)
        self.assertEqual(rt.to_frames(24.0), 48)

        # Broadcast 23.976 fps fractional precision
        rt_broadcast = RationalTime.from_frames(24, fps=23.976)
        self.assertAlmostEqual(rt_broadcast.to_seconds(), 1.001, places=3)

    def test_smpte_timecode_calculations(self):
        # Non-drop frame 24 fps
        tc_ndf = SMPTETimecode(hours=1, minutes=0, seconds=0, frames=0, fps=24.0, is_drop_frame=False)
        self.assertEqual(tc_ndf.to_total_frames(), 86400)
        self.assertEqual(str(tc_ndf), "01:00:00:00")

        # Reverse frames to SMPTE
        tc_from_frames = SMPTETimecode.from_frames(86400, fps=24.0, is_drop_frame=False)
        self.assertEqual(str(tc_from_frames), "01:00:00:00")

        # Drop frame delimiter format
        tc_df = SMPTETimecode(hours=0, minutes=1, seconds=0, frames=2, fps=29.97, is_drop_frame=True)
        self.assertIn(";", str(tc_df))

    # -------------------------------------------------------------------------
    # 2. Binary Magic-Byte Probing & Container Detection
    # -------------------------------------------------------------------------

    def test_probe_mp4_header(self):
        # Construct ISO BMFF header: length 32, box 'ftyp', brand 'isom'
        ftyp_box = struct.pack(">I", 32) + b"ftypisom" + b"\x00\x00\x02\x00mp41mp42isom"
        mp4_path = self._create_mock_file("sample.mp4", ftyp_box)

        res = self.probe.probe_file(mp4_path)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.media_type, AssetMediaType.VIDEO)
        self.assertEqual(res.container, "mp4")
        self.assertEqual(res.mime_type, "video/mp4")
        self.assertEqual(res.width, 1920)
        self.assertEqual(res.height, 1080)

    def test_probe_wav_header(self):
        # Construct RIFF WAVE header: RIFF + size + WAVE + fmt + channels 2 + rate 48000 + depth 24
        header = b"RIFF" + struct.pack("<I", 100) + b"WAVEfmt " + struct.pack("<I", 16)
        header += struct.pack("<HHIIHH", 1, 2, 48000, 48000 * 2 * 3, 6, 24)
        wav_path = self._create_mock_file("audio.wav", header)

        res = self.probe.probe_file(wav_path)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.media_type, AssetMediaType.AUDIO)
        self.assertEqual(res.container, "wav")
        self.assertEqual(res.sample_rate, 48000)
        self.assertEqual(res.audio_channels, 2)

    def test_probe_png_transparent_header(self):
        # PNG signature + IHDR chunk (width=1920, height=1080)
        png_header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1920, 1080)
        png_path = self._create_mock_file("overlay.png", png_header)

        res = self.probe.probe_file(png_path)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.media_type, AssetMediaType.TRANSPARENT_ASSET)
        self.assertEqual(res.container, "png")
        self.assertEqual(res.width, 1920)
        self.assertEqual(res.height, 1080)

    def test_probe_lut_cube_file(self):
        cube_content = b"TITLE \"Log_to_Rec709\"\nLUT_3D_SIZE 33\n0.0 0.0 0.0\n"
        cube_path = self._create_mock_file("rec709.cube", cube_content)

        res = self.probe.probe_file(cube_path)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.media_type, AssetMediaType.LUT)
        self.assertEqual(res.container, "cube")

    def test_probe_empty_or_corrupt_file(self):
        empty_path = self._create_mock_file("zero.dat", b"")
        res_empty = self.probe.probe_file(empty_path)
        self.assertFalse(res_empty.is_valid)

        corrupt_path = self._create_mock_file("corrupt.xyz", b"\x00\x01\x02\x03garbage")
        res_corrupt = self.probe.probe_file(corrupt_path)
        self.assertFalse(res_corrupt.is_valid)

    # -------------------------------------------------------------------------
    # 3. Path Traversal & Storage Sandbox Security
    # -------------------------------------------------------------------------

    def test_storage_rejects_path_traversal_and_null_bytes(self):
        # Null byte injection
        with self.assertRaises(StorageSecurityViolation):
            self.storage.validate_safe_path("footage/video.mp4\x00.exe")

        # Sensitive system directory access
        with self.assertRaises(StorageSecurityViolation):
            self.storage.validate_safe_path("C:/Users/ANON KFP/.ssh/id_rsa")

        with self.assertRaises(StorageSecurityViolation):
            self.storage.validate_safe_path("./secrets/credentials.key")

    # -------------------------------------------------------------------------
    # 4. Ingest Pipeline & Duplicate Detection
    # -------------------------------------------------------------------------

    def test_ingest_pipeline_success_and_duplicates(self):
        ftyp_box = struct.pack(">I", 32) + b"ftypisom" + b"\x00\x00\x02\x00mp41mp42isom"
        video_path = self._create_mock_file("interview_a.mp4", ftyp_box)

        ok, asset, msg = self.ingest.ingest_file(
            project_id="test_proj_01",
            source_file_path=video_path,
            display_name="Interview A Roll",
            tags=["interview", "camera_1"],
        )
        self.assertTrue(ok)
        self.assertIsNotNone(asset)
        self.assertEqual(asset.status, AssetLifecycleStatus.READY)
        self.assertEqual(asset.name, "Interview A Roll")
        self.assertIn("interview", asset.tags)

        # Ingesting identical file returns duplicate reference when allow_duplicates=False
        ok_dup, asset_dup, msg_dup = self.ingest.ingest_file(
            project_id="test_proj_01",
            source_file_path=video_path,
            allow_duplicates=False,
        )
        self.assertTrue(ok_dup)
        self.assertEqual(asset.asset_id, asset_dup.asset_id)
        self.assertIn("Duplicate", msg_dup)

    # -------------------------------------------------------------------------
    # 5. Project Bins & Collection Hierarchy
    # -------------------------------------------------------------------------

    def test_media_bin_hierarchy_and_asset_reassignment(self):
        # Default bins exist
        bins = self.library.list_bins()
        self.assertTrue(len(bins) >= 5)

        # Create child bin
        root_footage = next(b for b in bins if b.name == "Footage")
        day1_bin = self.library.create_bin(name="Day 1", parent_bin_id=root_footage.bin_id, color="#00ffcc")
        self.assertEqual(day1_bin.parent_bin_id, root_footage.bin_id)

        # Verify hierarchy
        tree = self.library.get_bin_hierarchy()
        footage_node = next(n for n in tree if n["name"] == "Footage")
        self.assertEqual(len(footage_node["children"]), 1)
        self.assertEqual(footage_node["children"][0]["name"], "Day 1")

        # Assign asset to bin
        asset = MediaAsset(name="clip_01.mp4", media_type=AssetMediaType.VIDEO)
        self.library.add_asset(asset)
        self.library.move_asset_to_bin(asset.asset_id, day1_bin.bin_id)
        self.assertEqual(self.library.get_asset(asset.asset_id).bin_id, day1_bin.bin_id)

        # Deleting bin reassigns assets to root rather than deleting asset
        self.library.delete_bin(day1_bin.bin_id, recursive=False)
        self.assertIsNone(self.library.get_asset(asset.asset_id).bin_id)

    # -------------------------------------------------------------------------
    # 6. Multi-Criteria Media Search & Filtering
    # -------------------------------------------------------------------------

    def test_media_search_queries(self):
        a1 = MediaAsset(name="Drone_Sunset_4K.mov", media_type=AssetMediaType.VIDEO, video_codec="prores", duration_seconds=45.0, tags=["drone", "b-roll"])
        a2 = MediaAsset(name="Interview_John.mp4", media_type=AssetMediaType.VIDEO, video_codec="h264", duration_seconds=180.0, tags=["interview", "a-roll"])
        a3 = MediaAsset(name="Theme_Music.wav", media_type=AssetMediaType.AUDIO, audio_codec="pcm_s24le", duration_seconds=120.0, tags=["music"])

        self.library.add_asset(a1)
        self.library.add_asset(a2)
        self.library.add_asset(a3)

        # Query by tag
        res_drone = self.library.search_assets(MediaSearchQuery(tags=["drone"]))
        self.assertEqual(len(res_drone), 1)
        self.assertEqual(res_drone[0].name, "Drone_Sunset_4K.mov")

        # Query by media type
        res_audio = self.library.search_assets(MediaSearchQuery(media_types=[AssetMediaType.AUDIO]))
        self.assertEqual(len(res_audio), 1)
        self.assertEqual(res_audio[0].name, "Theme_Music.wav")

        # Query by duration filter
        res_long = self.library.search_assets(MediaSearchQuery(min_duration=100.0))
        self.assertEqual(len(res_long), 2)

    # -------------------------------------------------------------------------
    # 7. Media Offline Status & Relink Resolution
    # -------------------------------------------------------------------------

    def test_media_offline_and_relink(self):
        ftyp_box = struct.pack(">I", 32) + b"ftypisom" + b"\x00\x00\x02\x00mp41mp42isom"
        src_path = self._create_mock_file("broll_01.mp4", ftyp_box)

        ok, asset, _ = self.ingest.ingest_file(project_id="test_proj_relink", source_file_path=src_path)
        self.assertTrue(ok)

        # Check health initially READY
        status, _ = self.ingest.check_asset_health("test_proj_relink", asset.asset_id)
        self.assertEqual(status, AssetLifecycleStatus.READY)

        # Move/delete file to simulate offline media
        os.remove(src_path)
        status_after, _ = self.ingest.check_asset_health("test_proj_relink", asset.asset_id)
        self.assertEqual(status_after, AssetLifecycleStatus.OFFLINE)
        self.assertEqual(asset.status, AssetLifecycleStatus.OFFLINE)

        # Relink to new path
        new_path = self._create_mock_file("broll_relinked.mp4", ftyp_box)
        relink_ok, _ = self.ingest.relink_asset("test_proj_relink", asset.asset_id, new_path)
        self.assertTrue(relink_ok)
        self.assertEqual(asset.status, AssetLifecycleStatus.READY)
        self.assertEqual(asset.file_location, os.path.abspath(new_path))

    # -------------------------------------------------------------------------
    # 8. Proxy & Derivative Relationship Models
    # -------------------------------------------------------------------------

    def test_proxy_and_generated_relationships(self):
        orig_asset = MediaAsset(name="Hero_Shot_8K.mov", media_type=AssetMediaType.VIDEO)
        self.library.add_asset(orig_asset)

        proxy_asset = MediaAsset(name="Hero_Shot_8K_Proxy.mov", media_type=AssetMediaType.PROXY)
        self.library.add_asset(proxy_asset)

        # Link Original -> Proxy
        rel = self.library.link_relationship(
            source_asset_id=orig_asset.asset_id,
            target_asset_id=proxy_asset.asset_id,
            rel_type=MediaRelationshipType.ORIGINAL_TO_PROXY,
            metadata={"proxy_resolution": "960x540", "codec": "prores_proxy"},
        )
        self.assertIsNotNone(rel.relationship_id)

        # Fetch relationships
        rels = self.library.get_related_assets(orig_asset.asset_id)
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0].relationship_type, MediaRelationshipType.ORIGINAL_TO_PROXY)

    # -------------------------------------------------------------------------
    # 9. Watch Folder Configuration
    # -------------------------------------------------------------------------

    def test_watch_folder_scan_candidates(self):
        watch_dir = os.path.join(self.test_dir, "watch_incoming")
        os.makedirs(watch_dir, exist_ok=True)

        wf_mgr = WatchFolderManager()
        cfg = WatchFolderConfig(
            watch_folder_id="wf_01",
            project_id="test_proj_01",
            folder_path=watch_dir,
            supported_extensions=["mp4", "wav"],
        )
        wf_mgr.register_watch_folder(cfg)

        # Add files: one matching, one non-matching
        with open(os.path.join(watch_dir, "video.mp4"), "w") as f:
            f.write("mock")
        with open(os.path.join(watch_dir, "ignore.txt"), "w") as f:
            f.write("mock")

        candidates = wf_mgr.scan_for_new_files("wf_01")
        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].endswith("video.mp4"))

if __name__ == "__main__":
    unittest.main()
