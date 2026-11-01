"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Capacity Optimizer & Scaling Advisor: Elastic Strategy Comparative Analysis.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from capacity_planning.cost_model import InfrastructureCostModel
from capacity_planning.models import (
    ScalingStrategyEvaluation,
    ScalingStrategyType,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Optimizer")


class ElasticCapacityOptimizer:
    """
    Evaluates alternative scaling strategies (Horizontal Scale-out, Vertical Scale-up,
    Worker Pool Expansion, Workload Throttling, etc.) against headroom, performance gain,
    complexity, risk, and incremental cost.
    """

    def __init__(
        self,
        repository: Optional[CapacityRepository] = None,
        cost_model: Optional[InfrastructureCostModel] = None,
    ):
        self.repo = repository or CapacityRepository()
        self.cost_model = cost_model or InfrastructureCostModel(self.repo)

    def evaluate_scaling_options(
        self,
        resource_id: str,
        target_headroom_increase: float,
    ) -> List[ScalingStrategyEvaluation]:
        res = self.repo.get_resource(resource_id)
        if not res:
            raise KeyError(f"Resource '{resource_id}' does not exist.")

        evaluations: List[ScalingStrategyEvaluation] = []

        # 1. Horizontal Scale-Out
        h_cost = self.cost_model.calculate_scaling_cost_delta(res.resource_type, target_headroom_increase)
        evaluations.append(
            ScalingStrategyEvaluation(
                evaluation_id=f"eval-hscale-{uuid.uuid4().hex[:6]}",
                resource_id=resource_id,
                strategy_type=ScalingStrategyType.HORIZONTAL_SCALE_OUT,
                proposed_capacity_change=target_headroom_increase,
                expected_headroom_increase=target_headroom_increase,
                expected_performance_gain_pct=round(min(100.0, (target_headroom_increase / res.total_capacity) * 80.0), 1),
                estimated_cost_delta_per_hr=h_cost,
                operational_complexity="LOW",
                reversibility=True,
                policy_compatible=True,
                risk_score=0.1,
            )
        )

        # 2. Vertical Scale-Up (Larger instance sizing)
        v_cost = round(h_cost * 1.15, 4)
        evaluations.append(
            ScalingStrategyEvaluation(
                evaluation_id=f"eval-vscale-{uuid.uuid4().hex[:6]}",
                resource_id=resource_id,
                strategy_type=ScalingStrategyType.VERTICAL_SCALE_UP,
                proposed_capacity_change=target_headroom_increase,
                expected_headroom_increase=target_headroom_increase,
                expected_performance_gain_pct=round(min(100.0, (target_headroom_increase / res.total_capacity) * 90.0), 1),
                estimated_cost_delta_per_hr=v_cost,
                operational_complexity="MEDIUM",
                reversibility=True,
                policy_compatible=True,
                risk_score=0.25,
            )
        )

        # 3. Workload Throttling / Batch Shedding (zero monetary cost)
        evaluations.append(
            ScalingStrategyEvaluation(
                evaluation_id=f"eval-throttle-{uuid.uuid4().hex[:6]}",
                resource_id=resource_id,
                strategy_type=ScalingStrategyType.WORKLOAD_THROTTLING,
                proposed_capacity_change=0.0,
                expected_headroom_increase=round(target_headroom_increase * 0.5, 2),
                expected_performance_gain_pct=15.0,
                estimated_cost_delta_per_hr=0.0,
                operational_complexity="LOW",
                reversibility=True,
                policy_compatible=True,
                risk_score=0.35,  # Moderate risk due to shedding non-critical tasks
            )
        )

        # Rank strategies by lowest cost per performance unit
        evaluations.sort(key=lambda s: (s.risk_score, s.estimated_cost_delta_per_hr))
        return evaluations
