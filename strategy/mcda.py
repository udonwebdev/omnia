"""
OMNIA Module 37: Multi-Criteria Decision Analysis (MCDA) Engine
Implements weighted scoring, constraint filtering, cost-benefit trade-offs,
and Pareto dominance analysis without inventing artificial certainty.
"""

import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple
from strategy.models import (
    StrategicOptionRecord,
    DecisionCriterion,
    CriterionDirection,
    OptionAssessment,
)
from strategy.persistence import StrategyRepository

logger = logging.getLogger("Omnia.Strategy.MCDA")


class MultiCriteriaDecisionEngine:
    """Evaluates candidate options against defined criteria and weights."""

    def __init__(self, repo: StrategyRepository):
        self.repo = repo

    def evaluate_options(
        self,
        case_id: str,
        options: List[StrategicOptionRecord],
        criteria: List[DecisionCriterion],
        raw_metrics_matrix: Dict[str, Dict[str, float]],  # option_id -> {criterion_id: raw_value}
    ) -> List[OptionAssessment]:
        """
        Calculates normalized weighted scores, verifies mandatory thresholds,
        and identifies Pareto dominated options.
        """
        if not options or not criteria:
            return []

        # 1. Normalize criterion weights so they sum to 1.0
        total_weight = sum(c.weight for c in criteria)
        norm_weights = {c.criterion_id: (c.weight / total_weight if total_weight > 0 else 1.0 / len(criteria)) for c in criteria}

        # 2. Find min/max for each criterion to normalize [0, 1]
        crit_ranges: Dict[str, Tuple[float, float]] = {}
        for c in criteria:
            vals = [raw_metrics_matrix.get(opt.option_id, {}).get(c.criterion_id, 0.0) for opt in options]
            min_v = min(vals) if vals else 0.0
            max_v = max(vals) if vals else 1.0
            if min_v == max_v:
                max_v = min_v + 1.0  # Avoid division by zero
            crit_ranges[c.criterion_id] = (min_v, max_v)

        assessments: List[OptionAssessment] = []

        # 3. Score options
        for opt in options:
            opt_metrics = raw_metrics_matrix.get(opt.option_id, {})
            score_acc = 0.0
            violations = []
            violates_mandatory = False

            for c in criteria:
                raw_val = opt_metrics.get(c.criterion_id, 0.0)
                min_v, max_v = crit_ranges[c.criterion_id]

                # Check mandatory threshold
                if c.is_mandatory and c.minimum_threshold is not None:
                    if c.direction == CriterionDirection.MAXIMIZE and raw_val < c.minimum_threshold:
                        violates_mandatory = True
                        violations.append(f"Criterion '{c.name}' value {raw_val} below minimum threshold {c.minimum_threshold}")
                    elif c.direction == CriterionDirection.MINIMIZE and raw_val > c.minimum_threshold:
                        violates_mandatory = True
                        violations.append(f"Criterion '{c.name}' value {raw_val} exceeds maximum allowed threshold {c.minimum_threshold}")

                # Linear normalization to [0, 1]
                if c.direction == CriterionDirection.MAXIMIZE:
                    norm_val = (raw_val - min_v) / (max_v - min_v)
                else:  # MINIMIZE (lower raw value is better)
                    norm_val = (max_v - raw_val) / (max_v - min_v)

                score_acc += norm_val * norm_weights[c.criterion_id]

            normalized_score = round(score_acc * 100.0, 2)

            ass = OptionAssessment(
                assessment_id=f"ass-{uuid.uuid4().hex[:8]}",
                case_id=case_id,
                option_id=opt.option_id,
                criterion_scores=opt_metrics,
                normalized_score=normalized_score,
                is_pareto_dominated=False,  # Computed in next step
                violates_mandatory_constraint=violates_mandatory,
                constraint_violations=violations,
            )
            assessments.append(ass)

        # 4. Compute Pareto Dominance
        # Option A dominates Option B if A >= B in all criteria and A > B in at least one
        for i, ass_a in enumerate(assessments):
            for j, ass_b in enumerate(assessments):
                if i != j and not ass_b.is_pareto_dominated:
                    a_metrics = raw_metrics_matrix.get(ass_a.option_id, {})
                    b_metrics = raw_metrics_matrix.get(ass_b.option_id, {})

                    better_or_equal = True
                    strictly_better = False

                    for c in criteria:
                        val_a = a_metrics.get(c.criterion_id, 0.0)
                        val_b = b_metrics.get(c.criterion_id, 0.0)

                        if c.direction == CriterionDirection.MAXIMIZE:
                            if val_a < val_b:
                                better_or_equal = False
                                break
                            if val_a > val_b:
                                strictly_better = True
                        else:  # MINIMIZE
                            if val_a > val_b:
                                better_or_equal = False
                                break
                            if val_a < val_b:
                                strictly_better = True

                    if better_or_equal and strictly_better:
                        ass_b.is_pareto_dominated = True

        for ass in assessments:
            self.repo.save_assessment(ass)

        logger.info(f"Evaluated {len(assessments)} options for case '{case_id}' across {len(criteria)} criteria")
        return assessments
