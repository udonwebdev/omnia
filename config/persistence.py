import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional
from config.models import (
    ConfigSchema,
    ConfigType,
    ConfigScope,
    RuntimeMutability,
    ConfigValue,
    ConfigVersion,
    ConfigVersionStatus,
    ConfigRollout,
    RolloutStrategy,
    RolloutStatus,
    DriftRecord,
    DriftType
)

logger = logging.getLogger("Omnia.Config.Persistence")

class ConfigPersistence:
    """SQLite persistence repository for runtime configuration schemas, versions, values, rollouts, and drift records."""

    def __init__(self, db_path: str = "persistence/omnia_tasks.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Schemas ---
    def save_schema(self, schema: ConfigSchema) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO config_schemas (
                    key, domain, data_type, default_value_json, schema_spec_json,
                    scope, mutability, requires_restart, is_secret,
                    allowed_values_json, min_value, max_value, unit,
                    description, dependencies_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                schema.key,
                schema.domain,
                schema.data_type.value,
                json.dumps(schema.default_value),
                json.dumps(schema.schema_spec),
                schema.scope.value,
                schema.mutability.value,
                1 if schema.requires_restart else 0,
                1 if schema.is_secret else 0,
                json.dumps(schema.allowed_values),
                schema.min_value,
                schema.max_value,
                schema.unit,
                schema.description,
                json.dumps(schema.dependencies),
                schema.created_at,
                schema.updated_at
            ))
            conn.commit()
            return True

    def get_schema(self, key: str) -> Optional[ConfigSchema]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config_schemas WHERE key = ?", (key,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_schema(row)

    def list_schemas(self, domain: Optional[str] = None) -> List[ConfigSchema]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if domain:
                cursor.execute("SELECT * FROM config_schemas WHERE domain = ? ORDER BY key", (domain,))
            else:
                cursor.execute("SELECT * FROM config_schemas ORDER BY key")
            return [self._row_to_schema(r) for r in cursor.fetchall()]

    def _row_to_schema(self, r: sqlite3.Row) -> ConfigSchema:
        return ConfigSchema(
            key=r["key"],
            domain=r["domain"],
            data_type=ConfigType(r["data_type"]),
            default_value=json.loads(r["default_value_json"]),
            schema_spec=json.loads(r["schema_spec_json"]),
            scope=ConfigScope(r["scope"]),
            mutability=RuntimeMutability(r["mutability"]),
            requires_restart=bool(r["requires_restart"]),
            is_secret=bool(r["is_secret"]),
            allowed_values=json.loads(r["allowed_values_json"]),
            min_value=r["min_value"],
            max_value=r["max_value"],
            unit=r["unit"],
            description=r["description"],
            dependencies=json.loads(r["dependencies_json"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"]
        )

    # --- Versions ---
    def save_version(self, version: ConfigVersion) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO config_versions (
                    version, parent_version, scope, target_entity, content_hash,
                    values_json, author, justification, approval_token,
                    status, created_at, activated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                version.version,
                version.parent_version,
                version.scope.value,
                version.target_entity,
                version.content_hash,
                json.dumps(version.values),
                version.author,
                version.justification,
                version.approval_token,
                version.status.value,
                version.created_at,
                version.activated_at
            ))
            conn.commit()
            return True

    def get_version(self, version_num: int) -> Optional[ConfigVersion]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config_versions WHERE version = ?", (version_num,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_version(row)

    def get_active_version(self, scope: ConfigScope = ConfigScope.CLUSTER, target_entity: str = "CLUSTER") -> Optional[ConfigVersion]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM config_versions 
                WHERE status = 'ACTIVE' AND scope = ? AND target_entity = ?
                ORDER BY version DESC LIMIT 1
            """, (scope.value, target_entity))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_version(row)

    def get_latest_version_num(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(version) FROM config_versions")
            res = cursor.fetchone()
            return res[0] if res and res[0] is not None else 0

    def list_versions(self, limit: int = 20) -> List[ConfigVersion]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config_versions ORDER BY version DESC LIMIT ?", (limit,))
            return [self._row_to_version(r) for r in cursor.fetchall()]

    def set_version_status(self, version_num: int, status: ConfigVersionStatus, activated_at: Optional[float] = None) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if activated_at is not None:
                cursor.execute("UPDATE config_versions SET status = ?, activated_at = ? WHERE version = ?", (status.value, activated_at, version_num))
            else:
                cursor.execute("UPDATE config_versions SET status = ? WHERE version = ?", (status.value, version_num))
            conn.commit()
            return True

    def _row_to_version(self, r: sqlite3.Row) -> ConfigVersion:
        return ConfigVersion(
            version=r["version"],
            parent_version=r["parent_version"],
            scope=ConfigScope(r["scope"]),
            target_entity=r["target_entity"],
            content_hash=r["content_hash"],
            values=json.loads(r["values_json"]),
            author=r["author"],
            justification=r["justification"],
            approval_token=r["approval_token"],
            status=ConfigVersionStatus(r["status"]),
            created_at=r["created_at"],
            activated_at=r["activated_at"]
        )

    # --- Values ---
    def save_value(self, val: ConfigValue) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO config_values (
                    key, scope, entity_id, value_json, version, is_secret_ref, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                val.key,
                val.scope.value,
                val.entity_id,
                json.dumps(val.value),
                val.version,
                1 if val.is_secret_ref else 0,
                val.updated_at
            ))
            conn.commit()
            return True

    def get_value(self, key: str, scope: ConfigScope, entity_id: str) -> Optional[ConfigValue]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM config_values WHERE key = ? AND scope = ? AND entity_id = ?",
                (key, scope.value, entity_id)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return ConfigValue(
                key=row["key"],
                scope=ConfigScope(row["scope"]),
                entity_id=row["entity_id"],
                value=json.loads(row["value_json"]),
                version=row["version"],
                is_secret_ref=bool(row["is_secret_ref"]),
                updated_at=row["updated_at"]
            )

    def get_all_active_values(self) -> List[ConfigValue]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config_values")
            return [
                ConfigValue(
                    key=row["key"],
                    scope=ConfigScope(row["scope"]),
                    entity_id=row["entity_id"],
                    value=json.loads(row["value_json"]),
                    version=row["version"],
                    is_secret_ref=bool(row["is_secret_ref"]),
                    updated_at=row["updated_at"]
                )
                for row in cursor.fetchall()
            ]

    # --- Rollouts ---
    def save_rollout(self, r: ConfigRollout) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO config_rollouts (
                    rollout_id, version, strategy, status, batch_size,
                    failure_threshold_pct, target_nodes_json, completed_nodes_json,
                    failed_nodes_json, current_batch, created_at, updated_at, failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r.rollout_id,
                r.version,
                r.strategy.value,
                r.status.value,
                r.batch_size,
                r.failure_threshold_pct,
                json.dumps(r.target_nodes),
                json.dumps(r.completed_nodes),
                json.dumps(r.failed_nodes),
                r.current_batch,
                r.created_at,
                r.updated_at,
                r.failure_reason
            ))
            conn.commit()
            return True

    def get_rollout(self, rollout_id: str) -> Optional[ConfigRollout]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config_rollouts WHERE rollout_id = ?", (rollout_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_rollout(row)

    def get_active_rollout(self) -> Optional[ConfigRollout]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM config_rollouts WHERE status IN ('PENDING', 'IN_PROGRESS', 'PAUSED') ORDER BY created_at DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_rollout(row)

    def _row_to_rollout(self, r: sqlite3.Row) -> ConfigRollout:
        return ConfigRollout(
            rollout_id=r["rollout_id"],
            version=r["version"],
            strategy=RolloutStrategy(r["strategy"]),
            status=RolloutStatus(r["status"]),
            batch_size=r["batch_size"],
            failure_threshold_pct=r["failure_threshold_pct"],
            target_nodes=json.loads(r["target_nodes_json"]),
            completed_nodes=json.loads(r["completed_nodes_json"]),
            failed_nodes=json.loads(r["failed_nodes_json"]),
            current_batch=r["current_batch"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            failure_reason=r["failure_reason"]
        )

    # --- Drift Records ---
    def record_drift(self, drift: DriftRecord) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO config_drift_records (
                    drift_id, node_id, detected_at, key, expected_version,
                    expected_value_json, actual_value_json, drift_type,
                    status, resolved_at, resolution_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                drift.drift_id,
                drift.node_id,
                drift.detected_at,
                drift.key,
                drift.expected_version,
                json.dumps(drift.expected_value),
                json.dumps(drift.actual_value),
                drift.drift_type.value,
                drift.status,
                drift.resolved_at,
                drift.resolution_notes
            ))
            conn.commit()
            return True

    def list_active_drifts(self, node_id: Optional[str] = None) -> List[DriftRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if node_id:
                cursor.execute("SELECT * FROM config_drift_records WHERE status = 'DETECTED' AND node_id = ? ORDER BY detected_at DESC", (node_id,))
            else:
                cursor.execute("SELECT * FROM config_drift_records WHERE status = 'DETECTED' ORDER BY detected_at DESC")
            return [
                DriftRecord(
                    drift_id=r["drift_id"],
                    node_id=r["node_id"],
                    detected_at=r["detected_at"],
                    key=r["key"],
                    expected_version=r["expected_version"],
                    expected_value=json.loads(r["expected_value_json"]),
                    actual_value=json.loads(r["actual_value_json"]),
                    drift_type=DriftType(r["drift_type"]),
                    status=r["status"],
                    resolved_at=r["resolved_at"],
                    resolution_notes=r["resolution_notes"]
                )
                for r in cursor.fetchall()
            ]

    def resolve_drift(self, drift_id: str, notes: str = "Reconciled") -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE config_drift_records SET status = 'RESOLVED', resolved_at = ?, resolution_notes = ? WHERE drift_id = ?",
                (time.time(), notes, drift_id)
            )
            conn.commit()
            return True
