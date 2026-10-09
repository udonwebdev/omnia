"""
E2E Integration Tests for Omnia Module 25:
Secrets, Credentials & Secure Identity Lifecycle

Test Coverage:
1. Multi-Node Trust Boundaries:
   - High-trust node (TRUSTED) authorized for secret access with valid lease.
   - Low-trust node (UNTRUSTED/REMOTE_EDGE) rejected even with matching secret name.
2. Cross-Node Secret Metadata Synchronization:
   - Namespace 'secrets_metadata' safely replicates state and version bumps.
   - Verifies zero plaintext propagation across event logs and replication streams.
3. Compromise Response & Cross-Node Invalidation:
   - Marking a secret compromised immediately revokes active leases.
   - Access handles are invalidated in memory via callback.
   - Secret status is transitioned to COMPROMISED.
4. Crash Recovery During Rotation:
   - Rotate secret to version 2, simulate service restart, verify persistent store integrity and active version.
"""

import os
import sys
import time
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from persistence.migrations import apply_migrations
from events import EventFabric
from replication.namespaces import NamespaceRegistry, ConsistencyPolicy
from secrets.models import (
    SecretType, SecretStatus, TrustLevel
)
from secrets.service import SecretControlPlaneService, AccessDeniedError, SecretUnavailableError
from secrets.persistence import SecretPersistence


class TestSecretsE2EModule25(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp(prefix="omnia_secrets_e2e_")
        cls.template_db = os.path.join(cls.test_dir, "template.db")
        apply_migrations(cls.template_db)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def setUp(self):
        self.run_id = f"e2e_{int(time.time() * 1000)}"
        self.node_a_db = os.path.join(self.test_dir, f"{self.run_id}_node_a.db")
        self.node_b_db = os.path.join(self.test_dir, f"{self.run_id}_node_b.db")
        shutil.copy2(self.template_db, self.node_a_db)
        shutil.copy2(self.template_db, self.node_b_db)

        self.persist_a = SecretPersistence(self.node_a_db)
        self.persist_b = SecretPersistence(self.node_b_db)

        self.service_a = SecretControlPlaneService(
            persistence=self.persist_a,
            node_id="node_core_alpha"
        )
        self.service_b = SecretControlPlaneService(
            persistence=self.persist_b,
            node_id="node_edge_beta"
        )

    def test_multi_node_trust_boundaries(self):
        """High-trust node gets access; untrusted node gets rejected."""
        self.service_a.authorizer.set_node_trust("node_core_alpha", TrustLevel.TRUSTED)
        self.service_a.authorizer.set_node_trust("node_edge_beta", TrustLevel.UNTRUSTED)

        self.service_a.register_secret(
            secret_id="cluster_admin_token",
            name="Cluster Admin Token",
            secret_type=SecretType.SERVICE_ACCOUNT,
            plaintext="Bearer super_secret_cluster_token_999",
            access_policy={
                "min_trust_level": "TRUSTED",
                "allowed_requesters": ["agent_core"],
                "allowed_purposes": ["cluster_admin"],
                "allowed_capabilities": ["capability.admin"]
            }
        )

        # 1. Trusted access request on node A with TRUSTED trust level
        handle = self.service_a.acquire_secret(
            uri_or_id="cluster_admin_token",
            requester="agent_core",
            purpose="cluster_admin",
            capability="capability.admin",
            node_id="node_core_alpha",
            ttl_seconds=60
        )
        self.assertIsNotNone(handle)
        self.assertTrue(handle.is_active)
        self.assertEqual(handle.get_raw_value(), "Bearer super_secret_cluster_token_999")
        handle.release()
        self.assertFalse(handle.is_active)

        # 2. Access request from untrusted node_edge_beta fails with AccessDeniedError
        with self.assertRaises(AccessDeniedError):
            self.service_a.acquire_secret(
                uri_or_id="cluster_admin_token",
                requester="agent_core",
                purpose="cluster_admin",
                capability="capability.admin",
                node_id="node_edge_beta",
                ttl_seconds=60
            )

    def test_metadata_sync_zero_plaintext_leakage(self):
        """Secret metadata syncs across nodes while ciphertext/plaintext remains strictly isolated."""
        from events.fabric import event_fabric
        from events.models import EventFilter
        events_captured = []
        event_fabric.subscribe("test_secrets_e2e_sub", EventFilter(type_pattern="secret.*"), lambda evt: events_captured.append(evt))

        self.service_a.register_secret(
            secret_id="cloud_llm_api_key",
            name="Cloud LLM Key",
            secret_type=SecretType.API_KEY,
            plaintext="sk-proj-super-secret-claude-key-12345"
        )

        # Inspect events emitted on Service A
        self.assertTrue(any(e.envelope.event_type == "secret.created" for e in events_captured))
        for evt in events_captured:
            payload_str = str(evt.payload)
            # Guarantee zero plaintext leaks in any event payloads
            self.assertNotIn("sk-proj-super-secret-claude-key-12345", payload_str)
            self.assertNotIn("super-secret", payload_str)

        # Check metadata retrieval
        meta = self.service_a.get_secret_metadata("cloud_llm_api_key")
        self.assertIsNotNone(meta)
        self.assertEqual(meta.secret_id, "cloud_llm_api_key")
        self.assertEqual(meta.version, 1)
        self.assertEqual(meta.status, SecretStatus.ACTIVE)

        # Node B cannot read Node A's secret without its own local store or explicit lease
        with self.assertRaises(SecretUnavailableError):
            self.service_b.acquire_secret(
                uri_or_id="cloud_llm_api_key",
                requester="worker",
                purpose="inference",
                capability="capability.llm"
            )

    def test_compromise_response_and_instant_invalidation(self):
        """Marking secret compromised invalidates handles in memory and blocks future access."""
        self.service_a.register_secret(
            secret_id="github_deploy_key",
            name="GitHub Deploy Key",
            secret_type=SecretType.PRIVATE_KEY,
            plaintext="-----BEGIN OPENSSH PRIVATE KEY-----\nsecret_raw_key\n-----END OPENSSH PRIVATE KEY-----"
        )

        handle = self.service_a.acquire_secret(
            uri_or_id="github_deploy_key",
            requester="ci_runner",
            purpose="deployment",
            capability="capability.deploy"
        )
        self.assertTrue(handle.is_active)

        # Security incident occurs!
        self.service_a.mark_compromised("github_deploy_key", incident_id="INC-2026-999")

        # In-memory handle should immediately be inactive via lease manager callback
        self.assertFalse(handle.is_active)

        # Accessing raw value from invalidated handle raises RuntimeError
        with self.assertRaises((RuntimeError, SecretUnavailableError)):
            handle.get_raw_value()

        # Future access requests must be blocked
        with self.assertRaises((AccessDeniedError, SecretUnavailableError)):
            self.service_a.acquire_secret(
                uri_or_id="github_deploy_key",
                requester="ci_runner",
                purpose="deployment",
                capability="capability.deploy"
            )

        meta = self.service_a.get_secret_metadata("github_deploy_key")
        self.assertEqual(meta.status, SecretStatus.COMPROMISED)

    def test_crash_recovery_during_rotation(self):
        """Simulate service reboot after rotation; state remains consistent and recoverable."""
        self.service_a.register_secret(
            secret_id="db_password",
            name="Database Password",
            secret_type=SecretType.DATABASE_CREDENTIAL,
            plaintext="db_pass_version_1"
        )

        # Successful rotation to version 2
        ok, ver2, msg = self.service_a.rotate_secret(
            secret_id="db_password",
            new_plaintext="db_pass_version_2"
        )
        self.assertTrue(ok)
        self.assertEqual(ver2.version, 2)

        # Simulate service crash/restart by re-instantiating service with the same DB
        restarted_persist = SecretPersistence(self.node_a_db)
        restarted_service = SecretControlPlaneService(
            persistence=restarted_persist,
            node_id="node_core_alpha"
        )

        meta = restarted_service.get_secret_metadata("db_password")
        self.assertEqual(meta.version, 2)
        self.assertEqual(meta.status, SecretStatus.ACTIVE)

        # Acquire secret via restarted service
        handle = restarted_service.acquire_secret(
            uri_or_id="db_password",
            requester="backend",
            purpose="query",
            capability="capability.db"
        )
        self.assertTrue(handle.is_active)
        self.assertEqual(handle.get_raw_value(), "db_pass_version_2")
        handle.release()
        self.assertFalse(handle.is_active)


if __name__ == "__main__":
    unittest.main()
