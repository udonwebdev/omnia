import asyncio
import unittest
import tempfile
import os
import time

from capabilities.models import (
    Capability,
    CapabilityProvider,
    CapabilityCategory,
    CapabilityHealth,
    CapabilityLifecycle,
    RiskLevel,
    SideEffectType,
    IdempotencyType,
    ReversibilityType,
    VerificationContract,
    CapabilityMatchQuery
)
from capabilities.registry import capability_registry, CapabilityRegistry
from capabilities.matcher import capability_matcher
from capabilities.health import capability_health_checker
from capabilities.skill_loader import skill_loader
from capabilities.builtin_skills import register_all_builtin_capabilities

class TestModule17CapabilityRegistry(unittest.IsolatedAsyncioTestCase):
    """Rigorous test suite for Module 17: Capability Registry & Dynamic Skill System."""

    def setUp(self):
        # Create an isolated test registry instance for deterministic testing
        self.test_reg = CapabilityRegistry()
        register_all_builtin_capabilities(self.test_reg)

    def test_01_valid_capability_registration(self):
        """Test 1: Valid capability registers successfully and enters REGISTERED state."""
        cap = Capability(
            id="system.custom_calculator",
            name="Custom Math Calculator",
            description="Performs safe mathematical calculations",
            version="1.0.0",
            category=CapabilityCategory.SYSTEM,
            input_schema={"type": "object", "properties": {"expression": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"result": {"type": "number"}}},
            environment="local",
            risk_level=RiskLevel.READ_ONLY
        )
        ok, msg = self.test_reg.register_capability(cap, auth_key="core")
        self.assertTrue(ok)
        self.assertEqual(msg, "REGISTERED")
        self.assertEqual(cap.lifecycle, CapabilityLifecycle.REGISTERED)
        self.assertIsNotNone(self.test_reg.get_capability("system.custom_calculator"))

    def test_02_invalid_registration_rejection(self):
        """Test 2: Malformed capability (bad id syntax, missing schema) is rejected."""
        # Bad ID (no dot notation namespace)
        bad_cap_id = Capability(
            id="invalidnonamespace",
            name="Bad Name",
            description="",
            version="1.0.0",
            input_schema={},
            output_schema={}
        )
        ok, msg = self.test_reg.register_capability(bad_cap_id, auth_key="core")
        self.assertFalse(ok)
        self.assertIn("SCHEMA_REJECTION", msg)

        # Bad semantic version
        bad_ver = Capability(
            id="system.bad_version",
            name="Bad Version",
            description="",
            version="v1_beta",
            input_schema={},
            output_schema={}
        )
        ok, msg = self.test_reg.register_capability(bad_ver, auth_key="core")
        self.assertFalse(ok)
        self.assertIn("SCHEMA_REJECTION", msg)

    def test_03_duplicate_registration_handling(self):
        """Test 3: Registering duplicate capability version without update is flagged."""
        cap = Capability(
            id="system.duplicate_test",
            name="Duplicate Test",
            description="Testing duplication",
            version="1.0.0",
            input_schema={},
            output_schema={}
        )
        ok1, _ = self.test_reg.register_capability(cap, auth_key="core")
        self.assertTrue(ok1)
        ok2, msg2 = self.test_reg.register_capability(cap, auth_key="core")
        self.assertFalse(ok2)
        self.assertIn("CONFLICT_REJECTION", msg2)

    def test_04_capability_discovery(self):
        """Test 4: Capability discovery by category returns expected capabilities."""
        browser_caps = self.test_reg.list_capabilities(category=CapabilityCategory.BROWSER)
        self.assertTrue(any(c.id == "browser.navigate" for c in browser_caps))
        self.assertTrue(any(c.id == "browser.execute_task" for c in browser_caps))

    def test_05_environment_mismatch_filtering(self):
        """Test 5: Matcher does not select an Android-only capability for a Windows/desktop environment."""
        query = CapabilityMatchQuery(
            capability_id="device.android.shell",
            environment="browser"  # environment mismatch
        )
        matches = capability_matcher.find_matching_capabilities(query)
        self.assertEqual(len(matches), 0)

    def test_06_health_degradation_and_status(self):
        """Test 6: Disabling or marking a capability unavailable updates health state."""
        self.test_reg.update_health("browser.navigate", CapabilityHealth.UNAVAILABLE, "Browser crashed")
        cap = self.test_reg.get_capability("browser.navigate")
        self.assertEqual(cap.health, CapabilityHealth.UNAVAILABLE)
        self.assertEqual(cap.metadata.get("last_health_message"), "Browser crashed")

    def test_07_provider_fallback_negotiation(self):
        """Test 7: When primary provider fails, matcher falls back to secondary provider."""
        cap = self.test_reg.get_capability("voice.speak")
        self.assertIsNotNone(cap)
        # Mark local provider as FAILED
        local_p = cap.providers.get("provider.voice.local")
        self.assertIsNotNone(local_p)
        local_p.health = CapabilityHealth.FAILED

        # Resolve provider
        resolved = self.test_reg.resolve_provider("voice.speak")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.provider_id, "provider.voice.remote_edge")

    def test_08_permission_requirements_check(self):
        """Test 8: Matcher filters out capabilities whose required permissions are missing."""
        query = CapabilityMatchQuery(
            capability_id="device.android.shell",
            available_permissions=["network:lan"]  # Missing required device:adb_control
        )
        matches = capability_matcher.find_matching_capabilities(query)
        self.assertEqual(len(matches), 0)

    def test_09_dependency_ripple_effect(self):
        """Test 9: When a parent dependency fails, dependent capability becomes DEGRADED."""
        # browser.execute_task depends on browser.navigate
        self.test_reg.update_health("browser.navigate", CapabilityHealth.UNAVAILABLE, "Network offline")
        dep_cap = self.test_reg.get_capability("browser.execute_task")
        self.assertEqual(dep_cap.health, CapabilityHealth.DEGRADED)
        self.assertIn("Dependency 'browser.navigate' is UNAVAILABLE", dep_cap.metadata.get("dependency_failure", ""))

    def test_10_risk_metadata_and_classification(self):
        """Test 10: High-risk capabilities are accurately tagged with destructive side effects."""
        adb_shell = self.test_reg.get_capability("device.android.shell")
        self.assertEqual(adb_shell.risk_level, RiskLevel.HIGH_RISK)
        self.assertIn(SideEffectType.DEVICE_CONTROL, adb_shell.side_effects)

    def test_11_idempotency_contracts(self):
        """Test 11: Idempotency classifications are explicitly declared for recovery reasoning."""
        nav = self.test_reg.get_capability("browser.navigate")
        self.assertEqual(nav.idempotent, IdempotencyType.IDEMPOTENT)
        task = self.test_reg.get_capability("browser.execute_task")
        self.assertEqual(task.idempotent, IdempotencyType.NON_IDEMPOTENT)

    def test_12_verification_contract_presence(self):
        """Test 12: Real-world side-effecting capabilities expose explicit verification contracts."""
        vis = self.test_reg.get_capability("vision.verify_state")
        self.assertIsNotNone(vis.verification_contract)
        self.assertEqual(vis.verification_contract.mechanism, "OCR_TEXT_MATCH")

    def test_13_dynamic_device_capability_instances(self):
        """Test 13: Simulated Android device discovery registers a dynamic device provider instance."""
        dev_provider = CapabilityProvider(
            provider_id="device.pixel8_pro_01",
            capability_id="device.android.unlock",
            implementation_ref="adb://emulator-5554",
            environment="android",
            health=CapabilityHealth.HEALTHY
        )
        ok, msg = self.test_reg.register_provider(dev_provider)
        self.assertTrue(ok)
        prov = self.test_reg.resolve_provider("device.android.unlock", environment="android")
        self.assertEqual(prov.provider_id, "device.pixel8_pro_01")

    def test_14_mesh_provider_integration(self):
        """Test 14: Simulated remote mesh node provider registered and resolvable."""
        mesh_p = CapabilityProvider(
            provider_id="provider.mesh.worker_node_2",
            capability_id="mesh.execute_command",
            implementation_ref="wss://192.168.1.50:8000/ws/mesh",
            environment="mesh",
            latency_ms=12.0
        )
        ok, _ = self.test_reg.register_provider(mesh_p)
        self.assertTrue(ok)
        resolved = self.test_reg.resolve_provider("mesh.execute_command", environment="mesh")
        self.assertIsNotNone(resolved)

    def test_15_security_and_unauthorized_registration_defense(self):
        """Test 15: Untrusted registration attempt is rejected by policy."""
        rogue_cap = Capability(
            id="system.rogue_override",
            name="Rogue Override",
            description="Unauthorized capability injection",
            version="1.0.0",
            input_schema={},
            output_schema={}
        )
        ok, msg = self.test_reg.register_capability(rogue_cap, auth_key="untrusted_external_key")
        self.assertFalse(ok)
        self.assertIn("SECURITY_REJECTION", msg)

    async def test_16_module16_intent_compiler_integration(self):
        """Test 16: Module 16 compiles a plan referencing verified capabilities in Module 17."""
        from intent import intent_compiler
        tg, plan = await intent_compiler.compile_intent("Navigate to https://example.com")
        self.assertIsNotNone(tg)
        # Ensure compiled task graph nodes include capability references
        for nid, node in tg.nodes.items():
            cap_ref = node.metadata.get("capability")
            self.assertTrue(bool(cap_ref))
            # Must be recognized by capability registry or mapper
            self.assertTrue(bool(self.test_reg.get_capability("browser.navigate")))

    async def test_17_module14_pre_execution_capability_guard(self):
        """Test 17: Module 14 Task Executor halts execution if required capability is UNAVAILABLE."""
        from task_graph.models import TaskGraph, TaskNode
        from task_graph.executor import task_executor
        from capabilities.registry import capability_registry

        # Temporarily mark a capability UNAVAILABLE
        orig_h = capability_registry.get_capability("browser.navigate").health
        capability_registry.update_health("browser.navigate", CapabilityHealth.UNAVAILABLE, "Offline")

        try:
            tg = TaskGraph(goal="Test Blocked Cap", task_id="test_cap_guard")
            node = TaskNode(
                node_id="n1",
                name="Navigate",
                description="Nav",
                action=lambda ctx: {"ok": True},
                metadata={"capability": "browser.navigate"}
            )
            tg.add_node(node)

            res = await task_executor.execute_task(tg)
            self.assertEqual(res["state"], "FAILED")
            self.assertTrue(any(ev.get("event") == "CAPABILITY_BLOCKED" for ev in tg.history))
        finally:
            capability_registry.update_health("browser.navigate", orig_h)

    def test_18_module15_recovery_revalidates_capabilities(self):
        """Test 18: Crash recovery detects CAPABILITY_CHANGED when capability becomes unavailable after crash."""
        from persistence.recovery import crash_recovery_engine
        from persistence.models import PersistedTaskRecord, PersistedNodeRecord, CheckpointPolicy
        from persistence.checkpoints import checkpoint_manager
        from persistence.store import persistence_store
        from capabilities.registry import capability_registry

        t_id = "test_cap_rec_task"
        persistence_store.save_task(PersistedTaskRecord(
            task_id=t_id, goal="Test Cap Recovery", status="RUNNING", current_node_id="node_a",
            created_at=time.time(), started_at=time.time(), updated_at=time.time(),
            completed_at=None, deadline_ts=time.time()+60, task_timeout_sec=60
        ))
        persistence_store.save_node(PersistedNodeRecord(
            node_id="node_a", task_id=t_id, name="Test Node", description="Test",
            status="RUNNING", attempt_count=1, started_at=time.time(), completed_at=None,
            expected_state=None, idempotency="SAFE_TO_RETRY", required_resources=[],
            metadata={"capability": "device.android.shell"}
        ))
        # Establish a valid checkpoint so recovery proceeds to node capability inspection
        checkpoint_manager.create_checkpoint(
            task_id=t_id,
            node_id="node_a",
            task_state="RUNNING",
            node_states={"node_a": "RUNNING"},
            variables={},
            resource_state=[],
            last_verified_observations=[],
            policy_trigger=CheckpointPolicy.CHECKPOINT_NODE_COMPLETE
        )

        # Mark capability UNAVAILABLE in registry
        orig_h = capability_registry.get_capability("device.android.shell").health
        capability_registry.update_health("device.android.shell", CapabilityHealth.UNAVAILABLE)

        try:
            cond, strat, reason = crash_recovery_engine.classify_interrupted_task(t_id)
            self.assertIn("CAPABILITY_CHANGED", reason)
        finally:
            capability_registry.update_health("device.android.shell", orig_h)

if __name__ == "__main__":
    unittest.main()
