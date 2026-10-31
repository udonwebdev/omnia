"""
OMNIA Module 37: Strategic Recommendation Generator
Generates explainable, reproducible recommendations with explicit abstention capabilities.
Never forces a winner when evidence is insufficient or contradictory.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    StrategicOptionRecord,
    OptionAssessment,
    RiskTradeoffAssessment,
    SensitivityResult,
    StrategicRecommendation,
    RecommendationOutcome,
    ValueInformationAssessment,
    InformationAction,
)
from strategy.persistence import StrategyRepository

logger = logging.getLogger("Omnia.Strategy.Recommendation")


class StrategicRecommendationGenerator:
    """Synthesizes MCDA scores, risks, sensitivity, and VOI into a traceable recommendation."""

    def __init__(self, repo: StrategyRepository):
        self.repo = repo

    def generate_recommendation(
        self,
        case_id: str,
        options: List[StrategicOptionRecord],
        assessments: List[OptionAssessment],
        risk_assessments: Dict[str, RiskTradeoffAssessment],
        sensitivity: SensitivityResult,
        voi: ValueInformationAssessment,
        review_horizon_days: int = 90,
    ) -> StrategicRecommendation:
        """
        Formulates an explainable recommendation or abstains with INSUFFICIENT_EVIDENCE / DISPUTED_EVIDENCE.
        """
        # 1. Filter out options violating mandatory constraints or Pareto dominated
        viable_ass = [a for a in assessments if not a.violates_mandatory_constraint and not a.is_pareto_dominated]

        # 2. Check for abstention conditions
        if not viable_ass:
            rec = StrategicRecommendation(
                recommendation_id=f"rec-{uuid.uuid4().hex[:8]}",
                case_id=case_id,
                outcome=RecommendationOutcome.INSUFFICIENT_EVIDENCE,
                recommended_option_id=None,
                primary_justification="Abstained: All candidate options violate mandatory operational constraints.",
                key_tradeoffs=["No option satisfies mandatory thresholds"],
                major_risks=["Operational paralysis unless constraints are renegotiated"],
                critical_assumptions=["Mandatory constraint thresholds are strictly required"],
                conditions_for_invalidation=["Relaxation of mandatory constraint limits"],
                confidence_level="LOW",
                suggested_review_date_ts=time.time() + (14 * 86400),
            )
            self.repo.save_recommendation(rec)
            return rec

        if voi.recommended_action == InformationAction.GATHER_SPECIFIC_EVIDENCE:
            rec = StrategicRecommendation(
                recommendation_id=f"rec-{uuid.uuid4().hex[:8]}",
                case_id=case_id,
                outcome=RecommendationOutcome.DISPUTED_EVIDENCE,
                recommended_option_id=None,
                primary_justification=f"Abstained: {voi.explanation}",
                key_tradeoffs=["Premature decision risk vs delay cost to gather resolving evidence"],
                major_risks=["Selecting wrong architectural path due to unresolved contradictory telemetry"],
                critical_assumptions=["Disputed evidence can be resolved by targeted inquiry"],
                conditions_for_invalidation=["Resolution of evidence conflict"],
                confidence_level="LOW",
                suggested_review_date_ts=time.time() + (7 * 86400),
            )
            self.repo.save_recommendation(rec)
            return rec

        # 3. Sort viable options by normalized score
        sorted_viable = sorted(viable_ass, key=lambda x: x.normalized_score, reverse=True)
        top_ass = sorted_viable[0]

        # Check for tied top options
        if len(sorted_viable) > 1 and abs(top_ass.normalized_score - sorted_viable[1].normalized_score) < 0.5:
            runner_up_ass = sorted_viable[1]
            rec = StrategicRecommendation(
                recommendation_id=f"rec-{uuid.uuid4().hex[:8]}",
                case_id=case_id,
                outcome=RecommendationOutcome.TIED_OPTIONS,
                recommended_option_id=None,
                primary_justification=(
                    f"Abstained: Candidate options '{top_ass.option_id}' and '{runner_up_ass.option_id}' "
                    f"are statistically tied ({top_ass.normalized_score:.1f} vs {runner_up_ass.normalized_score:.1f})."
                ),
                key_tradeoffs=["Cost vs speed trade-offs balance out evenly between leading alternatives"],
                major_risks=["Arbitrary tie-breaking without stakeholder policy guidance"],
                critical_assumptions=["Both alternatives have comparable operational viability"],
                conditions_for_invalidation=["Stakeholder criteria reweighting"],
                confidence_level="MEDIUM",
                suggested_review_date_ts=time.time() + (7 * 86400),
            )
            self.repo.save_recommendation(rec)
            return rec

        # 4. Clear winner found
        top_opt = next((o for o in options if o.option_id == top_ass.option_id), None)
        top_risk = risk_assessments.get(top_ass.option_id)

        confidence_level = "HIGH" if sensitivity.stability_score >= 0.8 else ("MEDIUM" if sensitivity.stability_score >= 0.6 else "LOW")

        key_tradeoffs = [
            f"Expected benefit: {', '.join(top_opt.benefits[:2]) if top_opt else 'Strong overall balance'}",
            f"Estimated capital/operational cost: ${top_opt.estimated_cost:,.2f}" if top_opt else "Cost evaluated",
            f"Implementation complexity: {top_opt.implementation_complexity if top_opt else 'MEDIUM'}",
            f"Reversibility: {top_opt.reversibility_score*100:.0f}% reversible" if top_opt else "Reversible",
        ]

        major_risks = [
            f"Failure probability: {top_risk.probability_of_failure*100:.1f}%, Severity: {top_risk.severity_of_failure*100:.1f}%" if top_risk else "Standard operational risk",
            f"Mitigation: {top_risk.mitigation_strategy}" if top_risk and top_risk.mitigation_strategy else "Operational safeguards required",
        ]

        conditions_invalidation = [
            f"Top criterion weight shifts exceed {sensitivity.threshold_break_evens.get(list(sensitivity.threshold_break_evens.keys())[0], 25):.1f}%",
            "Key operational cost variance exceeds 30%",
            "Critical assumptions invalidated during execution",
        ]

        justification = (
            f"Option '{top_opt.title if top_opt else top_ass.option_id}' ranked highest with a normalized score "
            f"of {top_ass.normalized_score:.1f}/100.0. {sensitivity.sensitivity_narrative}"
        )

        rec = StrategicRecommendation(
            recommendation_id=f"rec-{uuid.uuid4().hex[:8]}",
            case_id=case_id,
            outcome=RecommendationOutcome.RECOMMENDED,
            recommended_option_id=top_ass.option_id,
            primary_justification=justification,
            key_tradeoffs=key_tradeoffs,
            major_risks=major_risks,
            critical_assumptions=top_opt.critical_assumptions if top_opt else [],
            conditions_for_invalidation=conditions_invalidation,
            confidence_level=confidence_level,
            suggested_review_date_ts=time.time() + (review_horizon_days * 86400),
        )
        self.repo.save_recommendation(rec)
        logger.info(f"Generated strategic recommendation for case '{case_id}': {rec.outcome.value} -> {rec.recommended_option_id}")
        return rec
