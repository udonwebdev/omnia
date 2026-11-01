"""
forensics/hypothesis_engine.py
Hypothesis-driven investigation engine for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional

from forensics.models import ForensicHypothesis, HypothesisStatus
from forensics.persistence import ForensicsRepository

logger = logging.getLogger("omnia.forensics.hypothesis")


class HypothesisEngine:
    """
    Evaluates competing explanations for observed incident facts.
    Maintains explicit evidence links, calculates support and refutation scores,
    and updates hypothesis verdicts in accordance with forensic methodology.
    """

    def __init__(self, repo: ForensicsRepository):
        self.repo = repo

    def create_hypothesis(
        self,
        case_id: str,
        title: str,
        theory_description: str,
        competing_with_id: Optional[str] = None
    ) -> ForensicHypothesis:
        """Formulates a new investigative hypothesis."""
        hypo = ForensicHypothesis(
            hypothesis_id=f"hyp_{uuid.uuid4().hex[:12]}",
            case_id=case_id,
            title=title,
            theory_description=theory_description,
            competing_with_id=competing_with_id,
            status=HypothesisStatus.PROPOSED,
            support_score=0.0,
            refutation_score=0.0,
            supporting_evidence=[],
            contradictory_evidence=[],
            verdict_rationale=None,
            created_at=time.time(),
            updated_at=time.time()
        )
        return self.repo.record_hypothesis(hypo)

    def add_supporting_evidence(
        self,
        hypothesis_id: str,
        evidence_summary: str,
        weight: float = 1.0
    ) -> bool:
        """Links supporting evidence to a hypothesis, increasing its support score."""
        hypo = self.repo.get_hypothesis(hypothesis_id)
        if not hypo:
            return False
        hypo.supporting_evidence.append(evidence_summary)
        hypo.support_score += weight
        hypo.updated_at = time.time()
        return self._recalculate_and_save(hypo)

    def add_contradictory_evidence(
        self,
        hypothesis_id: str,
        evidence_summary: str,
        weight: float = 1.0
    ) -> bool:
        """Links contradictory evidence, increasing refutation score."""
        hypo = self.repo.get_hypothesis(hypothesis_id)
        if not hypo:
            return False
        hypo.contradictory_evidence.append(evidence_summary)
        hypo.refutation_score += weight
        hypo.updated_at = time.time()
        return self._recalculate_and_save(hypo)

    def _recalculate_and_save(self, hypo: ForensicHypothesis) -> bool:
        """Re-evaluates verdict status based on scores."""
        if hypo.refutation_score >= 2.0 and hypo.refutation_score > hypo.support_score:
            hypo.status = HypothesisStatus.REFUTED
            hypo.verdict_rationale = (
                f"Refuted by {len(hypo.contradictory_evidence)} contradictory findings "
                f"(refutation score {hypo.refutation_score:.1f} vs support {hypo.support_score:.1f})."
            )
        elif hypo.support_score >= 2.0 and hypo.support_score > (hypo.refutation_score * 2):
            hypo.status = HypothesisStatus.SUPPORTED
            hypo.verdict_rationale = (
                f"Supported by {len(hypo.supporting_evidence)} corroborating findings "
                f"(support score {hypo.support_score:.1f} vs refutation {hypo.refutation_score:.1f})."
            )
        elif len(hypo.supporting_evidence) > 0 or len(hypo.contradictory_evidence) > 0:
            hypo.status = HypothesisStatus.UNDER_INVESTIGATION
            hypo.verdict_rationale = "Active evaluation of mixed evidence."
        else:
            hypo.status = HypothesisStatus.PROPOSED

        return self.repo.update_hypothesis(hypo)

    def evaluate_competing_pair(self, hypo_a_id: str, hypo_b_id: str) -> Dict[str, Any]:
        """Compares two competing hypotheses to establish relative likelihood."""
        all_hypos = {h.hypothesis_id: h for h in self.repo.list_hypotheses("")}
        if hypo_a_id not in all_hypos or hypo_b_id not in all_hypos:
            return {"error": "One or both hypotheses not found."}

        ha = all_hypos[hypo_a_id]
        hb = all_hypos[hypo_b_id]

        net_a = ha.support_score - ha.refutation_score
        net_b = hb.support_score - hb.refutation_score

        favored = None
        if net_a > net_b and net_a > 0:
            favored = ha.hypothesis_id
        elif net_b > net_a and net_b > 0:
            favored = hb.hypothesis_id

        return {
            "hypothesis_a": {
                "id": ha.hypothesis_id,
                "title": ha.title,
                "status": ha.status.value,
                "net_score": net_a
            },
            "hypothesis_b": {
                "id": hb.hypothesis_id,
                "title": hb.title,
                "status": hb.status.value,
                "net_score": net_b
            },
            "favored_hypothesis_id": favored
        }
