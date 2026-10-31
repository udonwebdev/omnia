"""
Unit tests for Omnia Module 36: Autonomous Knowledge Synthesis & Intelligence Briefing Engine.
"""

import os
import unittest
import tempfile
import shutil

from synthesis.models import (
    ProductType,
    AudienceLevel,
    ProductLifecycleState,
    EpistemicClaimType,
    ChangeType,
    ContradictionStatus,
    DeliveryStatus,
)
from synthesis.persistence import SynthesisRepository
from synthesis.registry import IntelligenceProductRegistry
from synthesis.analyzer import DevelopmentDetector, ContradictionAnalyzer, SignificanceAssessmentService
from synthesis.engine import KnowledgeSynthesisEngine
from synthesis.generator import BriefingGenerator, BriefingQualityEvaluator
from synthesis.delivery import BriefingDeliveryCoordinator
from synthesis.service import IntelligenceOrchestrator


class TestSynthesisModule36(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_synthesis.db")
        self.repo = SynthesisRepository(self.db_path)
        self.registry = IntelligenceProductRegistry(self.repo)
        self.dev_detector = DevelopmentDetector(self.repo)
        self.contradiction_analyzer = ContradictionAnalyzer(self.repo)
        self.significance_service = SignificanceAssessmentService()
        self.engine = KnowledgeSynthesisEngine(self.repo)
        self.generator = BriefingGenerator(self.repo)
        self.delivery = BriefingDeliveryCoordinator(self.repo)
        self.service = IntelligenceOrchestrator(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_product_registration_and_validation(self):
        # 1. Reject invalid product registration
        with self.assertRaises(ValueError):
            self.registry.register_product(
                name="",
                purpose="Missing name",
                product_type=ProductType.EXECUTIVE_BRIEF,
                domain="STORAGE",
                intended_audience=AudienceLevel.EXECUTIVE,
                authorized_scope="INTERNAL",
                required_sources=["telemetry"],
            )

        # 2. Register valid product
        prod = self.registry.register_product(
            name="Daily Storage Health Brief",
            purpose="Summarize cluster storage metrics and latency shifts",
            product_type=ProductType.EXECUTIVE_BRIEF,
            domain="STORAGE_ENGINE",
            intended_audience=AudienceLevel.EXECUTIVE,
            authorized_scope="STORAGE_CLUSTER_A",
            required_sources=["storage.iops", "storage.latency"],
            update_cadence="DAILY",
        )
        self.assertIsNotNone(prod.product_id)
        self.assertEqual(prod.state, ProductLifecycleState.ACTIVE)

        fetched = self.repo.get_product(prod.product_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Daily Storage Health Brief")

    def test_development_detection_and_classification(self):
        prod = self.service.register_product(
            name="Network Incident Brief",
            purpose="Track network latency",
            product_type=ProductType.TECHNICAL_REPORT,
            domain="NETWORK",
            intended_audience=AudienceLevel.TECHNICAL,
            authorized_scope="NETWORK_CORE",
            required_sources=["switch_telemetry"],
        )

        prev_evidence = [
            {"id": "ev_1", "title": "Core Router Latency", "value": "12ms", "status": "NORMAL"}
        ]
        curr_evidence = [
            {"id": "ev_1", "title": "Core Router Latency", "value": "85ms", "status": "DEGRADED", "significance": 0.8},
            {"id": "ev_2", "title": "Packet Drop Rate", "value": "4.2%", "status": "ELEVATED", "significance": 0.9}
        ]

        devs = self.dev_detector.detect_changes(prod.product_id, curr_evidence, prev_evidence)
        self.assertEqual(len(devs), 2)

        # ev_1 is UPDATED
        dev_updated = next(d for d in devs if "Core Router Latency" in d.summary)
        self.assertEqual(dev_updated.change_type, ChangeType.UPDATED)
        self.assertEqual(dev_updated.previous_state, "12ms")
        self.assertEqual(dev_updated.new_state, "85ms")

        # ev_2 is NEW
        dev_new = next(d for d in devs if "Packet Drop Rate" in d.summary)
        self.assertEqual(dev_new.change_type, ChangeType.NEW)

    def test_contradiction_analyzer_preserves_dissent(self):
        prod = self.service.register_product(
            name="Security Assessment Digest",
            purpose="Evaluate cluster security posture",
            product_type=ProductType.THREAT_SUMMARY,
            domain="SECURITY",
            intended_audience=AudienceLevel.EXECUTIVE,
            authorized_scope="GLOBAL",
            required_sources=["scanner_a", "scanner_b"],
        )

        evidence = [
            {"topic": "Firewall Rule 22", "polarity": "COMPLIANT", "claim": "Port 22 closed to public", "source_ref": "scanner_internal"},
            {"topic": "Firewall Rule 22", "polarity": "NON_COMPLIANT", "claim": "Port 22 open on ingress", "source_ref": "external_audit"}
        ]

        contras = self.contradiction_analyzer.analyze_contradictions(prod.product_id, evidence)
        self.assertEqual(len(contras), 1)
        c = contras[0]
        self.assertEqual(c.status, ContradictionStatus.UNRESOLVED)
        self.assertIn("scanner_internal", c.source_a_ref)
        self.assertIn("external_audit", c.source_b_ref)

    def test_explainable_significance_assessment(self):
        assessment = self.significance_service.assess(
            event_or_change_id="change_db_outage",
            urgency=0.9,
            potential_impact=0.85,
            evidence_reliability=0.95,
            affected_blast_radius=8,
        )
        self.assertFalse(assessment.is_provisional)
        self.assertGreater(assessment.overall_significance, 0.7)
        self.assertIn("Impact: 0.85", assessment.reasoning)
        self.assertIn("Blast Radius entities: 8", assessment.reasoning)

    def test_epistemic_claim_labeling_and_quality_audit(self):
        raw_evidence = [
            {"claim": "Observed CPU peak was 92%", "type": "DIRECT_OBSERVATION", "source_ref": "node_metrics"},
            {"claim": "CPU load is projected to reach 100% by midnight", "type": "FORECAST", "source_ref": "model_m32"},
            {"claim": "Simulation predicts cache flush recovers 40% memory", "type": "SIMULATION_RESULT", "source_ref": "twin_m34"},
        ]

        claims = self.engine.synthesize_claims("test_ver_1", raw_evidence)
        self.assertEqual(len(claims), 3)

        claim_types = [c.claim_type for c in claims]
        self.assertIn(EpistemicClaimType.DIRECT_OBSERVATION, claim_types)
        self.assertIn(EpistemicClaimType.FORECAST, claim_types)
        self.assertIn(EpistemicClaimType.SIMULATION_RESULT, claim_types)

        # Quality audit passes because claims are grounded in provided sources
        quality = self.generator.evaluator.evaluate(claims, raw_evidence, [])
        self.assertTrue(quality.passed)
        self.assertEqual(quality.evidence_traceability_pct, 100.0)
        self.assertTrue(quality.citation_integrity)

    def test_scope_authorization_and_idempotent_delivery(self):
        prod = self.service.register_product(
            name="Classified Infrastructure Memo",
            purpose="Review classified cluster topology",
            product_type=ProductType.DECISION_SUPPORT,
            domain="INFRASTRUCTURE",
            intended_audience=AudienceLevel.INTERNAL,
            authorized_scope="TOP_SECRET_CORE",
            required_sources=["infra_db"],
        )

        briefing = self.service.synthesize_and_generate_briefing(
            product_id=prod.product_id,
            evidence_items=[{"claim": "Core fiber route confirmed", "type": "VERIFIED_FACT", "source_ref": "infra_db"}],
        )

        # 1. Delivery blocked when recipient lacks scope
        blocked_deliv = self.delivery.deliver_briefing(
            briefing_version_id=briefing.version_id,
            recipient_id="operator_bob",
            recipient_authorized_scopes=["PUBLIC", "UNCLASSIFIED"],
        )
        self.assertEqual(blocked_deliv.status, DeliveryStatus.BLOCKED)
        self.assertIn("Access denied", blocked_deliv.error_message)

        # 2. Delivery succeeds when authorized
        ok_deliv = self.delivery.deliver_briefing(
            briefing_version_id=briefing.version_id,
            recipient_id="operator_alice",
            recipient_authorized_scopes=["TOP_SECRET_CORE"],
            idempotency_key="deliv_key_alice_1",
        )
        self.assertEqual(ok_deliv.status, DeliveryStatus.DELIVERED)

        # 3. Idempotent re-delivery returns same status without duplicate send
        dup_deliv = self.delivery.deliver_briefing(
            briefing_version_id=briefing.version_id,
            recipient_id="operator_alice",
            recipient_authorized_scopes=["TOP_SECRET_CORE"],
            idempotency_key="deliv_key_alice_1",
        )
        self.assertEqual(dup_deliv.delivery_id, ok_deliv.delivery_id)
        self.assertEqual(dup_deliv.status, DeliveryStatus.DELIVERED)


if __name__ == "__main__":
    unittest.main()
