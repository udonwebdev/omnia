"""
OMNIA Module 37: SQLite Persistence Repository for Release Engineering
Stores releases, artifacts, environments, deployments, qualifications, and rollbacks.
"""

import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from release.models import (
    ReleaseRecord,
    ArtifactRecord,
    EnvironmentRecord,
    DeploymentRecord,
    RollbackRecord,
    ReleaseState,
    DeploymentStrategy,
    EnvironmentType,
    MigrationSafetyClass,
)

logger = logging.getLogger("Omnia.Release.Persistence")


class ReleaseRepository:
    """Manages persistent SQLite operations for releases, artifacts, and deployments."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Ensures Schema Version 19 tables are created."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS releases (
                release_id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                version TEXT NOT NULL,
                source_revision TEXT NOT NULL,
                state TEXT NOT NULL,
                artifact_id TEXT,
                target_environment TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                description TEXT NOT NULL,
                migration_safety TEXT NOT NULL,
                approval_request_id TEXT,
                approval_token TEXT,
                qualification_results TEXT NOT NULL,
                state_history TEXT NOT NULL,
                active_deployment_id TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS release_artifacts (
                artifact_id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                version TEXT NOT NULL,
                source_revision TEXT NOT NULL,
                build_id TEXT NOT NULL,
                digest_sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                format_type TEXT NOT NULL,
                storage_uri TEXT NOT NULL,
                builder_identity TEXT NOT NULL,
                toolchain_metadata TEXT NOT NULL,
                dependency_manifest TEXT NOT NULL,
                sbom_digest TEXT,
                vulnerabilities_summary TEXT NOT NULL,
                created_at REAL NOT NULL,
                is_tamper_verified INTEGER NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS release_environments (
                environment_id TEXT PRIMARY KEY,
                environment_type TEXT NOT NULL,
                app_id TEXT NOT NULL,
                provider_type TEXT NOT NULL,
                current_release_id TEXT,
                current_artifact_digest TEXT,
                desired_release_id TEXT,
                configuration_revision TEXT NOT NULL,
                health_status TEXT NOT NULL,
                requires_approval INTEGER NOT NULL,
                in_maintenance INTEGER NOT NULL,
                last_verified_at REAL,
                target_endpoint TEXT NOT NULL,
                cluster_lease_node TEXT,
                lease_expires_at REAL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS deployments (
                deployment_id TEXT PRIMARY KEY,
                release_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                environment_id TEXT NOT NULL,
                strategy TEXT NOT NULL,
                status TEXT NOT NULL,
                current_traffic_pct REAL NOT NULL,
                current_stage_index INTEGER NOT NULL,
                stages TEXT NOT NULL,
                verification_evidence TEXT,
                error_message TEXT,
                created_at REAL NOT NULL,
                completed_at REAL,
                executed_by TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS rollback_records (
                rollback_id TEXT PRIMARY KEY,
                failed_release_id TEXT NOT NULL,
                restored_release_id TEXT NOT NULL,
                environment_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                migration_safety TEXT NOT NULL,
                status TEXT NOT NULL,
                approval_token TEXT,
                verification_evidence TEXT,
                created_at REAL NOT NULL,
                completed_at REAL,
                error_message TEXT
            );
            """)
            conn.commit()

    # --- Releases ---
    def save_release(self, rel: ReleaseRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO releases (
                release_id, app_id, version, source_revision, state, artifact_id,
                target_environment, created_by, created_at, updated_at, description,
                migration_safety, approval_request_id, approval_token,
                qualification_results, state_history, active_deployment_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rel.release_id,
                rel.app_id,
                rel.version,
                rel.source_revision,
                rel.state.value if isinstance(rel.state, ReleaseState) else str(rel.state),
                rel.artifact_id,
                rel.target_environment,
                rel.created_by,
                rel.created_at,
                rel.updated_at,
                rel.description,
                rel.migration_safety.value if isinstance(rel.migration_safety, MigrationSafetyClass) else str(rel.migration_safety),
                rel.approval_request_id,
                rel.approval_token,
                json.dumps(rel.qualification_results),
                json.dumps(rel.state_history),
                rel.active_deployment_id,
            ))
            conn.commit()

    def get_release(self, release_id: str) -> Optional[ReleaseRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM releases WHERE release_id = ?", (release_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ReleaseRecord(
                release_id=row["release_id"],
                app_id=row["app_id"],
                version=row["version"],
                source_revision=row["source_revision"],
                state=ReleaseState(row["state"]),
                artifact_id=row["artifact_id"],
                target_environment=row["target_environment"],
                created_by=row["created_by"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                description=row["description"],
                migration_safety=MigrationSafetyClass(row["migration_safety"]),
                approval_request_id=row["approval_request_id"],
                approval_token=row["approval_token"],
                qualification_results=json.loads(row["qualification_results"]),
                state_history=json.loads(row["state_history"]),
                active_deployment_id=row["active_deployment_id"],
            )

    def list_releases(self, app_id: Optional[str] = None, state: Optional[str] = None, limit: int = 50) -> List[ReleaseRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM releases WHERE 1=1"
            params = []
            if app_id:
                query += " AND app_id = ?"
                params.append(app_id)
            if state:
                query += " AND state = ?"
                params.append(state)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [
                ReleaseRecord(
                    release_id=r["release_id"],
                    app_id=r["app_id"],
                    version=r["version"],
                    source_revision=r["source_revision"],
                    state=ReleaseState(r["state"]),
                    artifact_id=r["artifact_id"],
                    target_environment=r["target_environment"],
                    created_by=r["created_by"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    description=r["description"],
                    migration_safety=MigrationSafetyClass(r["migration_safety"]),
                    approval_request_id=r["approval_request_id"],
                    approval_token=r["approval_token"],
                    qualification_results=json.loads(r["qualification_results"]),
                    state_history=json.loads(r["state_history"]),
                    active_deployment_id=r["active_deployment_id"],
                ) for r in rows
            ]

    # --- Artifacts ---
    def save_artifact(self, art: ArtifactRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO release_artifacts (
                artifact_id, app_id, version, source_revision, build_id,
                digest_sha256, size_bytes, format_type, storage_uri,
                builder_identity, toolchain_metadata, dependency_manifest,
                sbom_digest, vulnerabilities_summary, created_at, is_tamper_verified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                art.artifact_id,
                art.app_id,
                art.version,
                art.source_revision,
                art.build_id,
                art.digest_sha256,
                art.size_bytes,
                art.format_type,
                art.storage_uri,
                art.builder_identity,
                json.dumps(art.toolchain_metadata),
                json.dumps(art.dependency_manifest),
                art.sbom_digest,
                json.dumps(art.vulnerabilities_summary),
                art.created_at,
                1 if art.is_tamper_verified else 0,
            ))
            conn.commit()

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM release_artifacts WHERE artifact_id = ?", (artifact_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ArtifactRecord(
                artifact_id=row["artifact_id"],
                app_id=row["app_id"],
                version=row["version"],
                source_revision=row["source_revision"],
                build_id=row["build_id"],
                digest_sha256=row["digest_sha256"],
                size_bytes=row["size_bytes"],
                format_type=row["format_type"],
                storage_uri=row["storage_uri"],
                builder_identity=row["builder_identity"],
                toolchain_metadata=json.loads(row["toolchain_metadata"]),
                dependency_manifest=json.loads(row["dependency_manifest"]),
                sbom_digest=row["sbom_digest"],
                vulnerabilities_summary=json.loads(row["vulnerabilities_summary"]),
                created_at=row["created_at"],
                is_tamper_verified=bool(row["is_tamper_verified"]),
            )

    # --- Environments ---
    def save_environment(self, env: EnvironmentRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO release_environments (
                environment_id, environment_type, app_id, provider_type,
                current_release_id, current_artifact_digest, desired_release_id,
                configuration_revision, health_status, requires_approval,
                in_maintenance, last_verified_at, target_endpoint,
                cluster_lease_node, lease_expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                env.environment_id,
                env.environment_type.value if isinstance(env.environment_type, EnvironmentType) else str(env.environment_type),
                env.app_id,
                env.provider_type,
                env.current_release_id,
                env.current_artifact_digest,
                env.desired_release_id,
                env.configuration_revision,
                env.health_status,
                1 if env.requires_approval else 0,
                1 if env.in_maintenance else 0,
                env.last_verified_at,
                env.target_endpoint,
                env.cluster_lease_node,
                env.lease_expires_at,
            ))
            conn.commit()

    def get_environment(self, environment_id: str) -> Optional[EnvironmentRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM release_environments WHERE environment_id = ?", (environment_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return EnvironmentRecord(
                environment_id=row["environment_id"],
                environment_type=EnvironmentType(row["environment_type"]),
                app_id=row["app_id"],
                provider_type=row["provider_type"],
                current_release_id=row["current_release_id"],
                current_artifact_digest=row["current_artifact_digest"],
                desired_release_id=row["desired_release_id"],
                configuration_revision=row["configuration_revision"],
                health_status=row["health_status"],
                requires_approval=bool(row["requires_approval"]),
                in_maintenance=bool(row["in_maintenance"]),
                last_verified_at=row["last_verified_at"],
                target_endpoint=row["target_endpoint"],
                cluster_lease_node=row["cluster_lease_node"],
                lease_expires_at=row["lease_expires_at"],
            )

    def list_environments(self, app_id: Optional[str] = None) -> List[EnvironmentRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if app_id:
                cursor.execute("SELECT * FROM release_environments WHERE app_id = ?", (app_id,))
            else:
                cursor.execute("SELECT * FROM release_environments")
            rows = cursor.fetchall()
            return [
                EnvironmentRecord(
                    environment_id=r["environment_id"],
                    environment_type=EnvironmentType(r["environment_type"]),
                    app_id=r["app_id"],
                    provider_type=r["provider_type"],
                    current_release_id=r["current_release_id"],
                    current_artifact_digest=r["current_artifact_digest"],
                    desired_release_id=r["desired_release_id"],
                    configuration_revision=r["configuration_revision"],
                    health_status=r["health_status"],
                    requires_approval=bool(r["requires_approval"]),
                    in_maintenance=bool(r["in_maintenance"]),
                    last_verified_at=r["last_verified_at"],
                    target_endpoint=r["target_endpoint"],
                    cluster_lease_node=r["cluster_lease_node"],
                    lease_expires_at=r["lease_expires_at"],
                ) for r in rows
            ]

    # --- Deployments ---
    def save_deployment(self, dep: DeploymentRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO deployments (
                deployment_id, release_id, artifact_id, environment_id,
                strategy, status, current_traffic_pct, current_stage_index,
                stages, verification_evidence, error_message, created_at,
                completed_at, executed_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                dep.deployment_id,
                dep.release_id,
                dep.artifact_id,
                dep.environment_id,
                dep.strategy.value if isinstance(dep.strategy, DeploymentStrategy) else str(dep.strategy),
                dep.status,
                dep.current_traffic_pct,
                dep.current_stage_index,
                json.dumps(dep.stages),
                dep.verification_evidence,
                dep.error_message,
                dep.created_at,
                dep.completed_at,
                dep.executed_by,
            ))
            conn.commit()

    def get_deployment(self, deployment_id: str) -> Optional[DeploymentRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM deployments WHERE deployment_id = ?", (deployment_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return DeploymentRecord(
                deployment_id=row["deployment_id"],
                release_id=row["release_id"],
                artifact_id=row["artifact_id"],
                environment_id=row["environment_id"],
                strategy=DeploymentStrategy(row["strategy"]),
                status=row["status"],
                current_traffic_pct=row["current_traffic_pct"],
                current_stage_index=row["current_stage_index"],
                stages=json.loads(row["stages"]),
                verification_evidence=row["verification_evidence"],
                error_message=row["error_message"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
                executed_by=row["executed_by"],
            )

    # --- Rollback Records ---
    def save_rollback(self, rb: RollbackRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO rollback_records (
                rollback_id, failed_release_id, restored_release_id, environment_id,
                reason, migration_safety, status, approval_token, verification_evidence,
                created_at, completed_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rb.rollback_id,
                rb.failed_release_id,
                rb.restored_release_id,
                rb.environment_id,
                rb.reason,
                rb.migration_safety.value if isinstance(rb.migration_safety, MigrationSafetyClass) else str(rb.migration_safety),
                rb.status,
                rb.approval_token,
                rb.verification_evidence,
                rb.created_at,
                rb.completed_at,
                rb.error_message,
            ))
            conn.commit()

    def get_rollback(self, rollback_id: str) -> Optional[RollbackRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rollback_records WHERE rollback_id = ?", (rollback_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return RollbackRecord(
                rollback_id=row["rollback_id"],
                failed_release_id=row["failed_release_id"],
                restored_release_id=row["restored_release_id"],
                environment_id=row["environment_id"],
                reason=row["reason"],
                migration_safety=MigrationSafetyClass(row["migration_safety"]),
                status=row["status"],
                approval_token=row["approval_token"],
                verification_evidence=row["verification_evidence"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
                error_message=row["error_message"],
            )
