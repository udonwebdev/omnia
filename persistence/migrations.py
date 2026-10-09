import sqlite3
import os
import shutil
import time
import logging
from typing import List, Tuple

logger = logging.getLogger("Omnia.Persistence.Migrations")

CURRENT_SCHEMA_VERSION = 11

MIGRATION_V1 = """
-- Schema Version 1: Durable Task Graph & Crash Recovery Tables

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    current_node_id TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    updated_at REAL NOT NULL,
    completed_at REAL,
    deadline_ts REAL NOT NULL,
    task_timeout_sec REAL NOT NULL,
    attempt_count INTEGER DEFAULT 1,
    replan_count INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at);

CREATE TABLE IF NOT EXISTS task_nodes (
    node_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL,
    attempt_count INTEGER DEFAULT 0,
    started_at REAL,
    completed_at REAL,
    expected_state TEXT,
    idempotency TEXT DEFAULT 'SAFE_TO_RETRY',
    required_resources_json TEXT DEFAULT '[]',
    dependencies_json TEXT DEFAULT '[]',
    last_error_category TEXT,
    last_error_message TEXT,
    last_verification_status TEXT,
    metadata_json TEXT DEFAULT '{}',
    PRIMARY KEY (task_id, node_id),
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_nodes_task_id ON task_nodes(task_id);
CREATE INDEX IF NOT EXISTS idx_task_nodes_status ON task_nodes(status);

CREATE TABLE IF NOT EXISTS task_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    node_id TEXT,
    timestamp REAL NOT NULL,
    task_state TEXT NOT NULL,
    node_states_json TEXT NOT NULL,
    variables_json TEXT NOT NULL,
    resource_state_json TEXT NOT NULL,
    last_verified_observations_json TEXT NOT NULL,
    policy_trigger TEXT NOT NULL,
    browser_state_ref TEXT,
    device_state_ref TEXT,
    vision_frame_ref TEXT,
    checksum TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_task_id ON task_checkpoints(task_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_timestamp ON task_checkpoints(timestamp);

CREATE TABLE IF NOT EXISTS task_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_events_task_seq ON task_events(task_id, sequence_number);
CREATE INDEX IF NOT EXISTS idx_events_task_id ON task_events(task_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON task_events(timestamp);

CREATE TABLE IF NOT EXISTS task_resource_locks (
    lock_id TEXT PRIMARY KEY,
    resource_id TEXT UNIQUE NOT NULL,
    task_id TEXT NOT NULL,
    acquired_at REAL NOT NULL,
    heartbeat_ts REAL NOT NULL,
    process_id INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_locks_task_id ON task_resource_locks(task_id);
CREATE INDEX IF NOT EXISTS idx_locks_heartbeat ON task_resource_locks(heartbeat_ts);

CREATE TABLE IF NOT EXISTS task_heartbeats (
    task_id TEXT PRIMARY KEY,
    heartbeat_ts REAL NOT NULL,
    current_node_id TEXT,
    process_id INTEGER NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_heartbeats_ts ON task_heartbeats(heartbeat_ts);

CREATE TABLE IF NOT EXISTS recovery_attempts (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    condition TEXT NOT NULL,
    strategy TEXT NOT NULL,
    decision_reason TEXT NOT NULL,
    success INTEGER DEFAULT 0,
    evidence_json TEXT DEFAULT '{}',
    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_recovery_task_id ON recovery_attempts(task_id);
"""

MIGRATION_V2 = """
-- Schema Version 2: Human Approval Gateway & Consent Orchestrator Tables

CREATE TABLE IF NOT EXISTS approval_requests (
    approval_id TEXT PRIMARY KEY,
    version INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    request_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    reason TEXT NOT NULL,
    mission_id TEXT,
    task_id TEXT,
    task_node_id TEXT,
    plan_version INTEGER DEFAULT 1,
    capability_id TEXT,
    provider_id TEXT,
    risk_level TEXT NOT NULL,
    policy_reference TEXT,
    requested_action TEXT NOT NULL,
    action_params_json TEXT DEFAULT '{}',
    target_resource TEXT,
    target_device TEXT,
    target_application TEXT,
    expected_effect TEXT,
    potential_side_effects TEXT,
    is_reversible INTEGER DEFAULT 0,
    expires_at REAL NOT NULL,
    scope TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    correlation_id TEXT,
    causation_id TEXT,
    metadata_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_approvals_status ON approval_requests(status);
CREATE INDEX IF NOT EXISTS idx_approvals_task_id ON approval_requests(task_id);
CREATE INDEX IF NOT EXISTS idx_approvals_mission_id ON approval_requests(mission_id);
CREATE INDEX IF NOT EXISTS idx_approvals_expires_at ON approval_requests(expires_at);

CREATE TABLE IF NOT EXISTS approval_decisions (
    decision_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    decided_at REAL NOT NULL,
    decided_by TEXT NOT NULL,
    decision_source TEXT NOT NULL,
    device_id TEXT,
    session_id TEXT,
    reason TEXT,
    approval_version INTEGER DEFAULT 1,
    metadata_json TEXT DEFAULT '{}',
    FOREIGN KEY (approval_id) REFERENCES approval_requests(approval_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_approval_decisions_approval_id ON approval_decisions(approval_id);

CREATE TABLE IF NOT EXISTS approval_releases (
    release_token TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    task_id TEXT,
    task_node_id TEXT,
    mission_id TEXT,
    authorized_action TEXT NOT NULL,
    authorization_scope TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    authorized_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    policy_reference TEXT,
    consumed INTEGER DEFAULT 0,
    consumed_at REAL,
    FOREIGN KEY (approval_id) REFERENCES approval_requests(approval_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_approval_releases_approval_id ON approval_releases(approval_id);
CREATE INDEX IF NOT EXISTS idx_approval_releases_fingerprint ON approval_releases(fingerprint);
"""

MIGRATION_V3 = """
-- Schema Version 3: Autonomous Resource Scheduler & Concurrency Orchestrator Tables

CREATE TABLE IF NOT EXISTS schedule_requests (
    schedule_id TEXT PRIMARY KEY,
    mission_id TEXT,
    task_id TEXT NOT NULL,
    task_node_id TEXT,
    created_at REAL NOT NULL,
    ready_at REAL,
    deadline REAL,
    priority TEXT NOT NULL,
    urgency TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    estimated_duration_sec REAL DEFAULT 10.0,
    preemption_policy TEXT NOT NULL,
    parallelizable INTEGER DEFAULT 1,
    required_resources_json TEXT DEFAULT '[]',
    exclusive_resources_json TEXT DEFAULT '[]',
    shared_resources_json TEXT DEFAULT '[]',
    required_capabilities_json TEXT DEFAULT '[]',
    required_devices_json TEXT DEFAULT '[]',
    dependencies_json TEXT DEFAULT '[]',
    state TEXT NOT NULL,
    assigned_slot_id TEXT,
    priority_score REAL DEFAULT 0.0,
    wait_count INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sched_state ON schedule_requests(state);
CREATE INDEX IF NOT EXISTS idx_sched_task ON schedule_requests(task_id);
CREATE INDEX IF NOT EXISTS idx_sched_prio ON schedule_requests(priority_score);

CREATE TABLE IF NOT EXISTS resource_reservations (
    reservation_id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    mission_id TEXT,
    task_id TEXT NOT NULL,
    task_node_id TEXT,
    resource_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    access_mode TEXT NOT NULL,
    amount REAL DEFAULT 1.0,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    state TEXT NOT NULL,
    lease_id TEXT,
    lease_heartbeat REAL,
    release_reason TEXT,
    FOREIGN KEY (schedule_id) REFERENCES schedule_requests(schedule_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_resv_sched ON resource_reservations(schedule_id);
CREATE INDEX IF NOT EXISTS idx_resv_resource ON resource_reservations(resource_id);
CREATE INDEX IF NOT EXISTS idx_resv_state ON resource_reservations(state);

CREATE TABLE IF NOT EXISTS execution_slots (
    slot_id TEXT PRIMARY KEY,
    slot_name TEXT NOT NULL,
    worker_type TEXT NOT NULL,
    capacity REAL DEFAULT 1.0,
    supported_capabilities_json TEXT DEFAULT '[]',
    health TEXT NOT NULL,
    current_schedule_id TEXT,
    current_task_id TEXT,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduling_decisions (
    decision_id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    priority_score REAL NOT NULL,
    selected_slot_id TEXT,
    conflicts_json TEXT DEFAULT '[]',
    created_at REAL NOT NULL,
    FOREIGN KEY (schedule_id) REFERENCES schedule_requests(schedule_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sched_dec_schedule ON scheduling_decisions(schedule_id);
"""

MIGRATION_V4 = """
-- Schema Version 4: Distributed Coordination, Leader Election & Ownership Tables

CREATE TABLE IF NOT EXISTS cluster_nodes (
    node_id TEXT PRIMARY KEY,
    node_name TEXT NOT NULL,
    node_version TEXT NOT NULL,
    public_key TEXT,
    identity_fingerprint TEXT NOT NULL,
    platform TEXT,
    architecture TEXT,
    endpoint_url TEXT,
    trust_state TEXT NOT NULL,
    membership_state TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_cluster_nodes_state ON cluster_nodes(membership_state);
CREATE INDEX IF NOT EXISTS idx_cluster_nodes_trust ON cluster_nodes(trust_state);

CREATE TABLE IF NOT EXISTS leadership_leases (
    lease_id TEXT PRIMARY KEY,
    leader_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    renewal_sequence INTEGER DEFAULT 1,
    state TEXT NOT NULL,
    fencing_token TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_leader_epoch ON leadership_leases(epoch);

CREATE TABLE IF NOT EXISTS distributed_ownership_claims (
    claim_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    owner_node_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    fencing_token TEXT NOT NULL,
    state TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_owner_subject ON distributed_ownership_claims(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_owner_node ON distributed_ownership_claims(owner_node_id);
CREATE INDEX IF NOT EXISTS idx_owner_state ON distributed_ownership_claims(state);

CREATE TABLE IF NOT EXISTS distributed_locks (
    lock_id TEXT PRIMARY KEY,
    resource_id TEXT UNIQUE NOT NULL,
    owner_node_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    fencing_token TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    state TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dist_locks_resource ON distributed_locks(resource_id);
"""

MIGRATION_V5 = """
-- Schema Version 5: Distributed State Synchronization, Replication & Reconciliation Tables

CREATE TABLE IF NOT EXISTS replication_namespaces (
    namespace_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_type TEXT NOT NULL,
    replication_policy TEXT NOT NULL,
    consistency_policy TEXT NOT NULL,
    sensitivity TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS replication_state_records (
    state_id TEXT PRIMARY KEY,
    namespace_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    owner_node TEXT NOT NULL,
    owner_epoch INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    integrity_hash TEXT NOT NULL,
    FOREIGN KEY (namespace_id) REFERENCES replication_namespaces(namespace_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_repl_state_entity ON replication_state_records(namespace_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_repl_state_rev ON replication_state_records(namespace_id, revision);
CREATE INDEX IF NOT EXISTS idx_repl_state_owner ON replication_state_records(owner_node, owner_epoch);

CREATE TABLE IF NOT EXISTS replication_deltas (
    delta_id TEXT PRIMARY KEY,
    namespace_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    source_node TEXT NOT NULL,
    source_epoch INTEGER NOT NULL,
    base_revision INTEGER NOT NULL,
    target_revision INTEGER NOT NULL,
    operation TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    causal_metadata_json TEXT DEFAULT '{}',
    integrity_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    applied_at REAL,
    FOREIGN KEY (namespace_id) REFERENCES replication_namespaces(namespace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_repl_delta_ns_rev ON replication_deltas(namespace_id, target_revision);
CREATE INDEX IF NOT EXISTS idx_repl_delta_entity ON replication_deltas(namespace_id, entity_id);

CREATE TABLE IF NOT EXISTS replication_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    namespace_id TEXT NOT NULL,
    source_node TEXT NOT NULL,
    source_epoch INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    created_at REAL NOT NULL,
    schema_version TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    records_json TEXT NOT NULL,
    FOREIGN KEY (namespace_id) REFERENCES replication_namespaces(namespace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_repl_snap_ns_rev ON replication_snapshots(namespace_id, revision);

CREATE TABLE IF NOT EXISTS replication_sync_cursors (
    peer_node TEXT NOT NULL,
    namespace_id TEXT NOT NULL,
    last_applied_revision INTEGER DEFAULT 0,
    last_acknowledged_revision INTEGER DEFAULT 0,
    last_verified_revision INTEGER DEFAULT 0,
    last_sync_time REAL NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (peer_node, namespace_id)
);

CREATE TABLE IF NOT EXISTS replication_conflicts (
    conflict_id TEXT PRIMARY KEY,
    namespace_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    local_version_json TEXT NOT NULL,
    remote_version_json TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    resolution_strategy TEXT NOT NULL,
    resolution_status TEXT NOT NULL,
    created_at REAL NOT NULL,
    resolved_at REAL,
    evidence_json TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_repl_conflicts_status ON replication_conflicts(resolution_status);
"""

MIGRATION_V6 = """
-- Schema Version 6: Distributed Configuration, Policy & Runtime Control Plane

CREATE TABLE IF NOT EXISTS config_schemas (
    key TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    data_type TEXT NOT NULL,
    default_value_json TEXT NOT NULL,
    schema_spec_json TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'CLUSTER',
    mutability TEXT NOT NULL DEFAULT 'HOT_RELOAD',
    requires_restart INTEGER NOT NULL DEFAULT 0,
    is_secret INTEGER NOT NULL DEFAULT 0,
    allowed_values_json TEXT DEFAULT '[]',
    min_value REAL,
    max_value REAL,
    unit TEXT,
    description TEXT,
    dependencies_json TEXT DEFAULT '[]',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_config_schemas_domain ON config_schemas(domain);

CREATE TABLE IF NOT EXISTS config_versions (
    version INTEGER PRIMARY KEY,
    parent_version INTEGER,
    scope TEXT NOT NULL,
    target_entity TEXT NOT NULL DEFAULT 'CLUSTER',
    content_hash TEXT NOT NULL,
    values_json TEXT NOT NULL,
    author TEXT NOT NULL,
    justification TEXT,
    approval_token TEXT,
    status TEXT NOT NULL DEFAULT 'STAGED',
    created_at REAL NOT NULL,
    activated_at REAL
);

CREATE INDEX IF NOT EXISTS idx_config_versions_status ON config_versions(status);
CREATE INDEX IF NOT EXISTS idx_config_versions_created_at ON config_versions(created_at);

CREATE TABLE IF NOT EXISTS config_values (
    key TEXT NOT NULL,
    scope TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    value_json TEXT NOT NULL,
    version INTEGER NOT NULL,
    is_secret_ref INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (key, scope, entity_id),
    FOREIGN KEY (key) REFERENCES config_schemas(key) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_config_values_scope_entity ON config_values(scope, entity_id);

CREATE TABLE IF NOT EXISTS config_rollouts (
    rollout_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    status TEXT NOT NULL,
    batch_size INTEGER NOT NULL DEFAULT 1,
    failure_threshold_pct REAL NOT NULL DEFAULT 0.0,
    target_nodes_json TEXT NOT NULL DEFAULT '[]',
    completed_nodes_json TEXT NOT NULL DEFAULT '[]',
    failed_nodes_json TEXT NOT NULL DEFAULT '[]',
    current_batch INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    failure_reason TEXT,
    FOREIGN KEY (version) REFERENCES config_versions(version)
);

CREATE INDEX IF NOT EXISTS idx_config_rollouts_version ON config_rollouts(version);
CREATE INDEX IF NOT EXISTS idx_config_rollouts_status ON config_rollouts(status);

CREATE TABLE IF NOT EXISTS config_drift_records (
    drift_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    detected_at REAL NOT NULL,
    key TEXT NOT NULL,
    expected_version INTEGER NOT NULL,
    expected_value_json TEXT NOT NULL,
    actual_value_json TEXT NOT NULL,
    drift_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DETECTED',
    resolved_at REAL,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_config_drift_node ON config_drift_records(node_id);
CREATE INDEX IF NOT EXISTS idx_config_drift_status ON config_drift_records(status);
"""

MIGRATION_V7 = """
-- Schema Version 7: Secrets, Credentials & Secure Identity Lifecycle

CREATE TABLE IF NOT EXISTS secret_metadata (
    secret_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    secret_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'CLUSTER',
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    expires_at REAL,
    last_rotated_at REAL,
    last_used_at REAL,
    rotation_policy_json TEXT NOT NULL DEFAULT '{}',
    access_policy_json TEXT NOT NULL DEFAULT '{}',
    integrity_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_secret_meta_type ON secret_metadata(secret_type);
CREATE INDEX IF NOT EXISTS idx_secret_meta_status ON secret_metadata(status);
CREATE INDEX IF NOT EXISTS idx_secret_meta_scope ON secret_metadata(scope);

CREATE TABLE IF NOT EXISTS secret_versions (
    secret_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at REAL NOT NULL,
    activated_at REAL,
    retired_at REAL,
    fingerprint TEXT NOT NULL,
    ciphertext TEXT NOT NULL,
    key_id TEXT NOT NULL,
    salt TEXT NOT NULL,
    nonce TEXT NOT NULL,
    PRIMARY KEY (secret_id, version),
    FOREIGN KEY (secret_id) REFERENCES secret_metadata(secret_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_secret_versions_status ON secret_versions(status);

CREATE TABLE IF NOT EXISTS secret_leases (
    lease_id TEXT PRIMARY KEY,
    secret_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    requester TEXT NOT NULL,
    purpose TEXT NOT NULL,
    capability TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'CLUSTER',
    node_id TEXT NOT NULL DEFAULT 'local_node',
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    revoked_at REAL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    FOREIGN KEY (secret_id) REFERENCES secret_metadata(secret_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_secret_leases_secret ON secret_leases(secret_id);
CREATE INDEX IF NOT EXISTS idx_secret_leases_status ON secret_leases(status);
CREATE INDEX IF NOT EXISTS idx_secret_leases_expires ON secret_leases(expires_at);

CREATE TABLE IF NOT EXISTS secret_audit_log (
    event_id TEXT PRIMARY KEY,
    secret_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    requester TEXT NOT NULL,
    purpose TEXT NOT NULL,
    capability TEXT NOT NULL,
    scope TEXT NOT NULL,
    node_id TEXT NOT NULL,
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    timestamp REAL NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_secret_audit_secret ON secret_audit_log(secret_id);
CREATE INDEX IF NOT EXISTS idx_secret_audit_time ON secret_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_secret_audit_action ON secret_audit_log(action);
"""

MIGRATION_V8 = """
-- Schema Version 8: External Integration & Connector Gateway Tables

CREATE TABLE IF NOT EXISTS connector_definitions (
    connector_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    description TEXT NOT NULL,
    supported_protocols TEXT NOT NULL DEFAULT '["HTTP"]',
    risk_profile TEXT NOT NULL DEFAULT 'MEDIUM',
    schema_version TEXT NOT NULL DEFAULT '1.0.0',
    operations_json TEXT NOT NULL DEFAULT '{}',
    auth_requirements_json TEXT NOT NULL DEFAULT '{}',
    rate_limit_policy_json TEXT NOT NULL DEFAULT '{}',
    retry_policy_json TEXT NOT NULL DEFAULT '{}',
    timeout_policy_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'REGISTERED',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conn_def_provider ON connector_definitions(provider_id);
CREATE INDEX IF NOT EXISTS idx_conn_def_status ON connector_definitions(status);

CREATE TABLE IF NOT EXISTS connector_instances (
    instance_id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'SANDBOX',
    base_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'INITIALIZING',
    credential_reference TEXT,
    config_reference TEXT,
    health TEXT NOT NULL DEFAULT 'UNKNOWN',
    health_message TEXT,
    last_health_check REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (connector_id) REFERENCES connector_definitions(connector_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conn_inst_conn ON connector_instances(connector_id);
CREATE INDEX IF NOT EXISTS idx_conn_inst_env ON connector_instances(environment);
CREATE INDEX IF NOT EXISTS idx_conn_inst_status ON connector_instances(status);
CREATE INDEX IF NOT EXISTS idx_conn_inst_health ON connector_instances(health);

CREATE TABLE IF NOT EXISTS connector_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    task_id TEXT,
    status TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_payload TEXT,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conn_idemp_op ON connector_idempotency(operation_id);
CREATE INDEX IF NOT EXISTS idx_conn_idemp_expires ON connector_idempotency(expires_at);

CREATE TABLE IF NOT EXISTS connector_webhooks (
    webhook_id TEXT PRIMARY KEY,
    endpoint_path TEXT NOT NULL UNIQUE,
    provider_id TEXT NOT NULL,
    secret_reference TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    verification_algorithm TEXT NOT NULL DEFAULT 'HMAC_SHA256',
    max_payload_bytes INTEGER NOT NULL DEFAULT 1048576,
    replay_window_sec REAL NOT NULL DEFAULT 300.0,
    created_at REAL NOT NULL,
    last_event_at REAL
);

CREATE INDEX IF NOT EXISTS idx_conn_webhook_provider ON connector_webhooks(provider_id);

CREATE TABLE IF NOT EXISTS connector_webhook_events (
    event_id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    signature_verified INTEGER NOT NULL DEFAULT 0,
    normalized_type TEXT NOT NULL,
    received_at REAL NOT NULL,
    FOREIGN KEY (webhook_id) REFERENCES connector_webhooks(webhook_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conn_wevt_wh ON connector_webhook_events(webhook_id);
CREATE INDEX IF NOT EXISTS idx_conn_wevt_prov_id ON connector_webhook_events(provider_event_id);

CREATE TABLE IF NOT EXISTS connector_circuit_state (
    connector_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'CLOSED',
    failure_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    last_failure_time REAL,
    last_state_change REAL NOT NULL,
    half_open_probe_in_flight INTEGER NOT NULL DEFAULT 0
);
"""

MIGRATION_V9 = """
-- Schema Version 9: Data Ingestion, Normalization & Knowledge Pipeline Tables (Module 27)

CREATE TABLE IF NOT EXISTS ingestion_envelopes (
    envelope_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    connector_id TEXT,
    connector_instance_id TEXT,
    operation_id TEXT,
    received_at REAL NOT NULL,
    observed_at REAL NOT NULL,
    content_type TEXT NOT NULL,
    schema_name TEXT,
    schema_version TEXT,
    payload_reference TEXT,
    payload_hash TEXT NOT NULL,
    payload_size INTEGER NOT NULL,
    classification TEXT NOT NULL DEFAULT 'INTERNAL',
    trust_boundary TEXT NOT NULL DEFAULT 'UNTRUSTED_EXTERNAL',
    correlation_id TEXT,
    causation_id TEXT,
    trace_id TEXT,
    raw_payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'INGESTED',
    quarantine_reason TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ingest_env_source ON ingestion_envelopes(source_id);
CREATE INDEX IF NOT EXISTS idx_ingest_env_status ON ingestion_envelopes(status);
CREATE INDEX IF NOT EXISTS idx_ingest_env_hash ON ingestion_envelopes(payload_hash);
CREATE INDEX IF NOT EXISTS idx_ingest_env_created ON ingestion_envelopes(created_at);

CREATE TABLE IF NOT EXISTS ingestion_normalized_records (
    record_id TEXT PRIMARY KEY,
    envelope_id TEXT NOT NULL,
    canonical_entity_type TEXT NOT NULL,
    canonical_id TEXT NOT NULL,
    canonical_data_json TEXT NOT NULL,
    quality_score REAL NOT NULL DEFAULT 1.0,
    quality_metadata_json TEXT NOT NULL DEFAULT '{}',
    freshness_status TEXT NOT NULL DEFAULT 'FRESH',
    source_authority TEXT NOT NULL DEFAULT 'EXTERNAL_UNVERIFIED',
    observed_at REAL NOT NULL,
    normalized_at REAL NOT NULL,
    expires_at REAL,
    FOREIGN KEY (envelope_id) REFERENCES ingestion_envelopes(envelope_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ingest_norm_type ON ingestion_normalized_records(canonical_entity_type);
CREATE INDEX IF NOT EXISTS idx_ingest_norm_can_id ON ingestion_normalized_records(canonical_id);
CREATE INDEX IF NOT EXISTS idx_ingest_norm_freshness ON ingestion_normalized_records(freshness_status);

CREATE TABLE IF NOT EXISTS ingestion_provenance (
    provenance_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    envelope_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    connector_id TEXT,
    operation_id TEXT,
    resource_id TEXT,
    transformations_json TEXT NOT NULL DEFAULT '[]',
    lineage_chain_json TEXT NOT NULL DEFAULT '[]',
    observed_at REAL NOT NULL,
    received_at REAL NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (record_id) REFERENCES ingestion_normalized_records(record_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ingest_prov_rec ON ingestion_provenance(record_id);
CREATE INDEX IF NOT EXISTS idx_ingest_prov_env ON ingestion_provenance(envelope_id);

CREATE TABLE IF NOT EXISTS ingestion_conflicts (
    conflict_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    source_a TEXT NOT NULL,
    value_a_json TEXT NOT NULL,
    source_b TEXT NOT NULL,
    value_b_json TEXT NOT NULL,
    detected_at REAL NOT NULL,
    resolution_strategy TEXT NOT NULL DEFAULT 'PRESERVE_CONFLICT',
    resolution_status TEXT NOT NULL DEFAULT 'UNRESOLVED',
    resolved_at REAL,
    resolved_value_json TEXT,
    resolution_rationale TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingest_conf_entity ON ingestion_conflicts(entity_id);
CREATE INDEX IF NOT EXISTS idx_ingest_conf_status ON ingestion_conflicts(resolution_status);

CREATE TABLE IF NOT EXISTS ingestion_checkpoints (
    pipeline_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    cursor_val TEXT NOT NULL,
    last_envelope_id TEXT,
    processed_count INTEGER NOT NULL DEFAULT 0,
    watermark_ts REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (pipeline_id, source_id)
);
"""

MIGRATION_V10 = """
-- Schema Version 10: Unified Search & Retrieval Engine Tables (Module 28)

CREATE TABLE IF NOT EXISTS retrieval_evidence (
    evidence_id TEXT PRIMARY KEY,
    query_id TEXT NOT NULL,
    corpus_type TEXT NOT NULL,
    item_id TEXT NOT NULL,
    source_record_id TEXT,
    title TEXT NOT NULL,
    content_snippet TEXT NOT NULL,
    retrieval_score REAL NOT NULL,
    normalized_score REAL NOT NULL,
    confidence_score REAL NOT NULL,
    source_id TEXT NOT NULL,
    canonical_id TEXT,
    provenance_hash TEXT NOT NULL,
    observed_at REAL NOT NULL,
    retrieved_at REAL NOT NULL,
    classification TEXT NOT NULL DEFAULT 'INTERNAL',
    trust_boundary TEXT NOT NULL DEFAULT 'TRUSTED_INTERNAL',
    freshness_status TEXT NOT NULL DEFAULT 'FRESH',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_retrieval_ev_query ON retrieval_evidence(query_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_ev_corpus ON retrieval_evidence(corpus_type);
CREATE INDEX IF NOT EXISTS idx_retrieval_ev_can ON retrieval_evidence(canonical_id);

CREATE TABLE IF NOT EXISTS retrieval_queries (
    query_id TEXT PRIMARY KEY,
    query_text TEXT NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}',
    mode TEXT NOT NULL DEFAULT 'HYBRID',
    total_hits INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL NOT NULL DEFAULT 0.0,
    executed_at REAL NOT NULL,
    actor_id TEXT DEFAULT 'system',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_retrieval_query_time ON retrieval_queries(executed_at);

CREATE TABLE IF NOT EXISTS retrieval_cache (
    cache_key TEXT PRIMARY KEY,
    query_hash TEXT NOT NULL,
    filters_hash TEXT NOT NULL,
    results_json TEXT NOT NULL,
    cached_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_retrieval_cache_exp ON retrieval_cache(expires_at);
"""

MIGRATION_V11 = """
-- Schema Version 11: Evidence & Decision Engine Tables (Module 29)

CREATE TABLE IF NOT EXISTS decision_records (
    decision_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    decision_type TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'EVALUATING',
    confidence_score REAL NOT NULL,
    uncertainty_score REAL NOT NULL DEFAULT 0.0,
    primary_claim_id TEXT,
    summary TEXT NOT NULL,
    evaluated_at REAL NOT NULL,
    expires_at REAL,
    actor_id TEXT DEFAULT 'system',
    policy_version TEXT NOT NULL DEFAULT '1.0.0',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_dec_subject ON decision_records(subject_id);
CREATE INDEX IF NOT EXISTS idx_dec_state ON decision_records(state);
CREATE INDEX IF NOT EXISTS idx_dec_eval_at ON decision_records(evaluated_at);

CREATE TABLE IF NOT EXISTS decision_claims (
    claim_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    statement TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    confidence_score REAL NOT NULL,
    supporting_evidence_count INTEGER NOT NULL DEFAULT 0,
    contradicting_evidence_count INTEGER NOT NULL DEFAULT 0,
    evaluated_at REAL NOT NULL,
    rationale TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (decision_id) REFERENCES decision_records(decision_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_claim_dec ON decision_claims(decision_id);
CREATE INDEX IF NOT EXISTS idx_claim_status ON decision_claims(status);

CREATE TABLE IF NOT EXISTS decision_evidence_links (
    link_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    stance TEXT NOT NULL, -- SUPPORTING, CONTRADICTING, NEUTRAL
    weight REAL NOT NULL DEFAULT 1.0,
    provenance_hash TEXT NOT NULL,
    linked_at REAL NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES decision_records(decision_id) ON DELETE CASCADE,
    FOREIGN KEY (claim_id) REFERENCES decision_claims(claim_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_link_dec ON decision_evidence_links(decision_id);
CREATE INDEX IF NOT EXISTS idx_link_claim ON decision_evidence_links(claim_id);
CREATE INDEX IF NOT EXISTS idx_link_ev ON decision_evidence_links(evidence_id);

CREATE TABLE IF NOT EXISTS decision_conflicts (
    conflict_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    severity REAL NOT NULL,
    resolution_state TEXT NOT NULL DEFAULT 'UNRESOLVED',
    resolved_by TEXT,
    resolution_rationale TEXT,
    detected_at REAL NOT NULL,
    resolved_at REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (decision_id) REFERENCES decision_records(decision_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conflict_dec ON decision_conflicts(decision_id);
CREATE INDEX IF NOT EXISTS idx_conflict_claim ON decision_conflicts(claim_id);
"""

def backup_database(db_path: str, backup_dir: str = "persistence_backups") -> str:
    """Creates a timestamped snapshot of the SQLite database prior to any schema modification."""
    if not os.path.exists(db_path):
        return ""
    os.makedirs(backup_dir, exist_ok=True)
    ts = int(time.time())
    base_name = os.path.basename(db_path)
    backup_path = os.path.join(backup_dir, f"{base_name}.backup_{ts}.db")
    shutil.copy2(db_path, backup_path)
    logger.info(f"Database backed up to: {backup_path}")
    return backup_path

def apply_migrations(db_path: str) -> int:
    """Applies ordered, transactional migrations to ensure schema freshness without data destruction."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Check if schema_migrations table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        has_migrations = cursor.fetchone() is not None
        
        current_version = 0
        if has_migrations:
            cursor.execute("SELECT MAX(version) FROM schema_migrations")
            res = cursor.fetchone()
            if res and res[0] is not None:
                current_version = res[0]

        if current_version < 1:
            logger.info("Applying Migration v1 (Initial Schema)...")
            if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
                backup_database(db_path)

            cursor.executescript(MIGRATION_V1)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (1, time.time(), "Initial durable task graph, checkpoints, and crash recovery tables")
            )
            conn.commit()
            logger.info("Migration v1 applied successfully.")
            current_version = 1

        if current_version < 2:
            logger.info("Applying Migration v2 (Human Approval Gateway Tables)...")
            cursor.executescript(MIGRATION_V2)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (2, time.time(), "Human Approval Gateway and Consent Orchestrator tables")
            )
            conn.commit()
            logger.info("Migration v2 applied successfully.")
            current_version = 2

        if current_version < 3:
            logger.info("Applying Migration v3 (Resource Scheduler & Concurrency Orchestrator Tables)...")
            cursor.executescript(MIGRATION_V3)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (3, time.time(), "Resource Scheduler and Concurrency Orchestrator tables")
            )
            conn.commit()
            logger.info("Migration v3 applied successfully.")
            current_version = 3

        if current_version < 4:
            logger.info("Applying Migration v4 (Distributed Coordination & Leadership Tables)...")
            cursor.executescript(MIGRATION_V4)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (4, time.time(), "Distributed Coordination, Leader Election and Ownership tables")
            )
            conn.commit()
            logger.info("Migration v4 applied successfully.")
            current_version = 4

        if current_version < 5:
            logger.info("Applying Migration v5 (Distributed State Synchronization & Replication Tables)...")
            cursor.executescript(MIGRATION_V5)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (5, time.time(), "Distributed State Synchronization, Replication and Reconciliation tables")
            )
            conn.commit()
            logger.info("Migration v5 applied successfully.")
            current_version = 5

        if current_version < 6:
            logger.info("Applying Migration v6 (Distributed Configuration & Control Plane Tables)...")
            cursor.executescript(MIGRATION_V6)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (6, time.time(), "Distributed Configuration, Policy and Runtime Control Plane tables")
            )
            conn.commit()
            logger.info("Migration v6 applied successfully.")
            current_version = 6

        if current_version < 7:
            logger.info("Applying Migration v7 (Secrets, Credentials & Secure Identity Tables)...")
            cursor.executescript(MIGRATION_V7)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (7, time.time(), "Secrets, Credentials and Secure Identity Lifecycle tables")
            )
            conn.commit()
            logger.info("Migration v7 applied successfully.")
            current_version = 7

        if current_version < 8:
            logger.info("Applying Migration v8 (External Integration & Connector Gateway Tables)...")
            cursor.executescript(MIGRATION_V8)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (8, time.time(), "External Integration and Connector Gateway tables")
            )
            conn.commit()
            logger.info("Migration v8 applied successfully.")
            current_version = 8

        if current_version < 9:
            logger.info("Applying Migration v9 (Data Ingestion, Normalization & Pipeline Tables)...")
            cursor.executescript(MIGRATION_V9)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (9, time.time(), "Data Ingestion, Normalization and Knowledge Pipeline tables")
            )
            conn.commit()
            logger.info("Migration v9 applied successfully.")
            current_version = 9

        if current_version < 10:
            logger.info("Applying Migration v10 (Unified Search & Retrieval Engine Tables)...")
            cursor.executescript(MIGRATION_V10)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (10, time.time(), "Unified Search and Retrieval Engine tables")
            )
            conn.commit()
            logger.info("Migration v10 applied successfully.")
            current_version = 10

        if current_version < 11:
            logger.info("Applying Migration v11 (Evidence & Decision Engine Tables)...")
            cursor.executescript(MIGRATION_V11)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (11, time.time(), "Evidence and Decision Engine tables")
            )
            conn.commit()
            logger.info("Migration v11 applied successfully.")
            current_version = 11

        return current_version
    except Exception as e:
        conn.rollback()
        logger.error(f"MIGRATION_FAILED: Migration rolled back. Reason: {e}")
        raise RuntimeError(f"MIGRATION_FAILED: {e}")
    finally:
        conn.close()
