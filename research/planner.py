"""
OMNIA Module 35: Research Planning & Knowledge Gap Analysis
Translates ambiguous research questions into bounded investigative plans,
identifies knowledge gaps, and organizes required evidence without hallucinating facts.
"""

import uuid
import logging
from typing import Dict, Any, List, Optional
from research.models import (
    ResearchRequest,
    ResearchState,
    KnowledgeGapRecord,
)
from research.persistence import ResearchRepository

logger = logging.getLogger("Omnia.Research.Planner")


class ResearchPlanner:
    """Orchestrates structured research objectives and analyzes knowledge gaps."""

    def __init__(self, repo: ResearchRepository):
        self.repo = repo

    def initialize_investigation(
        self,
        question: str,
        domain: str = "SYSTEMS_PERFORMANCE",
        scope: str = "INTERNAL_SERVICES",
        risk_level: str = "LOW",
        requires_approval: bool = False,
    ) -> ResearchRequest:
        """Parses and normalizes a research question into a structured request."""
        clean_q = question.strip()
        if not clean_q or len(clean_q) < 5:
            raise ValueError("Research question must be a meaningful non-empty inquiry")

        research_id = f"res-{uuid.uuid4().hex[:8]}"
        req = ResearchRequest(
            research_id=research_id,
            original_question=clean_q,
            normalized_objective=f"Investigate: {clean_q}",
            domain=domain,
            scope=scope,
            state=ResearchState.INITIALIZED,
            risk_level=risk_level,
            requires_approval=requires_approval,
        )
        self.repo.save_request(req)
        logger.info(f"Initialized research investigation '{research_id}': {clean_q}")
        return req

    def identify_knowledge_gaps(
        self,
        research_id: str,
        known_evidence: List[str],
        required_signals: List[str],
    ) -> List[KnowledgeGapRecord]:
        """
        Compares known evidence against required signals to identify missing observations.
        Never fills missing empirical gaps with generated assumptions.
        """
        req = self.repo.get_request(research_id)
        if not req:
            raise ValueError(f"Research investigation '{research_id}' not found")

        req.transition_to(ResearchState.GAP_ANALYSIS)
        self.repo.save_request(req)

        gaps: List[KnowledgeGapRecord] = []
        known_lower = " ".join([k.lower() for k in known_evidence])

        for sig in required_signals:
            if sig.lower() not in known_lower:
                gap = KnowledgeGapRecord(
                    gap_id=f"gap-{uuid.uuid4().hex[:8]}",
                    research_id=research_id,
                    description=f"Missing empirical telemetry/evidence for '{sig}'",
                    why_it_matters=f"Required to test causal relationship regarding {sig}",
                    evidence_required=sig,
                    possible_acquisition_method="CONTROLLED_BENCHMARK_OR_TELEMETRY_PULL",
                    priority="HIGH",
                    resolution_status="OPEN",
                )
                self.repo.save_knowledge_gap(gap)
                gaps.append(gap)

        logger.info(f"Identified {len(gaps)} knowledge gaps for research '{research_id}'")
        return gaps
