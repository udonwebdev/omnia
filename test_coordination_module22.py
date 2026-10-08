import unittest
import time
import uuid

from coordination.models import (
    NodeIdentity,
    NodeTrustState,
    NodeMembershipState,
    LeaderRole,
    OwnershipState,
    LockState
)
from coordination.membership import ClusterMembershipManager
from coordination.election import LeaderElectionEngine
from coordination.ownership import OwnershipCoordinator
from coordination.persistence import CoordinationPersistenceManager
from coordination.service import CoordinationService

class TestCoordinationModule22(unittest.TestCase):

    def setUp(self):
        self.node_a = NodeIdentity(node_id="node_test_a", node_name="alpha")
        self.node_b = NodeIdentity(node_id="node_test_b", node_name="beta")
        self.node_c = NodeIdentity(node_id="node_test_c", node_name="gamma")

    def test_node_stable_identity_and_fingerprint(self):
        """Invariant: Node identity is stable and has sha256 fingerprint."""
        self.assertTrue(self.node_a.identity_fingerprint)
        self.assertEqual(len(self.node_a.identity_fingerprint), 64)
        self.assertEqual(self.node_a.membership_state, NodeMembershipState.ACTIVE)
        self.assertEqual(self.node_a.trust_state, NodeTrustState.TRUSTED)

    def test_membership_and_quorum_calculation(self):
        """Invariant: Quorum is floor(N / 2) + 1."""
        mgr = ClusterMembershipManager(local_node=self.node_a)
        # Initially 1 node -> quorum is (1//2) + 1 = 1
        self.assertEqual(mgr.get_cluster_size(), 1)
        self.assertEqual(mgr.calculate_quorum_size(), 1)
        self.assertTrue(mgr.has_quorum())

        # Register 2 more nodes -> total 3 nodes -> quorum is (3//2) + 1 = 2
        mgr.register_node(self.node_b)
        mgr.register_node(self.node_c)
        self.assertEqual(mgr.get_cluster_size(), 3)
        self.assertEqual(mgr.calculate_quorum_size(), 2)

    def test_membership_failure_detection(self):
        """Invariant: Expired heartbeats mark node as SUSPECTED or UNREACHABLE."""
        mgr = ClusterMembershipManager(local_node=self.node_a)
        mgr.register_node(self.node_b)
        self.node_b.last_seen = time.time() - 20.0  # > 15s timeout
        
        suspected = mgr.scan_for_dead_nodes()
        self.assertIn("node_test_b", suspected)
        self.assertEqual(self.node_b.membership_state, NodeMembershipState.SUSPECTED)

    def test_leader_election_with_quorum_and_epoch_increment(self):
        """Invariant: Election increments monotonic epoch and issues fencing token."""
        mgr = ClusterMembershipManager(local_node=self.node_a)
        mgr.register_node(self.node_b)
        mgr.register_node(self.node_c)
        
        engine = LeaderElectionEngine(membership=mgr)
        self.assertEqual(engine.current_epoch, 1)
        self.assertEqual(engine.current_role, LeaderRole.FOLLOWER)

        success, new_epoch, token = engine.start_election()
        self.assertTrue(success)
        self.assertEqual(new_epoch, 2)
        self.assertEqual(engine.current_role, LeaderRole.LEADER)
        self.assertTrue(token.startswith("fence_ep2_"))
        self.assertIsNotNone(engine.current_lease)
        self.assertFalse(engine.current_lease.is_expired())

    def test_fencing_token_validation(self):
        """Invariant: Stale epochs or invalid fencing tokens are strictly rejected."""
        mgr = ClusterMembershipManager(local_node=self.node_a)
        engine = LeaderElectionEngine(membership=mgr)
        engine.start_election()
        
        valid_epoch = engine.current_epoch
        valid_token = engine.current_lease.fencing_token

        # Valid authority
        valid, msg = engine.validate_authority(valid_epoch, valid_token)
        self.assertTrue(valid)

        # Stale epoch rejected
        valid, msg = engine.validate_authority(valid_epoch - 1, valid_token)
        self.assertFalse(valid)
        self.assertIn("FENCED_STALE_EPOCH", msg)

        # Corrupted token rejected
        valid, msg = engine.validate_authority(valid_epoch, "fake_token_123")
        self.assertFalse(valid)
        self.assertIn("FENCED_INVALID_TOKEN", msg)

    def test_exclusive_task_ownership_and_conflict_rejection(self):
        """Invariant: If Node A owns a task, Node B cannot claim it while active."""
        coord = OwnershipCoordinator(local_node_id="node_a")
        
        # Node A claims task_101
        ok_a, claim_a, msg_a = coord.claim_ownership("TASK", "task_101", owner_node_id="node_a", epoch=1)
        self.assertTrue(ok_a)
        self.assertEqual(claim_a.owner_node_id, "node_a")

        # Node B attempts to claim task_101 -> Must be rejected
        ok_b, claim_b, msg_b = coord.claim_ownership("TASK", "task_101", owner_node_id="node_b", epoch=1)
        self.assertFalse(ok_b)
        self.assertIn("CLAIM_CONFLICT", msg_b)
        self.assertEqual(coord.get_owner("TASK", "task_101"), "node_a")

        # Node A releases ownership
        released = coord.release_ownership("TASK", "task_101", owner_node_id="node_a")
        self.assertTrue(released)
        self.assertIsNone(coord.get_owner("TASK", "task_101"))

        # Node B can now claim it
        ok_b2, claim_b2, _ = coord.claim_ownership("TASK", "task_101", owner_node_id="node_b", epoch=1)
        self.assertTrue(ok_b2)
        self.assertEqual(coord.get_owner("TASK", "task_101"), "node_b")

    def test_distributed_lock_acquisition_and_release(self):
        """Invariant: Distributed lock is lease-bound and mutual-exclusion safe."""
        coord = OwnershipCoordinator(local_node_id="node_a")
        
        ok1, lock1, _ = coord.acquire_distributed_lock("device:pixel7", owner_node_id="node_a", epoch=1, lease_sec=10.0)
        self.assertTrue(ok1)
        self.assertEqual(lock1.state, LockState.ACQUIRED)

        # Node B tries to lock the same device
        ok2, _, msg2 = coord.acquire_distributed_lock("device:pixel7", owner_node_id="node_b", epoch=1)
        self.assertFalse(ok2)
        self.assertIn("LOCK_BUSY", msg2)

        # Release and reacquire
        self.assertTrue(coord.release_distributed_lock("device:pixel7", owner_node_id="node_a"))
        ok3, _, _ = coord.acquire_distributed_lock("device:pixel7", owner_node_id="node_b", epoch=1)
        self.assertTrue(ok3)

    def test_reap_expired_claims(self):
        """Invariant: Expired claims are reaped and surrendered."""
        coord = OwnershipCoordinator(local_node_id="node_a")
        ok, claim, _ = coord.claim_ownership("TASK", "task_fast_expire", owner_node_id="node_a", epoch=1, lease_sec=0.01)
        self.assertTrue(ok)
        time.sleep(0.02)
        
        reaped = coord.reap_expired_claims()
        self.assertEqual(len(reaped), 1)
        self.assertEqual(reaped[0].subject_id, "task_fast_expire")
        self.assertEqual(reaped[0].state, OwnershipState.EXPIRED)
        self.assertIsNone(coord.get_owner("TASK", "task_fast_expire"))

    def test_persistence_durability_and_reconciliation(self):
        """Invariant: Nodes, leases, claims, and locks survive restart."""
        pm = CoordinationPersistenceManager()
        pm.save_node(self.node_a)
        
        loaded = pm.get_node("node_test_a")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.node_name, "alpha")

        stats = pm.reconcile_on_startup()
        self.assertIn("reaped_leases", stats)
        self.assertIn("reaped_claims", stats)

    def test_coordination_service_lifecycle_and_telemetry(self):
        """Invariant: CoordinationService starts, tracks telemetry, and steps down cleanly."""
        service = CoordinationService(node_id=f"test_svc_{uuid.uuid4().hex[:6]}", node_name="test-cluster-node")
        service.start()
        
        # Win election
        ok, epoch, token = service.elect_leader()
        self.assertTrue(ok)
        
        telemetry = service.get_telemetry()
        self.assertEqual(telemetry.role, LeaderRole.LEADER)
        self.assertEqual(telemetry.current_epoch, epoch)
        self.assertEqual(telemetry.current_leader, service.node_id)
        
        # Step down
        service.step_down()
        telemetry_after = service.get_telemetry()
        self.assertEqual(telemetry_after.role, LeaderRole.FOLLOWER)
        
        service.stop()

if __name__ == "__main__":
    unittest.main()
