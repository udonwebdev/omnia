"""
Unit tests for Module 31: Temporal Knowledge & Causal State Engine.
"""
import unittest
import os
import shutil
import tempfile
import json
from datetime import datetime, timezone, timedelta

from temporal.models import (
    CausalRelationType,
    CausalStatus,
    EvidenceSupportType,
    TemporalStateRecord,
    CausalLink,
    CausalEvidenceBinding,
    StateTransitionDiff,
)
from temporal.persistence import TemporalPersistence
from temporal.engine import TemporalEngine
from temporal.causal import CausalReasoner
from temporal.service import TemporalCausalService


class TestTemporalCausalSubsystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.test_dir, "test_temporal.db")
        cls.persistence = TemporalPersistence(db_path=cls.db_path)
        cls.engine = TemporalEngine(cls.persistence)
        cls.reasoner = CausalReasoner(cls.persistence)
        cls.service = TemporalCausalService(
            persistence=cls.persistence,
            engine=cls.engine,
            reasoner=cls.reasoner,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_bi_temporal_recording_and_reconstruction(self):
        """Test recording states at different valid times and reconstructing state as_of."""
        t0 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        t1 = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # State 1: 10:00 - 11:00
        rec1 = self.service.record_state(
            entity_id="srv_01",
            state_payload={"status": "INITIALIZING", "load": 0.1},
            valid_from=t0,
            valid_until=t1,
        )
        self.assertIsNotNone(rec1.record_id)
        self.assertEqual(rec1.entity_id, "srv_01")

        # State 2: 11:00 - 12:00
        rec2 = self.service.record_state(
            entity_id="srv_01",
            state_payload={"status": "ONLINE", "load": 0.55},
            valid_from=t1,
            valid_until=t2,
        )

        # State 3: 12:00 onwards
        rec3 = self.service.record_state(
            entity_id="srv_01",
            state_payload={"status": "DEGRADED", "load": 0.95},
            valid_from=t2,
            valid_until=None,
        )

        # Query as_of 10:30
        as_of_t0 = datetime(2026, 1, 1, 10, 30, 0, tzinfo=timezone.utc)
        recon_t0 = self.service.reconstruct_state("srv_01", valid_time=as_of_t0)
        self.assertIsNotNone(recon_t0)
        self.assertEqual(recon_t0.state_payload.get("status"), "INITIALIZING")

        # Query as_of 11:15
        as_of_t1 = datetime(2026, 1, 1, 11, 15, 0, tzinfo=timezone.utc)
        recon_t1 = self.service.reconstruct_state("srv_01", valid_time=as_of_t1)
        self.assertIsNotNone(recon_t1)
        self.assertEqual(recon_t1.state_payload.get("status"), "ONLINE")

        # Query as_of 14:00 (open interval)
        as_of_t2 = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        recon_t2 = self.service.reconstruct_state("srv_01", valid_time=as_of_t2)
        self.assertIsNotNone(recon_t2)
        self.assertEqual(recon_t2.state_payload.get("status"), "DEGRADED")

    def test_02_state_transition_diffs(self):
        """Test computing state transitions across consecutive temporal records."""
        diffs = self.service.detect_state_transitions("srv_01")
        self.assertGreaterEqual(len(diffs), 2)

        # First transition from INITIALIZING -> ONLINE
        d1 = diffs[0]
        self.assertIn("status", d1.changed_keys)
        self.assertEqual(d1.from_state.get("status"), "INITIALIZING")
        self.assertEqual(d1.to_state.get("status"), "ONLINE")

        # Second transition from ONLINE -> DEGRADED
        d2 = diffs[1]
        self.assertIn("status", d2.changed_keys)
        self.assertEqual(d2.from_state.get("status"), "ONLINE")
        self.assertEqual(d2.to_state.get("status"), "DEGRADED")

    def test_03_causal_link_and_evidence_binding(self):
        """Test asserting causal links with evidence links and retrieving them."""
        # Cause: memory leak -> Effect: service degradation
        link = self.service.assert_causal_link(
            cause_entity_id="incident_leak",
            effect_entity_id="srv_01",
            relation_type="TRIGGERED",
            confidence=0.92,
            evidence_ids=["ev_memory_dump_42", "ev_alert_log_99"],
            mechanism_description="Unbounded cache growth triggered OOM conditions.",
        )
        self.assertIsNotNone(link.causal_link_id)
        self.assertEqual(link.cause_entity_id, "incident_leak")
        self.assertEqual(link.effect_entity_id, "srv_01")

        # Verify evidence bindings
        bindings = self.persistence.get_evidence_bindings_for_link(link.causal_link_id)
        self.assertEqual(len(bindings), 2)
        ev_ids = [b.evidence_id for b in bindings]
        self.assertIn("ev_memory_dump_42", ev_ids)
        self.assertIn("ev_alert_log_99", ev_ids)

    def test_04_causal_chain_tracing_and_cycle_prevention(self):
        """Test backward root cause analysis and forward consequence projection with cycles."""
        # Build chain: A -> B -> C -> D
        self.service.assert_causal_link("node_A", "node_B", "RESULTED_IN", confidence=0.95)
        self.service.assert_causal_link("node_B", "node_C", "TRIGGERED", confidence=0.90)
        self.service.assert_causal_link("node_C", "node_D", "INDUCED", confidence=0.85)

        # Introduce a cycle: D -> B
        self.service.assert_causal_link("node_D", "node_B", "REINFORCED", confidence=0.50)

        # Backward Root Cause from D
        chain_back = self.service.trace_causal_chain(entity_id="node_D", direction="ROOT_CAUSE", max_depth=5)
        self.assertEqual(chain_back.root_entity_id, "node_D")
        self.assertEqual(chain_back.direction, "ROOT_CAUSE")
        # Ensure root cause terminates without infinite loop
        visited_ids = [node.entity_id for node in chain_back.nodes]
        self.assertIn("node_C", visited_ids)
        self.assertIn("node_B", visited_ids)
        self.assertIn("node_A", visited_ids)

        # Forward consequence from A
        chain_fwd = self.service.trace_causal_chain(entity_id="node_A", direction="CONSEQUENCE", max_depth=5)
        self.assertEqual(chain_fwd.root_entity_id, "node_A")
        fwd_ids = [node.entity_id for node in chain_fwd.nodes]
        self.assertIn("node_B", fwd_ids)
        self.assertIn("node_C", fwd_ids)
        self.assertIn("node_D", fwd_ids)


if __name__ == "__main__":
    unittest.main()
