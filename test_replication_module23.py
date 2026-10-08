import unittest
import time
import uuid

from replication.models import (
    StateClassification,
    ConsistencyPolicy,
    DeltaOperation,
    ConflictType,
    ConflictResolutionStrategy,
    StateRecord,
    StateDelta,
    Snapshot
)
from replication.namespaces import namespace_registry, StateNamespace
from replication.versioning import VersionComparator, ReplicationOwnershipEnforcer
from replication.deltas import delta_manager
from replication.snapshots import snapshot_manager
from replication.integrity import integrity_verifier
from replication.conflicts import conflict_resolver
from replication.reconciliation import reconciliation_engine
from replication.persistence import replication_persistence
from replication.service import ReplicationService
from coordination import coordination_service, NodeIdentity

class TestReplicationModule23(unittest.TestCase):

    def setUp(self):
        self.service = ReplicationService(node_id="test_node_alpha")
        self.service.start()

    def tearDown(self):
        self.service.stop()

    def test_namespace_sensitivity_and_secret_isolation(self):
        """Invariant: Sensitive and local-only namespaces are strictly blocked from replication."""
        # Configured secrets namespace
        self.assertFalse(namespace_registry.can_replicate("secrets"))
        self.assertFalse(namespace_registry.can_replicate("audio_buffers"))
        self.assertFalse(namespace_registry.can_replicate("ephemeral_frames"))

        # Authoritative operational namespaces are replicable
        self.assertTrue(namespace_registry.can_replicate("tasks"))
        self.assertTrue(namespace_registry.can_replicate("missions"))

        # Unknown namespaces default to non-replicated
        self.assertFalse(namespace_registry.can_replicate("unknown_namespace_xyz"))

        # Publishing to a sensitive namespace must be denied
        ok, rec, delta, msg = self.service.publish_state("secrets", "api_key_1", {"key": "secret123"})
        self.assertFalse(ok)
        self.assertIn("REPLICATION_DENIED", msg)

    def test_deterministic_versioning_and_epoch_fencing(self):
        """Invariant: Epoch takes precedence over revision; stale epochs are rejected."""
        comp = VersionComparator()
        # Newer epoch wins
        self.assertEqual(comp.compare_versions(local_epoch=1, local_revision=10, remote_epoch=2, remote_revision=1), "NEWER")
        # Stale epoch rejected
        self.assertEqual(comp.compare_versions(local_epoch=2, local_revision=1, remote_epoch=1, remote_revision=10), "STALE_EPOCH")
        # Same epoch compares revisions
        self.assertEqual(comp.compare_versions(local_epoch=1, local_revision=5, remote_epoch=1, remote_revision=6), "NEWER")
        self.assertEqual(comp.compare_versions(local_epoch=1, local_revision=5, remote_epoch=1, remote_revision=4), "OLDER")

    def test_epoch_fencing_rejection(self):
        """Invariant: Remote delta from a stale epoch is strictly rejected with FENCED_STALE_EPOCH."""
        # Local cluster epoch is at least 1
        stale_delta = StateDelta(
            namespace_id="tasks",
            entity_id="task_epoch_test",
            source_node="old_node",
            source_epoch=0,  # Stale epoch (< 1)
            base_revision=0,
            target_revision=1,
            operation=DeltaOperation.CREATE,
            payload={"goal": "stale operation"}
        )

        ok, rec, msg = self.service.apply_remote_delta(stale_delta)
        self.assertFalse(ok)
        self.assertIn("FENCED_STALE_EPOCH", msg)

    def test_delta_idempotency_and_duplicate_delivery(self):
        """Invariant: Duplicate delta delivery results in exactly one state application."""
        entity_id = f"task_{uuid.uuid4().hex[:6]}"
        delta = StateDelta(
            delta_id=f"dlta_{uuid.uuid4().hex[:8]}",
            namespace_id="tasks",
            entity_id=entity_id,
            source_node=self.service.node_id,
            source_epoch=coordination_service.election.current_epoch,
            base_revision=0,
            target_revision=1,
            operation=DeltaOperation.CREATE,
            payload={"status": "INITIALIZED"}
        )

        # First delivery
        ok1, rec1, msg1 = self.service.apply_remote_delta(delta)
        self.assertTrue(ok1)
        self.assertEqual(rec1.revision, 1)

        # Duplicate delivery of identical delta
        ok2, rec2, msg2 = self.service.apply_remote_delta(delta)
        self.assertTrue(ok2)
        self.assertIn("IDEMPOTENT", msg2)
        self.assertEqual(rec2.revision, 1)

    def test_out_of_order_and_gap_detection(self):
        """Invariant: When a revision gap is detected, delta is buffered and not applied until gap closes."""
        entity_id = f"task_{uuid.uuid4().hex[:6]}"
        curr_epoch = coordination_service.election.current_epoch

        # Deliver delta 2 (expecting base 1, but current is 0)
        delta_2 = StateDelta(
            delta_id=f"dlta_{uuid.uuid4().hex[:8]}",
            namespace_id="tasks",
            entity_id=entity_id,
            source_node=self.service.node_id,
            source_epoch=curr_epoch,
            base_revision=1,
            target_revision=2,
            operation=DeltaOperation.UPDATE,
            payload={"progress": 50.0}
        )

        ok, rec, msg = self.service.apply_remote_delta(delta_2)
        self.assertFalse(ok)
        self.assertIn("VERSION_GAP", msg)
        self.assertEqual(len(delta_manager.get_buffered_deltas("tasks", entity_id)), 1)

        # Now deliver missing delta 1 (base 0 -> 1)
        delta_1 = StateDelta(
            delta_id=f"dlta_{uuid.uuid4().hex[:8]}",
            namespace_id="tasks",
            entity_id=entity_id,
            source_node=self.service.node_id,
            source_epoch=curr_epoch,
            base_revision=0,
            target_revision=1,
            operation=DeltaOperation.CREATE,
            payload={"progress": 25.0}
        )

        ok1, rec1, msg1 = self.service.apply_remote_delta(delta_1)
        self.assertTrue(ok1)
        # Buffer draining should automatically advance state to revision 2!
        final_rec = self.service.get_state("tasks", entity_id)
        self.assertIsNotNone(final_rec)
        self.assertEqual(final_rec.revision, 2)
        self.assertEqual(final_rec.payload["progress"], 50.0)

    def test_snapshot_creation_and_integrity_verification(self):
        """Invariant: Snapshot has cryptographic boundary hash and installs atomically."""
        curr_epoch = coordination_service.election.current_epoch
        # Populate 2 records
        self.service.publish_state("tasks", "task_snap_1", {"title": "Task 1"})
        self.service.publish_state("tasks", "task_snap_2", {"title": "Task 2"})

        snap = self.service.create_snapshot("tasks")
        self.assertIsNotNone(snap)
        self.assertGreaterEqual(snap.record_count, 2)
        self.assertTrue(integrity_verifier.verify_snapshot_hash(snap))

        # Corrupt snapshot content hash
        snap.content_hash = "tampered_hash_value"
        ok_install, err_msg = self.service.install_snapshot(snap)
        self.assertFalse(ok_install)
        self.assertIn("CHECKSUM_MISMATCH", err_msg)

    def test_divergence_detection_and_anti_entropy(self):
        """Invariant: Hierarchical root hash comparison pinpoints divergent entities."""
        r1 = StateRecord(namespace_id="tasks", entity_type="TASK", entity_id="t1", owner_node="a", owner_epoch=1, revision=1, payload={"val": 1})
        r2_local = StateRecord(namespace_id="tasks", entity_type="TASK", entity_id="t2", owner_node="a", owner_epoch=1, revision=1, payload={"val": 2})
        r2_remote = StateRecord(namespace_id="tasks", entity_type="TASK", entity_id="t2", owner_node="a", owner_epoch=1, revision=2, payload={"val": 200})

        local_records = [r1, r2_local]
        remote_records = [r1, r2_remote]

        diverged, divergent_keys, details = reconciliation_engine.detect_divergence("tasks", local_records, remote_records)
        self.assertTrue(diverged)
        self.assertEqual(divergent_keys, ["t2"])

    def test_persistence_durability_and_reload(self):
        """Invariant: Replicated state and deltas persist to SQLite and survive reload."""
        eid = f"task_{uuid.uuid4().hex[:6]}"
        ok, rec, delta, _ = self.service.publish_state("tasks", eid, {"status": "PERSISTED_OK"})
        self.assertTrue(ok)

        # Direct database query
        loaded = replication_persistence.get_state_record("tasks", eid)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.payload["status"], "PERSISTED_OK")
        self.assertEqual(loaded.revision, 1)

if __name__ == "__main__":
    unittest.main()
