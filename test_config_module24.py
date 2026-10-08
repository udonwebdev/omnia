import unittest
import time
import os
import shutil
import tempfile
from typing import Dict, Any

from config.models import (
    ConfigSchema,
    ConfigType,
    ConfigScope,
    RuntimeMutability,
    ConfigValue,
    ConfigVersion,
    ConfigVersionStatus,
    ConfigRollout,
    RolloutStrategy,
    RolloutStatus,
    DriftType,
    DriftRecord
)
from config.defaults import DEFAULT_CONFIG_SCHEMAS
from config.validation import ConfigValidator
from config.diff import ConfigDiffEngine
from config.persistence import ConfigPersistence
from config.rollout import RolloutOrchestrator
from config.rollback import RollbackEngine
from config.drift import DriftDetector
from config.service import ConfigControlPlaneService
from persistence.migrations import apply_migrations

class TestConfigModule24(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.template_fd, cls.template_db = tempfile.mkstemp(suffix=".template.db")
        os.close(cls.template_fd)
        apply_migrations(cls.template_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.template_db):
            try:
                os.remove(cls.template_db)
            except Exception:
                pass

    def setUp(self):
        self.test_fd, self.temp_db = tempfile.mkstemp(suffix=".test.db")
        os.close(self.test_fd)
        shutil.copy2(self.template_db, self.temp_db)
        self.persistence = ConfigPersistence(self.temp_db)
        self.service = ConfigControlPlaneService(persistence=self.persistence, node_id="test_node_1")

    def tearDown(self):
        if os.path.exists(self.temp_db):
            try:
                os.remove(self.temp_db)
            except Exception:
                pass

    def test_schema_catalog_and_domains(self):
        schemas = self.service.list_schemas()
        self.assertGreaterEqual(len(schemas), 30)
        domains = {s.domain for s in schemas}
        expected_domains = {
            "system", "execution", "vision", "browser", "mesh",
            "coordination", "replication", "scheduler", "supervisor",
            "approval", "security"
        }
        self.assertTrue(expected_domains.issubset(domains))

    def test_validation_type_checking(self):
        validator = ConfigValidator()
        schemas = self.service._schemas

        # Valid types
        ok, errs = validator.validate_configuration({"system.log_level": "DEBUG"}, schemas)
        self.assertTrue(ok)

        # Invalid ENUM
        ok, errs = validator.validate_configuration({"system.log_level": "ULTRA_VERBOSE"}, schemas)
        self.assertFalse(ok)
        self.assertTrue(any("not in allowed values" in e for e in errs))

        # Invalid type: float for integer
        ok, errs = validator.validate_configuration({"execution.max_retries": 3.5}, schemas)
        self.assertFalse(ok)
        self.assertTrue(any("Expected INTEGER" in e for e in errs))

        # Invalid range bounds
        ok, errs = validator.validate_configuration({"execution.max_retries": 99}, schemas)
        self.assertFalse(ok)
        self.assertTrue(any("exceeds maximum" in e for e in errs))

    def test_secret_reference_enforcement(self):
        validator = ConfigValidator()
        schemas = self.service._schemas

        # Valid secret URI
        ok, errs = validator.validate_configuration({"security.api_auth_token_ref": "secret://vault/tokens/api_prod"}, schemas)
        self.assertTrue(ok)

        # Invalid secret URI
        ok, errs = validator.validate_configuration({"security.api_auth_token_ref": "plaintext_token_12345"}, schemas)
        self.assertFalse(ok)
        self.assertTrue(any("Invalid secret reference format" in e for e in errs))

        # Raw secret in non-secret field rejected
        ok, errs = validator.validate_configuration({"system.environment": "sk-live-secretkey123"}, schemas)
        self.assertFalse(ok)
        self.assertTrue(any("Raw sensitive secret detected" in e for e in errs))

    def test_cross_key_dependencies(self):
        validator = ConfigValidator()
        schemas = self.service._schemas

        # Heartbeat period >= Lease TTL must fail
        ok, errs = validator.validate_configuration({
            "coordination.heartbeat_period_sec": 10.0,
            "coordination.lease_ttl_sec": 5.0
        }, schemas)
        self.assertFalse(ok)
        self.assertTrue(any("DEPENDENCY_ERROR" in e for e in errs))

        # Valid dependency
        ok, errs = validator.validate_configuration({
            "coordination.heartbeat_period_sec": 2.0,
            "coordination.lease_ttl_sec": 10.0
        }, schemas)
        self.assertTrue(ok)

    def test_hierarchical_value_precedence(self):
        # Cluster default
        c_val = self.service.resolve_effective_value("execution.worker_concurrency")
        self.assertEqual(c_val, 4)

        # Node override
        self.service.persistence.save_value(ConfigValue(
            key="execution.worker_concurrency",
            scope=ConfigScope.NODE,
            entity_id="node_a",
            value=8,
            version=1
        ))
        self.assertEqual(self.service.resolve_effective_value("execution.worker_concurrency", node_id="node_a"), 8)
        self.assertEqual(self.service.resolve_effective_value("execution.worker_concurrency", node_id="node_b"), 4)

        # Device override
        self.service.persistence.save_value(ConfigValue(
            key="vision.capture_fps",
            scope=ConfigScope.DEVICE,
            entity_id="camera_1",
            value=24,
            version=1
        ))
        self.assertEqual(self.service.resolve_effective_value("vision.capture_fps", device_id="camera_1"), 24)
        self.assertEqual(self.service.resolve_effective_value("vision.capture_fps", device_id="camera_2"), 10)

    def test_optimistic_concurrency_and_versioning(self):
        cur_v = self.service.get_telemetry().current_version
        self.assertEqual(cur_v, 1)

        # Successful proposal matching parent version
        ok, v2, errs = self.service.propose_version(
            values={"system.log_level": "WARNING"},
            author="alice",
            parent_version=1
        )
        self.assertTrue(ok)
        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.parent_version, 1)
        self.assertEqual(v2.status, ConfigVersionStatus.STAGED)

        # Mismatched parent version must be rejected
        ok2, v_bad, errs2 = self.service.propose_version(
            values={"system.log_level": "ERROR"},
            author="bob",
            parent_version=99
        )
        self.assertFalse(ok2)
        self.assertTrue(any("CONCURRENCY_CONFLICT" in e for e in errs2))

    def test_diff_secret_masking_and_risk(self):
        diff_engine = ConfigDiffEngine()
        old_vals = {"system.log_level": "INFO", "security.api_auth_token_ref": "secret://vault/old"}
        new_vals = {"system.log_level": "DEBUG", "security.api_auth_token_ref": "secret://vault/new"}

        changes = diff_engine.compute_diff(old_vals, new_vals, self.service._schemas)
        self.assertEqual(len(changes), 2)

        # Secret masking in report
        report = diff_engine.format_diff_report(changes, mask_secrets=True)
        self.assertIn("[MASKED]", report)
        self.assertNotIn("secret://vault/new", report)

        # Critical risk assessment due to security parameter
        risk, reasons = diff_engine.assess_risk(changes)
        self.assertEqual(risk, "CRITICAL")
        self.assertTrue(any("security" in r for r in reasons))

    def test_rollout_strategies_and_batches(self):
        rollout_orch = self.service.rollout_orchestrator
        nodes = ["node_1", "node_2", "node_3", "node_4"]

        # ALL_AT_ONCE
        r_all = rollout_orch.create_rollout(2, nodes, strategy=RolloutStrategy.ALL_AT_ONCE)
        batches_all = rollout_orch.compute_batches(r_all)
        self.assertEqual(len(batches_all), 1)
        self.assertEqual(len(batches_all[0]), 4)

        # ROLLING batch size 2
        r_roll = rollout_orch.create_rollout(2, nodes, strategy=RolloutStrategy.ROLLING, batch_size=2)
        batches_roll = rollout_orch.compute_batches(r_roll)
        self.assertEqual(len(batches_roll), 2)
        self.assertEqual(batches_roll[0], ["node_1", "node_2"])

        # CANARY (first 1 node, then rest)
        r_can = rollout_orch.create_rollout(2, nodes, strategy=RolloutStrategy.CANARY, batch_size=2)
        batches_can = rollout_orch.compute_batches(r_can)
        self.assertEqual(batches_can[0], ["node_1"])
        self.assertEqual(batches_can[1], ["node_2", "node_3"])
        self.assertEqual(batches_can[2], ["node_4"])

    def test_rollout_failure_threshold(self):
        rollout_orch = self.service.rollout_orchestrator
        nodes = ["node_1", "node_2", "node_3"]
        r = rollout_orch.create_rollout(2, nodes, strategy=RolloutStrategy.ROLLING, batch_size=1, failure_threshold_pct=0.0)

        # Node 1 fails
        def _apply_failing(node_id: str, ver: int):
            if node_id == "node_1":
                return False, "Node unreachable"
            return True, None

        r_adv = rollout_orch.advance_rollout(r.rollout_id, _apply_failing)
        self.assertEqual(r_adv.status, RolloutStatus.FAILED)
        self.assertIn("Failure threshold exceeded", r_adv.failure_reason)

    def test_safe_rollback_restoration(self):
        cur_v = self.service.get_telemetry().current_version

        # Propose and activate Version 2
        ok, v2, _ = self.service.propose_version(values={"system.log_level": "WARNING"}, author="alice", parent_version=cur_v)
        self.service.activate_version(v2.version, target_nodes=["node_1"])

        self.assertEqual(self.service.persistence.get_active_version().version, v2.version)
        self.assertEqual(self.service.resolve_effective_value("system.log_level"), "WARNING")

        # Roll back to Version 1
        rb_ok, rb_ver, _ = self.service.rollback_version(
            current_version_num=v2.version,
            target_version_num=cur_v,
            reason="Test rollback",
            target_nodes=["node_1"]
        )
        self.assertTrue(rb_ok)
        self.assertEqual(rb_ver.version, cur_v)
        self.assertEqual(self.service.persistence.get_active_version().version, cur_v)
        self.assertEqual(self.service.resolve_effective_value("system.log_level"), "INFO")

    def test_drift_detection_and_reconciliation(self):
        active_v = self.service.persistence.get_active_version()
        
        # Simulate node with drifted values
        node_vals = dict(active_v.values)
        node_vals["execution.max_retries"] = 1  # Expected is 3

        drifts = self.service.detect_node_drift(
            node_id="drifted_node_1",
            actual_values=node_vals,
            actual_version=active_v.version
        )
        self.assertEqual(len(drifts), 1)
        self.assertEqual(drifts[0].key, "execution.max_retries")
        self.assertEqual(drifts[0].expected_value, 3)
        self.assertEqual(drifts[0].actual_value, 1)
        self.assertEqual(drifts[0].drift_type, DriftType.UNAUTHORIZED_OVERRIDE)

        # Resolve drift
        resolved = self.service.resolve_drift(drifts[0].drift_id, strategy="FORCE_SYNC")
        self.assertTrue(resolved)
        active_drifts = self.service.persistence.list_active_drifts("drifted_node_1")
        self.assertEqual(len(active_drifts), 0)

if __name__ == "__main__":
    unittest.main()
