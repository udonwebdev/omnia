"""
Omnia Module 43: Autonomous Infrastructure Provisioning, Deployment & Environment Lifecycle Management.
Database Persistence Layer (Schema Version 28).
"""

from __future__ import annotations

import json
import sqlite3
import logging
from typing import Any, Dict, List, Optional

from infrastructure_lifecycle.models import (
    DecommissionPlanRecord,
    DeploymentRecord,
    DeploymentState,
    DeploymentStrategy,
    DeploymentVerificationRecord,
    DriftType,
    EnvironmentLifecycleState,
    EnvironmentRecord,
    EnvironmentResourceRecord,
    EnvironmentType,
    InfrastructureBlueprint,
    InfrastructureDriftRecord,
    InfrastructureProviderRecord,
    ProviderCapability,
    ProviderType,
    ProvisioningExecutionRecord,
    ProvisioningPlanRecord,
    ReleaseRecord,
    RollbackRecord,
)

logger = logging.getLogger("Omnia.Infrastructure.Persistence")


class InfrastructureRepository:
    """Manages persistent SQLite operations for Module 43 across 12 dedicated tables."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # 1. Providers
    # -------------------------------------------------------------
    def save_provider(self, p: InfrastructureProviderRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_providers (
                    provider_id, name, provider_type, supported_capabilities_json,
                    auth_secret_ref, is_active, metadata_json, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_id) DO UPDATE SET
                    name=excluded.name,
                    supported_capabilities_json=excluded.supported_capabilities_json,
                    auth_secret_ref=excluded.auth_secret_ref,
                    is_active=excluded.is_active,
                    metadata_json=excluded.metadata_json
                """,
                (
                    p.provider_id,
                    p.name,
                    p.provider_type.value,
                    json.dumps([c.value for c in p.supported_capabilities]),
                    p.auth_secret_ref,
                    1 if p.is_active else 0,
                    json.dumps(p.metadata),
                    p.registered_at,
                ),
            )
            conn.commit()

    def get_provider(self, provider_id: str) -> Optional[InfrastructureProviderRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM infra_providers WHERE provider_id = ?", (provider_id,)).fetchone()
            if not row:
                return None
            return InfrastructureProviderRecord(
                provider_id=row["provider_id"],
                name=row["name"],
                provider_type=ProviderType(row["provider_type"]),
                supported_capabilities=[ProviderCapability(c) for c in json.loads(row["supported_capabilities_json"] or "[]")],
                auth_secret_ref=row["auth_secret_ref"],
                is_active=bool(row["is_active"]),
                metadata=json.loads(row["metadata_json"] or "{}"),
                registered_at=row["registered_at"],
            )

    def list_providers(self, active_only: bool = True) -> List[InfrastructureProviderRecord]:
        with self._get_connection() as conn:
            q = "SELECT * FROM infra_providers"
            if active_only:
                q += " WHERE is_active = 1"
            rows = conn.execute(q).fetchall()
            return [
                InfrastructureProviderRecord(
                    provider_id=r["provider_id"],
                    name=r["name"],
                    provider_type=ProviderType(r["provider_type"]),
                    supported_capabilities=[ProviderCapability(c) for c in json.loads(r["supported_capabilities_json"] or "[]")],
                    auth_secret_ref=r["auth_secret_ref"],
                    is_active=bool(r["is_active"]),
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    registered_at=r["registered_at"],
                )
                for r in rows
            ]

    # -------------------------------------------------------------
    # 2. Blueprints
    # -------------------------------------------------------------
    def save_blueprint(self, b: InfrastructureBlueprint) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_blueprints (
                    blueprint_id, name, version, environment_type,
                    resource_definitions_json, dependencies_json, network_spec_json,
                    storage_spec_json, compute_spec_json, required_secrets_json,
                    lifecycle_ttl_hours, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(blueprint_id) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    environment_type=excluded.environment_type,
                    resource_definitions_json=excluded.resource_definitions_json,
                    dependencies_json=excluded.dependencies_json,
                    network_spec_json=excluded.network_spec_json,
                    storage_spec_json=excluded.storage_spec_json,
                    compute_spec_json=excluded.compute_spec_json,
                    required_secrets_json=excluded.required_secrets_json,
                    lifecycle_ttl_hours=excluded.lifecycle_ttl_hours
                """,
                (
                    b.blueprint_id,
                    b.name,
                    b.version,
                    b.environment_type.value,
                    json.dumps(b.resource_definitions),
                    json.dumps(b.dependencies),
                    json.dumps(b.network_spec),
                    json.dumps(b.storage_spec),
                    json.dumps(b.compute_spec),
                    json.dumps(b.required_secrets),
                    b.lifecycle_ttl_hours,
                    b.created_at,
                ),
            )
            conn.commit()

    def get_blueprint(self, blueprint_id: str) -> Optional[InfrastructureBlueprint]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM infra_blueprints WHERE blueprint_id = ?", (blueprint_id,)).fetchone()
            if not row:
                return None
            return InfrastructureBlueprint(
                blueprint_id=row["blueprint_id"],
                name=row["name"],
                version=row["version"],
                environment_type=EnvironmentType(row["environment_type"]),
                resource_definitions=json.loads(row["resource_definitions_json"] or "[]"),
                dependencies=json.loads(row["dependencies_json"] or "[]"),
                network_spec=json.loads(row["network_spec_json"] or "{}"),
                storage_spec=json.loads(row["storage_spec_json"] or "{}"),
                compute_spec=json.loads(row["compute_spec_json"] or "{}"),
                required_secrets=json.loads(row["required_secrets_json"] or "[]"),
                lifecycle_ttl_hours=row["lifecycle_ttl_hours"],
                created_at=row["created_at"],
            )

    # -------------------------------------------------------------
    # 3. Environments & Resources
    # -------------------------------------------------------------
    def save_environment(self, env: EnvironmentRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_environments (
                    environment_id, name, environment_type, provider_id, blueprint_id,
                    current_state, region, owner, active_release_version,
                    active_configuration_version, expiration_timestamp, last_verified_at,
                    is_locked, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(environment_id) DO UPDATE SET
                    name=excluded.name,
                    current_state=excluded.current_state,
                    active_release_version=excluded.active_release_version,
                    active_configuration_version=excluded.active_configuration_version,
                    last_verified_at=excluded.last_verified_at,
                    is_locked=excluded.is_locked,
                    metadata_json=excluded.metadata_json
                """,
                (
                    env.environment_id,
                    env.name,
                    env.environment_type.value,
                    env.provider_id,
                    env.blueprint_id,
                    env.current_state.value,
                    env.region,
                    env.owner,
                    env.active_release_version,
                    env.active_configuration_version,
                    env.expiration_timestamp,
                    env.last_verified_at,
                    1 if env.is_locked else 0,
                    json.dumps(env.metadata),
                    env.created_at,
                ),
            )
            conn.commit()

    def get_environment(self, environment_id: str) -> Optional[EnvironmentRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM infra_environments WHERE environment_id = ?", (environment_id,)).fetchone()
            if not row:
                return None
            return EnvironmentRecord(
                environment_id=row["environment_id"],
                name=row["name"],
                environment_type=EnvironmentType(row["environment_type"]),
                provider_id=row["provider_id"],
                blueprint_id=row["blueprint_id"],
                current_state=EnvironmentLifecycleState(row["current_state"]),
                region=row["region"],
                owner=row["owner"],
                active_release_version=row["active_release_version"],
                active_configuration_version=row["active_configuration_version"],
                expiration_timestamp=row["expiration_timestamp"],
                last_verified_at=row["last_verified_at"],
                is_locked=bool(row["is_locked"]),
                metadata=json.loads(row["metadata_json"] or "{}"),
                created_at=row["created_at"],
            )

    def list_environments(self, active_only: bool = False) -> List[EnvironmentRecord]:
        with self._get_connection() as conn:
            q = "SELECT * FROM infra_environments"
            if active_only:
                q += f" WHERE current_state != '{EnvironmentLifecycleState.DECOMMISSIONED.value}'"
            rows = conn.execute(q).fetchall()
            return [
                EnvironmentRecord(
                    environment_id=r["environment_id"],
                    name=r["name"],
                    environment_type=EnvironmentType(r["environment_type"]),
                    provider_id=r["provider_id"],
                    blueprint_id=r["blueprint_id"],
                    current_state=EnvironmentLifecycleState(r["current_state"]),
                    region=r["region"],
                    owner=r["owner"],
                    active_release_version=r["active_release_version"],
                    active_configuration_version=r["active_configuration_version"],
                    expiration_timestamp=r["expiration_timestamp"],
                    last_verified_at=r["last_verified_at"],
                    is_locked=bool(r["is_locked"]),
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def save_environment_resource(self, res: EnvironmentResourceRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_environment_resources (
                    resource_id, environment_id, resource_name, resource_type,
                    status, provider_resource_ref, capacity_allocated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                    status=excluded.status,
                    provider_resource_ref=excluded.provider_resource_ref,
                    capacity_allocated=excluded.capacity_allocated
                """,
                (
                    res.resource_id,
                    res.environment_id,
                    res.resource_name,
                    res.resource_type,
                    res.status,
                    res.provider_resource_ref,
                    res.capacity_allocated,
                    res.created_at,
                ),
            )
            conn.commit()

    def list_environment_resources(self, environment_id: str) -> List[EnvironmentResourceRecord]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM infra_environment_resources WHERE environment_id = ?",
                (environment_id,),
            ).fetchall()
            return [
                EnvironmentResourceRecord(
                    resource_id=r["resource_id"],
                    environment_id=r["environment_id"],
                    resource_name=r["resource_name"],
                    resource_type=r["resource_type"],
                    status=r["status"],
                    provider_resource_ref=r["provider_resource_ref"],
                    capacity_allocated=r["capacity_allocated"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    # -------------------------------------------------------------
    # 4. Provisioning Plans & Executions
    # -------------------------------------------------------------
    def save_provisioning_plan(self, plan: ProvisioningPlanRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_provisioning_plans (
                    plan_id, environment_id, blueprint_id, actions_json,
                    dependency_order_json, capacity_verified, estimated_cost_usd,
                    requires_approval, approval_token, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plan_id) DO UPDATE SET
                    actions_json=excluded.actions_json,
                    capacity_verified=excluded.capacity_verified,
                    approval_token=excluded.approval_token,
                    status=excluded.status
                """,
                (
                    plan.plan_id,
                    plan.environment_id,
                    plan.blueprint_id,
                    json.dumps(plan.actions),
                    json.dumps(plan.dependency_order),
                    1 if plan.capacity_verified else 0,
                    plan.estimated_cost_usd,
                    1 if plan.requires_approval else 0,
                    plan.approval_token,
                    plan.status,
                    plan.created_at,
                ),
            )
            conn.commit()

    def get_provisioning_plan(self, plan_id: str) -> Optional[ProvisioningPlanRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM infra_provisioning_plans WHERE plan_id = ?", (plan_id,)).fetchone()
            if not row:
                return None
            return ProvisioningPlanRecord(
                plan_id=row["plan_id"],
                environment_id=row["environment_id"],
                blueprint_id=row["blueprint_id"],
                actions=json.loads(row["actions_json"] or "[]"),
                dependency_order=json.loads(row["dependency_order_json"] or "[]"),
                capacity_verified=bool(row["capacity_verified"]),
                estimated_cost_usd=row["estimated_cost_usd"],
                requires_approval=bool(row["requires_approval"]),
                approval_token=row["approval_token"],
                status=row["status"],
                created_at=row["created_at"],
            )

    def save_provisioning_execution(self, ex: ProvisioningExecutionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_provisioning_executions (
                    execution_id, plan_id, environment_id, status,
                    executed_actions_json, errors_json, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ex.execution_id,
                    ex.plan_id,
                    ex.environment_id,
                    ex.status,
                    json.dumps(ex.executed_actions),
                    json.dumps(ex.errors),
                    ex.executed_at,
                ),
            )
            conn.commit()

    # -------------------------------------------------------------
    # 5. Releases & Deployments
    # -------------------------------------------------------------
    def save_release(self, rel: ReleaseRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_releases (
                    release_id, application_name, version, artifact_uri,
                    checksum_sha256, source_revision, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id) DO UPDATE SET
                    artifact_uri=excluded.artifact_uri,
                    checksum_sha256=excluded.checksum_sha256
                """,
                (
                    rel.release_id,
                    rel.application_name,
                    rel.version,
                    rel.artifact_uri,
                    rel.checksum_sha256,
                    rel.source_revision,
                    rel.created_at,
                ),
            )
            conn.commit()

    def get_release(self, release_id: str) -> Optional[ReleaseRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM infra_releases WHERE release_id = ?", (release_id,)).fetchone()
            if not row:
                return None
            return ReleaseRecord(
                release_id=row["release_id"],
                application_name=row["application_name"],
                version=row["version"],
                artifact_uri=row["artifact_uri"],
                checksum_sha256=row["checksum_sha256"],
                source_revision=row["source_revision"],
                created_at=row["created_at"],
            )

    def save_deployment(self, d: DeploymentRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_deployments (
                    deployment_id, environment_id, release_id, strategy,
                    status, previous_release_id, approval_token, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deployment_id) DO UPDATE SET
                    status=excluded.status,
                    completed_at=excluded.completed_at
                """,
                (
                    d.deployment_id,
                    d.environment_id,
                    d.release_id,
                    d.strategy.value,
                    d.status.value,
                    d.previous_release_id,
                    d.approval_token,
                    d.started_at,
                    d.completed_at,
                ),
            )
            conn.commit()

    def get_deployment(self, deployment_id: str) -> Optional[DeploymentRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM infra_deployments WHERE deployment_id = ?", (deployment_id,)).fetchone()
            if not row:
                return None
            return DeploymentRecord(
                deployment_id=row["deployment_id"],
                environment_id=row["environment_id"],
                release_id=row["release_id"],
                strategy=DeploymentStrategy(row["strategy"]),
                status=DeploymentState(row["status"]),
                previous_release_id=row["previous_release_id"],
                approval_token=row["approval_token"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
            )

    # -------------------------------------------------------------
    # 6. Verifications & Rollbacks
    # -------------------------------------------------------------
    def save_verification(self, v: DeploymentVerificationRecord) -> None:
        return self.save_deployment_verification(v)

    def save_deployment_verification(self, v: DeploymentVerificationRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_verifications (
                    verification_id, deployment_id, environment_id,
                    infrastructure_ready, application_ready, operational_ready,
                    is_fully_verified, check_results_json, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    v.verification_id,
                    v.deployment_id,
                    v.environment_id,
                    1 if v.infrastructure_ready else 0,
                    1 if v.application_ready else 0,
                    1 if v.operational_ready else 0,
                    1 if v.is_fully_verified else 0,
                    json.dumps(v.check_results),
                    v.verified_at,
                ),
            )
            conn.commit()

    def save_rollback(self, rb: RollbackRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_rollbacks (
                    rollback_id, deployment_id, target_environment_id,
                    from_release_id, to_release_id, approval_token, status, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rb.rollback_id,
                    rb.deployment_id,
                    rb.target_environment_id,
                    rb.from_release_id,
                    rb.to_release_id,
                    rb.approval_token,
                    rb.status,
                    rb.executed_at,
                ),
            )
            conn.commit()

    # -------------------------------------------------------------
    # 7. Drift & Decommissioning
    # -------------------------------------------------------------
    def save_drift(self, drift: InfrastructureDriftRecord) -> None:
        return self.save_drift_record(drift)

    def save_drift_record(self, drift: InfrastructureDriftRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_drift_findings (
                    drift_id, environment_id, drift_type, resource_id,
                    expected_state, actual_state, remediation_suggestion,
                    is_reconciled, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(drift_id) DO UPDATE SET
                    is_reconciled=excluded.is_reconciled
                """,
                (
                    drift.drift_id,
                    drift.environment_id,
                    drift.drift_type.value,
                    drift.resource_id,
                    drift.expected_state,
                    drift.actual_state,
                    drift.remediation_suggestion,
                    1 if drift.is_reconciled else 0,
                    drift.detected_at,
                ),
            )
            conn.commit()

    def list_unreconciled_drift(self, environment_id: Optional[str] = None) -> List[InfrastructureDriftRecord]:
        return self.list_drift_records(reconciled=False, environment_id=environment_id)

    def list_drift_records(
        self,
        reconciled: Optional[bool] = None,
        environment_id: Optional[str] = None,
    ) -> List[InfrastructureDriftRecord]:
        with self._get_connection() as conn:
            q = "SELECT * FROM infra_drift_findings WHERE is_reconciled = 0"
            params = []
            if environment_id:
                q += " AND environment_id = ?"
                params.append(environment_id)
            rows = conn.execute(q, params).fetchall()
            return [
                InfrastructureDriftRecord(
                    drift_id=r["drift_id"],
                    environment_id=r["environment_id"],
                    drift_type=DriftType(r["drift_type"]),
                    resource_id=r["resource_id"],
                    expected_state=r["expected_state"],
                    actual_state=r["actual_state"],
                    remediation_suggestion=r["remediation_suggestion"],
                    is_reconciled=bool(r["is_reconciled"]),
                    detected_at=r["detected_at"],
                )
                for r in rows
            ]

    def save_decommission_plan(self, plan: DecommissionPlanRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO infra_decommission_plans (
                    decommission_id, environment_id, resources_to_delete_json,
                    data_retention_preserved, approval_token, status, executed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decommission_id) DO UPDATE SET
                    approval_token=excluded.approval_token,
                    status=excluded.status,
                    executed_at=excluded.executed_at
                """,
                (
                    plan.decommission_id,
                    plan.environment_id,
                    json.dumps(plan.resources_to_delete),
                    1 if plan.data_retention_preserved else 0,
                    plan.approval_token,
                    plan.status,
                    plan.executed_at,
                    plan.created_at,
                ),
            )
            conn.commit()

    def get_decommission_plan(self, decommission_id: str) -> Optional[DecommissionPlanRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM infra_decommission_plans WHERE decommission_id = ?", (decommission_id,)).fetchone()
            if not row:
                return None
            return DecommissionPlanRecord(
                decommission_id=row["decommission_id"],
                environment_id=row["environment_id"],
                resources_to_delete=json.loads(row["resources_to_delete_json"] or "[]"),
                data_retention_preserved=bool(row["data_retention_preserved"]),
                approval_token=row["approval_token"],
                status=row["status"],
                executed_at=row["executed_at"],
                created_at=row["created_at"],
            )
