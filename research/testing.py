"""
OMNIA Module 35: Hypothesis Testing & Competing Explanation Analysis
Applies statistical and comparative evaluations against hypothesis predictions.
Never fabricates p-values or confidence intervals, and returns INCONCLUSIVE when evidence is insufficient.
"""

import uuid
import math
import logging
from typing import Dict, Any, List, Optional
from research.models import (
    HypothesisRecord,
    HypothesisState,
    HypothesisTestResult,
    ResearchConclusion,
    ConclusionState,
)
from research.persistence import ResearchRepository

logger = logging.getLogger("Omnia.Research.Testing")


class HypothesisTestingEngine:
    """Evaluates empirical measurements against competing hypotheses."""

    def __init__(self, repo: ResearchRepository):
        self.repo = repo

    def evaluate_hypothesis(
        self,
        hypothesis_id: str,
        baseline_values: List[float],
        treatment_values: List[float],
        expected_effect_direction: str = "DECREASE",  # "DECREASE" or "INCREASE"
    ) -> HypothesisTestResult:
        """
        Calculates descriptive differences, mean effect, and confidence interval.
        Returns SUPPORTED, NOT_SUPPORTED, or INCONCLUSIVE without inventing statistical certainty.
        """
        hypo = self.repo.get_hypothesis(hypothesis_id)
        if not hypo:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found")

        n_b = len(baseline_values)
        n_t = len(treatment_values)

        if n_b < 3 or n_t < 3:
            # Insufficient sample size -> must report INCONCLUSIVE
            test_res = HypothesisTestResult(
                test_id=f"test-{uuid.uuid4().hex[:8]}",
                hypothesis_id=hypothesis_id,
                method="DESCRIPTIVE_SAMPLE_COMPARISON",
                sample_size=n_b + n_t,
                test_statistic=None,
                p_value=None,
                effect_size=0.0,
                confidence_interval=None,
                evaluated_state=HypothesisState.INCONCLUSIVE,
                reasoning="Sample size is strictly insufficient (n < 3) to draw statistical conclusions.",
                limitations=["Insufficient sample size for inferential statistics"],
            )
            self.repo.save_hypothesis_test(test_res)
            return test_res

        mean_b = sum(baseline_values) / n_b
        mean_t = sum(treatment_values) / n_t
        effect_size = round(mean_t - mean_b, 4)

        # Standard deviation
        var_b = sum((x - mean_b) ** 2 for x in baseline_values) / (n_b - 1)
        var_t = sum((x - mean_t) ** 2 for x in treatment_values) / (n_t - 1)
        se = math.sqrt((var_b / n_b) + (var_t / n_t))

        # 95% Confidence Interval approx (z = 1.96)
        ci_lower = round(effect_size - 1.96 * se, 4)
        ci_upper = round(effect_size + 1.96 * se, 4)

        # Evaluation against direction
        supported = False
        if expected_effect_direction == "DECREASE":
            supported = effect_size < 0 and ci_upper < 0
        elif expected_effect_direction == "INCREASE":
            supported = effect_size > 0 and ci_lower > 0

        state = HypothesisState.SUPPORTED if supported else HypothesisState.NOT_SUPPORTED
        reasoning = (
            f"Mean baseline: {mean_b:.2f}, Mean treatment: {mean_t:.2f}. "
            f"Observed effect size: {effect_size:.2f} (95% CI: [{ci_lower}, {ci_upper}]). "
            f"Direction expectation '{expected_effect_direction}' was {'satisfied' if supported else 'not satisfied'}."
        )

        test_res = HypothesisTestResult(
            test_id=f"test-{uuid.uuid4().hex[:8]}",
            hypothesis_id=hypothesis_id,
            method="WELCH_T_INTERVAL_EVALUATION",
            sample_size=n_b + n_t,
            test_statistic=round(effect_size / se, 4) if se > 0 else 0.0,
            p_value=None,  # Do not fabricate exact p-values without external scipy
            effect_size=effect_size,
            confidence_interval=[ci_lower, ci_upper],
            evaluated_state=state,
            reasoning=reasoning,
            limitations=["Assumes approximate normality of sampled metrics"],
        )

        self.repo.save_hypothesis_test(test_res)

        # Update hypothesis state
        confidence = 0.85 if supported else 0.20
        hypo.state = state
        hypo.confidence_score = confidence
        hypo.supporting_evidence.append(reasoning)
        self.repo.save_hypothesis(hypo)

        logger.info(f"Evaluated hypothesis {hypothesis_id}: {state.value} ({reasoning})")
        return test_res

    def synthesize_conclusion(
        self,
        research_id: str,
        hypotheses: List[HypothesisRecord],
        direct_observations: List[str],
    ) -> ResearchConclusion:
        """
        Synthesizes evaluated evidence into a traceable ResearchConclusion.
        Distinguishes directly observed facts from interpretations and unresolved items.
        """
        supported = [h for h in hypotheses if h.state == HypothesisState.SUPPORTED]
        rejected = [h for h in hypotheses if h.state in (HypothesisState.NOT_SUPPORTED, HypothesisState.REJECTED)]

        if supported:
            state = ConclusionState.SUPPORTED_WITHIN_SCOPE
            summary = f"Research supported hypothesis: '{supported[0].statement}' within tested parameters."
        elif rejected:
            state = ConclusionState.CONTRADICTED
            summary = "All evaluated alternative hypotheses were not supported or contradicted by empirical observations."
        else:
            state = ConclusionState.INCONCLUSIVE
            summary = "Empirical data collected remains inconclusive regarding competing explanations."

        evidence_trail = [
            f"Hypothesis '{h.hypothesis_id}' evaluated as {h.state.value} (Confidence: {h.confidence_score})"
            for h in hypotheses
        ]

        conclusion = ResearchConclusion(
            conclusion_id=f"concl-{uuid.uuid4().hex[:8]}",
            research_id=research_id,
            state=state,
            summary=summary,
            direct_observations=direct_observations,
            supported_claims=[h.statement for h in supported],
            rejected_hypotheses=[h.statement for h in rejected],
            unresolved_uncertainties=["Generalization beyond tested runtime conditions requires multi-cluster verification"],
            scope_limitations=["Results constrained to isolated testbed environment"],
            evidence_trail=evidence_trail,
        )

        self.repo.save_conclusion(conclusion)
        logger.info(f"Synthesized research conclusion for '{research_id}': {state.value}")
        return conclusion
