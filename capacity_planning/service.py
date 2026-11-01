"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
High-level Orchestration Facade and Service API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from capacity_planning.collector import CapacityTelemetryCollector
from capacity_planning.cost_model import InfrastructureCostModel
from capacity_planning.demand import WorkloadDemandAnalyzer
from capacity_planning.forecaster import CapacityForecasterEngine
from capacity_planning.governance import AutonomousScalingGovernor
from capacity_planning.inventory import ResourceInventoryRegistry
from capacity_planning.models import (
    CapacityForecastRecord,
    CapacityPlanRecord,
    CapacityScenarioDefinition,
    CapacitySimulationResult,
    ForecastAccuracyEvaluation,
    ForecastHorizon,
    InfrastructureCostProjection,
    MetricUnit,
    ResourceDimension,
    ResourceInventoryItem,
    ResourceMeasurementRecord,
    SaturationRiskFinding,
    ScalingExecutionRecord,
    ScalingGovernanceMode,
    ScalingProposalRecord,
    ScalingStrategyEvaluation,
    ScalingStrategyType,
    WorkloadCategory,
    WorkloadDemandProfile,
)
from capacity_planning.monitor import ContinuousCapacityMonitor
from capacity_planning.optimizer import ElasticCapacityOptimizer
from capacity_planning.persistence import CapacityRepository
from capacity_planning.planner import CapacityPlanner
from capacity_planning.reporting import CapacityReporter
from capacity_planning.saturation import SaturationDetector

# Module 10 Event Fabric Integration
try:
    from events.fabric import EventFabric, event_fabric
    from events.models import Event, EventEnvelope
except ImportError:
    event_fabric = None
    EventFabric = None
    Event = None
    EventEnvelope = None

logger = logging.getLogger("Omnia.Capacity.Service")


class CapacityPlanningOrchestrator:
    """
    Unified high-level facade for Module 42:
    Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
    """

    def __init__(self, db_path: str = "omnia.db"):
        self.repo = CapacityRepository(db_path=db_path)
        self.inventory = ResourceInventoryRegistry(self.repo)
        self.collector = CapacityTelemetryCollector(self.repo)
        self.demand = WorkloadDemandAnalyzer(self.repo)
        self.forecaster = CapacityForecasterEngine(self.repo)
        self.saturation = SaturationDetector(self.repo)
        self.cost_model = InfrastructureCostModel(self.repo)
        self.optimizer = ElasticCapacityOptimizer(self.repo, self.cost_model)
        self.simulator = None  # Lazy-loaded on import to avoid circular dependency
        from capacity_planning.simulator import WhatIfCapacitySimulator
        self.simulator = WhatIfCapacitySimulator(self.repo)
        self.planner = CapacityPlanner(
            self.repo, self.forecaster, self.saturation, self.optimizer, self.cost_model
        )
        self.governor = AutonomousScalingGovernor(self.repo, self.inventory)
        self.monitor = ContinuousCapacityMonitor(self.repo)
        self.reporter = CapacityReporter(self.repo, self.cost_model)

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if event_fabric and Event and EventEnvelope:
            try:
                env = EventEnvelope(
                    event_type=f"capacity.{event_type}",
                    source="capacity_planning_service",
                )
                ev = Event(
                    envelope=env,
                    payload=payload,
                )
                import asyncio
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
                if loop and loop.is_running():
                    loop.create_task(event_fabric.publish(ev))
                else:
                    asyncio.run(event_fabric.publish(ev))
            except Exception as e:
                logger.warning(f"Failed to publish event {event_type} to event fabric: {e}")

    # --- 1. Resource Inventory & Telemetry ---
    def register_resource(
        self,
        resource_id: str,
        resource_name: str,
        dimension: ResourceDimension,
        resource_type: str,
        source: str,
        total_capacity: float,
        unit: MetricUnit,
        associated_service: str = "omnia-core",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ResourceInventoryItem:
        item = self.inventory.register_resource(
            resource_id=resource_id,
            resource_name=resource_name,
            dimension=dimension,
            resource_type=resource_type,
            source=source,
            total_capacity=total_capacity,
            unit=unit,
            associated_service=associated_service,
            metadata=metadata,
        )
        self._publish_event("resource_registered", {"resource_id": resource_id, "dimension": dimension.value})
        return item

    def record_measurement(
        self,
        resource_id: str,
        current_value: Optional[float],
        configured_capacity: Optional[float] = None,
        data_confidence: float = 1.0,
    ) -> ResourceMeasurementRecord:
        m = self.collector.record_measurement(
            resource_id=resource_id,
            current_value=current_value,
            configured_capacity=configured_capacity,
            data_confidence=data_confidence,
        )
        self._publish_event("measurement_recorded", {
            "resource_id": resource_id,
            "utilization_pct": m.utilization_pct,
            "status": m.collection_status,
        })
        return m

    # --- 2. Workload Demand & Forecasting ---
    def record_demand(
        self,
        category: WorkloadCategory,
        workload_name: str,
        cpu_consumption: float,
        memory_mb: float,
        duration_sec: float,
        request_rate_per_sec: float = 0.0,
        peak_cpu_consumption: Optional[float] = None,
        concurrency_requirement: int = 1,
    ) -> WorkloadDemandProfile:
        p = self.demand.record_workload_demand(
            category=category,
            workload_name=workload_name,
            cpu_consumption=cpu_consumption,
            memory_mb=memory_mb,
            duration_sec=duration_sec,
            request_rate_per_sec=request_rate_per_sec,
            peak_cpu_consumption=peak_cpu_consumption,
            concurrency_requirement=concurrency_requirement,
        )
        self._publish_event("demand_recorded", {"workload_name": workload_name, "category": category.value})
        return p

    def forecast_capacity(
        self,
        resource_id: str,
        horizon: ForecastHorizon = ForecastHorizon.TWENTY_FOUR_HOURS,
    ) -> CapacityForecastRecord:
        fc = self.forecaster.generate_forecast(resource_id=resource_id, horizon=horizon)
        self._publish_event("forecast_generated", {
            "resource_id": resource_id,
            "horizon": horizon.value,
            "projected_utilization_pct": fc.projected_utilization_pct,
        })
        return fc

    # --- 3. Saturation Detection & Cost Modeling ---
    def detect_saturation_risks(
        self,
        warning_threshold_pct: float = 75.0,
        critical_threshold_pct: float = 90.0,
    ) -> List[SaturationRiskFinding]:
        risks = self.saturation.detect_saturation_risks(
            warning_threshold_pct=warning_threshold_pct,
            critical_threshold_pct=critical_threshold_pct,
        )
        for r in risks:
            self._publish_event("saturation_risk_detected", {
                "risk_id": r.risk_id,
                "resource_id": r.resource_id,
                "severity": r.severity.value,
            })
        return risks

    def get_cost_projection(self) -> InfrastructureCostProjection:
        return self.cost_model.estimate_current_costs()

    def evaluate_scaling_options(
        self,
        resource_id: str,
        target_headroom_increase: float,
    ) -> List[ScalingStrategyEvaluation]:
        return self.optimizer.evaluate_scaling_options(resource_id, target_headroom_increase)

    # --- 4. What-If Simulation ---
    def simulate_capacity_scenario(
        self,
        scenario_name: str,
        workload_multiplier: float,
        unavailable_resources: Optional[List[str]] = None,
        quota_reduction_pct: float = 0.0,
        description: str = "",
    ) -> CapacitySimulationResult:
        sc = self.simulator.define_scenario(
            scenario_name=scenario_name,
            workload_multiplier=workload_multiplier,
            unavailable_resources=unavailable_resources,
            quota_reduction_pct=quota_reduction_pct,
            description=description,
        )
        sim = self.simulator.run_simulation(sc.scenario_id)
        self._publish_event("simulation_completed", {
            "scenario_name": scenario_name,
            "max_utilization_pct": sim.max_projected_utilization_pct,
            "is_resilient": sim.is_resilient,
        })
        return sim

    # --- 5. Capacity Planning & Governed Execution ---
    def create_capacity_plan(
        self,
        title: str,
        horizon: ForecastHorizon = ForecastHorizon.TWENTY_FOUR_HOURS,
        governance_mode: ScalingGovernanceMode = ScalingGovernanceMode.APPROVAL_REQUIRED,
    ) -> CapacityPlanRecord:
        plan = self.planner.generate_capacity_plan(
            title=title,
            horizon=horizon,
            governance_mode=governance_mode,
        )
        self._publish_event("plan_created", {"plan_id": plan.plan_id, "title": title})
        return plan

    def submit_scaling_proposal(
        self,
        plan_id: str,
        resource_id: str,
        strategy_type: ScalingStrategyType,
        to_capacity: float,
    ) -> ScalingProposalRecord:
        prop = self.planner.create_scaling_proposal(
            plan_id=plan_id,
            resource_id=resource_id,
            strategy_type=strategy_type,
            to_capacity=to_capacity,
        )
        self._publish_event("proposal_submitted", {
            "proposal_id": prop.proposal_id,
            "resource_id": resource_id,
            "to_capacity": to_capacity,
        })
        return prop

    def execute_scaling_proposal(
        self,
        proposal_id: str,
        approval_token: Optional[str] = None,
        governance_mode: ScalingGovernanceMode = ScalingGovernanceMode.APPROVAL_REQUIRED,
    ) -> ScalingExecutionRecord:
        ex = self.governor.execute_scaling_proposal(
            proposal_id=proposal_id,
            approval_token=approval_token,
            governance_mode=governance_mode,
        )
        self._publish_event("scaling_executed", {
            "execution_id": ex.execution_id,
            "resource_id": ex.resource_id,
            "applied_capacity": ex.applied_capacity,
        })
        return ex

    # --- 6. Continuous Monitoring & Reporting ---
    def evaluate_forecast_accuracy(
        self,
        forecast_id: str,
        actual_demand: float,
    ) -> ForecastAccuracyEvaluation:
        eval_rec = self.monitor.evaluate_forecast_accuracy(forecast_id, actual_demand)
        self._publish_event("forecast_evaluated", {
            "forecast_id": forecast_id,
            "percentage_error": eval_rec.percentage_error,
        })
        return eval_rec

    def get_capacity_overview(self) -> Dict[str, Any]:
        return self.reporter.generate_capacity_overview()


# Global Singleton Instance
capacity_planning_service = CapacityPlanningOrchestrator()
