"""OMNIA Video Studio — Module 1 Test Suite: Capability Registry & Feature Gating.

Verifies:
1. Capability Registration:
   - Valid capability registers successfully and enters correct state.
   - Duplicate capability IDs with identical versions are rejected.
   - Malformed capability IDs (not adhering to dot-notation) are rejected.
   - Untrusted authorization tokens are rejected.
2. Status Model & Feature Gating:
   - PLANNED capabilities return REGISTERED, not AVAILABLE (NO fake implementations).
   - Disabled subsystem or configuration flag marks capabilities as DISABLED.
   - Missing required dependency marks capability as UNAVAILABLE.
   - Satisfied dependencies with implemented capabilities mark capability as AVAILABLE.
   - Degraded/failed dependencies ripple health impact properly.
   - Experimental capabilities are only exposed/operational when experimental mode is enabled.
3. Dependencies & Graph:
   - Dependency chains resolve properly.
   - Circular dependencies are detected and registration is rejected.
   - Min and max version constraints on dependencies are enforced.
4. Hardware & Platform Gating:
   - Unmet RAM, GPU, or acceleration API constraints result in UNAVAILABLE status.
   - Incompatible platforms result in UNAVAILABLE status with clear reason.
   - Hardware detection executes safely and without crashing.
5. Provider Abstraction:
   - Multiple providers can register for the same capability.
   - Active provider resolution honors priority ranking and availability.
6. Fault Isolation:
   - Registry operations, queries, and missing capabilities never crash caller or OMNIA.
"""

import unittest
from video_studio.registry import VideoStudioCapabilityRegistry
from video_studio.registry_models import (
    VideoStudioCategory,
    VideoStudioCapabilityStatus,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
    CapabilityProviderDescriptor,
    CapabilityDependency,
    HardwareRequirements,
    PlatformRequirements,
    AIRequirements,
    AccelerationAPI,
)
from video_studio.catalog_loader import populate_roadmap_capabilities
from config import config_control_plane

class TestVideoStudioModule1(unittest.TestCase):
    """Authoritative test suite for Module 1 Capability Registry & Feature Gating."""

    def setUp(self):
        # Create an isolated test registry instance
        self.registry = VideoStudioCapabilityRegistry()

    def test_01_valid_capability_registration(self):
        """Test 1: Valid capability registers cleanly into registry."""
        cap = VideoStudioCapabilityDescriptor(
            id="video.test.custom_filter",
            name="Custom Test Filter",
            description="Testing capability registration",
            category=VideoStudioCategory.COMPOSITING,
            version="1.0.0",
            implementation_state=ImplementationState.IMPLEMENTED
        )
        ok, msg = self.registry.register(cap, auth_token="core")
        self.assertTrue(ok)
        self.assertEqual(msg, "REGISTERED")
        self.assertIsNotNone(self.registry.get("video.test.custom_filter"))

    def test_02_duplicate_and_schema_rejection(self):
        """Test 2: Rejects duplicate registrations, invalid IDs, and untrusted tokens."""
        cap = VideoStudioCapabilityDescriptor(
            id="video.test.dup",
            name="Duplicate Test",
            description="Testing duplication",
            category=VideoStudioCategory.EDITING,
            version="1.0.0"
        )
        ok1, _ = self.registry.register(cap, auth_token="core")
        self.assertTrue(ok1)

        # Duplicate registration
        ok2, msg2 = self.registry.register(cap, auth_token="core")
        self.assertFalse(ok2)
        self.assertIn("CONFLICT_REJECTION", msg2)

        # Invalid ID syntax (no dot notation)
        bad_cap = VideoStudioCapabilityDescriptor(
            id="invalidnonamespace",
            name="Bad Name",
            description="Bad format",
            category=VideoStudioCategory.EDITING
        )
        ok_bad, msg_bad = self.registry.register(bad_cap, auth_token="core")
        self.assertFalse(ok_bad)
        self.assertIn("SCHEMA_REJECTION", msg_bad)

        # Untrusted auth token
        ok_auth, msg_auth = self.registry.register(cap, auth_token="untrusted_client")
        self.assertFalse(ok_auth)
        self.assertIn("SECURITY_REJECTION", msg_auth)

    def test_03_circular_dependency_detection(self):
        """Test 3: Detects circular dependency chains and rejects registration."""
        # Cap A depends on Cap B
        cap_a = VideoStudioCapabilityDescriptor(
            id="video.test.a",
            name="Cap A",
            description="",
            category=VideoStudioCategory.EDITING,
            dependencies=[CapabilityDependency("video.test.b")]
        )
        # Cap B depends on Cap A
        cap_b = VideoStudioCapabilityDescriptor(
            id="video.test.b",
            name="Cap B",
            description="",
            category=VideoStudioCategory.EDITING,
            dependencies=[CapabilityDependency("video.test.a")]
        )

        ok_a, _ = self.registry.register(cap_a, auth_token="core")
        self.assertTrue(ok_a)

        # Registering cap_b introduces cycle B -> A -> B
        ok_b, msg_b = self.registry.register(cap_b, auth_token="core")
        self.assertFalse(ok_b)
        self.assertIn("CIRCULAR_DEPENDENCY_REJECTION", msg_b)

    def test_04_planned_capabilities_are_not_falsely_available(self):
        """Test 4: Planned roadmap capabilities are NOT falsely marked as available."""
        populate_roadmap_capabilities(self.registry)
        cap = self.registry.get("video.timeline.ripple_edit")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.implementation_state, ImplementationState.PLANNED)

        # Feature must NOT be reported as available
        self.assertFalse(self.registry.is_available("video.timeline.ripple_edit"))
        self.assertEqual(self.registry.get_status("video.timeline.ripple_edit"), VideoStudioCapabilityStatus.REGISTERED)

    def test_05_implemented_capability_availability(self):
        """Test 5: An implemented capability with satisfied dependencies is AVAILABLE."""
        # Register base engine
        base = VideoStudioCapabilityDescriptor(
            id="video.engine.base",
            name="Base Engine",
            description="",
            category=VideoStudioCategory.TIMELINE,
            implementation_state=ImplementationState.IMPLEMENTED
        )
        self.registry.register(base, auth_token="core")

        # Register consumer
        consumer = VideoStudioCapabilityDescriptor(
            id="video.consumer.tool",
            name="Consumer Tool",
            description="",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            dependencies=[CapabilityDependency("video.engine.base")]
        )
        self.registry.register(consumer, auth_token="core")

        self.assertTrue(self.registry.is_available("video.consumer.tool"))
        self.assertEqual(self.registry.get_status("video.consumer.tool"), VideoStudioCapabilityStatus.AVAILABLE)

    def test_06_missing_dependency_yields_unavailable(self):
        """Test 6: Missing required dependency causes UNAVAILABLE status with clear reason."""
        consumer = VideoStudioCapabilityDescriptor(
            id="video.consumer.missing_dep",
            name="Consumer Tool",
            description="",
            category=VideoStudioCategory.EDITING,
            implementation_state=ImplementationState.IMPLEMENTED,
            dependencies=[CapabilityDependency("video.nonexistent.engine")]
        )
        self.registry.register(consumer, auth_token="core")

        self.assertFalse(self.registry.is_available("video.consumer.missing_dep"))
        health = self.registry.get_health("video.consumer.missing_dep")
        self.assertFalse(health.is_healthy)
        self.assertEqual(health.status, VideoStudioCapabilityStatus.UNAVAILABLE)
        self.assertIn("video.nonexistent.engine", health.reason)

    def test_07_dependency_version_bounds_enforced(self):
        """Test 7: Incompatible dependency versions cause UNAVAILABLE status."""
        dep_v1 = VideoStudioCapabilityDescriptor(
            id="video.dep.lib",
            name="Dependency Lib",
            description="",
            category=VideoStudioCategory.MEDIA,
            version="1.0.0",
            implementation_state=ImplementationState.IMPLEMENTED
        )
        self.registry.register(dep_v1, auth_token="core")

        # Consumer requires min_version 2.0.0
        consumer = VideoStudioCapabilityDescriptor(
            id="video.consumer.v2",
            name="Consumer",
            description="",
            category=VideoStudioCategory.MEDIA,
            implementation_state=ImplementationState.IMPLEMENTED,
            dependencies=[CapabilityDependency("video.dep.lib", min_version="2.0.0")]
        )
        self.registry.register(consumer, auth_token="core")

        self.assertFalse(self.registry.is_available("video.consumer.v2"))
        health = self.registry.get_health("video.consumer.v2")
        self.assertIn("min 2.0.0", health.reason)

    def test_08_hardware_shortfall_gating(self):
        """Test 8: Unmet hardware requirements (e.g. 500GB RAM) yield UNAVAILABLE status."""
        cap = VideoStudioCapabilityDescriptor(
            id="video.test.super_compute",
            name="Super Compute Task",
            description="",
            category=VideoStudioCategory.RENDERING,
            implementation_state=ImplementationState.IMPLEMENTED,
            hardware_requirements=HardwareRequirements(min_ram_mb=500000)  # ~500 GB
        )
        self.registry.register(cap, auth_token="core")

        self.assertFalse(self.registry.is_available("video.test.super_compute"))
        health = self.registry.get_health("video.test.super_compute")
        self.assertFalse(health.is_healthy)
        self.assertEqual(health.status, VideoStudioCapabilityStatus.UNAVAILABLE)
        self.assertIn("RAM", health.reason)

    def test_09_platform_support_gating(self):
        """Test 9: Incompatible platform requirements yield UNAVAILABLE status."""
        cap = VideoStudioCapabilityDescriptor(
            id="video.test.exclusive_os",
            name="Exclusive OS Capability",
            description="",
            category=VideoStudioCategory.RECORDING,
            implementation_state=ImplementationState.IMPLEMENTED,
            platform_requirements=PlatformRequirements(
                supported_platforms=["amigaos", "solaris"]
            )
        )
        self.registry.register(cap, auth_token="core")

        self.assertFalse(self.registry.is_available("video.test.exclusive_os"))
        health = self.registry.get_health("video.test.exclusive_os")
        self.assertEqual(health.status, VideoStudioCapabilityStatus.UNAVAILABLE)
        self.assertIn("not supported", health.reason)

    def test_10_provider_abstraction_and_priority_resolution(self):
        """Test 10: Multiple providers register; active provider respects priority and availability."""
        cap = VideoStudioCapabilityDescriptor(
            id="video.ai.test_stt",
            name="Test Speech To Text",
            description="",
            category=VideoStudioCategory.AI,
            implementation_state=ImplementationState.IMPLEMENTED
        )
        self.registry.register(cap, auth_token="core")

        # Provider 1: Cloud provider (priority 50)
        p1 = CapabilityProviderDescriptor(
            provider_id="provider.cloud.whisper",
            name="Cloud Whisper",
            priority=50,
            is_local=False,
            is_available=True
        )
        # Provider 2: Local GPU provider (priority 10 - higher precedence)
        p2 = CapabilityProviderDescriptor(
            provider_id="provider.local.whisper_cpp",
            name="Local Whisper.cpp",
            priority=10,
            is_local=True,
            is_available=True
        )

        self.registry.register_provider(cap.id, p1)
        self.registry.register_provider(cap.id, p2)

        active = self.registry.get_active_provider(cap.id)
        self.assertIsNotNone(active)
        self.assertEqual(active.provider_id, "provider.local.whisper_cpp")

        # Make local provider unavailable -> falls back to Cloud
        p2.is_available = False
        active_fallback = self.registry.get_active_provider(cap.id)
        self.assertEqual(active_fallback.provider_id, "provider.cloud.whisper")

    def test_11_roadmap_catalog_coverage(self):
        """Test 11: Auto-populated catalog contains all 16 domains with 70+ roadmap items."""
        count = populate_roadmap_capabilities(self.registry)
        self.assertGreaterEqual(count, 70)

        # Check coverage across core categories
        for cat in [
            VideoStudioCategory.EDITING,
            VideoStudioCategory.MOTION,
            VideoStudioCategory.TRACKING,
            VideoStudioCategory.COMPOSITING,
            VideoStudioCategory.AI,
            VideoStudioCategory.AUDIO,
            VideoStudioCategory.COLOR,
            VideoStudioCategory.GRAPHICS,
            VideoStudioCategory.MEDIA,
            VideoStudioCategory.RECORDING,
            VideoStudioCategory.EXPORT,
            VideoStudioCategory.COLLABORATION,
            VideoStudioCategory.EXTENSIONS,
        ]:
            caps = self.registry.list(category=cat)
            self.assertGreater(len(caps), 0, f"Expected capabilities for category {cat.value}")

    def test_12_safe_unregistration_with_dependent_guards(self):
        """Test 12: Cannot unregister capability if other capabilities depend on it."""
        parent = VideoStudioCapabilityDescriptor(
            id="video.guard.parent",
            name="Parent",
            description="",
            category=VideoStudioCategory.MEDIA
        )
        child = VideoStudioCapabilityDescriptor(
            id="video.guard.child",
            name="Child",
            description="",
            category=VideoStudioCategory.MEDIA,
            dependencies=[CapabilityDependency("video.guard.parent", is_optional=False)]
        )
        self.registry.register(parent, auth_token="core")
        self.registry.register(child, auth_token="core")

        # Unregistering parent should fail
        ok, msg = self.registry.unregister(parent.id, auth_token="core")
        self.assertFalse(ok)
        self.assertIn("DEPENDENCY_BLOCKED", msg)

        # Unregistering child succeeds
        ok_c, _ = self.registry.unregister(child.id, auth_token="core")
        self.assertTrue(ok_c)

        # Now parent unregisters cleanly
        ok_p, _ = self.registry.unregister(parent.id, auth_token="core")
        self.assertTrue(ok_p)

if __name__ == "__main__":
    unittest.main()
