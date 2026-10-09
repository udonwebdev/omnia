"""
Evaluator for Module 29 Evidence & Decision Engine.
Implements claim evaluation, stance attribution, conflict detection, and policy-governed conclusions.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Tuple

from decision.models import (
    Claim,
    ClaimStatus,
    EvidenceLink,
    EvidenceStance,
    DecisionConflict,
    ConflictSeverity,
    DecisionRecord,
    DecisionState,
    DecisionPolicy
)
from retrieval.models import EvidenceItem

logger = logging.getLogger("Omnia.Decision.Evaluator")


class DecisionEvaluator:
    """Evaluates claims against retrieved evidence items, detecting contradictions and calculating calibrated confidence."""

    def evaluate_claims(
        self,
        decision_id: str,
        claims: List[Claim],
        evidence_items: List[EvidenceItem],
        policy: DecisionPolicy
    ) -> Tuple[List[Claim], List[EvidenceLink], List[DecisionConflict]]:
        evaluated_claims: List[Claim] = []
        links: List[EvidenceLink] = []
        conflicts: List[DecisionConflict] = []

        for claim in claims:
            statement_lower = claim.statement.lower()
            statement_tokens = set([t for t in statement_lower.split() if len(t) > 2])

            sup_weight = 0.0
            contra_weight = 0.0
            sup_count = 0
            contra_count = 0

            for ev in evidence_items:
                ev_text = (ev.title + " " + ev.content_snippet).lower()
                overlap = sum(1 for t in statement_tokens if t in ev_text)
                relevance = overlap / max(1, len(statement_tokens))

                if relevance < 0.2:
                    continue

                # Stance heuristic: negation words indicate contradiction
                negation_cues = [" not ", " failed ", " invalid ", " error ", " false ", " never ", " degraded "]
                is_contradicting = any(cue in ev_text for cue in negation_cues)

                stance = EvidenceStance.CONTRADICTING if is_contradicting else EvidenceStance.SUPPORTING
                link_weight = round(ev.confidence_score * relevance, 4)

                links.append(EvidenceLink(
                    link_id=f"lnk_{uuid.uuid4().hex[:12]}",
                    decision_id=decision_id,
                    claim_id=claim.claim_id,
                    evidence_id=ev.evidence_id,
                    stance=stance,
                    weight=link_weight,
                    provenance_hash=ev.provenance_hash,
                    linked_at=time.time()
                ))

                if stance == EvidenceStance.SUPPORTING:
                    sup_weight += link_weight
                    sup_count += 1
                else:
                    contra_weight += link_weight
                    contra_count += 1

            total_weight = sup_weight + contra_weight
            if total_weight == 0.0:
                claim.status = ClaimStatus.INCONCLUSIVE
                claim.confidence_score = 0.0
                claim.rationale = "No relevant evidence discovered"
            else:
                # Contradiction ratio
                contra_ratio = contra_weight / total_weight
                # Calibrated confidence: net positive weight normalized
                net_confidence = max(0.0, (sup_weight - contra_weight) / total_weight)

                claim.supporting_evidence_count = sup_count
                claim.contradicting_evidence_count = contra_count
                claim.confidence_score = round(net_confidence, 4)

                if contra_count > 0 and sup_count > 0:
                    conflicts.append(DecisionConflict(
                        conflict_id=f"cnf_{uuid.uuid4().hex[:12]}",
                        decision_id=decision_id,
                        claim_id=claim.claim_id,
                        conflict_type="EVIDENCE_CONTRADICTION",
                        severity=ConflictSeverity.HIGH if contra_ratio > 0.4 else ConflictSeverity.MEDIUM,
                        resolution_state="DETECTED",
                        detected_at=time.time(),
                        metadata={"contra_ratio": round(contra_ratio, 4)}
                    ))

                if contra_ratio > policy.max_contradiction_ratio:
                    claim.status = ClaimStatus.CONTRADICTED
                    claim.rationale = f"Contradiction ratio {contra_ratio:.2f} exceeded policy threshold {policy.max_contradiction_ratio:.2f}"
                elif net_confidence >= policy.min_confidence_to_accept:
                    claim.status = ClaimStatus.SUPPORTED
                    claim.rationale = f"Confidence {net_confidence:.2f} satisfies policy threshold {policy.min_confidence_to_accept:.2f}"
                else:
                    claim.status = ClaimStatus.INCONCLUSIVE
                    claim.rationale = f"Confidence {net_confidence:.2f} insufficient to reach conclusion"

            evaluated_claims.append(claim)

        return evaluated_claims, links, conflicts

    def synthesize_decision(
        self,
        decision_id: str,
        subject_id: str,
        decision_type: str,
        claims: List[Claim],
        evidence_links: List[EvidenceLink],
        conflicts: List[DecisionConflict],
        policy: DecisionPolicy,
        actor_id: str = "system"
    ) -> DecisionRecord:
        now = time.time()
        if not claims:
            return DecisionRecord(
                decision_id=decision_id,
                subject_id=subject_id,
                decision_type=decision_type,
                state=DecisionState.ABSTAINED,
                confidence_score=0.0,
                uncertainty_score=1.0,
                summary="Abstained: No claims provided for evaluation.",
                evaluated_at=now,
                expires_at=now + policy.ttl_seconds,
                actor_id=actor_id
            )

        avg_confidence = sum(c.confidence_score for c in claims) / len(claims)
        any_contradicted = any(c.status == ClaimStatus.CONTRADICTED for c in claims)
        all_supported = all(c.status == ClaimStatus.SUPPORTED for c in claims)
        has_critical_conflicts = any(cf.severity in (ConflictSeverity.HIGH, ConflictSeverity.CRITICAL) for cf in conflicts)

        # Calculate uncertainty score based on conflict and lack of evidence
        total_links = len(evidence_links)
        uncertainty = 1.0 - avg_confidence if total_links > 0 else 1.0
        if has_critical_conflicts:
            uncertainty = min(1.0, uncertainty + 0.3)

        if has_critical_conflicts or any_contradicted:
            state = DecisionState.DISPUTED
            summary = f"Disputed conclusion for {subject_id}: Conflicting evidence detected."
        elif all_supported and avg_confidence >= policy.min_confidence_to_accept and uncertainty <= policy.max_uncertainty:
            state = DecisionState.ACCEPTED
            summary = f"Accepted conclusion for {subject_id}: High-confidence evidence verification."
        elif avg_confidence < 0.3 or uncertainty > policy.max_uncertainty:
            state = DecisionState.ABSTAINED
            summary = f"Abstained from conclusion on {subject_id}: High uncertainty ({uncertainty:.2f})."
        else:
            state = DecisionState.REJECTED
            summary = f"Rejected conclusion for {subject_id}: Insufficient supporting evidence."

        return DecisionRecord(
            decision_id=decision_id,
            subject_id=subject_id,
            decision_type=decision_type,
            state=state,
            confidence_score=round(avg_confidence, 4),
            uncertainty_score=round(uncertainty, 4),
            primary_claim_id=claims[0].claim_id,
            summary=summary,
            evaluated_at=now,
            expires_at=now + policy.ttl_seconds,
            actor_id=actor_id,
            claims=claims,
            evidence_links=evidence_links,
            conflicts=conflicts
        )
