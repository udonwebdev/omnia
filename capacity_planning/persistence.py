"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Database Persistence Layer (Schema Version 27).
"""

from __future__ import annotations

import json
import sqlite3
import logging
from typing import Any, Dict, List, Optional

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
    SaturationRiskSeverity,
    ScalingExecutionRecord,
    ScalingGovernanceMode,
    ScalingProposalRecord,
    ScalingProposalStatus,
    ScalingStrategyEvaluation,
    ScalingStrategyType,
    WorkloadCategory,
    WorkloadDemandProfile,
)

logger = logging.getLogger("Omnia.Capacity.Persistence")


class CapacityRepository:
    """Manages persistent SQLite operations for Module 42 across 13 dedicated tables."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # 1. Resource Inventory
    # -------------------------------------------------------------
    def save_resource(self, item: ResourceInventoryItem) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_resources (
                    resource_id, resource_name, dimension, resource_type, source,
                    total_capacity, unit, associated_service, is_active, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                    resource_name=excluded.resource_name,
                    total_capacity=excluded.total_capacity,
                    unit=excluded.unit,
                    associated_service=excluded.associated_service,
                    is_active=excluded.is_active,
                    metadata_json=excluded.metadata_json
                """,
                (
                    item.resource_id,
                    item.resource_name,
                    item.dimension.value,
                    item.resource_type,
                    item.source,
                    item.total_capacity,
                    item.unit.value,
                    item.associated_service,
                    1 if item.is_active else 0,
                    json.dumps(item.metadata),
                    item.created_at,
                ),
            )
            conn.commit()

    def get_resource(self, resource_id: str) -> Optional[ResourceInventoryItem]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM cap_resources WHERE resource_id = ?", (resource_id,)).fetchone()
            if not row:
                return None
            return ResourceInventoryItem(
                resource_id=row["resource_id"],
                resource_name=row["resource_name"],
                dimension=ResourceDimension(row["dimension"]),
                resource_type=row["resource_type"],
                source=row["source"],
                total_capacity=row["total_capacity"],
                unit=MetricUnit(row["unit"]),
                associated_service=row["associated_service"],
                is_active=bool(row["is_active"]),
                metadata=json.loads(row["metadata_json"] or "{}"),
                created_at=row["created_at"],
            )

    def list_resources(self, active_only: bool = True) -> List[ResourceInventoryItem]:
        with self._get_connection() as conn:
            query = "SELECT * FROM cap_resources"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY dimension ASC, resource_name ASC"
            rows = conn.execute(query).fetchall()
            return [
                ResourceInventoryItem(
                    resource_id=r["resource_id"],
                    resource_name=r["resource_name"],
                    dimension=ResourceDimension(r["dimension"]),
                    resource_type=r["resource_type"],
                    source=r["source"],
                    total_capacity=r["total_capacity"],
                    unit=MetricUnit(r["unit"]),
                    associated_service=r["associated_service"],
                    is_active=bool(r["is_active"]),
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    # -------------------------------------------------------------
    # 2. Measurements
    # -------------------------------------------------------------
    def save_measurement(self, m: ResourceMeasurementRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_measurements (
                    measurement_id, resource_id, timestamp, current_value,
                    configured_capacity, available_headroom, utilization_pct,
                    unit, collection_status, data_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(measurement_id) DO UPDATE SET
                    current_value=excluded.current_value,
                    available_headroom=excluded.available_headroom,
                    utilization_pct=excluded.utilization_pct,
                    collection_status=excluded.collection_status,
                    data_confidence=excluded.data_confidence
                """,
                (
                    m.measurement_id,
                    m.resource_id,
                    m.timestamp,
                    m.current_value,
                    m.configured_capacity,
                    m.available_headroom,
                    m.utilization_pct,
                    m.unit.value,
                    m.collection_status,
                    m.data_confidence,
                ),
            )
            conn.commit()

    def get_latest_measurements(self) -> Dict[str, ResourceMeasurementRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT m.* FROM cap_measurements m
                INNER JOIN (
                    SELECT resource_id, MAX(timestamp) as max_ts
                    FROM cap_measurements
                    GROUP BY resource_id
                ) latest ON m.resource_id = latest.resource_id AND m.timestamp = latest.max_ts
                """
            )
            results = {}
            for r in cursor.fetchall():
                results[r["resource_id"]] = ResourceMeasurementRecord(
                    measurement_id=r["measurement_id"],
                    resource_id=r["resource_id"],
                    timestamp=r["timestamp"],
                    current_value=r["current_value"],
                    configured_capacity=r["configured_capacity"],
                    available_headroom=r["available_headroom"],
                    utilization_pct=r["utilization_pct"],
                    unit=MetricUnit(r["unit"]),
                    collection_status=r["collection_status"],
                    data_confidence=r["data_confidence"],
                )
            return results

    def get_historical_measurements(self, resource_id: str, limit: int = 50) -> List[ResourceMeasurementRecord]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM cap_measurements WHERE resource_id = ? ORDER BY timestamp DESC LIMIT ?",
                (resource_id, limit),
            ).fetchall()
            return [
                ResourceMeasurementRecord(
                    measurement_id=r["measurement_id"],
                    resource_id=r["resource_id"],
                    timestamp=r["timestamp"],
                    current_value=r["current_value"],
                    configured_capacity=r["configured_capacity"],
                    available_headroom=r["available_headroom"],
                    utilization_pct=r["utilization_pct"],
                    unit=MetricUnit(r["unit"]),
                    collection_status=r["collection_status"],
                    data_confidence=r["data_confidence"],
                )
                for r in reversed(rows)
            ]

    # -------------------------------------------------------------
    # 3. Workload Demands
    # -------------------------------------------------------------
    def save_workload_demand(self, p: WorkloadDemandProfile) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_workload_demands (
                    profile_id, category, workload_name, avg_cpu_consumption,
                    avg_memory_mb, avg_duration_sec, request_rate_per_sec,
                    burstiness_index, concurrency_requirement, sample_count, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    avg_cpu_consumption=excluded.avg_cpu_consumption,
                    avg_memory_mb=excluded.avg_memory_mb,
                    avg_duration_sec=excluded.avg_duration_sec,
                    request_rate_per_sec=excluded.request_rate_per_sec,
                    burstiness_index=excluded.burstiness_index,
                    concurrency_requirement=excluded.concurrency_requirement,
                    sample_count=excluded.sample_count,
                    updated_at=excluded.updated_at
                """,
                (
                    p.profile_id,
                    p.category.value,
                    p.workload_name,
                    p.avg_cpu_consumption,
                    p.avg_memory_mb,
                    p.avg_duration_sec,
                    p.request_rate_per_sec,
                    p.burstiness_index,
                    p.concurrency_requirement,
                    p.sample_count,
                    p.updated_at,
                ),
            )
            conn.commit()

    def list_workload_demands(self) -> List[WorkloadDemandProfile]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM cap_workload_demands ORDER BY category ASC").fetchall()
            return [
                WorkloadDemandProfile(
                    profile_id=r["profile_id"],
                    category=WorkloadCategory(r["category"]),
                    workload_name=r["workload_name"],
                    avg_cpu_consumption=r["avg_cpu_consumption"],
                    avg_memory_mb=r["avg_memory_mb"],
                    avg_duration_sec=r["avg_duration_sec"],
                    request_rate_per_sec=r["request_rate_per_sec"],
                    burstiness_index=r["burstiness_index"],
                    concurrency_requirement=r["concurrency_requirement"],
                    sample_count=r["sample_count"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    # -------------------------------------------------------------
    # 4. Capacity Forecasts
    # -------------------------------------------------------------
    def save_forecast(self, f: CapacityForecastRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_forecasts (
                    forecast_id, resource_id, horizon, forecasted_demand,
                    current_capacity, projected_headroom, projected_utilization_pct,
                    estimated_saturation_hours, confidence_lower_bound,
                    confidence_upper_bound, confidence_score, model_method,
                    data_quality, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(forecast_id) DO UPDATE SET
                    forecasted_demand=excluded.forecasted_demand,
                    projected_headroom=excluded.projected_headroom,
                    projected_utilization_pct=excluded.projected_utilization_pct,
                    estimated_saturation_hours=excluded.estimated_saturation_hours,
                    confidence_score=excluded.confidence_score
                """,
                (
                    f.forecast_id,
                    f.resource_id,
                    f.horizon.value,
                    f.forecasted_demand,
                    f.current_capacity,
                    f.projected_headroom,
                    f.projected_utilization_pct,
                    f.estimated_saturation_hours,
                    f.confidence_lower_bound,
                    f.confidence_upper_bound,
                    f.confidence_score,
                    f.model_method,
                    f.data_quality,
                    f.generated_at,
                ),
            )
            conn.commit()

    def get_latest_forecast(self, resource_id: str, horizon: Any = ForecastHorizon.TWENTY_FOUR_HOURS) -> Optional[CapacityForecastRecord]:
        h_val = horizon.value if hasattr(horizon, "value") else str(horizon)
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM cap_forecasts WHERE resource_id = ? AND horizon = ? ORDER BY generated_at DESC LIMIT 1",
                (resource_id, h_val),
            ).fetchone()
            if not row:
                return None
            return CapacityForecastRecord(
                forecast_id=row["forecast_id"],
                resource_id=row["resource_id"],
                horizon=ForecastHorizon(row["horizon"]),
                forecasted_demand=row["forecasted_demand"],
                current_capacity=row["current_capacity"],
                projected_headroom=row["projected_headroom"],
                projected_utilization_pct=row["projected_utilization_pct"],
                estimated_saturation_hours=row["estimated_saturation_hours"],
                confidence_lower_bound=row["confidence_lower_bound"],
                confidence_upper_bound=row["confidence_upper_bound"],
                confidence_score=row["confidence_score"],
                model_method=row["model_method"],
                data_quality=row["data_quality"],
                generated_at=row["generated_at"],
            )

    # -------------------------------------------------------------
    # 5. Saturation Risks
    # -------------------------------------------------------------
    def save_risk(self, risk: SaturationRiskFinding) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_risks (
                    risk_id, resource_id, severity, observed_utilization_pct,
                    estimated_time_to_saturation_hours, likely_cause,
                    expected_operational_impact, recommended_mitigation,
                    confidence_level, is_resolved, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(risk_id) DO UPDATE SET
                    observed_utilization_pct=excluded.observed_utilization_pct,
                    is_resolved=excluded.is_resolved
                """,
                (
                    risk.risk_id,
                    risk.resource_id,
                    risk.severity.value,
                    risk.observed_utilization_pct,
                    risk.estimated_time_to_saturation_hours,
                    risk.likely_cause,
                    risk.expected_operational_impact,
                    risk.recommended_mitigation,
                    risk.confidence_level,
                    1 if risk.is_resolved else 0,
                    risk.detected_at,
                ),
            )
            conn.commit()

    def list_unresolved_risks(self) -> List[SaturationRiskFinding]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM cap_risks WHERE is_resolved = 0 ORDER BY observed_utilization_pct DESC"
            ).fetchall()
            return [
                SaturationRiskFinding(
                    risk_id=r["risk_id"],
                    resource_id=r["resource_id"],
                    severity=SaturationRiskSeverity(r["severity"]),
                    observed_utilization_pct=r["observed_utilization_pct"],
                    estimated_time_to_saturation_hours=r["estimated_time_to_saturation_hours"],
                    likely_cause=r["likely_cause"],
                    expected_operational_impact=r["expected_operational_impact"],
                    recommended_mitigation=r["recommended_mitigation"],
                    confidence_level=r["confidence_level"],
                    is_resolved=bool(r["is_resolved"]),
                    detected_at=r["detected_at"],
                )
                for r in rows
            ]

    # -------------------------------------------------------------
    # 6. Scenarios & Simulations
    # -------------------------------------------------------------
    def save_scenario(self, sc: CapacityScenarioDefinition) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_scenarios (
                    scenario_id, scenario_name, workload_multiplier,
                    unavailable_resources_json, quota_reduction_pct, description
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    scenario_name=excluded.scenario_name,
                    workload_multiplier=excluded.workload_multiplier,
                    unavailable_resources_json=excluded.unavailable_resources_json,
                    quota_reduction_pct=excluded.quota_reduction_pct,
                    description=excluded.description
                """,
                (
                    sc.scenario_id,
                    sc.scenario_name,
                    sc.workload_multiplier,
                    json.dumps(sc.unavailable_resources),
                    sc.quota_reduction_pct,
                    sc.description,
                ),
            )
            conn.commit()

    def save_simulation(self, sim: CapacitySimulationResult) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_simulations (
                    simulation_id, scenario_id, max_projected_utilization_pct,
                    bottleneck_resources_json, throughput_degradation_pct,
                    latency_increase_factor, estimated_additional_cost_hr,
                    recommended_scaling_action, is_resilient, simulated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(simulation_id) DO UPDATE SET
                    max_projected_utilization_pct=excluded.max_projected_utilization_pct,
                    is_resilient=excluded.is_resilient
                """,
                (
                    sim.simulation_id,
                    sim.scenario_id,
                    sim.max_projected_utilization_pct,
                    json.dumps(sim.bottleneck_resources),
                    sim.throughput_degradation_pct,
                    sim.latency_increase_factor,
                    sim.estimated_additional_cost_hr,
                    sim.recommended_scaling_action,
                    1 if sim.is_resilient else 0,
                    sim.simulated_at,
                ),
            )
            conn.commit()

    # -------------------------------------------------------------
    # 7. Scaling Proposals & Plans
    # -------------------------------------------------------------
    def save_plan(self, plan: CapacityPlanRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_plans (
                    plan_id, title, horizon, current_health_posture,
                    identified_gaps_json, recommended_strategies_json,
                    estimated_total_cost_delta, required_governance_mode,
                    approval_token, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    title=excluded.title,
                    current_health_posture=excluded.current_health_posture,
                    identified_gaps_json=excluded.identified_gaps_json,
                    recommended_strategies_json=excluded.recommended_strategies_json,
                    estimated_total_cost_delta=excluded.estimated_total_cost_delta,
                    approval_token=excluded.approval_token,
                    status=excluded.status
                """,
                (
                    plan.plan_id,
                    plan.title,
                    plan.horizon.value,
                    plan.current_health_posture,
                    json.dumps(plan.identified_gaps),
                    json.dumps(plan.recommended_strategies),
                    plan.estimated_total_cost_delta,
                    plan.required_governance_mode.value,
                    plan.approval_token,
                    plan.status,
                    plan.created_at,
                ),
            )
            conn.commit()

    def get_plan(self, plan_id: str) -> Optional[CapacityPlanRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM cap_plans WHERE plan_id = ?", (plan_id,)).fetchone()
            if not row:
                return None
            return CapacityPlanRecord(
                plan_id=row["plan_id"],
                title=row["title"],
                horizon=ForecastHorizon(row["horizon"]),
                current_health_posture=row["current_health_posture"],
                identified_gaps=json.loads(row["identified_gaps_json"] or "[]"),
                recommended_strategies=json.loads(row["recommended_strategies_json"] or "[]"),
                estimated_total_cost_delta=row["estimated_total_cost_delta"],
                required_governance_mode=ScalingGovernanceMode(row["required_governance_mode"]),
                approval_token=row["approval_token"],
                status=row["status"],
                created_at=row["created_at"],
            )

    def save_proposal(self, p: ScalingProposalRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_scaling_proposals (
                    proposal_id, plan_id, resource_id, strategy_type,
                    from_capacity, to_capacity, cost_impact_per_hr,
                    status, approval_token, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    status=excluded.status,
                    approval_token=excluded.approval_token
                """,
                (
                    p.proposal_id,
                    p.plan_id,
                    p.resource_id,
                    p.strategy_type.value,
                    p.from_capacity,
                    p.to_capacity,
                    p.cost_impact_per_hr,
                    p.status.value,
                    p.approval_token,
                    p.created_at,
                ),
            )
            conn.commit()

    def get_proposal(self, proposal_id: str) -> Optional[ScalingProposalRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM cap_scaling_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
            if not row:
                return None
            return ScalingProposalRecord(
                proposal_id=row["proposal_id"],
                plan_id=row["plan_id"],
                resource_id=row["resource_id"],
                strategy_type=ScalingStrategyType(row["strategy_type"]),
                from_capacity=row["from_capacity"],
                to_capacity=row["to_capacity"],
                cost_impact_per_hr=row["cost_impact_per_hr"],
                status=ScalingProposalStatus(row["status"]),
                approval_token=row["approval_token"],
                created_at=row["created_at"],
            )

    def save_execution(self, ex: ScalingExecutionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_scaling_executions (
                    execution_id, proposal_id, resource_id, applied_capacity,
                    previous_capacity, status, executed_by, execution_notes, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ex.execution_id,
                    ex.proposal_id,
                    ex.resource_id,
                    ex.applied_capacity,
                    ex.previous_capacity,
                    ex.status,
                    ex.executed_by,
                    ex.execution_notes,
                    ex.executed_at,
                ),
            )
            conn.commit()

    # -------------------------------------------------------------
    # 8. Forecast Accuracy Evaluations
    # -------------------------------------------------------------
    def save_accuracy_evaluation(self, eval_rec: ForecastAccuracyEvaluation) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO cap_forecast_evaluations (
                    evaluation_id, forecast_id, resource_id, predicted_demand,
                    actual_demand, absolute_error, percentage_error,
                    within_confidence_bounds, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eval_rec.evaluation_id,
                    eval_rec.forecast_id,
                    eval_rec.resource_id,
                    eval_rec.predicted_demand,
                    eval_rec.actual_demand,
                    eval_rec.absolute_error,
                    eval_rec.percentage_error,
                    1 if eval_rec.within_confidence_bounds else 0,
                    eval_rec.evaluated_at,
                ),
            )
            conn.commit()

    def list_accuracy_evaluations(self) -> List[ForecastAccuracyEvaluation]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM cap_forecast_evaluations ORDER BY evaluated_at DESC").fetchall()
            return [
                ForecastAccuracyEvaluation(
                    evaluation_id=r["evaluation_id"],
                    forecast_id=r["forecast_id"],
                    resource_id=r["resource_id"],
                    predicted_demand=r["predicted_demand"],
                    actual_demand=r["actual_demand"],
                    absolute_error=r["absolute_error"],
                    percentage_error=r["percentage_error"],
                    within_confidence_bounds=bool(r["within_confidence_bounds"]),
                    evaluated_at=r["evaluated_at"],
                )
                for r in rows
            ]
