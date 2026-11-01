"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Capacity Planning Subsystem: Plan Synthesis, Gap Identification & Strategy Ranking.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from capacity_planning.cost_model import InfrastructureCostModel
from capacity_planning.forecaster import CapacityForecasterEngine
from capacity_planning.models import (
    CapacityPlanRecord,
    ForecastHorizon,
    ScalingGovernanceMode,
    ScalingProposalRecord,
    ScalingProposalStatus,
    ScalingStrategyType,
)
from capacity_planning.optimizer import ElasticCapacityOptimizer
from capacity_planning.persistence import CapacityRepository
from capacity_planning.saturation import SaturationDetector

logger = logging.getLogger("Omnia.Capacity.Planner")


class CapacityPlanner:
    """
    Synthesizes current state, forecasts, saturation risks, and optimization options
    into versioned, actionable Capacity Plans.
    """

    def __init__(
        self,
        repository: Optional[CapacityRepository] = None,
        forecaster: Optional[CapacityForecasterEngine] = None,
        saturation_detector: Optional[SaturationDetector] = None,
        optimizer: Optional[ElasticCapacityOptimizer] = None,
        cost_model: Optional[InfrastructureCostModel] = None,
    ):
        self.repo = repository or CapacityRepository()
        self.forecaster = forecaster or CapacityForecasterEngine(self.repo)
        self.detector = saturation_detector or SaturationDetector(self.repo)
        self.optimizer = optimizer or ElasticCapacityOptimizer(self.repo)
        self.cost_model = cost_model or InfrastructureCostModel(self.repo)

    def generate_capacity_plan(
        self,
        title: str,
        horizon: ForecastHorizon = ForecastHorizon.TWENTY_FOUR_HOURS,
        governance_mode: ScalingGovernanceMode = ScalingGovernanceMode.APPROVAL_REQUIRED,
    ) -> CapacityPlanRecord:
        """
        Creates an end-to-end actionable capacity plan with identified gaps and recommended strategies.
        """
        risks = self.detector.detect_saturation_risks()
        resources = self.repo.list_resources(active_only=True)

        gaps = []
        recommended_strategies = []
        total_cost_delta = 0.0

        for r in resources:
            fc = self.forecaster.generate_forecast(r.resource_id, horizon=horizon)
            if fc.projected_utilization_pct >= 85.0:
                gap_desc = f"{r.resource_id} projected at {fc.projected_utilization_pct:.1f}% utilization in {horizon.value}"
                gaps.append(gap_desc)

                needed_headroom = max(r.total_capacity * 0.25, fc.forecasted_demand - (r.total_capacity * 0.75))
                opts = self.optimizer.evaluate_scaling_options(r.resource_id, needed_headroom)
                if opts:
                    best = opts[0]
                    recommended_strategies.append({
                        "resource_id": r.resource_id,
                        "strategy": best.strategy_type.value,
                        "capacity_change": best.proposed_capacity_change,
                        "cost_delta_per_hr": best.estimated_cost_delta_per_hr,
                        "risk_score": best.risk_score,
                    })
                    total_cost_delta += best.estimated_cost_delta_per_hr

        posture = "HEALTHY"
        if len(risks) > 0 or len(gaps) > 0:
            posture = "HEADROOM_CONSTRAINED"
        if any(r.severity.value == "CRITICAL" for r in risks):
            posture = "IMPENDING_SATURATION"

        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        plan = CapacityPlanRecord(
            plan_id=plan_id,
            title=title,
            horizon=horizon,
            current_health_posture=posture,
            identified_gaps=gaps,
            recommended_strategies=recommended_strategies,
            estimated_total_cost_delta=round(total_cost_delta, 4),
            required_governance_mode=governance_mode,
            status="PROPOSED",
        )
        self.repo.save_plan(plan)
        logger.info(f"Created Capacity Plan '{plan_id}' ({title}): Posture={posture}, Gaps={len(gaps)}")
        return plan

    def create_scaling_proposal(
        self,
        plan_id: str,
        resource_id: str,
        strategy_type: ScalingStrategyType,
        to_capacity: float,
    ) -> ScalingProposalRecord:
        res = self.repo.get_resource(resource_id)
        if not res:
            raise KeyError(f"Resource '{resource_id}' does not exist.")

        delta = to_capacity - res.total_capacity
        cost_delta = self.cost_model.calculate_scaling_cost_delta(res.resource_type, delta)

        prop_id = f"prop-{uuid.uuid4().hex[:8]}"
        proposal = ScalingProposalRecord(
            proposal_id=prop_id,
            plan_id=plan_id,
            resource_id=resource_id,
            strategy_type=strategy_type,
            from_capacity=res.total_capacity,
            to_capacity=to_capacity,
            cost_impact_per_hr=cost_delta,
            status=ScalingProposalStatus.PROPOSED,
        )
        self.repo.save_proposal(proposal)
        logger.info(f"Generated scaling proposal '{prop_id}' for '{resource_id}': {res.total_capacity} -> {to_capacity}")
        return proposal
