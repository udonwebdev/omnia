import unittest
import uuid
import time
from typing import Dict, Any

from replication.models import (
    StateDelta,
    Snapshot,
    DeltaOperation,
    PeerSyncStatus
)
from replication.service import ReplicationService
from replication.integrity import integrity_verifier
from coordination import CoordinationService, NodeIdentity

class TestReplicationE2EModule23(unittest.TestCase):

    def setUp(self):
        # Create a realistic 3-node cluster
        # Node A = Leader, Node B = Worker 1, Node C = Worker 2
        self.node_a_id = f"node_leader_{uuid.uuid4().hex[:6]}"
        self.node_b_id = f"node_worker_b_{uuid.uuid4().hex[:6]}"
        self.node_c_id = f"node_worker_c_{uuid.uuid4().hex[:6]}"

        self.coord_a = CoordinationService(node_id=self.node_a_id, node_name="cluster-leader")
        self.coord_b = CoordinationService(node_id=self.node_b_id, node_name="cluster-worker-b")
        self.coord_c = CoordinationService(node_id=self.node_c_id, node_name="cluster-worker-c")

        # Enroll into membership
        self.coord_a.membership.register_node(self.coord_b.local_node)
        self.coord_a.membership.register_node(self.coord_c.local_node)

        # Node A wins leader election
        ok, epoch, token = self.coord_a.elect_leader()
        self.assertTrue(ok)
        self.assertEqual(epoch, 2)

        # Initialize replication services for each node
        self.service_a = ReplicationService(node_id=self.node_a_id, coordination=self.coord_a)
        self.service_b = ReplicationService(node_id=self.node_b_id, coordination=self.coord_a)
        self.service_c = ReplicationService(node_id=self.node_c_id, coordination=self.coord_a)

        self.service_a.start()
        self.service_b.start()
        self.service_c.start()

    def tearDown(self):
        self.service_a.stop()
        self.service_b.stop()
        self.service_c.stop()

    def test_three_node_state_replication_stream(self):
        """E2E Invariant: Node A updates state -> Propagates to Node B and Node C -> All converge with matching hash."""
        task_id = f"task_mesh_{uuid.uuid4().hex[:6]}"
        
        # 1. Node A publishes authoritative task state
        ok, rec_a, delta_1, msg = self.service_a.publish_state(
            namespace_id="tasks",
            entity_id=task_id,
            payload={"goal": "Multi-device synchronized workflow", "progress": 10.0}
        )
        self.assertTrue(ok)
        self.assertEqual(rec_a.revision, 1)

        # 2. Replicate delta to Node B and Node C
        ok_b, rec_b, msg_b = self.service_b.apply_remote_delta(delta_1)
        ok_c, rec_c, msg_c = self.service_c.apply_remote_delta(delta_1)

        self.assertTrue(ok_b)
        self.assertTrue(ok_c)
        self.assertEqual(rec_b.revision, 1)
        self.assertEqual(rec_c.revision, 1)

        # 3. Cryptographic integrity convergence across all 3 nodes
        self.assertEqual(rec_a.integrity_hash, rec_b.integrity_hash)
        self.assertEqual(rec_b.integrity_hash, rec_c.integrity_hash)

        # 4. Node A publishes revision 2
        ok2, rec_a2, delta_2, _ = self.service_a.publish_state(
            namespace_id="tasks",
            entity_id=task_id,
            payload={"goal": "Multi-device synchronized workflow", "progress": 100.0}
        )
        self.assertTrue(ok2)
        self.assertEqual(rec_a2.revision, 2)

        # Deliver delta 2 to workers
        self.service_b.apply_remote_delta(delta_2)
        self.service_c.apply_remote_delta(delta_2)

        rec_b2 = self.service_b.get_state("tasks", task_id)
        rec_c2 = self.service_c.get_state("tasks", task_id)
        self.assertEqual(rec_b2.revision, 2)
        self.assertEqual(rec_c2.revision, 2)
        self.assertEqual(rec_b2.payload["progress"], 100.0)
        self.assertEqual(rec_a2.integrity_hash, rec_b2.integrity_hash)

    def test_offline_node_reconnect_and_snapshot_catchup(self):
        """E2E Invariant: Node C goes offline, misses revisions, reconnects, requests snapshot catch-up, and converges."""
        # 1. Node C goes offline and forgets in-memory records
        self.service_c.stop()
        self.service_c._local_records.clear()

        # 2. Node A publishes multiple revisions
        task_id = f"task_reconnect_{uuid.uuid4().hex[:6]}"
        for step in range(1, 5):
            self.service_a.publish_state("tasks", task_id, {"step": step, "status": "IN_PROGRESS"})

        final_rec_a = self.service_a.get_state("tasks", task_id)
        self.assertEqual(final_rec_a.revision, 4)

        # 3. Simulate Node C reconnecting with stale/missing record
        self.service_c._local_records.clear()
        self.assertIsNone(self.service_c.get_state("tasks", task_id))

        # 4. Node C requests and installs snapshot from Node A
        snapshot = self.service_a.create_snapshot("tasks")
        self.assertIsNotNone(snapshot)

        ok_install, install_msg = self.service_c.install_snapshot(snapshot)
        self.assertTrue(ok_install, install_msg)

        # 5. Verify Node C has completely converged to Node A's revision & hash
        rec_c = self.service_c.get_state("tasks", task_id)
        self.assertIsNotNone(rec_c)
        self.assertEqual(rec_c.revision, 4)
        self.assertEqual(rec_c.integrity_hash, final_rec_a.integrity_hash)

    def test_epoch_failover_and_stale_leader_fencing(self):
        """E2E Invariant: Node A was leader in Epoch 2. Node B elected leader in Epoch 3.

        Stale delta from Node A under Epoch 2 is strictly rejected by Node B & C.
        """
        # Node B syncs current cluster epoch (Epoch 2) before initiating failover election
        self.coord_b.election.current_epoch = self.coord_a.election.current_epoch
        self.coord_b.membership.register_node(self.coord_a.local_node)
        self.coord_b.membership.register_node(self.coord_c.local_node)

        # Node B wins election for Epoch 3
        ok, epoch_3, token_3 = self.coord_b.elect_leader()
        self.assertTrue(ok)
        self.assertEqual(epoch_3, 3)

        # Stale delta manufactured by old Node A under expired Epoch 2
        stale_delta = StateDelta(
            delta_id=f"dlta_stale_{uuid.uuid4().hex[:6]}",
            namespace_id="tasks",
            entity_id="task_stale_failover",
            source_node=self.node_a_id,
            source_epoch=2,  # Stale epoch (< 3)
            base_revision=0,
            target_revision=1,
            operation=DeltaOperation.CREATE,
            payload={"status": "FORGED_AFTER_FAILOVER"}
        )

        # Service B checks under new Epoch 3 coordinator
        service_b_new = ReplicationService(node_id=self.node_b_id, coordination=self.coord_b)
        service_b_new.start()

        ok_apply, _, err_msg = service_b_new.apply_remote_delta(stale_delta)
        self.assertFalse(ok_apply)
        self.assertIn("FENCED_STALE_EPOCH", err_msg)

        service_b_new.stop()

if __name__ == "__main__":
    unittest.main()
