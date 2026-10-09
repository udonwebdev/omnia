"""
Unit Tests for Omnia Module 29: Evidence & Decision Engine.
Verifies:
- Claim evaluation and stance attribution (Supporting, Contradicting)
- Weighted confidence calibration and contradiction thresholds
- Conflict detection and severity classification
- Policy-driven acceptance, dispute, and abstention states
- Decision record synthesis, expiration, and durable persistence
"""

import unittest
import os
import tempfile
import shutil
import time

from decision.models import (
    Claim,
    ClaimStatus,
    EvidenceStance,
    DecisionState,
    ConflictSeverity,
    DecisionPolicy,
    DecisionRecord
)
from decision.evaluator import DecisionEvaluator
from decision.persistence import DecisionPersistence
from decision.service import EvidenceDecisionService
from retrieval.models import EvidenceItem, CorpusType, DataClassification, TrustBoundary, FreshnessStatus
from persistence.migrations import apply_migrations


class TestModule29DecisionEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_fd, cls.template_db = tempfile.mkstemp(suffix=".decision_template.db")
        os.close(cls.template_fd)
        apply_migrations(cls.template_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.template_db):
            os.remove(cls.template_db)

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_decision.db")
        shutil.copyfile(self.template_db, self.db_path)

        self.persistence = DecisionPersistence(self.db_path)
        self.evaluator = DecisionEvaluator()
        self.service = EvidenceDecisionService(
            persistence=self.persistence,
            evaluator=self.evaluator,
            node_id="test_node"
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_claim_evaluation_supported(self):
        claim = Claim(
            claim_id="clm_01",
            decision_id="dec_01",
            statement="Node alpha mesh network latency is healthy"
        )
        evidence = [
            EvidenceItem(
                evidence_id="ev_01",
                query_id="q_01",
                corpus_type=CorpusType.INGESTED_RECORDS,
                item_id="rec_01",
                source_record_id="rec_01",
                title="Alpha Diagnostic",
                content_snippet="Node alpha mesh network latency is healthy and running optimal",
                retrieval_score=0.95,
                normalized_score=0.95,
                confidence_score=0.95,
                source_id="cluster.diagnostics",
                canonical_id="node_alpha",
                provenance_hash="prov_1",
                observed_at=time.time(),
                retrieved_at=time.time()
            )
        ]
        policy = DecisionPolicy(min_confidence_to_accept=0.70)
        evaluated, links, conflicts = self.evaluator.evaluate_claims(
            decision_id="dec_01",
            claims=[claim],
            evidence_items=evidence,
            policy=policy
        )

        self.assertEqual(len(evaluated), 1)
        self.assertEqual(evaluated[0].status, ClaimStatus.SUPPORTED)
        self.assertGreaterEqual(evaluated[0].confidence_score, 0.70)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].stance, EvidenceStance.SUPPORTING)
        self.assertEqual(len(conflicts), 0)

    def test_conflict_detection_and_disputed_decision(self):
        claim = Claim(
            claim_id="clm_02",
            decision_id="dec_02",
            statement="Primary cluster database replication is active"
        )
        evidence = [
            EvidenceItem(
                evidence_id="ev_sup",
                query_id="q_02",
                corpus_type=CorpusType.INGESTED_RECORDS,
                item_id="rec_sup",
                source_record_id="rec_sup",
                title="Repl Status",
                content_snippet="Primary cluster database replication is active and operational",
                retrieval_score=0.9,
                normalized_score=0.9,
                confidence_score=0.9,
                source_id="monitor.alpha",
                canonical_id="db_repl",
                provenance_hash="prov_sup",
                observed_at=time.time(),
                retrieved_at=time.time()
            ),
            EvidenceItem(
                evidence_id="ev_contra",
                query_id="q_02",
                corpus_type=CorpusType.TASK_JOURNAL,
                item_id="rec_contra",
                source_record_id="rec_contra",
                title="Repl Warning",
                content_snippet="Primary cluster database replication failed and is not active",
                retrieval_score=0.88,
                normalized_score=0.88,
                confidence_score=0.88,
                source_id="monitor.beta",
                canonical_id="db_repl",
                provenance_hash="prov_contra",
                observed_at=time.time(),
                retrieved_at=time.time()
            )
        ]
        policy = DecisionPolicy()
        evaluated, links, conflicts = self.evaluator.evaluate_claims(
            decision_id="dec_02",
            claims=[claim],
            evidence_items=evidence,
            policy=policy
        )

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].conflict_type, "EVIDENCE_CONTRADICTION")

        dec = self.evaluator.synthesize_decision(
            decision_id="dec_02",
            subject_id="cluster.replication",
            decision_type="HEALTH_STATUS",
            claims=evaluated,
            evidence_links=links,
            conflicts=conflicts,
            policy=policy
        )
        self.assertEqual(dec.state, DecisionState.DISPUTED)

    def test_decision_persistence_and_retrieval(self):
        dec = DecisionRecord(
            decision_id="dec_persist_01",
            subject_id="cluster.mesh.node_gamma",
            decision_type="SECURITY_POSTURE",
            state=DecisionState.ACCEPTED,
            confidence_score=0.88,
            uncertainty_score=0.12,
            summary="Gamma node verified against zero-trust policy",
            evaluated_at=time.time(),
            expires_at=time.time() + 3600.0,
            actor_id="admin_service"
        )
        self.persistence.save_decision(dec)

        fetched = self.persistence.get_decision("dec_persist_01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.decision_id, "dec_persist_01")
        self.assertEqual(fetched.state, DecisionState.ACCEPTED)
        self.assertEqual(fetched.subject_id, "cluster.mesh.node_gamma")
        self.assertFalse(fetched.is_expired())

    def test_abstention_on_insufficient_evidence(self):
        dec = self.service.evaluate(
            subject_id="unknown_subsystem",
            decision_type="STATUS_CHECK",
            claims_text=["Subsystem X exists in external mesh"],
            pre_gathered_evidence=[]
        )
        self.assertIn(dec.state, (DecisionState.ABSTAINED, DecisionState.REJECTED))
        self.assertEqual(dec.confidence_score, 0.0)


if __name__ == "__main__":
    unittest.main()
