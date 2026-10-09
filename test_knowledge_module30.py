"""
Unit Tests for Module 30: Knowledge Graph & Entity Resolution Engine
Validates:
1. GraphEntity and GraphRelationship lifecycle & persistence.
2. EntityIdentity association and lookup.
3. EntityResolver similarity evaluation and non-destructive auto-resolution.
4. Bounded graph traversal and shortest path discovery with cycle prevention.
5. Entity splitting to safely undo erroneous merges.
"""

import os
import unittest
import tempfile
import shutil

from knowledge.models import (
    GraphEntity,
    GraphRelationship,
    EntityIdentity,
    EntityType,
    EntityStatus,
    IdentifierType,
    ResolutionStatus,
)
from knowledge.persistence import KnowledgePersistence
from knowledge.resolver import EntityResolver
from knowledge.traversal import GraphTraversalEngine
from knowledge.service import KnowledgeGraphService


class TestKnowledgeGraphModule30(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.temp_dir, "test_knowledge.db")
        cls.persistence = KnowledgePersistence(db_path=cls.db_path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_1_entity_and_relationship_lifecycle(self):
        e1 = GraphEntity(
            entity_id="ent-node-alpha",
            canonical_name="Alpha Node",
            entity_type=EntityType.SYSTEM,
            aliases=["Node-A", "Alpha-Worker"],
            attributes={"region": "us-east-1", "capacity": 64},
        )
        e2 = GraphEntity(
            entity_id="ent-node-beta",
            canonical_name="Beta Node",
            entity_type=EntityType.SYSTEM,
            aliases=["Node-B"],
            attributes={"region": "us-west-2", "capacity": 128},
        )

        self.persistence.upsert_entity(e1)
        self.persistence.upsert_entity(e2)

        retrieved1 = self.persistence.get_entity("ent-node-alpha")
        self.assertIsNotNone(retrieved1)
        self.assertEqual(retrieved1.canonical_name, "Alpha Node")
        self.assertIn("Node-A", retrieved1.aliases)
        self.assertEqual(retrieved1.attributes.get("capacity"), 64)

        rel = GraphRelationship(
            relationship_id="rel-alpha-beta",
            source_id="ent-node-alpha",
            predicate="COMMUNICATES_WITH",
            target_id="ent-node-beta",
            properties={"latency_ms": 14.5},
            confidence=0.98,
            weight=1.0,
        )
        self.persistence.upsert_relationship(rel)

        out_rels = self.persistence.find_relationships_from("ent-node-alpha")
        self.assertEqual(len(out_rels), 1)
        self.assertEqual(out_rels[0].predicate, "COMMUNICATES_WITH")
        self.assertEqual(out_rels[0].target_id, "ent-node-beta")

        in_rels = self.persistence.find_relationships_to("ent-node-beta")
        self.assertEqual(len(in_rels), 1)
        self.assertEqual(in_rels[0].source_id, "ent-node-alpha")

    def test_2_entity_identities_and_lookup(self):
        entity = GraphEntity(
            entity_id="ent-usr-42",
            canonical_name="Jane Doe",
            entity_type=EntityType.PERSON,
        )
        self.persistence.upsert_entity(entity)

        ident1 = EntityIdentity(
            identity_id="id-email",
            entity_id="ent-usr-42",
            identifier_type=IdentifierType.EMAIL,
            identifier_value="jane.doe@example.com",
        )
        ident2 = EntityIdentity(
            identity_id="id-uuid",
            entity_id="ent-usr-42",
            identifier_type=IdentifierType.UUID,
            identifier_value="uuid-usr-42-abc",
        )
        self.persistence.add_identity(ident1)
        self.persistence.add_identity(ident2)

        found = self.persistence.find_entity_by_identity(IdentifierType.EMAIL, "jane.doe@example.com")
        self.assertIsNotNone(found)
        self.assertEqual(found.entity_id, "ent-usr-42")
        self.assertEqual(found.canonical_name, "Jane Doe")

    def test_3_entity_resolution_and_nondestructive_merge(self):
        resolver = EntityResolver(self.persistence)

        e1 = GraphEntity(
            entity_id="srv-auth-primary",
            canonical_name="Omnia AuthService",
            entity_type=EntityType.SERVICE,
            aliases=["Auth-Service-v1"],
            attributes={"port": 8080, "protocol": "https"},
        )
        e2 = GraphEntity(
            entity_id="srv-auth-secondary",
            canonical_name="Omnia AuthService",
            entity_type=EntityType.SERVICE,
            aliases=["Auth-Daemon"],
            attributes={"port": 8080, "protocol": "https"},
        )
        self.persistence.upsert_entity(e1)
        self.persistence.upsert_entity(e2)

        score, reasons = resolver.compute_similarity(e1, e2)
        self.assertGreaterEqual(score, 0.85)
        self.assertIn("exact_canonical_name_match", reasons)

        candidates = resolver.evaluate_candidates(e1, min_threshold=0.7)
        self.assertGreaterEqual(len(candidates), 1)

        actions = resolver.auto_resolve(auto_merge_threshold=0.8)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["primary_id"], "srv-auth-primary")
        self.assertEqual(actions[0]["merged_id"], "srv-auth-secondary")

        primary = self.persistence.get_entity("srv-auth-primary")
        secondary = self.persistence.get_entity("srv-auth-secondary")

        self.assertEqual(primary.status, EntityStatus.ACTIVE)
        self.assertTrue("Auth-Daemon" in primary.aliases or "Omnia AuthService" in primary.aliases)
        self.assertEqual(secondary.status, EntityStatus.MERGED)
        self.assertEqual(secondary.merged_into_id, "srv-auth-primary")

        split_ok = self.persistence.split_entity("srv-auth-secondary", reason="False positive resolution")
        self.assertTrue(split_ok)
        restored = self.persistence.get_entity("srv-auth-secondary")
        self.assertEqual(restored.status, EntityStatus.ACTIVE)
        self.assertIsNone(restored.merged_into_id)

    def test_4_graph_traversal_and_shortest_path(self):
        nodes = ["A", "B", "C", "D", "E"]
        for n in nodes:
            self.persistence.upsert_entity(GraphEntity(
                entity_id=f"node-{n}",
                canonical_name=f"Node {n}",
                entity_type=EntityType.SYSTEM,
            ))

        edges = [
            ("A", "B", 1.0),
            ("B", "C", 1.0),
            ("C", "D", 1.0),
            ("A", "E", 1.5),
            ("E", "D", 1.5),
        ]
        for src, tgt, w in edges:
            self.persistence.upsert_relationship(GraphRelationship(
                relationship_id=f"rel-{src}-{tgt}",
                source_id=f"node-{src}",
                predicate="CONNECTS_TO",
                target_id=f"node-{tgt}",
                weight=w,
            ))

        traversal = GraphTraversalEngine(self.persistence)

        sub1 = traversal.extract_subgraph("node-A", max_depth=1)
        sub1_ids = {e.entity_id for e in sub1.entities}
        self.assertEqual(sub1_ids, {"node-A", "node-B", "node-E"})

        path = traversal.find_shortest_path("node-A", "node-D")
        self.assertIsNotNone(path)
        self.assertEqual(path.total_depth, 2)
        self.assertEqual([e.entity_id for e in path.entities], ["node-A", "node-E", "node-D"])


if __name__ == "__main__":
    unittest.main()
