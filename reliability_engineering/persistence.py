"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Persistence Layer: SQLite Repository for Schema Version 26 Tables.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from reliability_engineering.models import (
    BackupRecord,
    BackupType,
    BackupValidationRecord,
    ComponentReliabilityCriticality,
    DisasterRecoveryPlanRecord,
    ExperimentLifecycleState,
    FailoverReadinessState,
    FailureDomain,
    FailureModeRecord,
    FailureScenarioRecord,
    FaultInjectionExperiment,
    RecoveryExecutionRecord,
    RecoveryStrategy,
    RecoveryVerificationRecord,
    ReliabilityComponent,
    ResilienceObjectiveRecord,
    ResilienceObjectiveType,
    ResilienceRegressionRecord,
    StateIntegrityFinding,
    ValidationStatus,
)


class ReliabilityRepository:
    """Manages persistent SQLite storage for all Module 41 reliability engineering records."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # 1. Reliability Components
    # -------------------------------------------------------------
    def save_component(self, comp: ReliabilityComponent) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_components (
                    component_id, component_name, criticality, owner, failure_domain,
                    data_ownership, dependencies_json, recovery_procedure, backup_strategy,
                    redundancy_config, failover_readiness, last_assessment_at, last_recovery_drill_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(component_id) DO UPDATE SET
                    component_name=excluded.component_name,
                    criticality=excluded.criticality,
                    owner=excluded.owner,
                    failure_domain=excluded.failure_domain,
                    data_ownership=excluded.data_ownership,
                    dependencies_json=excluded.dependencies_json,
                    recovery_procedure=excluded.recovery_procedure,
                    backup_strategy=excluded.backup_strategy,
                    redundancy_config=excluded.redundancy_config,
                    failover_readiness=excluded.failover_readiness,
                    last_assessment_at=excluded.last_assessment_at,
                    last_recovery_drill_at=excluded.last_recovery_drill_at
                """,
                (
                    comp.component_id,
                    comp.component_name,
                    comp.criticality.value,
                    comp.owner,
                    comp.failure_domain.value,
                    comp.data_ownership,
                    json.dumps(comp.dependencies),
                    comp.recovery_procedure,
                    comp.backup_strategy.value,
                    comp.redundancy_config,
                    comp.failover_readiness.value,
                    comp.last_assessment_at,
                    comp.last_recovery_drill_at,
                    comp.created_at,
                ),
            )
            conn.commit()

    def get_component(self, component_id: str) -> Optional[ReliabilityComponent]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_components WHERE component_id = ?", (component_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ReliabilityComponent(
                component_id=row["component_id"],
                component_name=row["component_name"],
                criticality=ComponentReliabilityCriticality(row["criticality"]),
                owner=row["owner"],
                failure_domain=FailureDomain(row["failure_domain"]),
                data_ownership=row["data_ownership"],
                dependencies=json.loads(row["dependencies_json"] or "[]"),
                recovery_procedure=row["recovery_procedure"],
                backup_strategy=BackupType(row["backup_strategy"]),
                redundancy_config=row["redundancy_config"],
                failover_readiness=FailoverReadinessState(row["failover_readiness"]),
                last_assessment_at=row["last_assessment_at"],
                last_recovery_drill_at=row["last_recovery_drill_at"],
                created_at=row["created_at"],
            )

    def list_components(self) -> List[ReliabilityComponent]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_components ORDER BY criticality ASC, component_id ASC")
            comps = []
            for row in cursor.fetchall():
                comps.append(
                    ReliabilityComponent(
                        component_id=row["component_id"],
                        component_name=row["component_name"],
                        criticality=ComponentReliabilityCriticality(row["criticality"]),
                        owner=row["owner"],
                        failure_domain=FailureDomain(row["failure_domain"]),
                        data_ownership=row["data_ownership"],
                        dependencies=json.loads(row["dependencies_json"] or "[]"),
                        recovery_procedure=row["recovery_procedure"],
                        backup_strategy=BackupType(row["backup_strategy"]),
                        redundancy_config=row["redundancy_config"],
                        failover_readiness=FailoverReadinessState(row["failover_readiness"]),
                        last_assessment_at=row["last_assessment_at"],
                        last_recovery_drill_at=row["last_recovery_drill_at"],
                        created_at=row["created_at"],
                    )
                )
            return comps

    # -------------------------------------------------------------
    # 2. Failure Mode Records (FMEA)
    # -------------------------------------------------------------
    def save_failure_mode(self, fm: FailureModeRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_failure_modes (
                    mode_id, component_id, failure_mode_name, potential_causes_json,
                    local_impact, downstream_impact, detectability_score, severity_score,
                    probability_score, risk_priority_number, is_spof, existing_controls_json,
                    recommended_mitigation, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mode_id) DO UPDATE SET
                    failure_mode_name=excluded.failure_mode_name,
                    potential_causes_json=excluded.potential_causes_json,
                    local_impact=excluded.local_impact,
                    downstream_impact=excluded.downstream_impact,
                    detectability_score=excluded.detectability_score,
                    severity_score=excluded.severity_score,
                    probability_score=excluded.probability_score,
                    risk_priority_number=excluded.risk_priority_number,
                    is_spof=excluded.is_spof,
                    existing_controls_json=excluded.existing_controls_json,
                    recommended_mitigation=excluded.recommended_mitigation
                """,
                (
                    fm.mode_id,
                    fm.component_id,
                    fm.failure_mode_name,
                    json.dumps(fm.potential_causes),
                    fm.local_impact,
                    fm.downstream_impact,
                    fm.detectability_score,
                    fm.severity_score,
                    fm.probability_score,
                    fm.risk_priority_number,
                    1 if fm.is_spof else 0,
                    json.dumps(fm.existing_controls),
                    fm.recommended_mitigation,
                    fm.created_at,
                ),
            )
            conn.commit()

    def list_failure_modes_for_component(self, component_id: str) -> List[FailureModeRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM rel_failure_modes WHERE component_id = ? ORDER BY risk_priority_number DESC",
                (component_id,),
            )
            modes = []
            for row in cursor.fetchall():
                modes.append(
                    FailureModeRecord(
                        mode_id=row["mode_id"],
                        component_id=row["component_id"],
                        failure_mode_name=row["failure_mode_name"],
                        potential_causes=json.loads(row["potential_causes_json"] or "[]"),
                        local_impact=row["local_impact"],
                        downstream_impact=row["downstream_impact"],
                        detectability_score=row["detectability_score"],
                        severity_score=row["severity_score"],
                        probability_score=row["probability_score"],
                        risk_priority_number=row["risk_priority_number"],
                        is_spof=bool(row["is_spof"]),
                        existing_controls=json.loads(row["existing_controls_json"] or "[]"),
                        recommended_mitigation=row["recommended_mitigation"],
                        created_at=row["created_at"],
                    )
                )
            return modes

    def list_all_spofs(self) -> List[FailureModeRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM rel_failure_modes WHERE is_spof = 1 ORDER BY severity_score DESC"
            )
            spofs = []
            for row in cursor.fetchall():
                spofs.append(
                    FailureModeRecord(
                        mode_id=row["mode_id"],
                        component_id=row["component_id"],
                        failure_mode_name=row["failure_mode_name"],
                        potential_causes=json.loads(row["potential_causes_json"] or "[]"),
                        local_impact=row["local_impact"],
                        downstream_impact=row["downstream_impact"],
                        detectability_score=row["detectability_score"],
                        severity_score=row["severity_score"],
                        probability_score=row["probability_score"],
                        risk_priority_number=row["risk_priority_number"],
                        is_spof=bool(row["is_spof"]),
                        existing_controls=json.loads(row["existing_controls_json"] or "[]"),
                        recommended_mitigation=row["recommended_mitigation"],
                        created_at=row["created_at"],
                    )
                )
            return spofs

    # -------------------------------------------------------------
    # 3. Resilience Objectives
    # -------------------------------------------------------------
    def save_objective(self, obj: ResilienceObjectiveRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_resilience_objectives (
                    objective_id, component_id, objective_type, target_value,
                    unit, demonstrated_value, is_demonstrated, verification_evidence, last_verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(objective_id) DO UPDATE SET
                    target_value=excluded.target_value,
                    demonstrated_value=excluded.demonstrated_value,
                    is_demonstrated=excluded.is_demonstrated,
                    verification_evidence=excluded.verification_evidence,
                    last_verified_at=excluded.last_verified_at
                """,
                (
                    obj.objective_id,
                    obj.component_id,
                    obj.objective_type.value,
                    obj.target_value,
                    obj.unit,
                    obj.demonstrated_value,
                    1 if obj.is_demonstrated else 0,
                    obj.verification_evidence,
                    obj.last_verified_at,
                ),
            )
            conn.commit()

    def get_objectives_for_component(self, component_id: str) -> List[ResilienceObjectiveRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_resilience_objectives WHERE component_id = ?", (component_id,))
            objs = []
            for row in cursor.fetchall():
                objs.append(
                    ResilienceObjectiveRecord(
                        objective_id=row["objective_id"],
                        component_id=row["component_id"],
                        objective_type=ResilienceObjectiveType(row["objective_type"]),
                        target_value=row["target_value"],
                        unit=row["unit"],
                        demonstrated_value=row["demonstrated_value"],
                        is_demonstrated=bool(row["is_demonstrated"]),
                        verification_evidence=row["verification_evidence"],
                        last_verified_at=row["last_verified_at"],
                    )
                )
            return objs

    # -------------------------------------------------------------
    # 4. Scenarios & Fault Experiments
    # -------------------------------------------------------------
    def save_scenario(self, sc: FailureScenarioRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_failure_scenarios (
                    scenario_id, title, category, target_environment, affected_components_json,
                    preconditions_json, injection_method, safety_constraints_json,
                    expected_behavior, abort_conditions_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id) DO UPDATE SET
                    title=excluded.title,
                    category=excluded.category,
                    target_environment=excluded.target_environment,
                    affected_components_json=excluded.affected_components_json,
                    preconditions_json=excluded.preconditions_json,
                    injection_method=excluded.injection_method,
                    safety_constraints_json=excluded.safety_constraints_json,
                    expected_behavior=excluded.expected_behavior,
                    abort_conditions_json=excluded.abort_conditions_json
                """,
                (
                    sc.scenario_id,
                    sc.title,
                    sc.category,
                    sc.target_environment,
                    json.dumps(sc.affected_components),
                    json.dumps(sc.preconditions),
                    sc.injection_method,
                    json.dumps(sc.safety_constraints),
                    sc.expected_behavior,
                    json.dumps(sc.abort_conditions),
                    sc.created_at,
                ),
            )
            conn.commit()

    def get_scenario(self, scenario_id: str) -> Optional[FailureScenarioRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_failure_scenarios WHERE scenario_id = ?", (scenario_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return FailureScenarioRecord(
                scenario_id=row["scenario_id"],
                title=row["title"],
                category=row["category"],
                target_environment=row["target_environment"],
                affected_components=json.loads(row["affected_components_json"] or "[]"),
                preconditions=json.loads(row["preconditions_json"] or "[]"),
                injection_method=row["injection_method"],
                safety_constraints=json.loads(row["safety_constraints_json"] or "[]"),
                expected_behavior=row["expected_behavior"],
                abort_conditions=json.loads(row["abort_conditions_json"] or "[]"),
                created_at=row["created_at"],
            )

    def save_experiment(self, exp: FaultInjectionExperiment) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_fault_experiments (
                    experiment_id, scenario_id, hypothesis, target_environment,
                    lifecycle_state, max_duration_sec, actual_duration_sec,
                    containment_successful, cascading_failure_detected, approval_token,
                    approved_by, started_at, completed_at, observations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(experiment_id) DO UPDATE SET
                    lifecycle_state=excluded.lifecycle_state,
                    actual_duration_sec=excluded.actual_duration_sec,
                    containment_successful=excluded.containment_successful,
                    cascading_failure_detected=excluded.cascading_failure_detected,
                    approval_token=excluded.approval_token,
                    approved_by=excluded.approved_by,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at,
                    observations_json=excluded.observations_json
                """,
                (
                    exp.experiment_id,
                    exp.scenario_id,
                    exp.hypothesis,
                    exp.target_environment,
                    exp.lifecycle_state.value,
                    exp.max_duration_sec,
                    exp.actual_duration_sec,
                    1 if exp.containment_successful else 0,
                    1 if exp.cascading_failure_detected else 0,
                    exp.approval_token,
                    exp.approved_by,
                    exp.started_at,
                    exp.completed_at,
                    json.dumps(exp.observations),
                ),
            )
            conn.commit()

    def get_experiment(self, experiment_id: str) -> Optional[FaultInjectionExperiment]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_fault_experiments WHERE experiment_id = ?", (experiment_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return FaultInjectionExperiment(
                experiment_id=row["experiment_id"],
                scenario_id=row["scenario_id"],
                hypothesis=row["hypothesis"],
                target_environment=row["target_environment"],
                lifecycle_state=ExperimentLifecycleState(row["lifecycle_state"]),
                max_duration_sec=row["max_duration_sec"],
                actual_duration_sec=row["actual_duration_sec"],
                containment_successful=bool(row["containment_successful"]),
                cascading_failure_detected=bool(row["cascading_failure_detected"]),
                approval_token=row["approval_token"],
                approved_by=row["approved_by"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                observations=json.loads(row["observations_json"] or "[]"),
            )

    # -------------------------------------------------------------
    # 5. Backups & Validation
    # -------------------------------------------------------------
    def save_backup(self, b: BackupRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_backups (
                    backup_id, data_source, backup_type, version, storage_reference,
                    checksum_sha256, is_encrypted, retention_days, record_count,
                    size_bytes, validation_status, last_validated_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(backup_id) DO UPDATE SET
                    validation_status=excluded.validation_status,
                    last_validated_at=excluded.last_validated_at
                """,
                (
                    b.backup_id,
                    b.data_source,
                    b.backup_type.value,
                    b.version,
                    b.storage_reference,
                    b.checksum_sha256,
                    1 if b.is_encrypted else 0,
                    b.retention_days,
                    b.record_count,
                    b.size_bytes,
                    b.validation_status.value,
                    b.last_validated_at,
                    b.created_at,
                ),
            )
            conn.commit()

    def get_backup(self, backup_id: str) -> Optional[BackupRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_backups WHERE backup_id = ?", (backup_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return BackupRecord(
                backup_id=row["backup_id"],
                data_source=row["data_source"],
                backup_type=BackupType(row["backup_type"]),
                version=row["version"],
                storage_reference=row["storage_reference"],
                checksum_sha256=row["checksum_sha256"],
                is_encrypted=bool(row["is_encrypted"]),
                retention_days=row["retention_days"],
                record_count=row["record_count"],
                size_bytes=row["size_bytes"],
                validation_status=ValidationStatus(row["validation_status"]),
                last_validated_at=row["last_validated_at"],
                created_at=row["created_at"],
            )

    def list_backups_for_source(self, data_source: str) -> List[BackupRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM rel_backups WHERE data_source = ? ORDER BY created_at DESC",
                (data_source,),
            )
            backups = []
            for row in cursor.fetchall():
                backups.append(
                    BackupRecord(
                        backup_id=row["backup_id"],
                        data_source=row["data_source"],
                        backup_type=BackupType(row["backup_type"]),
                        version=row["version"],
                        storage_reference=row["storage_reference"],
                        checksum_sha256=row["checksum_sha256"],
                        is_encrypted=bool(row["is_encrypted"]),
                        retention_days=row["retention_days"],
                        record_count=row["record_count"],
                        size_bytes=row["size_bytes"],
                        validation_status=ValidationStatus(row["validation_status"]),
                        last_validated_at=row["last_validated_at"],
                        created_at=row["created_at"],
                    )
                )
            return backups

    def save_backup_validation(self, val: BackupValidationRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_backup_validations (
                    validation_id, backup_id, status, checksum_verified, schema_compatible,
                    isolated_restore_tested, record_count_matches, validation_notes, validated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    val.validation_id,
                    val.backup_id,
                    val.status.value,
                    1 if val.checksum_verified else 0,
                    1 if val.schema_compatible else 0,
                    1 if val.isolated_restore_tested else 0,
                    1 if val.record_count_matches else 0,
                    val.validation_notes,
                    val.validated_at,
                ),
            )
            # Update parent backup status
            conn.execute(
                "UPDATE rel_backups SET validation_status = ?, last_validated_at = ? WHERE backup_id = ?",
                (val.status.value, val.validated_at, val.backup_id),
            )
            conn.commit()

    # -------------------------------------------------------------
    # 6. Disaster Recovery Plans, Executions & Verifications
    # -------------------------------------------------------------
    def save_dr_plan(self, plan: DisasterRecoveryPlanRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_dr_plans (
                    plan_id, title, disaster_scenario, version, affected_services_json,
                    recovery_priority, strategy, dependency_order_json, target_rto_sec,
                    target_rpo_sec, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    title=excluded.title,
                    version=excluded.version,
                    affected_services_json=excluded.affected_services_json,
                    recovery_priority=excluded.recovery_priority,
                    strategy=excluded.strategy,
                    dependency_order_json=excluded.dependency_order_json,
                    target_rto_sec=excluded.target_rto_sec,
                    target_rpo_sec=excluded.target_rpo_sec,
                    is_active=excluded.is_active
                """,
                (
                    plan.plan_id,
                    plan.title,
                    plan.disaster_scenario,
                    plan.version,
                    json.dumps(plan.affected_services),
                    plan.recovery_priority,
                    plan.strategy.value,
                    json.dumps(plan.dependency_order),
                    plan.target_rto_sec,
                    plan.target_rpo_sec,
                    1 if plan.is_active else 0,
                    plan.created_at,
                ),
            )
            conn.commit()

    def get_dr_plan(self, plan_id: str) -> Optional[DisasterRecoveryPlanRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_dr_plans WHERE plan_id = ?", (plan_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return DisasterRecoveryPlanRecord(
                plan_id=row["plan_id"],
                title=row["title"],
                disaster_scenario=row["disaster_scenario"],
                version=row["version"],
                affected_services=json.loads(row["affected_services_json"] or "[]"),
                recovery_priority=row["recovery_priority"],
                strategy=RecoveryStrategy(row["strategy"]),
                dependency_order=json.loads(row["dependency_order_json"] or "[]"),
                target_rto_sec=row["target_rto_sec"],
                target_rpo_sec=row["target_rpo_sec"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
            )

    def save_dr_execution(self, exec_rec: RecoveryExecutionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_dr_executions (
                    execution_id, plan_id, target_environment, status, approval_token,
                    approved_by, started_at, completed_at, duration_sec, steps_executed_json, errors_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    status=excluded.status,
                    completed_at=excluded.completed_at,
                    duration_sec=excluded.duration_sec,
                    steps_executed_json=excluded.steps_executed_json,
                    errors_json=excluded.errors_json
                """,
                (
                    exec_rec.execution_id,
                    exec_rec.plan_id,
                    exec_rec.target_environment,
                    exec_rec.status,
                    exec_rec.approval_token,
                    exec_rec.approved_by,
                    exec_rec.started_at,
                    exec_rec.completed_at,
                    exec_rec.duration_sec,
                    json.dumps(exec_rec.steps_executed),
                    json.dumps(exec_rec.errors),
                ),
            )
            conn.commit()

    def get_dr_execution(self, execution_id: str) -> Optional[RecoveryExecutionRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_dr_executions WHERE execution_id = ?", (execution_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return RecoveryExecutionRecord(
                execution_id=row["execution_id"],
                plan_id=row["plan_id"],
                target_environment=row["target_environment"],
                status=row["status"],
                approval_token=row["approval_token"],
                approved_by=row["approved_by"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                duration_sec=row["duration_sec"],
                steps_executed=json.loads(row["steps_executed_json"] or "[]"),
                errors=json.loads(row["errors_json"] or "[]"),
            )

    def save_recovery_verification(self, ver: RecoveryVerificationRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_recovery_verifications (
                    verification_id, execution_id, component_id, service_responsive,
                    data_integrity_verified, distributed_state_reconciled, actual_rto_sec,
                    actual_rpo_sec, rto_compliant, rpo_compliant, findings_json, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ver.verification_id,
                    ver.execution_id,
                    ver.component_id,
                    1 if ver.service_responsive else 0,
                    1 if ver.data_integrity_verified else 0,
                    1 if ver.distributed_state_reconciled else 0,
                    ver.actual_rto_sec,
                    ver.actual_rpo_sec,
                    1 if ver.rto_compliant else 0,
                    1 if ver.rpo_compliant else 0,
                    json.dumps(ver.findings),
                    ver.verified_at,
                ),
            )
            conn.commit()

    # -------------------------------------------------------------
    # 7. Regressions & State Integrity Findings
    # -------------------------------------------------------------
    def save_integrity_finding(self, finding: StateIntegrityFinding) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_state_integrity_reports (
                    finding_id, subsystem, divergence_type, severity, details, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.finding_id,
                    finding.subsystem,
                    finding.divergence_type,
                    finding.severity,
                    finding.details,
                    finding.detected_at,
                ),
            )
            conn.commit()

    def list_integrity_findings(self) -> List[StateIntegrityFinding]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_state_integrity_reports ORDER BY detected_at DESC")
            findings = []
            for row in cursor.fetchall():
                findings.append(
                    StateIntegrityFinding(
                        finding_id=row["finding_id"],
                        subsystem=row["subsystem"],
                        divergence_type=row["divergence_type"],
                        severity=row["severity"],
                        details=row["details"],
                        detected_at=row["detected_at"],
                    )
                )
            return findings

    def save_resilience_regression(self, reg: ResilienceRegressionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO rel_resilience_regressions (
                    regression_id, component_id, metric_name, baseline_value,
                    current_value, degradation_pct, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reg.regression_id,
                    reg.component_id,
                    reg.metric_name,
                    reg.baseline_value,
                    reg.current_value,
                    reg.degradation_pct,
                    reg.detected_at,
                ),
            )
            conn.commit()

    def list_resilience_regressions(self) -> List[ResilienceRegressionRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM rel_resilience_regressions ORDER BY detected_at DESC")
            regs = []
            for row in cursor.fetchall():
                regs.append(
                    ResilienceRegressionRecord(
                        regression_id=row["regression_id"],
                        component_id=row["component_id"],
                        metric_name=row["metric_name"],
                        baseline_value=row["baseline_value"],
                        current_value=row["current_value"],
                        degradation_pct=row["degradation_pct"],
                        detected_at=row["detected_at"],
                    )
                )
            return regs
