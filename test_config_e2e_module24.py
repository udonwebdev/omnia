import unittest
import time
import os
import shutil
import tempfile
from typing import Dict, Any

from config.models import (
    ConfigScope,
    ConfigVersionStatus,
    RolloutStrategy,
    RolloutStatus,
    DriftType
)
from config.persistence import ConfigPersistence
from config.service import ConfigControlPlaneService
from persistence.migrations import apply_migrations

class TestConfigE2EModule24(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.template_fd, cls.template_db = tempfile.mkstemp(suffix=".e2e_template.db")
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
        self.test_fd, self.temp_db = tempfile.mkstemp(suffix=".e2e_test.db")
        os.close(self.test_fd)
        shutil.copy2(self.template_db, self.temp_db)
        self.persistence = ConfigPersistence(self.temp_db)
        self.leader_service = ConfigControlPlaneService(persistence=self.persistence, node_id="leader_node")

    def tearDown(self):
        if os.path.exists(self.temp_db):
            try:
                os.remove(self.temp_db)
            except Exception:
                pass

    def test_e2e_canary_rollout_across_cluster(self):
        """Simulates 3-node cluster canary deployment with health verification."""
        cluster_nodes = ["worker_node_1", "worker_node_2", "leader_node"]
        cur_v = self.leader_service.get_telemetry().current_version
        self.assertEqual(cur_v, 1)

        # Propose Version 2
        ok, v2, errs = self.leader_service.propose_version(
            values={"execution.max_retries": 5, "vision.capture_fps": 15},
            author="lead_operator",
            justification="Tune execution concurrency and perception frame rate",
            parent_version=cur_v
        )
        self.assertTrue(ok)
        self.assertEqual(v2.version, 2)

        # Activate via CANARY strategy: worker_node_1 first, then remainder
        roll_ok, rollout, msg = self.leader_service.activate_version(
            version_num=v2.version,
            target_nodes=cluster_nodes,
            strategy=RolloutStrategy.CANARY,
            batch_size=2
        )
        self.assertTrue(roll_ok)
        self.assertEqual(rollout.status, RolloutStatus.COMPLETED)
        self.assertEqual(len(rollout.completed_nodes), 3)

        # Confirm cluster resolved values
        self.assertEqual(self.leader_service.resolve_effective_value("execution.max_retries"), 5)
        self.assertEqual(self.leader_service.resolve_effective_value("vision.capture_fps"), 15)

    def test_e2e_node_failure_triggers_automatic_rollback(self):
        """Simulates node failure during rollout halting progression and rolling back cluster safely."""
        cluster_nodes = ["worker_node_1", "worker_node_2", "leader_node"]
        cur_v = self.leader_service.get_telemetry().current_version

        # Propose Version 2
        ok, v2, _ = self.leader_service.propose_version(
            values={"execution.step_timeout_sec": 5.0},
            author="lead_operator",
            parent_version=cur_v
        )
        self.assertTrue(ok)

        # Create rollout with 0% failure threshold
        rollout_orch = self.leader_service.rollout_orchestrator
        rollout = rollout_orch.create_rollout(
            version=v2.version,
            target_nodes=cluster_nodes,
            strategy=RolloutStrategy.ROLLING,
            batch_size=1,
            failure_threshold_pct=0.0
        )

        # Advance: worker_node_1 succeeds
        def _apply_step(node_id: str, ver: int):
            if node_id == "worker_node_2":
                return False, "CONNECTION_REFUSED: Worker node 2 failed health check"
            return True, None

        # Batch 1 (worker_node_1)
        r1 = rollout_orch.advance_rollout(rollout.rollout_id, _apply_step)
        self.assertEqual(r1.status, RolloutStatus.IN_PROGRESS)

        # Batch 2 (worker_node_2) fails!
        r2 = rollout_orch.advance_rollout(rollout.rollout_id, _apply_step)
        self.assertEqual(r2.status, RolloutStatus.FAILED)
        self.assertIn("Failure threshold exceeded", r2.failure_reason)

        # Trigger automatic rollback back to baseline Version 1
        rb_ok, restored_ver, rb_msg = self.leader_service.rollback_version(
            current_version_num=v2.version,
            target_version_num=cur_v,
            reason="Automated rollback due to worker node 2 failure",
            target_nodes=["worker_node_1"]
        )
        self.assertTrue(rb_ok)
        self.assertEqual(restored_ver.version, cur_v)
        self.assertEqual(self.leader_service.persistence.get_active_version().version, cur_v)
        self.assertEqual(self.leader_service.resolve_effective_value("execution.step_timeout_sec"), 30.0)

    def test_e2e_drift_audit_and_reconciliation(self):
        """Audits unauthorized local changes on worker_node_1 and forces convergence."""
        active_v = self.leader_service.persistence.get_active_version()

        # Simulated worker node 1 running with unauthorized log level
        worker_node_1_actual = dict(active_v.values)
        worker_node_1_actual["system.log_level"] = "CRITICAL"

        # Detect drift
        drifts = self.leader_service.detect_node_drift(
            node_id="worker_node_1",
            actual_values=worker_node_1_actual,
            actual_version=active_v.version
        )
        self.assertEqual(len(drifts), 1)
        drift = drifts[0]
        self.assertEqual(drift.key, "system.log_level")
        self.assertEqual(drift.drift_type, DriftType.UNAUTHORIZED_OVERRIDE)

        # Reconcile drift via FORCE_SYNC
        reconciled = self.leader_service.resolve_drift(drift.drift_id, strategy="FORCE_SYNC")
        self.assertTrue(reconciled)

        # Re-inspect after sync: zero drifts remain
        worker_node_1_actual["system.log_level"] = "INFO"  # aligned
        drifts_after = self.leader_service.detect_node_drift(
            node_id="worker_node_1",
            actual_values=worker_node_1_actual,
            actual_version=active_v.version
        )
        self.assertEqual(len(drifts_after), 0)

if __name__ == "__main__":
    unittest.main()
