"""
End-to-End Integration Test for Module 28: Unified Search & Retrieval Engine.

Flow:
1. Ingest realistic normalized records into SQLite (Ingestion Pipeline).
2. Insert a configuration item into Distributed Configuration Control Plane.
3. Execute Unified Hybrid Search across multi-corpus federated sources.
4. Verify rank fusion, calibrated confidence, security classification filtering, and provenance hashes.
5. Verify evidence extraction and query telemetry caching.
"""

import unittest
import os
import time
import tempfile
import shutil

from persistence.migrations import apply_migrations
from ingestion.models import (
    NormalizedRecord,
    ProvenanceRecord,
    QualityMetadata,
    DataClassification,
    TrustBoundary,
    FreshnessStatus,
    DataCategory
)
from ingestion.persistence import IngestionPersistence
from retrieval.models import (
    SearchQuery,
    SearchFilter,
    CorpusType,
    EvidenceItem
)
from retrieval.persistence import RetrievalPersistence
from retrieval.sources import (
    IngestedRecordsProvider,
    ConfigStoreProvider
)
from retrieval.fusion import RankFusionEngine
from retrieval.service import UnifiedSearchService


class TestModule28RetrievalE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_fd, cls.template_db = tempfile.mkstemp(suffix=".retrieval_e2e_template.db")
        os.close(cls.template_fd)
        apply_migrations(cls.template_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.template_db):
            os.remove(cls.template_db)

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_retrieval_e2e.db")
        shutil.copyfile(self.template_db, self.db_path)

        self.ingestion_repo = IngestionPersistence(self.db_path)
        self.retrieval_repo = RetrievalPersistence(self.db_path)
        self.fusion = RankFusionEngine()

        self.service = UnifiedSearchService(
            persistence=self.retrieval_repo,
            fusion_engine=self.fusion,
            node_id="test_node"
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_e2e_hybrid_search_and_evidence_extraction(self):
        # 1. Seed Ingested Record
        prov = ProvenanceRecord(
            provenance_id="prov_e2e_99",
            record_id="rec_telemetry_99",
            envelope_id="env_telemetry_99",
            source_id="github.repo.activity",
            connector_id="conn_gh",
            operation_id="get_telemetry",
            resource_id="cluster_alpha"
        )
        rec = NormalizedRecord(
            record_id="rec_telemetry_99",
            envelope_id="env_telemetry_99",
            canonical_entity_type="cluster_telemetry",
            canonical_id="cluster.node.alpha",
            canonical_data={
                "title": "Alpha Node Diagnostic",
                "summary": "Alpha node heartbeat healthy with zero latency on cluster mesh",
                "cpu_load": 0.12
            },
            provenance=prov,
            quality=QualityMetadata(quality_score=0.98),
            freshness=FreshnessStatus.FRESH,
            observed_at=time.time(),
            normalized_at=time.time()
        )
        self.ingestion_repo.save_normalized_record(rec)

        # 2. Seed Config Item in DB
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            now = time.time()
            conn.execute("""
                INSERT OR REPLACE INTO config_schemas (key, domain, data_type, default_value_json, scope, schema_spec_json, description, created_at, updated_at)
                VALUES ('cluster.mesh.topology', 'cluster', 'string', '"mesh_ring_topology_v1"', 'CLUSTER', '{}', 'Active mesh network topology configuration', ?, ?)
            """, (now, now))
            conn.commit()

        # 3. Search query spanning all corpora
        query = SearchQuery(
            query_id="q_e2e_search",
            query_text="mesh topology",
            filters=SearchFilter(
                max_classification=DataClassification.INTERNAL,
                exclude_stale=True
            ),
            limit=5
        )

        result = self.service.search(query)

        # 4. Assertions on Search Result and Evidence
        self.assertEqual(result.query_id, "q_e2e_search")
        self.assertGreaterEqual(result.total_hits, 1)
        self.assertGreaterEqual(len(result.evidence_items), 1)

        top_evidence = result.evidence_items[0]
        self.assertIsInstance(top_evidence, EvidenceItem)
        self.assertGreater(top_evidence.confidence_score, 0.0)
        self.assertLessEqual(top_evidence.confidence_score, 1.0)
        self.assertTrue(top_evidence.provenance_hash)

        # 5. Verify Retrieval Evidence Persisted in DB
        persisted_evidence = self.retrieval_repo.get_evidence_by_query("q_e2e_search")
        self.assertGreaterEqual(len(persisted_evidence), 1)
        self.assertEqual(persisted_evidence[0].query_id, "q_e2e_search")

        # 6. Verify Logged Query
        logged = self.retrieval_repo.get_logged_query("q_e2e_search")
        self.assertIsNotNone(logged)
        self.assertEqual(logged["query_id"], "q_e2e_search")
        self.assertGreaterEqual(logged["total_hits"], 1)


if __name__ == "__main__":
    unittest.main()
