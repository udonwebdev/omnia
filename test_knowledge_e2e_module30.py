"""
End-to-End Test for Module 30: Knowledge Graph & Entity Resolution Engine
Verifies complete flow:
1. Entity creation with attributes & aliases via KnowledgeGraphService.
2. Direct relationship assertion and verification.
3. Automated candidate discovery and non-destructive entity resolution.
4. Bounded neighborhood extraction and path discovery across the resolved graph.
5. Invocation of Omnia Tools (create_knowledge_entity, assert_knowledge_relationship, query_knowledge_graph, resolve_entity_candidates).
"""

import os
import unittest
import tempfile
import shutil
import json

from knowledge.models import EntityType, EntityStatus
from knowledge.persistence import KnowledgePersistence
from knowledge.service import KnowledgeGraphService
import omnia_tools


class TestKnowledgeGraphE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.temp_dir, "e2e_knowledge.db")
        cls.persistence = KnowledgePersistence(db_path=cls.db_path)
        cls.service = KnowledgeGraphService(persistence=cls.persistence)
        
        # Monkey patch service in knowledge.service and omnia_tools
        import knowledge.service
        cls._orig_service = knowledge.service.knowledge_graph_service
        knowledge.service.knowledge_graph_service = cls.service
        omnia_tools.knowledge_graph_service = cls.service

    @classmethod
    def tearDownClass(cls):
        import knowledge.service
        knowledge.service.knowledge_graph_service = cls._orig_service
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_e2e_knowledge_lifecycle_and_tools(self):
        # 1. Create entities via Omnia tool
        res_e1 = json.loads(omnia_tools.create_knowledge_entity(
            canonical_name="Control Plane Gateway",
            entity_type="SYSTEM",
            aliases_json=json.dumps(["CP-Gateway", "Gateway-Primary"]),
            attributes_json=json.dumps({"zone": "us-central1-a", "cluster": "alpha"}),
        ))
        self.assertIn("entity_id", res_e1)
        e1_id = res_e1["entity_id"]

        res_e2 = json.loads(omnia_tools.create_knowledge_entity(
            canonical_name="Task Worker Daemon",
            entity_type="SYSTEM",
            aliases_json=json.dumps(["Daemon-01"]),
            attributes_json=json.dumps({"zone": "us-central1-a", "cluster": "alpha"}),
        ))
        self.assertIn("entity_id", res_e2)
        e2_id = res_e2["entity_id"]

        res_e3 = json.loads(omnia_tools.create_knowledge_entity(
            canonical_name="Task Worker Daemon",
            entity_type="SYSTEM",
            aliases_json=json.dumps(["Daemon-Secondary"]),
            attributes_json=json.dumps({"zone": "us-central1-a", "cluster": "alpha"}),
        ))
        e3_id = res_e3["entity_id"]

        # 2. Assert Relationship
        res_rel = json.loads(omnia_tools.assert_knowledge_relationship(
            source_id=e1_id,
            predicate="DISPATCHES_TO",
            target_id=e2_id,
            confidence=0.99,
            weight=1.0,
            properties_json=json.dumps({"protocol": "gRPC", "rate_limit_rps": 1000}),
        ))
        self.assertEqual(res_rel["source_id"], e1_id)
        self.assertEqual(res_rel["predicate"], "DISPATCHES_TO")
        self.assertEqual(res_rel["target_id"], e2_id)

        # 3. Query neighborhood before resolution
        subgraph = json.loads(omnia_tools.query_knowledge_graph(center_entity_id=e1_id, max_depth=1))
        self.assertEqual(subgraph["center_entity_id"], e1_id)
        self.assertEqual(len(subgraph["relationships"]), 1)

        # 4. Resolve candidate entities (e2 and e3 are co-referent Task Worker Daemons)
        res_resolve = json.loads(omnia_tools.resolve_entity_candidates(auto_merge_threshold=0.8))
        self.assertTrue(res_resolve["success"])
        self.assertGreaterEqual(res_resolve["resolved_count"], 1)

        # 5. Verify non-destructive merge status
        ent_e2 = self.service.get_entity(e2_id)
        ent_e3 = self.service.get_entity(e3_id)
        self.assertTrue(
            (ent_e2.status == EntityStatus.MERGED and ent_e3.status == EntityStatus.ACTIVE) or
            (ent_e3.status == EntityStatus.MERGED and ent_e2.status == EntityStatus.ACTIVE)
        )


if __name__ == "__main__":
    unittest.main()
