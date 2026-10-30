"""
Omnia Module 33: Learning Durable Persistence
SQLite persistence for all learning signals, datasets, model versions,
experiments, promotion requests, rollout records, and drift assessments,
strictly matching schema version 15 and domain dataclasses.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from learning.models import (
    AttributionConfidence,
    DatasetPurpose,
    DriftRecord,
    DriftSeverity,
    DriftType,
    ExperimentConfig,
    ExperimentStatus,
    ExperimentType,
    GateResult,
    LearningDataset,
    LearningSignal,
    ModelLifecycleStatus,
    ModelVersion,
    ParameterRecommendation,
    PromotionRequest,
    RolloutRecord,
    RolloutStage,
    RolloutStatus,
    SignalQualityStatus,
    SignalType,
)
from persistence.migrations import apply_migrations

DEFAULT_DB_PATH = "persistence/omnia_tasks.db"


class LearningRepository:
    """
    Data access layer for Module 33 tables matching schema version 15.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        apply_migrations(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # SIGNALS
    # -------------------------------------------------------------
    def save_signal(self, signal: LearningSignal) -> None:
        query = """
        INSERT OR REPLACE INTO learning_signals (
            signal_id, signal_type, schema_version, source_module, source_record_id,
            mission_id, task_id, experiment_id, correlation_id, event_time,
            observation_time, model_version, strategy_id, outcome_status,
            metrics_json, is_verified, verification_method, quality_status,
            exclusion_reason, is_eligible_for_eval, is_eligible_for_training,
            provenance_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            signal.signal_id,
            signal.signal_type.value if isinstance(signal.signal_type, SignalType) else str(signal.signal_type),
            signal.schema_version,
            signal.source_module,
            signal.source_record_id,
            signal.mission_id,
            signal.task_id,
            signal.experiment_id,
            signal.correlation_id,
            signal.event_time,
            signal.observation_time,
            signal.model_version,
            signal.strategy_id,
            signal.outcome_status,
            json.dumps(signal.metrics),
            1 if signal.is_verified else 0,
            signal.verification_method,
            signal.quality_status.value if isinstance(signal.quality_status, SignalQualityStatus) else str(signal.quality_status),
            signal.exclusion_reason,
            1 if signal.is_eligible_for_eval else 0,
            1 if signal.is_eligible_for_training else 0,
            signal.provenance_hash,
            signal.created_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_signal(self, signal_id: str) -> Optional[LearningSignal]:
        query = "SELECT * FROM learning_signals WHERE signal_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (signal_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_signal(row)

    def list_signals(
        self,
        strategy_id: Optional[str] = None,
        source_module: Optional[str] = None,
        limit: int = 100,
    ) -> List[LearningSignal]:
        conditions = []
        params: List[Any] = []
        if strategy_id:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)
        if source_module:
            conditions.append("source_module = ?")
            params.append(source_module)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM learning_signals {where_clause} ORDER BY observation_time DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [self._row_to_signal(r) for r in rows]

    # -------------------------------------------------------------
    # DATASETS
    # -------------------------------------------------------------
    def save_dataset(self, dataset: LearningDataset) -> None:
        query = """
        INSERT OR REPLACE INTO learning_datasets (
            dataset_id, version, purpose, schema_version, time_window_start,
            time_window_end, sample_count, manifest_json, inclusion_rules_json,
            features_schema_json, content_digest, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            dataset.dataset_id,
            dataset.version,
            dataset.purpose.value if isinstance(dataset.purpose, DatasetPurpose) else str(dataset.purpose),
            dataset.schema_version,
            dataset.time_window_start,
            dataset.time_window_end,
            dataset.sample_count,
            json.dumps(dataset.manifest),
            json.dumps(dataset.inclusion_rules),
            json.dumps(dataset.features_schema),
            dataset.content_digest,
            dataset.created_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_dataset(self, dataset_id: str) -> Optional[LearningDataset]:
        query = "SELECT * FROM learning_datasets WHERE dataset_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (dataset_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_dataset(row)

    # -------------------------------------------------------------
    # MODEL VERSIONS
    # -------------------------------------------------------------
    def save_model_version(self, version: ModelVersion) -> None:
        query = """
        INSERT OR REPLACE INTO learning_model_versions (
            model_id, version_id, model_family, artifact_ref, artifact_digest,
            feature_schema_version, risk_level, status, evaluation_summary_json,
            limitations_json, created_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            version.model_id,
            version.version_id,
            version.model_family,
            version.artifact_ref,
            version.artifact_digest,
            version.feature_schema_version,
            version.risk_level,
            version.status.value if isinstance(version.status, ModelLifecycleStatus) else str(version.status),
            json.dumps(version.evaluation_summary),
            json.dumps(version.limitations),
            version.created_by,
            version.created_at,
            version.updated_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_model_version(self, model_id: str, version_id: Optional[str] = None) -> Optional[ModelVersion]:
        if version_id:
            query = "SELECT * FROM learning_model_versions WHERE model_id = ? AND version_id = ?"
            params = (model_id, version_id)
        else:
            query = "SELECT * FROM learning_model_versions WHERE version_id = ? OR model_id = ? ORDER BY created_at DESC LIMIT 1"
            params = (model_id, model_id)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_model_version(row)

    # -------------------------------------------------------------
    # EXPERIMENTS
    # -------------------------------------------------------------
    def save_experiment(self, exp: ExperimentConfig) -> None:
        query = """
        INSERT OR REPLACE INTO learning_experiments (
            experiment_id, name, hypothesis, experiment_type, baseline_version,
            candidate_version, dataset_id, protocol_json, primary_metric,
            min_sample_size, success_threshold, max_regression_threshold,
            budget_json, status, results_json, started_at, completed_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            exp.experiment_id,
            exp.name,
            exp.hypothesis,
            exp.experiment_type.value if isinstance(exp.experiment_type, ExperimentType) else str(exp.experiment_type),
            exp.baseline_version,
            exp.candidate_version,
            exp.dataset_id,
            json.dumps(exp.protocol),
            exp.primary_metric,
            exp.min_sample_size,
            exp.success_threshold,
            exp.max_regression_threshold,
            json.dumps(exp.budget),
            exp.status.value if isinstance(exp.status, ExperimentStatus) else str(exp.status),
            json.dumps(exp.results),
            exp.started_at,
            exp.completed_at,
            exp.created_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentConfig]:
        query = "SELECT * FROM learning_experiments WHERE experiment_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (experiment_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_experiment(row)

    # -------------------------------------------------------------
    # PROMOTIONS
    # -------------------------------------------------------------
    def save_promotion_request(self, req: PromotionRequest) -> None:
        query = """
        INSERT OR REPLACE INTO learning_promotion_requests (
            request_id, candidate_id, candidate_version, baseline_version,
            experiment_id, risk_level, status, gates_evaluation_json,
            approval_request_id, approved_by, approved_at, rejection_reason,
            target_rollout_stage, current_rollout_stage, rollback_target_version,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        gates_json = json.dumps([g.to_dict() for g in req.gate_results])
        params = (
            req.request_id,
            req.candidate_id,
            req.candidate_version,
            req.baseline_version,
            req.experiment_id,
            req.risk_level,
            req.status,
            gates_json,
            req.approval_request_id,
            req.approved_by,
            req.approved_at,
            req.rejection_reason,
            req.target_rollout_stage.value if isinstance(req.target_rollout_stage, RolloutStage) else str(req.target_rollout_stage),
            req.current_rollout_stage.value if isinstance(req.current_rollout_stage, RolloutStage) else str(req.current_rollout_stage),
            req.rollback_target_version,
            req.created_at,
            req.updated_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_promotion_request(self, request_id: str) -> Optional[PromotionRequest]:
        query = "SELECT * FROM learning_promotion_requests WHERE request_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (request_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_promotion_request(row)

    # -------------------------------------------------------------
    # ROLLOUTS
    # -------------------------------------------------------------
    def save_rollout(self, rec: RolloutRecord) -> None:
        query = """
        INSERT OR REPLACE INTO learning_rollout_records (
            rollout_id, request_id, candidate_version, baseline_version,
            current_stage, canary_traffic_pct, status, metrics_summary_json,
            halt_reason, started_at, updated_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            rec.rollout_id,
            rec.request_id,
            rec.candidate_version,
            rec.baseline_version,
            rec.current_stage.value if isinstance(rec.current_stage, RolloutStage) else str(rec.current_stage),
            rec.canary_traffic_pct,
            rec.status.value if isinstance(rec.status, RolloutStatus) else str(rec.status),
            json.dumps(rec.metrics_summary),
            rec.halt_reason,
            rec.started_at,
            rec.updated_at,
            rec.completed_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def get_rollout(self, rollout_id: str) -> Optional[RolloutRecord]:
        query = "SELECT * FROM learning_rollout_records WHERE rollout_id = ?"
        with self._get_connection() as conn:
            cursor = conn.execute(query, (rollout_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_rollout(row)

    # -------------------------------------------------------------
    # DRIFT
    # -------------------------------------------------------------
    def save_drift(self, drift: DriftRecord) -> None:
        query = """
        INSERT OR REPLACE INTO learning_drift_records (
            record_id, model_id, version_id, drift_type, feature_or_metric,
            baseline_value, observed_value, drift_metric_value, threshold,
            severity, recommendation, assessed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            drift.record_id,
            drift.model_id,
            drift.version_id,
            drift.drift_type.value if isinstance(drift.drift_type, DriftType) else str(drift.drift_type),
            drift.feature_or_metric,
            drift.baseline_value,
            drift.observed_value,
            drift.drift_metric_value,
            drift.threshold,
            drift.severity.value if isinstance(drift.severity, DriftSeverity) else str(drift.severity),
            drift.recommendation,
            drift.assessed_at,
        )
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    # -------------------------------------------------------------
    # ROW MAPPERS
    # -------------------------------------------------------------
    def _row_to_signal(self, row: sqlite3.Row) -> LearningSignal:
        return LearningSignal(
            signal_id=row["signal_id"],
            signal_type=SignalType(row["signal_type"]),
            schema_version=row["schema_version"],
            source_module=row["source_module"],
            source_record_id=row["source_record_id"],
            mission_id=row["mission_id"],
            task_id=row["task_id"],
            experiment_id=row["experiment_id"],
            correlation_id=row["correlation_id"],
            event_time=row["event_time"],
            observation_time=row["observation_time"],
            model_version=row["model_version"],
            strategy_id=row["strategy_id"],
            outcome_status=row["outcome_status"],
            metrics=json.loads(row["metrics_json"]),
            is_verified=bool(row["is_verified"]),
            verification_method=row["verification_method"],
            quality_status=SignalQualityStatus(row["quality_status"]),
            exclusion_reason=row["exclusion_reason"],
            is_eligible_for_eval=bool(row["is_eligible_for_eval"]),
            is_eligible_for_training=bool(row["is_eligible_for_training"]),
            provenance_hash=row["provenance_hash"],
            created_at=row["created_at"],
        )

    def _row_to_dataset(self, row: sqlite3.Row) -> LearningDataset:
        return LearningDataset(
            dataset_id=row["dataset_id"],
            version=row["version"],
            purpose=DatasetPurpose(row["purpose"]),
            schema_version=row["schema_version"],
            time_window_start=row["time_window_start"],
            time_window_end=row["time_window_end"],
            sample_count=row["sample_count"],
            manifest=json.loads(row["manifest_json"]),
            inclusion_rules=json.loads(row["inclusion_rules_json"]),
            features_schema=json.loads(row["features_schema_json"]),
            content_digest=row["content_digest"],
            created_at=row["created_at"],
        )

    def _row_to_model_version(self, row: sqlite3.Row) -> ModelVersion:
        return ModelVersion(
            model_id=row["model_id"],
            version_id=row["version_id"],
            model_family=row["model_family"],
            artifact_ref=row["artifact_ref"],
            artifact_digest=row["artifact_digest"],
            feature_schema_version=row["feature_schema_version"],
            risk_level=row["risk_level"],
            status=ModelLifecycleStatus(row["status"]),
            evaluation_summary=json.loads(row["evaluation_summary_json"]),
            limitations=json.loads(row["limitations_json"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_experiment(self, row: sqlite3.Row) -> ExperimentConfig:
        return ExperimentConfig(
            experiment_id=row["experiment_id"],
            name=row["name"],
            hypothesis=row["hypothesis"],
            experiment_type=ExperimentType(row["experiment_type"]),
            baseline_version=row["baseline_version"],
            candidate_version=row["candidate_version"],
            dataset_id=row["dataset_id"],
            protocol=json.loads(row["protocol_json"]),
            primary_metric=row["primary_metric"],
            min_sample_size=row["min_sample_size"],
            success_threshold=row["success_threshold"],
            max_regression_threshold=row["max_regression_threshold"],
            budget=json.loads(row["budget_json"]),
            status=ExperimentStatus(row["status"]),
            results=json.loads(row["results_json"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
        )

    def _row_to_promotion_request(self, row: sqlite3.Row) -> PromotionRequest:
        raw_gates = json.loads(row["gates_evaluation_json"])
        gates = [GateResult(**g) for g in raw_gates]
        return PromotionRequest(
            request_id=row["request_id"],
            candidate_id=row["candidate_id"],
            candidate_version=row["candidate_version"],
            baseline_version=row["baseline_version"],
            experiment_id=row["experiment_id"],
            risk_level=row["risk_level"],
            status=row["status"],
            gate_results=gates,
            approval_request_id=row["approval_request_id"],
            approved_by=row["approved_by"],
            approved_at=row["approved_at"],
            rejection_reason=row["rejection_reason"],
            target_rollout_stage=RolloutStage(row["target_rollout_stage"]),
            current_rollout_stage=RolloutStage(row["current_rollout_stage"]),
            rollback_target_version=row["rollback_target_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_rollout(self, row: sqlite3.Row) -> RolloutRecord:
        return RolloutRecord(
            rollout_id=row["rollout_id"],
            request_id=row["request_id"],
            candidate_version=row["candidate_version"],
            baseline_version=row["baseline_version"],
            current_stage=RolloutStage(row["current_stage"]),
            canary_traffic_pct=row["canary_traffic_pct"],
            status=RolloutStatus(row["status"]),
            metrics_summary=json.loads(row["metrics_summary_json"]),
            halt_reason=row["halt_reason"],
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )
