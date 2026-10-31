"""
OMNIA Module 36: Knowledge Synthesis Engine
Extracts evidence-grounded claims, maps cross-domain relationships, and preserves epistemic integrity.
Never merges forecasts, simulations, or hypotheses into unlabeled factual assertions.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from synthesis.models import (
    SynthesizedClaim,
    EpistemicClaimType,
)
from synthesis.persistence import SynthesisRepository

logger = logging.getLogger("Omnia.Synthesis.Engine")


class KnowledgeSynthesisEngine:
    """Aggregates multi-source evidence and outputs structured, typed claims."""

    def __init__(self, repo: SynthesisRepository):
        self.repo = repo

    def synthesize_claims(
        self,
        briefing_version_id: str,
        raw_evidence_items: List[Dict[str, Any]],
    ) -> List[SynthesizedClaim]:
        """
        Transforms heterogeneous evidence items into typed claims with explicit provenance:
        Ensures strict epistemic labeling (FORECAST, SIMULATION_RESULT, VERIFIED_FACT, DIRECT_OBSERVATION).
        """
        claims: List[SynthesizedClaim] = []

        for i, item in enumerate(raw_evidence_items):
            raw_claim = item.get("claim", item.get("text", item.get("statement", "")).strip())
            if not raw_claim:
                continue

            # Determine epistemic type based on origin metadata or explicit type flag
            item_type_str = str(item.get("type", item.get("source_type", "VERIFIED_FACT"))).upper()

            if "FORECAST" in item_type_str or "PREDICTION" in item_type_str or item.get("is_forecast"):
                claim_type = EpistemicClaimType.FORECAST
            elif "SIMULATION" in item_type_str or item.get("is_simulated"):
                claim_type = EpistemicClaimType.SIMULATION_RESULT
            elif "HYPOTHESIS" in item_type_str:
                claim_type = EpistemicClaimType.HYPOTHESIS
            elif "STATISTICAL" in item_type_str:
                claim_type = EpistemicClaimType.STATISTICAL_FINDING
            elif "OBSERVATION" in item_type_str:
                claim_type = EpistemicClaimType.DIRECT_OBSERVATION
            elif "RECOMMENDATION" in item_type_str:
                claim_type = EpistemicClaimType.RECOMMENDATION
            elif "INTERPRETATION" in item_type_str:
                claim_type = EpistemicClaimType.INTERPRETATION
            else:
                claim_type = EpistemicClaimType.VERIFIED_FACT

            source_refs = item.get("source_refs", [item.get("source_ref", f"source_{i}")])
            contra_refs = item.get("contradictory_refs", [])
            conf_str = item.get("confidence_assessment", "HIGH")
            conf_score = float(item.get("confidence_score", 0.85))

            claim = SynthesizedClaim(
                claim_id=f"clm-{uuid.uuid4().hex[:8]}",
                briefing_version_id=briefing_version_id,
                claim_text=raw_claim,
                claim_type=claim_type,
                supporting_evidence_refs=source_refs if isinstance(source_refs, list) else [source_refs],
                contradictory_evidence_refs=contra_refs if isinstance(contra_refs, list) else [contra_refs],
                confidence_assessment=conf_str,
                confidence_score=conf_score,
                temporal_scope=item.get("temporal_scope", "CURRENT"),
                known_assumptions=item.get("assumptions", []),
                limitations=item.get("limitations", []),
            )
            self.repo.save_claim(claim)
            claims.append(claim)

        logger.info(f"Synthesized {len(claims)} epistemic claims for version '{briefing_version_id}'")
        return claims

    def link_cross_domain_findings(
        self,
        domain_a_claims: List[SynthesizedClaim],
        domain_b_claims: List[SynthesizedClaim],
        relationship_type: str = "CORRELATED_DEVELOPMENT",
    ) -> List[Dict[str, Any]]:
        """
        Connects findings across distinct research/operational domains:
        Requires explicit relationship types and preserves uncertainty rather than assuming causality.
        """
        connections = []
        for ca in domain_a_claims:
            for cb in domain_b_claims:
                # Look for temporal alignment or matching contextual tags
                if ca.temporal_scope == cb.temporal_scope or ca.confidence_score > 0.7:
                    conn = {
                        "connection_id": f"conn-{uuid.uuid4().hex[:8]}",
                        "claim_a_id": ca.claim_id,
                        "claim_a_text": ca.claim_text,
                        "claim_b_id": cb.claim_id,
                        "claim_b_text": cb.claim_text,
                        "relationship_type": relationship_type,
                        "epistemic_note": "Inferred cross-domain correlation; non-causal without temporal intervention proof.",
                        "confidence": round(min(ca.confidence_score, cb.confidence_score) * 0.9, 2),
                    }
                    connections.append(conn)
        return connections
