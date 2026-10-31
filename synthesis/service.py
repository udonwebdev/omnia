"""
OMNIA Module 36: Intelligence Briefing Master Service & Event Integration
Coordinates the entire intelligence loop:
Product Registry -> Evidence Gathering -> Development Detection -> Contradiction Analysis ->
Knowledge Synthesis -> Quality Gating -> Briefing Versioning -> Authorized Delivery.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from synthesis.models import (
    IntelligenceProductRecord,
    ProductType,
    AudienceLevel,
    BriefingVersion,
    DeliveryRecord,
    SynthesizedClaim,
    ContradictionRecord,
    DevelopmentRecord,
)
from synthesis.persistence import SynthesisRepository
from synthesis.registry import IntelligenceProductRegistry
from synthesis.analyzer import DevelopmentDetector, ContradictionAnalyzer, SignificanceAssessmentService
from synthesis.engine import KnowledgeSynthesisEngine
from synthesis.generator import BriefingGenerator
from synthesis.delivery import BriefingDeliveryCoordinator

logger = logging.getLogger("Omnia.Synthesis.Service")


class IntelligenceOrchestrator:
    """Master facade for autonomous knowledge synthesis and intelligence briefing generation."""

    def __init__(self, db_path: str = "omnia.db", event_bus: Optional[Any] = None):
        self.repo = SynthesisRepository(db_path=db_path)
        self.registry = IntelligenceProductRegistry(self.repo)
        self.dev_detector = DevelopmentDetector(self.repo)
        self.contradiction_analyzer = ContradictionAnalyzer(self.repo)
        self.significance_service = SignificanceAssessmentService()
        self.synthesis_engine = KnowledgeSynthesisEngine(self.repo)
        self.briefing_generator = BriefingGenerator(self.repo)
        self.delivery_coordinator = BriefingDeliveryCoordinator(self.repo)
        self.event_bus = event_bus

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publishes intelligence events to the Omnia Event Fabric."""
        if self.event_bus and hasattr(self.event_bus, "publish"):
            try:
                from events.models import EventEnvelope
                envelope = EventEnvelope(
                    topic=topic,
                    payload=payload,
                    source="intelligence.orchestrator",
                )
                self.event_bus.publish(envelope)
            except Exception as e:
                logger.debug(f"Event bus emit skipped: {e}")

    # Core Intelligence Pipeline
    def register_product(
        self,
        name: str,
        purpose: str,
        product_type: ProductType,
        domain: str,
        intended_audience: AudienceLevel,
        authorized_scope: str,
        required_sources: List[str],
        update_cadence: str = "ON_DEMAND",
        max_length_words: int = 1500,
        freshness_window_sec: float = 86400.0,
        retention_days: int = 90,
        approval_required: bool = False,
    ) -> IntelligenceProductRecord:
        """Registers a recurring or ad-hoc intelligence product."""
        prod = self.registry.register_product(
            name=name,
            purpose=purpose,
            product_type=product_type,
            domain=domain,
            intended_audience=intended_audience,
            authorized_scope=authorized_scope,
            required_sources=required_sources,
            update_cadence=update_cadence,
            max_length_words=max_length_words,
            freshness_window_sec=freshness_window_sec,
            retention_days=retention_days,
            approval_required=approval_required,
        )
        self._emit_event("intelligence.product.created", prod.to_dict())
        return prod

    def synthesize_and_generate_briefing(
        self,
        product_id: str,
        evidence_items: List[Dict[str, Any]],
        previous_evidence_items: Optional[List[Dict[str, Any]]] = None,
        custom_summary: Optional[str] = None,
        approval_token: Optional[str] = None,
    ) -> BriefingVersion:
        """
        Executes end-to-end knowledge synthesis and renders a versioned intelligence briefing:
        1. Analyzes developments and state shifts against previous evidence
        2. Detects material contradictions across sources
        3. Extracts structured epistemic claims
        4. Validates claim-to-evidence quality gate
        5. Persists immutable briefing version
        """
        product = self.repo.get_product(product_id)
        if not product:
            raise ValueError(f"Intelligence product '{product_id}' not found")

        self._emit_event("intelligence.synthesis.started", {"product_id": product_id})

        # Determine version number
        latest = self.repo.get_latest_briefing_version(product_id)
        version_num = (latest.version_number + 1) if latest else 1

        # 1. Detect developments
        developments = self.dev_detector.detect_changes(
            product_id=product_id,
            current_evidence_items=evidence_items,
            previous_evidence_items=previous_evidence_items,
        )
        for dev in developments:
            self._emit_event("intelligence.development.detected", dev.to_dict())

        # 2. Analyze contradictions
        contradictions = self.contradiction_analyzer.analyze_contradictions(
            product_id=product_id,
            evidence_items=evidence_items,
        )
        for c in contradictions:
            self._emit_event("intelligence.contradiction.detected", c.to_dict())

        # 3. Synthesize claims with epistemic labeling
        placeholder_version_id = f"bver-staged-{version_num}"
        claims = self.synthesis_engine.synthesize_claims(
            briefing_version_id=placeholder_version_id,
            raw_evidence_items=evidence_items,
        )

        # 4. Generate & audit briefing version
        briefing = self.briefing_generator.generate_briefing(
            product=product,
            version_number=version_num,
            claims=claims,
            evidence_sources=evidence_items,
            developments=developments,
            contradictions=contradictions,
            custom_executive_summary=custom_summary,
            approval_token=approval_token,
        )

        # Re-link claims to final version_id
        for c in claims:
            c.briefing_version_id = briefing.version_id
            self.repo.save_claim(c)

        self._emit_event("intelligence.briefing.generated", briefing.to_dict())
        return briefing

    def deliver_briefing(
        self,
        briefing_version_id: str,
        recipient_id: str,
        channel: str = "INTERNAL_PORTAL",
        idempotency_key: Optional[str] = None,
        recipient_authorized_scopes: Optional[List[str]] = None,
    ) -> DeliveryRecord:
        """Enforces scope authorization and executes idempotent briefing delivery."""
        self._emit_event("intelligence.briefing.delivery_started", {
            "version_id": briefing_version_id,
            "recipient_id": recipient_id,
            "channel": channel,
        })
        record = self.delivery_coordinator.deliver_briefing(
            briefing_version_id=briefing_version_id,
            recipient_id=recipient_id,
            channel=channel,
            idempotency_key=idempotency_key,
            recipient_authorized_scopes=recipient_authorized_scopes,
        )
        if record.status.value == "DELIVERED":
            self._emit_event("intelligence.briefing.delivered", record.to_dict())
        else:
            self._emit_event("intelligence.briefing.delivery_failed", record.to_dict())
        return record


# Global singleton
intelligence_service = IntelligenceOrchestrator()
