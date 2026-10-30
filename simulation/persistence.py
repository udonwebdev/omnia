"""
Omnia Module 34: Simulation Durable Persistence
SQLite repository managing environments, digital twins, snapshots,
scenarios, executions, fault records, and fidelity assessments.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from persistence.migrations import apply_migrations
from simulation.models import (
    DigitalTwin,
    EnvironmentClassification,
    EnvironmentType,
    FaultInjectionSpec,
    FaultType,
    FidelityAssessment,
    ScenarioDefinition,
    ScenarioType,
    SimulationEnvironment,
    SimulationExecutionRecord,
    SimulationStatus,
    StateFidelity,
    StateSnapshot,
    TwinStatus,
    TwinSyncMode,
)

DEFAULT_DB_PATH = "persistence/omnia_tasks.db"


class SimulationRepository:
    """
    Data access layer for Module 34 tables matching Schema Version 16.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        apply_migrations(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # ENVIRONMENTS
    # -------------------------------------------------------------
    def save_environment(self, env: SimulationEnvironment) -> None:
        query = """
        INSERT OR REPLACE INTO simulation_environments (
            environment_id, name, env_type, classification, version, owner,
            model_references_json, supported_capabilities_json, state_schema_json,
            supported_action_types_json, constraints_json, resource_limits_json,
            isolation_level, fidelity_classification, data_classification,
            status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            env.environment_id,
            env.name,
            env.env_type.value if isinstance(env.env_type, EnvironmentType) else str(env.env_type),
            env.classification.value if isinstance(env.classification, EnvironmentClassification) else str(env.classification),
            env.version,
            env.owner,
            json.dumps(env.model_references),
            json.dumps(env.supported_capabilities),
            json.dumps(env.state_schema),
            json.dumps(env.supported_action_types),
            json.dumps(env.constraints),
            json.dumps(env.resource_limits),
            env.isolation_level,
            env.fidelity_classification.value if isinstance(env.fidelity_classification, StateFidelity) else str(env.fidelity_classification),
            env.data_classification,
            env.status,
            env.created_at,
            env.updated_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_environment(self, environment_id: str) -> Optional[SimulationEnvironment]:
        query = "SELECT * FROM simulation_environments WHERE environment_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (environment_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_environment(row)

    def list_environments(self) -> List[SimulationEnvironment]:
        query = "SELECT * FROM simulation_environments ORDER BY created_at DESC"
        with self._get_connection() as conn:
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            return [self._row_to_environment(r) for r in rows]

    # -------------------------------------------------------------
    # DIGITAL TWINS
    # -------------------------------------------------------------
    def save_digital_twin(self, twin: DigitalTwin) -> None:
        query = """
        INSERT OR REPLACE INTO digital_twins (
            twin_id, source_system_id, source_system_type, version, sync_mode,
            state_schema_version, observed_state_json, inferred_state_json,
            simulated_state_json, capability_model_json, constraints_json,
            dependencies_json, known_omissions_json, last_sync_time,
            freshness_seconds, fidelity_status, provenance_hash,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            twin.twin_id,
            twin.source_system_id,
            twin.source_system_type,
            twin.version,
            twin.sync_mode.value if isinstance(twin.sync_mode, TwinSyncMode) else str(twin.sync_mode),
            twin.state_schema_version,
            json.dumps(twin.observed_state),
            json.dumps(twin.inferred_state),
            json.dumps(twin.simulated_state),
            json.dumps(twin.capability_model),
            json.dumps(twin.constraints),
            json.dumps(twin.dependencies),
            json.dumps(twin.known_omissions),
            twin.last_sync_time,
            twin.freshness_seconds,
            twin.fidelity_status.value if isinstance(twin.fidelity_status, StateFidelity) else str(twin.fidelity_status),
            twin.provenance_hash,
            twin.created_at,
            twin.updated_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_digital_twin(self, twin_id: str) -> Optional[DigitalTwin]:
        query = "SELECT * FROM digital_twins WHERE twin_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (twin_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_digital_twin(row)

    # -------------------------------------------------------------
    # SNAPSHOTS
    # -------------------------------------------------------------
    def save_snapshot(self, snap: StateSnapshot) -> None:
        query = """
        INSERT OR REPLACE INTO simulation_snapshots (
            snapshot_id, environment_id, source_version, captured_at,
            state_schema_version, state_payload_json, included_components_json,
            excluded_components_json, integrity_digest, consistency_status,
            data_classification, known_limitations_json, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            snap.snapshot_id,
            snap.environment_id,
            snap.source_version,
            snap.captured_at,
            snap.state_schema_version,
            json.dumps(snap.state_payload),
            json.dumps(snap.included_components),
            json.dumps(snap.excluded_components),
            snap.integrity_digest,
            snap.consistency_status,
            snap.data_classification,
            json.dumps(snap.known_limitations),
            snap.created_by,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        query = "SELECT * FROM simulation_snapshots WHERE snapshot_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (snapshot_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_snapshot(row)

    # -------------------------------------------------------------
    # SCENARIOS
    # -------------------------------------------------------------
    def save_scenario(self, scen: ScenarioDefinition) -> None:
        query = """
        INSERT OR REPLACE INTO simulation_scenarios (
            scenario_id, name, scenario_type, environment_id,
            initial_snapshot_id, proposed_actions_json, preconditions_json,
            constraints_json, expected_observations_json, time_horizon_seconds,
            resource_budget_json, uncertainty_assumptions_json,
            evaluation_metrics_json, created_at, created_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            scen.scenario_id,
            scen.name,
            scen.scenario_type.value if isinstance(scen.scenario_type, ScenarioType) else str(scen.scenario_type),
            scen.environment_id,
            scen.initial_snapshot_id,
            json.dumps(scen.proposed_actions),
            json.dumps(scen.preconditions),
            json.dumps(scen.constraints),
            json.dumps(scen.expected_observations),
            scen.time_horizon_seconds,
            json.dumps(scen.resource_budget),
            json.dumps(scen.uncertainty_assumptions),
            json.dumps(scen.evaluation_metrics),
            scen.created_at,
            scen.created_by,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_scenario(self, scenario_id: str) -> Optional[ScenarioDefinition]:
        query = "SELECT * FROM simulation_scenarios WHERE scenario_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (scenario_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_scenario(row)

    # -------------------------------------------------------------
    # EXECUTIONS
    # -------------------------------------------------------------
    def save_execution(self, exec_rec: SimulationExecutionRecord) -> None:
        query = """
        INSERT OR REPLACE INTO simulation_executions (
            simulation_id, scenario_id, environment_id, twin_id, snapshot_id,
            status, current_step, total_steps, action_history_json,
            state_transitions_json, events_generated_json, resource_consumption_json,
            result_summary_json, fidelity_classification, started_at, completed_at,
            error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            exec_rec.simulation_id,
            exec_rec.scenario_id,
            exec_rec.environment_id,
            exec_rec.twin_id,
            exec_rec.snapshot_id,
            exec_rec.status.value if isinstance(exec_rec.status, SimulationStatus) else str(exec_rec.status),
            exec_rec.current_step,
            exec_rec.total_steps,
            json.dumps(exec_rec.action_history),
            json.dumps(exec_rec.state_transitions),
            json.dumps(exec_rec.events_generated),
            json.dumps(exec_rec.resource_consumption),
            json.dumps(exec_rec.result_summary),
            exec_rec.fidelity_classification.value if isinstance(exec_rec.fidelity_classification, StateFidelity) else str(exec_rec.fidelity_classification),
            exec_rec.started_at,
            exec_rec.completed_at,
            exec_rec.error_message,
            exec_rec.created_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_execution(self, simulation_id: str) -> Optional[SimulationExecutionRecord]:
        query = "SELECT * FROM simulation_executions WHERE simulation_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (simulation_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_execution(row)

    # -------------------------------------------------------------
    # FAULTS
    # -------------------------------------------------------------
    def save_fault(self, fault: FaultInjectionSpec) -> None:
        query = """
        INSERT OR REPLACE INTO simulation_faults (
            fault_id, simulation_id, fault_type, target_component,
            activation_step, duration_steps, severity, injected_at,
            recovery_observed, recovery_details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            fault.fault_id,
            fault.simulation_id,
            fault.fault_type.value if isinstance(fault.fault_type, FaultType) else str(fault.fault_type),
            fault.target_component,
            fault.activation_step,
            fault.duration_steps,
            fault.severity,
            fault.injected_at,
            1 if fault.recovery_observed else 0,
            json.dumps(fault.recovery_details),
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    # -------------------------------------------------------------
    # FIDELITY
    # -------------------------------------------------------------
    def save_fidelity(self, fid: FidelityAssessment) -> None:
        query = """
        INSERT OR REPLACE INTO simulation_fidelity_records (
            record_id, simulation_id, twin_id, fidelity_level,
            reality_observation_id, deviation_metrics_json,
            failed_assumptions_json, unexplained_deviations_json,
            assessed_at, recommended_learning_signal
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            fid.record_id,
            fid.simulation_id,
            fid.twin_id,
            fid.fidelity_level.value if isinstance(fid.fidelity_level, StateFidelity) else str(fid.fidelity_level),
            fid.reality_observation_id,
            json.dumps(fid.deviation_metrics),
            json.dumps(fid.failed_assumptions),
            json.dumps(fid.unexplained_deviations),
            fid.assessed_at,
            1 if fid.recommended_learning_signal else 0,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    # -------------------------------------------------------------
    # ROW MAPPERS
    # -------------------------------------------------------------
    def _row_to_environment(self, row: sqlite3.Row) -> SimulationEnvironment:
        return SimulationEnvironment(
            environment_id=row["environment_id"],
            name=row["name"],
            env_type=EnvironmentType(row["env_type"]),
            classification=EnvironmentClassification(row["classification"]),
            version=row["version"],
            owner=row["owner"],
            model_references=json.loads(row["model_references_json"]),
            supported_capabilities=json.loads(row["supported_capabilities_json"]),
            state_schema=json.loads(row["state_schema_json"]),
            supported_action_types=json.loads(row["supported_action_types_json"]),
            constraints=json.loads(row["constraints_json"]),
            resource_limits=json.loads(row["resource_limits_json"]),
            isolation_level=row["isolation_level"],
            fidelity_classification=StateFidelity(row["fidelity_classification"]),
            data_classification=row["data_classification"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_digital_twin(self, row: sqlite3.Row) -> DigitalTwin:
        return DigitalTwin(
            twin_id=row["twin_id"],
            source_system_id=row["source_system_id"],
            source_system_type=row["source_system_type"],
            version=row["version"],
            sync_mode=TwinSyncMode(row["sync_mode"]),
            state_schema_version=row["state_schema_version"],
            observed_state=json.loads(row["observed_state_json"]),
            inferred_state=json.loads(row["inferred_state_json"]),
            simulated_state=json.loads(row["simulated_state_json"]),
            capability_model=json.loads(row["capability_model_json"]),
            constraints=json.loads(row["constraints_json"]),
            dependencies=json.loads(row["dependencies_json"]),
            known_omissions=json.loads(row["known_omissions_json"]),
            last_sync_time=row["last_sync_time"],
            freshness_seconds=row["freshness_seconds"],
            fidelity_status=StateFidelity(row["fidelity_status"]),
            provenance_hash=row["provenance_hash"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_snapshot(self, row: sqlite3.Row) -> StateSnapshot:
        return StateSnapshot(
            snapshot_id=row["snapshot_id"],
            environment_id=row["environment_id"],
            source_version=row["source_version"],
            captured_at=row["captured_at"],
            state_schema_version=row["state_schema_version"],
            state_payload=json.loads(row["state_payload_json"]),
            included_components=json.loads(row["included_components_json"]),
            excluded_components=json.loads(row["excluded_components_json"]),
            integrity_digest=row["integrity_digest"],
            consistency_status=row["consistency_status"],
            data_classification=row["data_classification"],
            known_limitations=json.loads(row["known_limitations_json"]),
            created_by=row["created_by"],
        )

    def _row_to_scenario(self, row: sqlite3.Row) -> ScenarioDefinition:
        return ScenarioDefinition(
            scenario_id=row["scenario_id"],
            name=row["name"],
            scenario_type=ScenarioType(row["scenario_type"]),
            environment_id=row["environment_id"],
            initial_snapshot_id=row["initial_snapshot_id"],
            proposed_actions=json.loads(row["proposed_actions_json"]),
            preconditions=json.loads(row["preconditions_json"]),
            constraints=json.loads(row["constraints_json"]),
            expected_observations=json.loads(row["expected_observations_json"]),
            time_horizon_seconds=row["time_horizon_seconds"],
            resource_budget=json.loads(row["resource_budget_json"]),
            uncertainty_assumptions=json.loads(row["uncertainty_assumptions_json"]),
            evaluation_metrics=json.loads(row["evaluation_metrics_json"]),
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    def _row_to_execution(self, row: sqlite3.Row) -> SimulationExecutionRecord:
        return SimulationExecutionRecord(
            simulation_id=row["simulation_id"],
            scenario_id=row["scenario_id"],
            environment_id=row["environment_id"],
            twin_id=row["twin_id"],
            snapshot_id=row["snapshot_id"],
            status=SimulationStatus(row["status"]),
            current_step=row["current_step"],
            total_steps=row["total_steps"],
            action_history=json.loads(row["action_history_json"]),
            state_transitions=json.loads(row["state_transitions_json"]),
            events_generated=json.loads(row["events_generated_json"]),
            resource_consumption=json.loads(row["resource_consumption_json"]),
            result_summary=json.loads(row["result_summary_json"]),
            fidelity_classification=StateFidelity(row["fidelity_classification"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error_message=row["error_message"],
            created_at=row["created_at"],
        )
