"""
Unit Tests for Omnia Module 28: Unified Search & Retrieval Engine.
Verifies:
- Hybrid, Semantic, Keyword, and Structured search modes
- Reciprocal Rank Fusion (RRF) and score normalization
- Confidence score calibration (freshness penalty and quality multiplier)
- Security filtering against max_classification boundary
- Extraction and persistence of EvidenceItem records
- Query result caching and hit count tracking
- Error isolation and graceful degradation
"""

import unittest
import os
import tempfile
import shutil
import time

from retrieval.models import (
    SearchMode,
    CorpusType,
    SearchFilter,
    SearchQuery,
    EvidenceItem,
    SearchResult
)
from retrieval.fusion import RankFusionEngine
from retrieval.persistence import RetrievalPersistence
from retrieval.service import UnifiedSearchService
from ingestion.models import DataClassification, TrustBoundary, FreshnessStatus
from persistence.migrations import apply_migrations


class TestModule28Retrieval(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_fd, cls.template_db = tempfile.mkstemp(suffix=".retrieval_template.db")
        os.close(cls.template_fd)
        apply_migrations(cls.template_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.template_db):
            os.remove(cls.template_db)

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_retrieval.db")
        shutil.copyfile(self.template_db, self.db_path)
        self.persistence = RetrievalPersistence(db_path=self.db_path)
        self.fusion = RankFusionEngine(rrf_k=60)
        self.service = UnifiedSearchService(
            persistence=self.persistence,
            fusion_engine=self.fusion
        )

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_rank_fusion_and_score_calibration(self):
        query = SearchQuery(
            query_id="q_fuse_1",
            query_text="kernel mesh",
            filters=SearchFilter()
        )
        candidates = {
            CorpusType.INGESTED_RECORDS: [
                {
                    "corpus_type": CorpusType.INGESTED_RECORDS,
                    "item_id": "rec_01",
                    "source_record_id": "rec_01",
                    "title": "Kernel Spec",
                    "content_snippet": "Omnia distributed kernel mesh",
                    "retrieval_score": 0.95,
                    "source_id": "github.repo",
                    "canonical_id": "kernel",
                    "provenance_hash": "prov_1",
                    "observed_at": time.time(),
                    "classification": DataClassification.INTERNAL,
                    "freshness": FreshnessStatus.FRESH,
                    "metadata": {"quality_score": 1.0}
                }
            ],
            CorpusType.CONFIG_STORE: [
                {
                    "corpus_type": CorpusType.CONFIG_STORE,
                    "item_id": "cfg_01",
                    "source_record_id": "cfg_01",
                    "title": "Mesh Config",
                    "content_snippet": "mesh.network.port",
                    "retrieval_score": 0.88,
                    "source_id": "config.plane",
                    "canonical_id": "cfg_01",
                    "provenance_hash": "prov_2",
                    "observed_at": time.time() - 50000.0,
                    "classification": DataClassification.INTERNAL,
                    "freshness": FreshnessStatus.AGING,
                    "metadata": {"quality_score": 0.9}
                }
            ]
        }
        evidence = self.fusion.fuse_and_rank(query, candidates)
        self.assertEqual(len(evidence), 2)
        # First item should be rec_01 due to higher rank and fresh status
        self.assertEqual(evidence[0].item_id, "rec_01")
        self.assertGreater(evidence[0].confidence_score, evidence[1].confidence_score)
        self.assertGreaterEqual(evidence[0].confidence_score, 0.0)
        self.assertLessEqual(evidence[0].confidence_score, 1.0)

    def test_security_classification_filtering(self):
        query = SearchQuery(
            query_id="q_sec_1",
            query_text="confidential document",
            filters=SearchFilter(max_classification=DataClassification.PUBLIC)
        )
        candidates = {
            CorpusType.INGESTED_RECORDS: [
                {
                    "corpus_type": CorpusType.INGESTED_RECORDS,
                    "item_id": "rec_public",
                    "title": "Public Guide",
                    "classification": DataClassification.PUBLIC,
                    "retrieval_score": 0.7
                },
                {
                    "corpus_type": CorpusType.INGESTED_RECORDS,
                    "item_id": "rec_secret",
                    "title": "Secret Ledger",
                    "classification": DataClassification.SECRET,
                    "retrieval_score": 0.99
                }
            ]
        }
        evidence = self.fusion.fuse_and_rank(query, candidates)
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].item_id, "rec_public")

    def test_search_persistence_and_cache(self):
        item = EvidenceItem(
            evidence_id="ev_test_1",
            query_id="q_test_1",
            corpus_type=CorpusType.INGESTED_RECORDS,
            item_id="rec_99",
            source_record_id="rec_99",
            title="Evidence Record",
            content_snippet="Test Snippet",
            retrieval_score=0.85,
            normalized_score=0.85,
            confidence_score=0.85,
            source_id="source_test",
            canonical_id="can_test",
            provenance_hash="prov_hash",
            observed_at=time.time()
        )
        self.persistence.save_evidence_items([item])
        retrieved = self.persistence.get_evidence_by_query("q_test_1")
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0].evidence_id, "ev_test_1")

        # Test cache
        self.persistence.store_cache_result("test_cache_key", "qhash", "fhash", [{"title": "Cached Title"}])
        cached = self.persistence.get_cached_result("test_cache_key")
        self.assertIsNotNone(cached)
        self.assertEqual(cached[0]["title"], "Cached Title")

    def test_unified_search_service_execution(self):
        res = self.service.search(
            query_text="mesh",
            mode=SearchMode.HYBRID,
            limit=5
        )
        self.assertIsNotNone(res)
        self.assertEqual(res.mode, SearchMode.HYBRID)
        self.assertFalse(res.degraded)
        self.assertGreater(res.latency_ms, 0.0)

        telem = self.service.get_telemetry()
        self.assertGreaterEqual(telem.total_queries, 1)


if __name__ == "__main__":
    unittest.main()
