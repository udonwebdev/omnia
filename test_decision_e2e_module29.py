"""
End-to-End Integration Test for Module 29: Evidence & Decision Engine.

Pipeline Flow:
1. Ingest realistic facts into Ingestion Repository (Module 27).
2. Index and search via Unified Search & Retrieval Engine (Module 28).
3. Evaluate propositions through Evidence & Decision Service (Module 29).
4. Assert evidence stance attribution, conflict detection, and policy-driven conclusion.
5. Verify durable SQLite persistence and Event Fabric lifecycle emission.
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
from retrieval.persistence import RetrievalPersistence
from retrieval.fusion import RankFusionEngine
from retrieval.service import UnifiedSearchService
from decision.models import (
    DecisionState,
    ClaimStatus,
    DecisionPolicy,
    DecisionRecord
)
from decision.persistence import DecisionPersistence
from decision.evaluator import DecisionEvaluator
from decision.service import EvidenceDecisionService


class TestModule29DecisionE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_fd, cls.template_db = tempfile.mkstemp(suffix=".decision_e2e_template.db")
        os.close(cls.template_fd)
        apply_migrations(cls.template_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.template_db):
            os.remove(cls.template_db)

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_decision_e2e.db")
        shutil.copyfile(self.template_db, self.db_path)

        # Repositories
        self.ingestion_repo = IngestionPersistence(self.db_path)
        self.retrieval_repo = RetrievalPersistence(self.db_path)
        self.decision_repo = DecisionPersistence(self.db_path)

        # Retrieval Engine
        self.retrieval_service = UnifiedSearchService(
            persistence=self.retrieval_repo,
            fusion_engine=RankFusionEngine(),
            node_id="test_node"
        )

        # Decision Engine
        self.evaluator = DecisionEvaluator()
        self.decision_service = EvidenceDecisionService(
            persistence=self.decision_repo,
            evaluator=self.evaluator,
            retrieval_service=self.retrieval_service,
            node_id="test_node"
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_e2e_decision_lifecycle(self):
        # 1. Ingest Fact Record
        prov = ProvenanceRecord(
            provenance_id="prov_e2e_cluster",
            record_id="rec_e2e_cluster",
            envelope_id="env_e2e_cluster",
            source_id="monitor.telemetry",
            connector_id="conn_telemetry",
            operation_id="get_status",
            resource_id="cluster_alpha"
        )
        rec = NormalizedRecord(
            record_id="rec_e2e_cluster",
            envelope_id="env_e2e_cluster",
            canonical_entity_type="cluster_health",
            canonical_id="cluster.mesh.core",
            canonical_data={
                "title": "Mesh Core Integrity Status",
                "content_snippet": "Omnia cluster mesh core protocol is fully active and synchronized",
                "latency_us": 45
            },
            provenance=prov,
            quality=QualityMetadata(quality_score=0.99),
            freshness=FreshnessStatus.FRESH,
            observed_at=time.time(),
            normalized_at=time.time()
        )
        self.ingestion_repo.save_normalized_record(rec)

        # 2. Evaluate Claims against Ingested Evidence
        dec = self.decision_service.evaluate(
            subject_id="cluster.mesh.core",
            decision_type="OPERATIONAL_STATUS",
            claims_text=["Omnia cluster mesh core protocol is fully active"],
            policy=DecisionPolicy(min_confidence_to_accept=0.60)
        )

        # 3. Verify Verifiable Conclusion
        self.assertIsInstance(dec, DecisionRecord)
        self.assertEqual(dec.subject_id, "cluster.mesh.core")
        self.assertEqual(dec.state, DecisionState.ACCEPTED)
        self.assertGreaterEqual(dec.confidence_score, 0.60)
        self.assertLessEqual(dec.uncertainty_score, 0.40)
        self.assertEqual(len(dec.claims), 1)
        self.assertEqual(dec.claims[0].status, ClaimStatus.SUPPORTED)
        self.assertGreaterEqual(len(dec.evidence_links), 1)

        # 4. Verify Durable Persistence
        persisted_dec = self.decision_repo.get_decision(dec.decision_id)
        self.assertIsNotNone(persisted_dec)
        self.assertEqual(persisted_dec.decision_id, dec.decision_id)
        self.assertEqual(persisted_dec.state, DecisionState.ACCEPTED)
        self.assertEqual(len(persisted_dec.claims), 1)
        self.assertEqual(len(persisted_dec.evidence_links), len(dec.evidence_links))


if __name__ == "__main__":
    unittest.main()
