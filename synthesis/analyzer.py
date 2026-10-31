"""
OMNIA Module 36: Intelligence Analyzer & Significance Assessor
Detects developments/changes, analyzes material contradictions, and performs explainable significance scoring.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from synthesis.models import (
    DevelopmentRecord,
    ChangeType,
    ContradictionRecord,
    ContradictionStatus,
    SignificanceAssessment,
)
from synthesis.persistence import SynthesisRepository

logger = logging.getLogger("Omnia.Synthesis.Analyzer")


class DevelopmentDetector:
    """Detects meaningful changes between current and previous evidence sets."""

    def __init__(self, repo: SynthesisRepository):
        self.repo = repo

    def detect_changes(
        self,
        product_id: str,
        current_evidence_items: List[Dict[str, Any]],
        previous_evidence_items: Optional[List[Dict[str, Any]]] = None,
    ) -> List[DevelopmentRecord]:
        """Classifies differences as NEW, UPDATED, CONFIRMED, or CONTRADICTED."""
        developments: List[DevelopmentRecord] = []
        prev_map = {item.get("id", f"idx_{i}"): item for i, item in enumerate(previous_evidence_items or [])}

        for i, item in enumerate(current_evidence_items):
            item_id = item.get("id", f"idx_{i}")
            if item_id not in prev_map:
                # Newly available evidence
                dev = DevelopmentRecord(
                    development_id=f"dev-{uuid.uuid4().hex[:8]}",
                    product_id=product_id,
                    change_type=ChangeType.NEW,
                    summary=f"New evidence discovered: {item.get('title', item.get('claim', 'Observation'))}",
                    previous_state=None,
                    new_state=str(item.get("value", item.get("status", "ACTIVE"))),
                    source_refs=[item.get("source_ref", item_id)],
                    significance_score=float(item.get("significance", 0.6)),
                )
                self.repo.save_development(dev)
                developments.append(dev)
            else:
                prev_item = prev_map[item_id]
                prev_val = str(prev_item.get("value", prev_item.get("status", "")))
                curr_val = str(item.get("value", item.get("status", "")))

                if prev_val != curr_val and curr_val:
                    # Material change detected
                    dev = DevelopmentRecord(
                        development_id=f"dev-{uuid.uuid4().hex[:8]}",
                        product_id=product_id,
                        change_type=ChangeType.UPDATED,
                        summary=f"Updated state for {item.get('title', item_id)}: '{prev_val}' -> '{curr_val}'",
                        previous_state=prev_val,
                        new_state=curr_val,
                        source_refs=[item.get("source_ref", item_id)],
                        significance_score=float(item.get("significance", 0.75)),
                    )
                    self.repo.save_development(dev)
                    developments.append(dev)
                else:
                    # Unchanged confirmation
                    dev = DevelopmentRecord(
                        development_id=f"dev-{uuid.uuid4().hex[:8]}",
                        product_id=product_id,
                        change_type=ChangeType.CONFIRMED,
                        summary=f"Confirmed steady state for {item.get('title', item_id)}",
                        previous_state=prev_val,
                        new_state=curr_val,
                        source_refs=[item.get("source_ref", item_id)],
                        significance_score=0.2,
                    )
                    self.repo.save_development(dev)
                    developments.append(dev)

        logger.info(f"Detected {len(developments)} developments for product '{product_id}'")
        return developments


class ContradictionAnalyzer:
    """Preserves and highlights disagreements and conflicting evidence."""

    def __init__(self, repo: SynthesisRepository):
        self.repo = repo

    def analyze_contradictions(
        self,
        product_id: str,
        evidence_items: List[Dict[str, Any]],
    ) -> List[ContradictionRecord]:
        """Detects conflicting claims between sources and documents reasons for divergence."""
        contradictions: List[ContradictionRecord] = []
        
        # Cross-compare pairs of claims
        for i in range(len(evidence_items)):
            for j in range(i + 1, len(evidence_items)):
                item_a = evidence_items[i]
                item_b = evidence_items[j]

                # Check if claims target same topic with contradictory polarity or values
                topic_a = item_a.get("topic", item_a.get("entity", "")).lower()
                topic_b = item_b.get("topic", item_b.get("entity", "")).lower()
                polarity_a = item_a.get("polarity", item_a.get("outcome", ""))
                polarity_b = item_b.get("polarity", item_b.get("outcome", ""))

                if topic_a and topic_a == topic_b and polarity_a and polarity_b and polarity_a != polarity_b:
                    contra = ContradictionRecord(
                        contradiction_id=f"contra-{uuid.uuid4().hex[:8]}",
                        product_id=product_id,
                        claim_a=f"{item_a.get('claim', topic_a)}: {polarity_a}",
                        claim_b=f"{item_b.get('claim', topic_b)}: {polarity_b}",
                        source_a_ref=item_a.get("source_ref", f"src_{i}"),
                        source_b_ref=item_b.get("source_ref", f"src_{j}"),
                        divergence_reason=f"Conflicting assessments on '{topic_a}' across sources",
                        status=ContradictionStatus.UNRESOLVED,
                        resolution_evidence_needed=f"Independent benchmark or telemetry across common time window for {topic_a}",
                    )
                    self.repo.save_contradiction(contra)
                    contradictions.append(contra)

        logger.info(f"Analyzed {len(contradictions)} material contradictions for product '{product_id}'")
        return contradictions


class SignificanceAssessmentService:
    """Calculates explainable, multi-dimensional significance scores."""

    def assess(
        self,
        event_or_change_id: str,
        urgency: float,  # 0.0 to 1.0
        potential_impact: float,  # 0.0 to 1.0
        evidence_reliability: float,  # 0.0 to 1.0
        affected_blast_radius: int = 1,
    ) -> SignificanceAssessment:
        """
        Computes weighted significance score without arbitrary numerical precision:
        Formula: 0.35 * Impact + 0.35 * Urgency + 0.20 * Reliability + 0.10 * log-scaled Blast Radius
        """
        # Clamp inputs
        u = max(0.0, min(1.0, urgency))
        imp = max(0.0, min(1.0, potential_impact))
        rel = max(0.0, min(1.0, evidence_reliability))
        blast_norm = min(1.0, affected_blast_radius / 10.0)

        overall = round(0.35 * imp + 0.35 * u + 0.20 * rel + 0.10 * blast_norm, 4)
        is_provisional = rel < 0.5

        reasoning = (
            f"Impact: {imp:.2f} (weight 0.35), Urgency: {u:.2f} (weight 0.35), "
            f"Reliability: {rel:.2f} (weight 0.20), Blast Radius entities: {affected_blast_radius} (weight 0.10). "
            f"Overall: {overall:.2f} ({'PROVISIONAL due to low reliability' if is_provisional else 'CONFIRMED'})."
        )

        return SignificanceAssessment(
            assessment_id=f"sig-{uuid.uuid4().hex[:8]}",
            event_or_change_id=event_or_change_id,
            urgency=u,
            potential_impact=imp,
            evidence_reliability=rel,
            affected_blast_radius=affected_blast_radius,
            overall_significance=overall,
            reasoning=reasoning,
            is_provisional=is_provisional,
        )
