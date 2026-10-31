"""
End-to-End integration test for Omnia Module 36: Autonomous Knowledge Synthesis & Intelligence Briefing Engine.
"""

import os
import unittest
import tempfile
import shutil

from synthesis.models import (
    ProductType,
    AudienceLevel,
    EpistemicClaimType,
    ChangeType,
    ContradictionStatus,
    DeliveryStatus,
)
from synthesis.service import IntelligenceOrchestrator


class TestSynthesisModule36E2E(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_synthesis_e2e.db")
        self.service = IntelligenceOrchestrator(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_complete_knowledge_synthesis_and_intelligence_briefing_lifecycle(self):
        """
        Full end-to-end intelligence cycle:
        1. Register intelligence product with scope constraints
        2. Ingest multi-source evidence including:
           - Direct observations
           - Predictive forecast (Module 32)
           - Simulation counterfactual (Module 34)
           - Competing contradictory claims across scanners
        3. Synthesize claims with strict epistemic labeling
        4. Detect developments and material contradictions
        5. Pass briefing quality audit (100% evidence traceability)
        6. Render Markdown Briefing Version 1
        7. Material update: Ingest new evidence shift
        8. Synthesize Version 2, proving Version 1 remains immutable
        9. Enforce recipient authorization & verify idempotent delivery
        """
        # Step 1: Register Product
        product = self.service.register_product(
            name="Omnia Autonomous Core Strategic Brief",
            purpose="Synthesize cluster operational status, forecasted bottlenecks, and security posture",
            product_type=ProductType.EXECUTIVE_BRIEF,
            domain="AUTONOMOUS_OPERATIONS",
            intended_audience=AudienceLevel.EXECUTIVE,
            authorized_scope="GLOBAL_OPS",
            required_sources=["telemetry.mesh", "forecast.engine", "sim.twin", "scanner.audit"],
            update_cadence="DAILY",
        )
        self.assertIsNotNone(product.product_id)

        # Step 2: Assemble Multi-Source Heterogeneous Evidence
        initial_evidence = [
            {
                "id": "ev_cpu",
                "topic": "Compute Capacity",
                "claim": "Cluster node CPU utilization is running steady at 48%",
                "type": "DIRECT_OBSERVATION",
                "source_ref": "telemetry.mesh",
                "value": "48%",
                "status": "HEALTHY",
            },
            {
                "id": "ev_fc",
                "topic": "Future Workload",
                "claim": "Predictive model forecasts 35% traffic surge at 18:00 UTC",
                "type": "FORECAST",
                "source_ref": "forecast.engine",
                "value": "+35%",
                "is_forecast": True,
            },
            {
                "id": "ev_sim",
                "topic": "Capacity Headroom",
                "claim": "Digital twin simulation confirms cluster absorbs surge without auto-scaling failure",
                "type": "SIMULATION_RESULT",
                "source_ref": "sim.twin",
                "is_simulated": True,
            },
            # Contradictory evidence pair regarding TLS compliance
            {
                "id": "ev_tls_a",
                "topic": "TLS Ingress",
                "polarity": "SECURE",
                "claim": "TLS 1.3 enforced on all external endpoints",
                "source_ref": "scanner.audit",
            },
            {
                "id": "ev_tls_b",
                "topic": "TLS Ingress",
                "polarity": "VULNERABLE",
                "claim": "Legacy TLS 1.0 handshake accepted on fallback port 8443",
                "source_ref": "threat.intel",
            }
        ]

        # Step 3, 4, 5, 6: Synthesize & Generate Briefing Version 1
        v1 = self.service.synthesize_and_generate_briefing(
            product_id=product.product_id,
            evidence_items=initial_evidence,
            custom_summary="All operations stable with anticipated evening surge and open TLS audit investigation."
        )

        self.assertEqual(v1.version_number, 1)
        self.assertEqual(v1.claims_count, 5)
        self.assertTrue(v1.quality_score["passed"])
        self.assertEqual(v1.quality_score["evidence_traceability_pct"], 100.0)

        # Verify Markdown Content Preserves Epistemic Badges & Contradictions
        v1_md = v1.rendered_content_markdown
        self.assertIn("# Omnia Autonomous Core Strategic Brief — Version 1", v1_md)
        self.assertIn("[DIRECT_OBSERVATION]", v1_md)
        self.assertIn("[FORECAST]", v1_md)
        self.assertIn("[SIMULATION_RESULT]", v1_md)
        self.assertIn("## 4. Disagreements & Competing Evidence", v1_md)
        self.assertIn("Conflicting assessments on 'tls ingress' across sources", v1_md)

        # Step 7 & 8: Material Update -> Synthesize Version 2
        updated_evidence = list(initial_evidence)
        # Update CPU utilization (spike detected)
        updated_evidence[0] = {
            "id": "ev_cpu",
            "topic": "Compute Capacity",
            "claim": "Cluster node CPU utilization spiked to 88% due to early batch execution",
            "type": "DIRECT_OBSERVATION",
            "source_ref": "telemetry.mesh",
            "value": "88%",
            "status": "ELEVATED",
            "significance": 0.85,
        }

        v2 = self.service.synthesize_and_generate_briefing(
            product_id=product.product_id,
            evidence_items=updated_evidence,
            previous_evidence_items=initial_evidence,
        )

        self.assertEqual(v2.version_number, 2)
        # Verify Version 1 is immutable and differs from Version 2
        v1_reloaded = self.service.repo.get_briefing_version(v1.version_id)
        self.assertEqual(v1_reloaded.version_number, 1)
        self.assertNotEqual(v1_reloaded.content_digest_sha256, v2.content_digest_sha256)

        # Verify Version 2 detected UPDATED development
        v2_md = v2.rendered_content_markdown
        self.assertIn("## 3. Significant Developments & State Changes", v2_md)
        self.assertIn("[UPDATED]", v2_md)
        self.assertIn("'48%' -> '88%'", v2_md)

        # Step 9: Delivery Verification & Idempotency
        # 1. Block unauthorized recipient
        blocked = self.service.deliver_briefing(
            briefing_version_id=v2.version_id,
            recipient_id="guest_viewer",
            channel="SLACK_HOOK",
            recipient_authorized_scopes=["GUEST_ONLY"],
        )
        self.assertEqual(blocked.status, DeliveryStatus.BLOCKED)

        # 2. Authorize delivery to executive recipient
        delivered = self.service.deliver_briefing(
            briefing_version_id=v2.version_id,
            recipient_id="chief_operations_officer",
            channel="EXECUTIVE_PORTAL",
            recipient_authorized_scopes=["GLOBAL_OPS"],
            idempotency_key="e2e_deliv_v2_coo",
        )
        self.assertEqual(delivered.status, DeliveryStatus.DELIVERED)
        self.assertIsNotNone(delivered.delivered_at)

        # 3. Idempotent replay does not duplicate delivery
        replay = self.service.deliver_briefing(
            briefing_version_id=v2.version_id,
            recipient_id="chief_operations_officer",
            channel="EXECUTIVE_PORTAL",
            recipient_authorized_scopes=["GLOBAL_OPS"],
            idempotency_key="e2e_deliv_v2_coo",
        )
        self.assertEqual(replay.delivery_id, delivered.delivery_id)
        self.assertEqual(replay.status, DeliveryStatus.DELIVERED)


if __name__ == "__main__":
    unittest.main()
