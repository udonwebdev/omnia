"""OMNIA Video Studio — Module 38 Test Suite: Project Packaging, Media Archiving & Portable Workflow.

Verifies:
1. Dependency discovery (identifies sequences, media assets, audio, graphics, missing, and excluded).
2. Package creation and versioned PackageManifest generation with SHA-256 checksums.
3. Cryptographic integrity verification (valid vs corrupt checksums).
4. Detection of missing manifest or corrupted/truncated archives.
5. Path traversal (Zip Slip) security rejection.
6. Safe extraction with collision prevention (SAFE_NO_OVERWRITE policy).
7. Dry-run inspection without disk modification.
8. Portable asset relinking upon extraction into new directory root.
9. Project snapshot lifecycle (creation, inspection, revision tracking).
10. VideoStudioCapabilityRegistry registration for all Module 38 capabilities.
"""

import unittest
import os
import tempfile
import zipfile
import json
import hashlib
import time

from video_studio.package_models import (
    PACKAGE_FORMAT_VERSION,
    PackageType,
    ArchiveFormat,
    DependencyCategory,
    ExtractionPolicy,
    PackagedFileEntry,
    PackageManifest,
    ExtractionResult,
    ProjectSnapshot,
)
from video_studio.package_engine import PackageEngine, package_engine, compute_sha256
from video_studio.package_service import PackageService, package_service
from video_studio.media_models import MediaAsset, AssetMediaType
from video_studio.media_library import ProjectMediaLibrary, media_library_registry
from video_studio.timeline_models import VideoSequence
from video_studio.timeline_service import TimelineService
from video_studio.registry import video_studio_capability_registry


class TestVideoStudioModule38(unittest.TestCase):
    """Module 38 Unit & Integration Tests."""

    def setUp(self):
        self.engine = PackageEngine()
        self.timeline_service = TimelineService()
        self.service = PackageService(
            engine=self.engine,
            tl_service=self.timeline_service,
        )
        self.temp_dir = tempfile.TemporaryDirectory()

        # Set up a mock project with real media files on disk
        self.project_id = "proj_pack_test"
        self.library = media_library_registry.get_or_create(self.project_id)

        # Create source video file
        self.media_file_1 = os.path.join(self.temp_dir.name, "clip_intro.mp4")
        with open(self.media_file_1, "wb") as f:
            f.write(b"MOCK_VIDEO_DATA_ATOM_HEADER_BYTES_12345")

        self.asset_1 = MediaAsset(
            asset_id="asset_intro_01",
            project_id=self.project_id,
            file_location=self.media_file_1,
            original_name="clip_intro.mp4",
            media_type=AssetMediaType.VIDEO,
            size_bytes=len(b"MOCK_VIDEO_DATA_ATOM_HEADER_BYTES_12345"),
            content_hash_sha256=compute_sha256(self.media_file_1),
        )
        self.library.add_asset(self.asset_1)

        # Create sequence in timeline service
        self.seq = self.timeline_service.create_sequence(self.project_id, "Main Edit Sequence")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_dependency_discovery(self):
        """Dependency discovery correctly gathers sequences and assets while identifying missing and excluded."""
        # Add a missing asset (file points to non-existent path)
        missing_asset = MediaAsset(
            asset_id="asset_ghost",
            project_id=self.project_id,
            file_location=os.path.join(self.temp_dir.name, "does_not_exist.mp4"),
            media_type=AssetMediaType.VIDEO,
        )
        self.library.add_asset(missing_asset)

        inc, miss, exc = self.engine.discover_dependencies(
            project_id=self.project_id,
            media_library=self.library,
            timeline_svc=self.timeline_service,
            package_type=PackageType.PORTABLE_PROJECT,
        )

        inc_ids = [item["asset_id"] for item in inc]
        miss_ids = [item["asset_id"] for item in miss]

        self.assertIn(self.seq.sequence_id, inc_ids, "Sequence should be included.")
        self.assertIn("asset_intro_01", inc_ids, "Existing asset should be included.")
        self.assertIn("asset_ghost", miss_ids, "Missing file should be reported as missing dependency.")

    def test_02_package_creation_and_manifest(self):
        """Package creation generates a valid ZIP archive containing manifest.json and media entries."""
        pkg_path = os.path.join(self.temp_dir.name, "output_package.zip")
        manifest = self.service.create_project_package(
            project_id=self.project_id,
            output_archive_path=pkg_path,
            project_name="Feature Film Package",
            package_type=PackageType.PORTABLE_PROJECT,
            description="Production handoff bundle",
        )

        self.assertTrue(os.path.exists(pkg_path))
        self.assertEqual(manifest.format_version, PACKAGE_FORMAT_VERSION)
        self.assertEqual(manifest.project_id, self.project_id)
        self.assertGreaterEqual(manifest.file_count, 2)  # 1 sequence + 1 media file
        self.assertIsNotNone(manifest.package_checksum_sha256)

        # Verify entry in manifest
        media_entry = next(e for e in manifest.entries if e.asset_id == "asset_intro_01")
        self.assertEqual(media_entry.relative_path, "media/clip_intro.mp4")
        self.assertEqual(media_entry.sha256_checksum, compute_sha256(self.media_file_1))

    def test_03_integrity_verification_success_and_tampering(self):
        """Integrity verification passes for intact archives and detects corrupted file hashes."""
        pkg_path = os.path.join(self.temp_dir.name, "intact_package.zip")
        self.service.create_project_package(self.project_id, pkg_path)

        # 1. Clean verification
        valid, errs, manifest = self.service.inspect_package(pkg_path)
        self.assertTrue(valid)
        self.assertEqual(len(errs), 0)
        self.assertIsNotNone(manifest)

        # 2. Tampered verification: overwrite one file in the zip with different content
        tampered_pkg = os.path.join(self.temp_dir.name, "tampered_package.zip")
        with zipfile.ZipFile(pkg_path, "r") as zf_in, zipfile.ZipFile(tampered_pkg, "w") as zf_out:
            for item in zf_in.infolist():
                data = zf_in.read(item.filename)
                if item.filename == "media/clip_intro.mp4":
                    data = b"TAMPERED_MALICIOUS_DIFFERENT_CONTENT"
                zf_out.writestr(item, data)

        valid_t, errs_t, _ = self.service.inspect_package(tampered_pkg)
        self.assertFalse(valid_t)
        self.assertGreater(len(errs_t), 0)
        self.assertTrue(any("Checksum mismatch" in e for e in errs_t))

    def test_04_missing_manifest_and_corrupt_zip_detection(self):
        """Package verification rejects bad zip files or archives without manifest.json."""
        # 1. Corrupt random data
        bad_zip = os.path.join(self.temp_dir.name, "corrupt.zip")
        with open(bad_zip, "wb") as f:
            f.write(b"NOT_A_ZIP_RANDOM_GARBAGE")
        valid, errs, _ = self.service.inspect_package(bad_zip)
        self.assertFalse(valid)
        self.assertIn("Invalid or truncated ZIP", errs[0])

        # 2. Zip without manifest.json
        no_manifest_zip = os.path.join(self.temp_dir.name, "no_manifest.zip")
        with zipfile.ZipFile(no_manifest_zip, "w") as zf:
            zf.writestr("test.txt", b"hello world")
        valid_m, errs_m, _ = self.service.inspect_package(no_manifest_zip)
        self.assertFalse(valid_m)
        self.assertTrue(any("Missing manifest.json" in e for e in errs_m))

    def test_05_path_traversal_zip_slip_security_block(self):
        """Extraction strictly blocks malicious archives attempting path traversal (Zip Slip)."""
        malicious_pkg = os.path.join(self.temp_dir.name, "malicious_zip_slip.zip")
        dest_root = os.path.join(self.temp_dir.name, "safe_extract_dest")

        # Create zip with valid manifest and malicious traversal path
        manifest = PackageManifest(
            project_id="evil_proj",
            entries=[
                PackagedFileEntry(
                    asset_id="evil_file",
                    relative_path="../evil_escape.txt",
                    size_bytes=len(b"pwned"),
                    sha256_checksum=hashlib.sha256(b"pwned").hexdigest(),
                )
            ]
        )
        with zipfile.ZipFile(malicious_pkg, "w") as zf:
            zf.writestr("manifest.json", json.dumps(manifest.to_dict()))
            zf.writestr("../evil_escape.txt", b"pwned")

        res = self.service.restore_project_package(malicious_pkg, dest_root)
        self.assertFalse(res.success)
        self.assertTrue(any("Zip Slip path traversal blocked" in e for e in res.errors))

    def test_06_dry_run_extraction(self):
        """Dry-run extraction validates package without writing files to disk."""
        pkg_path = os.path.join(self.temp_dir.name, "dry_run.zip")
        self.service.create_project_package(self.project_id, pkg_path)

        dest_root = os.path.join(self.temp_dir.name, "dry_run_target")
        res = self.service.restore_project_package(pkg_path, dest_root, dry_run=True)

        self.assertTrue(res.success)
        self.assertGreater(res.extracted_files_count, 0)
        # Verify directory was NOT populated
        self.assertFalse(os.path.exists(dest_root), "Dry-run must not create destination files.")

    def test_07_safe_extraction_and_collision_prevention(self):
        """Safe policy prevents overwriting existing files in destination directory."""
        pkg_path = os.path.join(self.temp_dir.name, "safe_pkg.zip")
        self.service.create_project_package(self.project_id, pkg_path)

        dest_root = os.path.join(self.temp_dir.name, "collision_dest")
        os.makedirs(os.path.join(dest_root, "media"), exist_ok=True)
        # Pre-create colliding file
        with open(os.path.join(dest_root, "media", "clip_intro.mp4"), "wb") as f:
            f.write(b"PRE_EXISTING_FILE")

        res = self.service.restore_project_package(
            pkg_path,
            dest_root,
            policy=ExtractionPolicy.SAFE_NO_OVERWRITE,
        )
        self.assertFalse(res.success)
        self.assertTrue(any("File collision under safe policy" in e for e in res.errors))

    def test_08_restoration_and_portable_relinking(self):
        """Restoring a package updates project asset file locations to point to the newly extracted paths."""
        pkg_path = os.path.join(self.temp_dir.name, "portable_bundle.zip")
        self.service.create_project_package(self.project_id, pkg_path)

        dest_root = os.path.join(self.temp_dir.name, "machine_b_restoration")
        res = self.service.restore_project_package(
            pkg_path,
            dest_root,
            policy=ExtractionPolicy.OVERWRITE_EXISTING,
        )

        self.assertTrue(res.success)
        self.assertGreater(res.extracted_files_count, 0)
        self.assertGreater(res.relinked_assets_count, 0)

        # Check library asset path
        library = media_library_registry.get_or_create(self.project_id)
        asset = library.get_asset("asset_intro_01")
        self.assertIsNotNone(asset)
        expected_new_path = os.path.join(os.path.abspath(dest_root), "media", "clip_intro.mp4")
        self.assertEqual(os.path.abspath(asset.file_location), expected_new_path)
        self.assertTrue(os.path.exists(asset.file_location))

    def test_09_project_snapshot_management(self):
        """Named project snapshots are created, cataloged, and retrieved with checksums."""
        snap_dir = os.path.join(self.temp_dir.name, "snapshots")
        os.makedirs(snap_dir, exist_ok=True)

        snapshot = self.service.create_snapshot(
            project_id=self.project_id,
            snapshot_name="Rough Cut v1 Checkpoint",
            archive_dir=snap_dir,
            description="Milestone snapshot before color pass",
        )

        self.assertEqual(snapshot.project_id, self.project_id)
        self.assertEqual(snapshot.name, "Rough Cut v1 Checkpoint")
        self.assertTrue(os.path.exists(snapshot.archive_path))
        self.assertGreater(snapshot.size_bytes, 0)
        self.assertIsNotNone(snapshot.sha256_checksum)

        # Query catalog
        snaps = self.service.list_snapshots(self.project_id)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(self.service.get_snapshot(snapshot.snapshot_id).name, "Rough Cut v1 Checkpoint")

    def test_10_capability_registry_entries(self):
        """Module 38 capabilities are registered and available in the capability registry."""
        caps = [
            "video.packaging.portable_archive",
            "video.packaging.integrity_verification",
            "video.packaging.safe_restoration",
            "video.packaging.project_snapshots",
        ]
        for cap_id in caps:
            cap = video_studio_capability_registry.get(cap_id)
            self.assertIsNotNone(cap, f"Capability {cap_id} must be registered.")
            self.assertEqual(cap.implementation_state.value, "IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
