"""
OMNIA Module 35: Hypothesis Engine & Lifecycle Registry
Manages testable, falsifiable competing hypotheses and tracks evidence links.
Enforces that failure to disprove a hypothesis is not treated as proof of truth.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional
from research.models import (
    HypothesisRecord,
    HypothesisType,
    HypothesisState,
)
from research.persistence import ResearchRepository

logger = logging.getLogger("Omnia.Research.Hypotheses")


class HypothesisEngine:
    """Manages creation, competing comparisons, and lifecycle progression of hypotheses."""

    def __init__(self, repo: ResearchRepository):
        self.repo = repo

    def register_hypothesis(
        self,
        research_id: str,
        statement: str,
        hypothesis_type: HypothesisType = HypothesisType.ALTERNATIVE,
        scope: str = "GLOBAL",
        assumptions: Optional[List[str]] = None,
        expected_observations: Optional[List[str]] = None,
        falsification_conditions: Optional[List[str]] = None,
    ) -> HypothesisRecord:
        """Creates and registers a testable, falsifiable hypothesis."""
        hypo_id = f"hypo-{uuid.uuid4().hex[:8]}"
        hypo = HypothesisRecord(
            hypothesis_id=hypo_id,
            research_id=research_id,
            statement=statement,
            hypothesis_type=hypothesis_type,
            scope=scope,
            assumptions=assumptions or [],
            supporting_evidence=[],
            contradictory_evidence=[],
            expected_observations=expected_observations or [],
            falsification_conditions=falsification_conditions or [],
            state=HypothesisState.PROPOSED,
            confidence_score=0.5,
        )
        self.repo.save_hypothesis(hypo)
        logger.info(f"Registered hypothesis '{hypo_id}' ({hypothesis_type.value}): {statement}")
        return hypo

    def link_evidence(
        self,
        hypothesis_id: str,
        evidence_text: str,
        is_supporting: bool = True,
    ) -> HypothesisRecord:
        """Associates empirical evidence items to a hypothesis."""
        hypo = self.repo.get_hypothesis(hypothesis_id)
        if not hypo:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found")

        if is_supporting:
            hypo.supporting_evidence.append(evidence_text)
        else:
            hypo.contradictory_evidence.append(evidence_text)

        hypo.updated_at = time.time()
        self.repo.save_hypothesis(hypo)
        return hypo

    def transition_state(
        self,
        hypothesis_id: str,
        new_state: HypothesisState,
        confidence: Optional[float] = None,
    ) -> HypothesisRecord:
        """Transitions hypothesis state based on formal testing outcomes."""
        hypo = self.repo.get_hypothesis(hypothesis_id)
        if not hypo:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found")

        hypo.state = new_state
        if confidence is not None:
            hypo.confidence_score = max(0.0, min(1.0, confidence))
        hypo.updated_at = time.time()
        self.repo.save_hypothesis(hypo)
        logger.info(f"Transitioned hypothesis '{hypothesis_id}' to {new_state.value} (Confidence: {hypo.confidence_score})")
        return hypo
