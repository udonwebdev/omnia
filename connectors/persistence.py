"""
Persistence Repository for Omnia Module 26:
External Integration & Connector Gateway

Backed by SQLite (Schema Migration Version 8).
"""

import sqlite3
import json
import logging
from typing import Optional, List, Dict, Any

from connectors.models import (
    ConnectorDefinition, ConnectorInstance, ConnectorOperation,
    IdempotencyRecord, WebhookEndpoint, WebhookEvent,
    ConnectorLifecycle, ConnectorHealth, OperationType,
    RateLimitPolicy, RetryPolicy, TimeoutPolicy, CredentialBinding,
    IdempotencyStatus
)

logger = logging.getLogger("Omnia.Connectors.Persistence")


class ConnectorPersistence:
    """SQLite repository for connector definitions, instances, and idempotency."""

    def __init__(self, db_path: str = "persistence/omnia_tasks.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Connector Definitions ---
    def save_connector_definition(self, definition: ConnectorDefinition):
        ops_dict = {}
        for op_id, op in definition.operations.items():
            ops_dict[op_id] = {
                "operation_id": op.operation_id,
                "name": op.name,
                "operation_type": op.operation_type.value,
                "path": op.path,
                "method": op.method,
                "description": op.description,
                "input_schema": op.input_schema,
                "output_schema": op.output_schema,
                "risk_level": op.risk_level,
                "idempotent": op.idempotent,
                "requires_approval": op.requires_approval
            }

        auth_dict = {}
        if definition.default_auth:
            auth_dict = {
                "auth_type": definition.default_auth.auth_type,
                "secret_reference": definition.default_auth.secret_reference,
                "header_name": definition.default_auth.header_name,
                "token_prefix": definition.default_auth.token_prefix
            }

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO connector_definitions (
                    connector_id, provider_id, name, version, description,
                    supported_protocols, risk_profile, schema_version,
                    operations_json, auth_requirements_json,
                    rate_limit_policy_json, retry_policy_json, timeout_policy_json,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                definition.connector_id,
                definition.provider_id,
                definition.name,
                definition.version,
                definition.description,
                json.dumps(definition.supported_protocols),
                definition.risk_profile,
                definition.schema_version,
                json.dumps(ops_dict),
                json.dumps(auth_dict),
                json.dumps({
                    "req_per_sec": definition.rate_limit_policy.requests_per_second,
                    "burst": definition.rate_limit_policy.burst_limit,
                    "max_concurrency": definition.rate_limit_policy.max_concurrent_requests
                }),
                json.dumps({
                    "max_attempts": definition.retry_policy.max_attempts,
                    "initial_backoff_sec": definition.retry_policy.initial_backoff_sec
                }),
                json.dumps({
                    "connect_timeout_sec": definition.timeout_policy.connect_timeout_sec,
                    "read_timeout_sec": definition.timeout_policy.read_timeout_sec
                }),
                definition.status.value,
                definition.created_at,
                definition.updated_at
            ))
            conn.commit()

    def get_connector_definition(self, connector_id: str) -> Optional[ConnectorDefinition]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM connector_definitions WHERE connector_id = ?", (connector_id,)).fetchone()
            if not row:
                return None
            return self._row_to_definition(row)

    def list_connector_definitions(self) -> List[ConnectorDefinition]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM connector_definitions").fetchall()
            return [self._row_to_definition(r) for r in rows]

    def _row_to_definition(self, row: sqlite3.Row) -> ConnectorDefinition:
        ops_dict = json.loads(row["operations_json"] or "{}")
        operations = {}
        for op_id, op_data in ops_dict.items():
            operations[op_id] = ConnectorOperation(
                operation_id=op_data["operation_id"],
                name=op_data.get("name", op_id),
                operation_type=OperationType(op_data.get("operation_type", "READ")),
                path=op_data.get("path", "/"),
                method=op_data.get("method", "GET"),
                description=op_data.get("description", ""),
                input_schema=op_data.get("input_schema", {}),
                output_schema=op_data.get("output_schema", {}),
                risk_level=op_data.get("risk_level", "LOW"),
                idempotent=op_data.get("idempotent", True),
                requires_approval=op_data.get("requires_approval", False)
            )

        auth_data = json.loads(row["auth_requirements_json"] or "{}")
        default_auth = None
        if auth_data:
            default_auth = CredentialBinding(
                auth_type=auth_data.get("auth_type", "NONE"),
                secret_reference=auth_data.get("secret_reference"),
                header_name=auth_data.get("header_name", "Authorization"),
                token_prefix=auth_data.get("token_prefix", "Bearer ")
            )

        return ConnectorDefinition(
            connector_id=row["connector_id"],
            provider_id=row["provider_id"],
            name=row["name"],
            version=row["version"],
            description=row["description"],
            supported_protocols=json.loads(row["supported_protocols"] or '["HTTP"]'),
            risk_profile=row["risk_profile"],
            schema_version=row["schema_version"],
            operations=operations,
            default_auth=default_auth,
            status=ConnectorLifecycle(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

    # --- Connector Instances ---
    def save_connector_instance(self, instance: ConnectorInstance):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO connector_instances (
                    instance_id, connector_id, environment, base_url, status,
                    credential_reference, config_reference, health, health_message,
                    last_health_check, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                instance.instance_id,
                instance.connector_id,
                instance.environment.value,
                instance.base_url,
                instance.status.value,
                instance.credential_reference,
                instance.config_reference,
                instance.health.value,
                instance.health_message,
                instance.last_health_check,
                instance.created_at,
                instance.updated_at
            ))
            conn.commit()

    def get_connector_instance(self, instance_id: str) -> Optional[ConnectorInstance]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM connector_instances WHERE instance_id = ?", (instance_id,)).fetchone()
            if not row:
                return None
            from connectors.models import Environment
            return ConnectorInstance(
                instance_id=row["instance_id"],
                connector_id=row["connector_id"],
                environment=Environment(row["environment"]),
                base_url=row["base_url"],
                status=ConnectorLifecycle(row["status"]),
                credential_reference=row["credential_reference"],
                config_reference=row["config_reference"],
                health=ConnectorHealth(row["health"]),
                health_message=row["health_message"],
                last_health_check=row["last_health_check"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    # --- Idempotency ---
    def save_idempotency_record(self, record: IdempotencyRecord):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO connector_idempotency (
                    idempotency_key, operation_id, instance_id, task_id, status,
                    request_hash, response_payload, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.idempotency_key,
                record.operation_id,
                record.instance_id,
                record.task_id,
                record.status.value,
                record.request_hash,
                record.response_payload,
                record.created_at,
                record.expires_at
            ))
            conn.commit()

    def get_idempotency_record(self, idempotency_key: str) -> Optional[IdempotencyRecord]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM connector_idempotency WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if not row:
                return None
            return IdempotencyRecord(
                idempotency_key=row["idempotency_key"],
                operation_id=row["operation_id"],
                instance_id=row["instance_id"],
                task_id=row["task_id"],
                status=IdempotencyStatus(row["status"]),
                request_hash=row["request_hash"],
                response_payload=row["response_payload"],
                created_at=row["created_at"],
                expires_at=row["expires_at"]
            )

    # --- Webhooks ---
    def save_webhook_endpoint(self, endpoint: WebhookEndpoint):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO connector_webhooks (
                    webhook_id, endpoint_path, provider_id, secret_reference,
                    status, verification_algorithm, max_payload_bytes,
                    replay_window_sec, created_at, last_event_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                endpoint.webhook_id,
                endpoint.endpoint_path,
                endpoint.provider_id,
                endpoint.secret_reference,
                endpoint.status,
                endpoint.verification_algorithm,
                endpoint.max_payload_bytes,
                endpoint.replay_window_sec,
                endpoint.created_at,
                endpoint.last_event_at
            ))
            conn.commit()

    def save_webhook_event(self, event: WebhookEvent):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO connector_webhook_events (
                    event_id, webhook_id, provider_event_id, signature_verified,
                    normalized_type, received_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.webhook_id,
                event.provider_event_id or "",
                1 if event.signature_verified else 0,
                event.normalized_type,
                event.received_at
            ))
            conn.commit()

    def has_webhook_event(self, provider_event_id: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT 1 FROM connector_webhook_events WHERE provider_event_id = ?", (provider_event_id,)).fetchone()
            return row is not None
