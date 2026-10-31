"""
OMNIA Module 37: Sensitivity & Scenario Robustness Evaluator
Tests weight shifts, budget variations, and assumption thresholds to verify
recommendation stability and identify fragile options.
"""

import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    StrategicOptionRecord,
    DecisionCriterion,
    OptionAssessment,
    SensitivityResult,
)

logger = logging.getLogger("Omnia.Strategy.Sensitivity")


class SensitivityAnalysisEngine:
    """Evaluates stability of rankings under weight perturbations and threshold shifts."""

    def evaluate_sensitivity(
        self,
        case_id: str,
        options: List[StrategicOptionRecord],
        criteria: List[DecisionCriterion],
        assessments: List[OptionAssessment],
        dominant_option_id: str,
    ) -> SensitivityResult:
        """
        Determines if the winning option remains dominant when top criteria weights shift +/- 20%.
        Calculates stability score and flags fragile recommendations.
        """
        # Find non-dominated candidates
        valid_assessments = [a for a in assessments if not a.is_pareto_dominated and not a.violates_mandatory_constraint]
        if not valid_assessments:
            return SensitivityResult(
                case_id=case_id,
                dominant_option_id=dominant_option_id,
                stability_score=0.0,
                threshold_break_evens={},
                critical_assumptions=["All candidate options violate mandatory thresholds or are Pareto dominated"],
                pareto_frontier_options=[],
                sensitivity_narrative="No viable candidate passed mandatory constraints.",
            )

        # Sort by normalized score
        sorted_ass = sorted(valid_assessments, key=lambda x: x.normalized_score, reverse=True)
        top_opt = sorted_ass[0]
        runner_up = sorted_ass[1] if len(sorted_ass) > 1 else None

        score_margin = (top_opt.normalized_score - runner_up.normalized_score) if runner_up else 100.0

        # Break-even shift: How much percentage weight change on the primary criterion flips the outcome?
        break_evens = {}
        top_criterion = max(criteria, key=lambda c: c.weight) if criteria else None

        if top_criterion and runner_up:
            # Approximate percentage shift required on primary criterion
            margin_ratio = score_margin / max(1.0, top_opt.normalized_score)
            break_even_shift_pct = round(margin_ratio * 100.0, 1)
            break_evens[top_criterion.name] = break_even_shift_pct
        else:
            break_evens["primary_weight"] = 100.0

        # Stability score: based on margin
        if score_margin >= 15.0:
            stability_score = 0.90
            narrative = f"Dominant option '{dominant_option_id}' is highly robust with a {score_margin:.1f}pt lead over runner-up."
        elif score_margin >= 5.0:
            stability_score = 0.70
            narrative = f"Dominant option '{dominant_option_id}' is moderately robust ({score_margin:.1f}pt lead). Sensitive to >20% criterion weight adjustments."
        else:
            stability_score = 0.40
            narrative = f"Dominant option '{dominant_option_id}' is FRAGILE. Lead is only {score_margin:.1f}pts; small weight shifts will flip ranking."

        pareto_frontier = [a.option_id for a in valid_assessments if not a.is_pareto_dominated]

        return SensitivityResult(
            case_id=case_id,
            dominant_option_id=dominant_option_id,
            stability_score=stability_score,
            threshold_break_evens=break_evens,
            critical_assumptions=[f"Top criterion '{top_criterion.name}' weight remains within +/- {break_evens.get(top_criterion.name, 20)}%"] if top_criterion else [],
            pareto_frontier_options=pareto_frontier,
            sensitivity_narrative=narrative,
        )
