"""
End-to-End integration tests for Module 31: Temporal Knowledge & Causal State Engine via Omnia Tools.
"""
import unittest
import json
from datetime import datetime, timezone, timedelta

from omnia_tools import (
    record_temporal_entity_state,
    reconstruct_temporal_state,
    assert_causal_link,
    trace_causal_chain,
)


class TestTemporalModule31E2E(unittest.TestCase):
    def test_e2e_temporal_causal_flow(self):
        """Exercises Module 31 end-to-end through the Omnia Tools interface."""
        now = datetime.now(timezone.utc)
        t_minus_2 = (now - timedelta(hours=2)).isoformat()
        t_minus_1 = (now - timedelta(hours=1)).isoformat()

        # 1. Record an earlier state
        rec1_raw = record_temporal_entity_state(
            entity_id="e2e_cluster_primary",
            state_payload_json=json.dumps({"role": "LEADER", "term": 1}),
            valid_from=t_minus_2,
            valid_until=t_minus_1,
        )
        rec1_dict = json.loads(rec1_raw)
        self.assertIn("record_id", rec1_dict)
        self.assertEqual(rec1_dict["entity_id"], "e2e_cluster_primary")

        # 2. Record current state
        rec2_raw = record_temporal_entity_state(
            entity_id="e2e_cluster_primary",
            state_payload_json=json.dumps({"role": "STEPPED_DOWN", "term": 2}),
            valid_from=t_minus_1,
            valid_until="",
        )
        rec2_dict = json.loads(rec2_raw)
        self.assertIn("record_id", rec2_dict)

        # 3. Query historical point-in-time state (as_of)
        as_of_target = (now - timedelta(minutes=90)).isoformat()
        past_query_raw = reconstruct_temporal_state(
            entity_id="e2e_cluster_primary",
            valid_time=as_of_target,
        )
        past_query = json.loads(past_query_raw)
        self.assertTrue(past_query.get("found"))
        self.assertEqual(past_query["record"]["state_payload"]["role"], "LEADER")

        # 4. Assert causal link backed by evidence
        link_raw = assert_causal_link(
            cause_entity_id="heartbeat_loss_event",
            effect_entity_id="e2e_cluster_primary",
            relation_type="RESULTED_IN",
            confidence=0.98,
            evidence_ids_json=json.dumps(["ev_timeout_99"]),
            mechanism_description="Missed 3 consecutive heartbeats triggered stepdown.",
        )
        link_dict = json.loads(link_raw)
        self.assertIn("causal_link_id", link_dict)
        self.assertEqual(link_dict["cause_entity_id"], "heartbeat_loss_event")

        # 5. Trace causal root cause
        trace_raw = trace_causal_chain(
            entity_id="e2e_cluster_primary",
            direction="ROOT_CAUSE",
            max_depth=3,
        )
        trace_dict = json.loads(trace_raw)
        self.assertEqual(trace_dict["root_entity_id"], "e2e_cluster_primary")
        self.assertEqual(trace_dict["direction"], "ROOT_CAUSE")
        self.assertGreaterEqual(len(trace_dict["nodes"]), 1)
        node_ids = [n["entity_id"] for n in trace_dict["nodes"]]
        self.assertIn("heartbeat_loss_event", node_ids)


if __name__ == "__main__":
    unittest.main()
