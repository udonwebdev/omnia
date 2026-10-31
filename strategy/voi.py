"""
OMNIA Module 37: Value-of-Information (VOI) Analyzer
Evaluates information gaps, uncertainty reduction, and recommends whether to decide now,
run another simulation, or conduct targeted research.
"""

import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    ValueInformationAssessment,
    InformationAction,
    SensitivityResult,
)

logger = logging.getLogger("Omnia.Strategy.VOI")


class ValueInformationAnalyzer:
    """Analyzes whether gathering further evidence justifies the cost and decision delay."""

    def evaluate_voi(
        self,
        case_id: str,
        sensitivity: SensitivityResult,
        known_information_gaps: List[str],
        has_active_contradictions: bool = False,
    ) -> ValueInformationAssessment:
        """
        Determines the optimal information action:
        - If recommendation is stable and no major gaps -> DECIDE_NOW
        - If active contradictions exist -> GATHER_SPECIFIC_EVIDENCE
        - If recommendation is fragile -> RUN_SIMULATION or CONDUCT_RESEARCH
        """
        if has_active_contradictions:
            action = InformationAction.GATHER_SPECIFIC_EVIDENCE
            exp_reduction = 45.0
            explanation = "Active contradictory evidence detected across sources. Resolving the conflict is required to validate option ranking."
        elif sensitivity.stability_score < 0.50:
            if "simulation" in " ".join(known_information_gaps).lower():
                action = InformationAction.RUN_SIMULATION
                exp_reduction = 35.0
                explanation = "Fragile lead between top alternatives. Digital-twin simulation (Module 34) recommended to stress-test failure boundaries."
            else:
                action = InformationAction.CONDUCT_RESEARCH
                exp_reduction = 30.0
                explanation = "Decision threshold is narrow. Targeted empirical benchmark or research inquiry (Module 35) recommended."
        elif known_information_gaps and len(known_information_gaps) >= 3:
            action = InformationAction.EXPERT_REVIEW
            exp_reduction = 20.0
            explanation = "Multiple unverified assumption gaps exist. Human expert domain review recommended."
        else:
            action = InformationAction.DECIDE_NOW
            exp_reduction = 5.0
            explanation = f"Evidence base is sufficient. Stability score {sensitivity.stability_score:.2f} confirms robust ranking without costly delay."

        cost_delay = "LOW" if action == InformationAction.DECIDE_NOW else "ACCEPTABLE_FOR_UNCERTAINTY_REDUCTION"

        return ValueInformationAssessment(
            case_id=case_id,
            recommended_action=action,
            information_gaps=known_information_gaps,
            expected_uncertainty_reduction_pct=exp_reduction,
            cost_of_delay_assessment=cost_delay,
            explanation=explanation,
        )
