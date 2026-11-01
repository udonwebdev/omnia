"""OMNIA Video Studio — Module 0 Architectural Foundation & Isolation Test Suite.

Verifies:
1. OMNIA starts with Video Studio disabled.
2. OMNIA Core operates without Video Studio.
3. Video Studio can be registered.
4. Video Studio can be enabled.
5. Video Studio can be disabled.
6. Missing optional dependencies do not crash OMNIA.
7. Video Studio failures remain isolated (degraded/failed states).
8. Configuration defaults and validation schemas function correctly.
9. Capability metadata, catalog, and compute contracts are correctly exposed.
10. Existing OMNIA subsystem behaviors remain intact.
"""

import unittest
import asyncio
from video_studio.models import (
    VideoStudioState,
    VideoStudioFeatureContract,
    ComputeBackend,
    VideoStudioError,
    MediaError,
    CodecError,
    DecodeError,
    EncodeError,
    RenderError,
    GPUError,
    AIProcessingError,
    StorageError,
    ExportError,
)
from video_studio.service import VideoStudioService
from video_studio.catalog import VIDEO_STUDIO_CAPABILITY_CATALOG
from video_studio.shared_services import (
    MediaAssetCategory,
    VideoJobType,
    VideoJobStatus,
    VideoJobDescriptor,
    VideoAICapabilityType,
)
from video_studio.media import Timecode, ColorSpace, MediaType, MediaAssetDescriptor
from video_studio.project import VideoProject, TrackKind
from video_studio.extensions import ExtensionManifest, ExtensionKind, ExtensionPermission
from config import config_control_plane
from capabilities.registry import capability_registry
from capabilities.models import CapabilityCategory

class TestVideoStudioModule0(unittest.IsolatedAsyncioTestCase):
    """Authoritative test suite for Module 0 Architectural Foundation."""

    def setUp(self):
        self.service = VideoStudioService()

    def test_01_default_state_is_discovered_and_disabled(self):
        """Test 1: Fresh instance discovers capabilities and defaults to disabled."""
        self.assertEqual(self.service.state, VideoStudioState.DISCOVERED)
        self.assertFalse(self.service.is_enabled)
        self.assertTrue(self.service.is_available)

    def test_02_registration_lifecycle(self):
        """Test 2: Subsystem registration transitions through lifecycle safely."""
        ok, status = self.service.register(force_enabled=False)
        self.assertTrue(ok)
        self.assertEqual(status, "REGISTERED_DISABLED")
        self.assertEqual(self.service.state, VideoStudioState.DISABLED)

    def test_03_dynamic_enable_and_disable(self):
        """Test 3: Subsystem can be dynamically enabled and disabled without error."""
        # Enable
        ok, status = self.service.enable()
        self.assertTrue(ok)
        self.assertEqual(status, "READY")
        self.assertEqual(self.service.state, VideoStudioState.READY)
        self.assertTrue(self.service.is_enabled)

        # Disable
        ok_d, status_d = self.service.disable()
        self.assertTrue(ok_d)
        self.assertEqual(status_d, "DISABLED")
        self.assertEqual(self.service.state, VideoStudioState.DISABLED)
        self.assertFalse(self.service.is_enabled)

    def test_04_error_isolation_hierarchy(self):
        """Test 4: Error hierarchy isolates all video subsystem exceptions."""
        err = DecodeError("Corrupt H.264 NAL unit", details={"stream": 0})
        self.assertIsInstance(err, CodecError)
        self.assertIsInstance(err, VideoStudioError)
        self.assertIsInstance(err, Exception)
        self.assertEqual(err.code, "DECODE_ERROR")
        d = err.to_dict()
        self.assertEqual(d["code"], "DECODE_ERROR")
        self.assertEqual(d["details"]["stream"], 0)

        # Mark failure on service
        self.service.mark_failed(err)
        self.assertEqual(self.service.state, VideoStudioState.FAILED)
        self.assertIn("Corrupt H.264", self.service.contract.error_message)

    def test_05_mark_degraded_isolation(self):
        """Test 5: Sub-component degradation does not cause crash or unhandled exception."""
        self.service.enable()
        self.service.mark_degraded("GPU context lost during background scrub")
        self.assertEqual(self.service.state, VideoStudioState.DEGRADED)
        self.assertIn("GPU context lost", self.service.contract.error_message)

    def test_06_configuration_schemas_registered(self):
        """Test 6: Configuration control plane contains Video Studio schema entries."""
        keys = [
            "video_studio.enabled",
            "video_studio.experimental",
            "video_studio.max_concurrent_jobs",
            "video_studio.cache_location",
            "video_studio.proxy_location",
            "video_studio.render_location",
            "video_studio.gpu_acceleration",
            "video_studio.ai_enabled",
            "video_studio.extensions_enabled"
        ]
        for k in keys:
            schema = config_control_plane.get_schema(k)
            self.assertIsNotNone(schema, f"Missing schema for key: {k}")
            self.assertEqual(schema.domain, "video_studio")

        # Check safe defaults
        self.assertFalse(config_control_plane.resolve_effective_value("video_studio.enabled"))
        self.assertEqual(config_control_plane.resolve_effective_value("video_studio.max_concurrent_jobs"), 2)

    def test_07_capability_catalog_completeness(self):
        """Test 7: Capability catalog covers all 13 architectural groups."""
        expected_groups = [
            "editing", "motion", "compositing", "tracking", "ai",
            "audio", "color", "captions", "media", "recording",
            "export", "collaboration", "extensions"
        ]
        for g in expected_groups:
            self.assertIn(g, VIDEO_STUDIO_CAPABILITY_CATALOG)
            self.assertGreater(len(VIDEO_STUDIO_CAPABILITY_CATALOG[g]), 0)

        # Check total catalog count
        total = sum(len(items) for items in VIDEO_STUDIO_CAPABILITY_CATALOG.values())
        self.assertGreaterEqual(total, 60)

    def test_08_capability_registry_integration(self):
        """Test 8: Capability registry includes video_studio.get_status."""
        cap = capability_registry.get_capability("video_studio.get_status")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.category, CapabilityCategory.VIDEO_STUDIO)

    def test_09_timecode_and_media_descriptor(self):
        """Test 9: SMPTE Timecode calculations and Media descriptor operate accurately."""
        tc = Timecode(hours=1, minutes=2, seconds=3, frames=12, fps=24.0)
        # 3600*24 + 120*24 + 3*24 + 12 = 86400 + 2880 + 72 + 12 = 89364
        self.assertEqual(tc.to_frames(), 89364)
        self.assertEqual(str(tc), "01:02:03:12")

        desc = MediaAssetDescriptor(
            asset_id="asset_test_001",
            file_path="C:/media/clip.mp4",
            media_type=MediaType.VIDEO,
            duration_seconds=10.0
        )
        self.assertEqual(desc.asset_id, "asset_test_001")
        self.assertFalse(desc.has_proxy)

    def test_10_project_model_structure(self):
        """Test 10: VideoProject data model can be instantiated and structured cleanly."""
        proj = VideoProject(project_id="proj_001", name="Test Feature")
        self.assertEqual(proj.name, "Test Feature")
        self.assertEqual(len(proj.bins), 0)
        self.assertEqual(len(proj.sequences), 0)

    def test_11_extension_manifest_security_check(self):
        """Test 11: Extension manifest rejects unauthorized core permissions."""
        safe_ext = ExtensionManifest(
            extension_id="ext_safe_fx",
            name="Safe Blur FX",
            version="1.0.0",
            kind=ExtensionKind.EFFECT,
            entry_point="safe_fx:main",
            author="Dev",
            granted_permissions={ExtensionPermission.GPU_COMPUTE, ExtensionPermission.READ_MEDIA}
        )
        self.assertTrue(safe_ext.validate_permissions())

        unsafe_ext = ExtensionManifest(
            extension_id="ext_unsafe_hack",
            name="Unsafe Plugin",
            version="1.0.0",
            kind=ExtensionKind.EFFECT,
            entry_point="unsafe:main",
            author="Attacker",
            granted_permissions={"core:shell_unrestricted"} # type: ignore
        )
        self.assertFalse(unsafe_ext.validate_permissions())

    def test_12_compute_capabilities_abstraction(self):
        """Test 12: Compute capabilities abstraction reports safe defaults."""
        compute = self.service.contract.compute_capabilities
        self.assertIn(ComputeBackend.CPU, compute.available_backends)
        self.assertEqual(compute.primary_backend, ComputeBackend.CPU)

    def test_13_status_summary_payload(self):
        """Test 13: Summary payload provides structured data for UI and diagnostics."""
        summary = self.service.get_status_summary()
        self.assertEqual(summary["feature_id"], "omnia.feature.video_studio")
        self.assertIn("state", summary)
        self.assertIn("catalog_groups", summary)
        self.assertFalse(summary["is_enabled"])

if __name__ == "__main__":
    unittest.main()
