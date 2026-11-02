import sqlite3
import os
import shutil
import time
import logging
from typing import List, Tuple

logger = logging.getLogger("Omnia.Persistence.Migrations")

CURRENT_SCHEMA_VERSION = 35

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

MIGRATION_V12 = """
-- Schema Version 12: Knowledge Graph & Entity Resolution Engine

CREATE TABLE IF NOT EXISTS knowledge_entities (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    attributes_json TEXT NOT NULL DEFAULT '{}',
    classification TEXT NOT NULL DEFAULT 'INTERNAL',
    trust_boundary TEXT NOT NULL DEFAULT 'INTERNAL',
    confidence REAL NOT NULL DEFAULT 1.0,
    provenance_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    merged_into_id TEXT,
    owner_node TEXT NOT NULL DEFAULT 'local',
    version INTEGER NOT NULL DEFAULT 1,
    valid_from REAL NOT NULL,
    valid_until REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ke_type ON knowledge_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_ke_status ON knowledge_entities(status);
CREATE INDEX IF NOT EXISTS idx_ke_name ON knowledge_entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_ke_merged ON knowledge_entities(merged_into_id);

CREATE TABLE IF NOT EXISTS knowledge_relationships (
    relationship_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    target_id TEXT NOT NULL,
    properties_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL DEFAULT 1.0,
    weight REAL NOT NULL DEFAULT 1.0,
    directed INTEGER NOT NULL DEFAULT 1,
    provenance_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    valid_from REAL NOT NULL,
    valid_until REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (source_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_kr_source ON knowledge_relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_kr_target ON knowledge_relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_kr_pred ON knowledge_relationships(predicate);
CREATE INDEX IF NOT EXISTS idx_kr_status ON knowledge_relationships(status);

CREATE TABLE IF NOT EXISTS entity_identities (
    identity_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at REAL NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    UNIQUE(identifier_type, identifier_value)
);

CREATE INDEX IF NOT EXISTS idx_ei_type_val ON entity_identities(identifier_type, identifier_value);
CREATE INDEX IF NOT EXISTS idx_ei_entity ON entity_identities(entity_id);

CREATE TABLE IF NOT EXISTS entity_resolution_candidates (
    candidate_id TEXT PRIMARY KEY,
    source_entity_id TEXT NOT NULL,
    target_entity_id TEXT NOT NULL,
    similarity_score REAL NOT NULL,
    match_reasons_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'PENDING',
    evaluated_at REAL NOT NULL,
    resolution_notes TEXT,
    FOREIGN KEY (source_entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (target_entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_erc_pair ON entity_resolution_candidates(source_entity_id, target_entity_id);
CREATE INDEX IF NOT EXISTS idx_erc_status ON entity_resolution_candidates(status);
"""

MIGRATION_V13 = """
-- Schema Version 13: Temporal Knowledge & Causal State Engine

CREATE TABLE IF NOT EXISTS temporal_entity_states (
    state_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    valid_from REAL NOT NULL,
    valid_until REAL,
    transaction_time REAL NOT NULL,
    recorded_by TEXT NOT NULL DEFAULT 'system',
    state_payload_json TEXT NOT NULL DEFAULT '{}',
    is_deleted INTEGER NOT NULL DEFAULT 0,
    evidence_id TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tes_entity ON temporal_entity_states(entity_id);
CREATE INDEX IF NOT EXISTS idx_tes_valid ON temporal_entity_states(valid_from, valid_until);
CREATE INDEX IF NOT EXISTS idx_tes_tx ON temporal_entity_states(transaction_time);

CREATE TABLE IF NOT EXISTS causal_links (
    causal_link_id TEXT PRIMARY KEY,
    cause_entity_id TEXT NOT NULL,
    effect_entity_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
    mechanism_description TEXT,
    observed_lag_sec REAL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'HYPOTHESIZED',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (cause_entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE,
    FOREIGN KEY (effect_entity_id) REFERENCES knowledge_entities(entity_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cl_cause ON causal_links(cause_entity_id);
CREATE INDEX IF NOT EXISTS idx_cl_effect ON causal_links(effect_entity_id);
CREATE INDEX IF NOT EXISTS idx_cl_status ON causal_links(status);

CREATE TABLE IF NOT EXISTS causal_evidence_bindings (
    binding_id TEXT PRIMARY KEY,
    causal_link_id TEXT NOT NULL,
    evidence_id TEXT NOT NULL,
    support_type TEXT NOT NULL DEFAULT 'SUPPORTS',
    strength REAL NOT NULL DEFAULT 1.0,
    created_at REAL NOT NULL,
    FOREIGN KEY (causal_link_id) REFERENCES causal_links(causal_link_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ceb_link ON causal_evidence_bindings(causal_link_id);
CREATE INDEX IF NOT EXISTS idx_ceb_ev ON causal_evidence_bindings(evidence_id);
"""

MIGRATION_V14 = """
-- Schema Version 14: Predictive Intelligence & Risk Forecasting Engine

CREATE TABLE IF NOT EXISTS forecast_requests (
    request_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    target_description TEXT NOT NULL,
    target_type TEXT NOT NULL,
    horizon_start REAL NOT NULL,
    horizon_end REAL NOT NULL,
    horizon_duration_sec REAL NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'REQUESTED',
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_frq_target ON forecast_requests(target_id);
CREATE INDEX IF NOT EXISTS idx_frq_status ON forecast_requests(status);

CREATE TABLE IF NOT EXISTS forecast_records (
    forecast_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    forecast_type TEXT NOT NULL,
    predicted_value REAL,
    predicted_class TEXT,
    probability REAL,
    is_calibrated_probability INTEGER NOT NULL DEFAULT 0,
    interval_lower REAL,
    interval_upper REAL,
    interval_confidence REAL,
    is_calibrated_interval INTEGER NOT NULL DEFAULT 0,
    coverage_guarantee TEXT,
    method_name TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '1.0.0',
    inputs_hash TEXT NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    assumptions_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    explanation_json TEXT NOT NULL DEFAULT '{}',
    risk_assessment_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'COMPLETED',
    superseded_by TEXT,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    FOREIGN KEY (request_id) REFERENCES forecast_requests(request_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_frc_target ON forecast_records(target_id);
CREATE INDEX IF NOT EXISTS idx_frc_status ON forecast_records(status);
CREATE INDEX IF NOT EXISTS idx_frc_expires ON forecast_records(expires_at);

CREATE TABLE IF NOT EXISTS forecast_outcomes (
    outcome_id TEXT PRIMARY KEY,
    forecast_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    observed_value REAL,
    observed_class TEXT,
    observed_at REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'system',
    is_verified INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (forecast_id) REFERENCES forecast_records(forecast_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_foc_forecast ON forecast_outcomes(forecast_id);
CREATE INDEX IF NOT EXISTS idx_foc_target ON forecast_outcomes(target_id);

CREATE TABLE IF NOT EXISTS forecast_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    forecast_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    error_value REAL NOT NULL,
    is_accurate INTEGER NOT NULL DEFAULT 0,
    evaluation_notes TEXT,
    evaluated_at REAL NOT NULL,
    FOREIGN KEY (forecast_id) REFERENCES forecast_records(forecast_id) ON DELETE CASCADE,
    FOREIGN KEY (outcome_id) REFERENCES forecast_outcomes(outcome_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fev_forecast ON forecast_evaluations(forecast_id);
CREATE INDEX IF NOT EXISTS idx_fev_metric ON forecast_evaluations(metric_name);

CREATE TABLE IF NOT EXISTS forecast_calibration_records (
    calibration_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    target_type TEXT NOT NULL,
    sample_count INTEGER NOT NULL,
    brier_score REAL,
    ece REAL,
    mae REAL,
    rmse REAL,
    coverage_rate REAL,
    time_window_start REAL NOT NULL,
    time_window_end REAL NOT NULL,
    is_valid INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fcr_model ON forecast_calibration_records(model_name, target_type);

CREATE TABLE IF NOT EXISTS forecast_drift_assessments (
    drift_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    target_id TEXT NOT NULL,
    detected INTEGER NOT NULL DEFAULT 0,
    drift_type TEXT NOT NULL,
    p_value REAL,
    metric_shift REAL NOT NULL DEFAULT 0.0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    recommendation TEXT NOT NULL,
    detected_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fda_model ON forecast_drift_assessments(model_name);
"""


MIGRATION_V15 = """
-- Schema Version 15: Adaptive Learning & Model Lifecycle Governance Engine

CREATE TABLE IF NOT EXISTS learning_signals (
    signal_id TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0.0',
    source_module TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    mission_id TEXT,
    task_id TEXT,
    experiment_id TEXT,
    correlation_id TEXT,
    event_time REAL NOT NULL,
    observation_time REAL NOT NULL,
    model_version TEXT,
    strategy_id TEXT,
    outcome_status TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    is_verified INTEGER NOT NULL DEFAULT 0,
    verification_method TEXT,
    quality_status TEXT NOT NULL DEFAULT 'ACCEPTED',
    exclusion_reason TEXT,
    is_eligible_for_eval INTEGER NOT NULL DEFAULT 1,
    is_eligible_for_training INTEGER NOT NULL DEFAULT 1,
    provenance_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ls_source ON learning_signals(source_module, source_record_id);
CREATE INDEX IF NOT EXISTS idx_ls_quality ON learning_signals(quality_status);
CREATE INDEX IF NOT EXISTS idx_ls_strategy ON learning_signals(strategy_id, model_version);
CREATE INDEX IF NOT EXISTS idx_ls_time ON learning_signals(event_time);

CREATE TABLE IF NOT EXISTS learning_datasets (
    dataset_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    purpose TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT '1.0.0',
    time_window_start REAL NOT NULL,
    time_window_end REAL NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    manifest_json TEXT NOT NULL DEFAULT '{}',
    inclusion_rules_json TEXT NOT NULL DEFAULT '[]',
    features_schema_json TEXT NOT NULL DEFAULT '{}',
    content_digest TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ld_purpose ON learning_datasets(purpose);
CREATE INDEX IF NOT EXISTS idx_ld_version ON learning_datasets(dataset_id, version);

CREATE TABLE IF NOT EXISTS learning_model_versions (
    model_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    model_family TEXT NOT NULL,
    artifact_ref TEXT NOT NULL,
    artifact_digest TEXT NOT NULL,
    feature_schema_version TEXT NOT NULL DEFAULT '1.0.0',
    risk_level TEXT NOT NULL DEFAULT 'LOW',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    evaluation_summary_json TEXT NOT NULL DEFAULT '{}',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (model_id, version_id)
);

CREATE INDEX IF NOT EXISTS idx_lmv_status ON learning_model_versions(status);
CREATE INDEX IF NOT EXISTS idx_lmv_family ON learning_model_versions(model_family);

CREATE TABLE IF NOT EXISTS learning_experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    experiment_type TEXT NOT NULL,
    baseline_version TEXT NOT NULL,
    candidate_version TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    protocol_json TEXT NOT NULL DEFAULT '{}',
    primary_metric TEXT NOT NULL,
    min_sample_size INTEGER NOT NULL DEFAULT 20,
    success_threshold REAL NOT NULL DEFAULT 0.05,
    max_regression_threshold REAL NOT NULL DEFAULT 0.02,
    budget_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'CREATED',
    results_json TEXT NOT NULL DEFAULT '{}',
    started_at REAL,
    completed_at REAL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_le_status ON learning_experiments(status);
CREATE INDEX IF NOT EXISTS idx_le_candidate ON learning_experiments(candidate_version);

CREATE TABLE IF NOT EXISTS learning_promotion_requests (
    request_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    candidate_version TEXT NOT NULL,
    baseline_version TEXT NOT NULL,
    experiment_id TEXT,
    risk_level TEXT NOT NULL DEFAULT 'LOW',
    status TEXT NOT NULL DEFAULT 'PENDING',
    gates_evaluation_json TEXT NOT NULL DEFAULT '{}',
    approval_request_id TEXT,
    approved_by TEXT,
    approved_at REAL,
    rejection_reason TEXT,
    target_rollout_stage TEXT NOT NULL DEFAULT 'CANARY',
    current_rollout_stage TEXT NOT NULL DEFAULT 'OFFLINE',
    rollback_target_version TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lpr_candidate ON learning_promotion_requests(candidate_id, candidate_version);
CREATE INDEX IF NOT EXISTS idx_lpr_status ON learning_promotion_requests(status);

CREATE TABLE IF NOT EXISTS learning_rollout_records (
    rollout_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    candidate_version TEXT NOT NULL,
    baseline_version TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    canary_traffic_pct REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    metrics_summary_json TEXT NOT NULL DEFAULT '{}',
    halt_reason TEXT,
    started_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY (request_id) REFERENCES learning_promotion_requests(request_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lrr_request ON learning_rollout_records(request_id);
CREATE INDEX IF NOT EXISTS idx_lrr_status ON learning_rollout_records(status);

CREATE TABLE IF NOT EXISTS learning_drift_records (
    record_id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    drift_type TEXT NOT NULL,
    feature_or_metric TEXT NOT NULL,
    baseline_value REAL NOT NULL,
    observed_value REAL NOT NULL,
    drift_metric_value REAL NOT NULL,
    threshold REAL NOT NULL,
    severity TEXT NOT NULL DEFAULT 'LOW',
    recommendation TEXT NOT NULL,
    assessed_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ldr_model ON learning_drift_records(model_id, version_id);
CREATE INDEX IF NOT EXISTS idx_ldr_severity ON learning_drift_records(severity);
"""


MIGRATION_V16 = """
-- Schema Version 16: Autonomous Simulation, Digital Twin & Scenario Testing Engine

CREATE TABLE IF NOT EXISTS simulation_environments (
    environment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    env_type TEXT NOT NULL,
    classification TEXT NOT NULL DEFAULT 'TEST',
    version TEXT NOT NULL DEFAULT '1.0.0',
    owner TEXT NOT NULL DEFAULT 'system',
    model_references_json TEXT NOT NULL DEFAULT '[]',
    supported_capabilities_json TEXT NOT NULL DEFAULT '[]',
    state_schema_json TEXT NOT NULL DEFAULT '{}',
    supported_action_types_json TEXT NOT NULL DEFAULT '[]',
    constraints_json TEXT NOT NULL DEFAULT '{}',
    resource_limits_json TEXT NOT NULL DEFAULT '{}',
    isolation_level TEXT NOT NULL DEFAULT 'PROCESS_ISOLATED',
    fidelity_classification TEXT NOT NULL DEFAULT 'UNVALIDATED',
    data_classification TEXT NOT NULL DEFAULT 'INTERNAL',
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sim_env_type ON simulation_environments(env_type);
CREATE INDEX IF NOT EXISTS idx_sim_env_class ON simulation_environments(classification);

CREATE TABLE IF NOT EXISTS digital_twins (
    twin_id TEXT PRIMARY KEY,
    source_system_id TEXT NOT NULL,
    source_system_type TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    sync_mode TEXT NOT NULL DEFAULT 'STATIC',
    state_schema_version TEXT NOT NULL DEFAULT '1.0.0',
    observed_state_json TEXT NOT NULL DEFAULT '{}',
    inferred_state_json TEXT NOT NULL DEFAULT '{}',
    simulated_state_json TEXT NOT NULL DEFAULT '{}',
    capability_model_json TEXT NOT NULL DEFAULT '{}',
    constraints_json TEXT NOT NULL DEFAULT '{}',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    known_omissions_json TEXT NOT NULL DEFAULT '[]',
    last_sync_time REAL NOT NULL,
    freshness_seconds REAL NOT NULL DEFAULT 0.0,
    fidelity_status TEXT NOT NULL DEFAULT 'UNVALIDATED',
    provenance_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dt_source ON digital_twins(source_system_id, source_system_type);
CREATE INDEX IF NOT EXISTS idx_dt_fidelity ON digital_twins(fidelity_status);

CREATE TABLE IF NOT EXISTS simulation_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    environment_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    captured_at REAL NOT NULL,
    state_schema_version TEXT NOT NULL DEFAULT '1.0.0',
    state_payload_json TEXT NOT NULL DEFAULT '{}',
    included_components_json TEXT NOT NULL DEFAULT '[]',
    excluded_components_json TEXT NOT NULL DEFAULT '[]',
    integrity_digest TEXT NOT NULL,
    consistency_status TEXT NOT NULL DEFAULT 'CONSISTENT',
    data_classification TEXT NOT NULL DEFAULT 'INTERNAL',
    known_limitations_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_sim_snap_env ON simulation_snapshots(environment_id);

CREATE TABLE IF NOT EXISTS simulation_scenarios (
    scenario_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    scenario_type TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    initial_snapshot_id TEXT NOT NULL,
    proposed_actions_json TEXT NOT NULL DEFAULT '[]',
    preconditions_json TEXT NOT NULL DEFAULT '{}',
    constraints_json TEXT NOT NULL DEFAULT '{}',
    expected_observations_json TEXT NOT NULL DEFAULT '{}',
    time_horizon_seconds REAL NOT NULL DEFAULT 60.0,
    resource_budget_json TEXT NOT NULL DEFAULT '{}',
    uncertainty_assumptions_json TEXT NOT NULL DEFAULT '{}',
    evaluation_metrics_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_sim_scen_type ON simulation_scenarios(scenario_type);
CREATE INDEX IF NOT EXISTS idx_sim_scen_env ON simulation_scenarios(environment_id);

CREATE TABLE IF NOT EXISTS simulation_executions (
    simulation_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    twin_id TEXT,
    snapshot_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    current_step INTEGER NOT NULL DEFAULT 0,
    total_steps INTEGER NOT NULL DEFAULT 0,
    action_history_json TEXT NOT NULL DEFAULT '[]',
    state_transitions_json TEXT NOT NULL DEFAULT '[]',
    events_generated_json TEXT NOT NULL DEFAULT '[]',
    resource_consumption_json TEXT NOT NULL DEFAULT '{}',
    result_summary_json TEXT NOT NULL DEFAULT '{}',
    fidelity_classification TEXT NOT NULL DEFAULT 'UNVALIDATED',
    started_at REAL,
    completed_at REAL,
    error_message TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sim_exec_status ON simulation_executions(status);
CREATE INDEX IF NOT EXISTS idx_sim_exec_scen ON simulation_executions(scenario_id);

CREATE TABLE IF NOT EXISTS simulation_faults (
    fault_id TEXT PRIMARY KEY,
    simulation_id TEXT NOT NULL,
    fault_type TEXT NOT NULL,
    target_component TEXT NOT NULL,
    activation_step INTEGER NOT NULL DEFAULT 0,
    duration_steps INTEGER NOT NULL DEFAULT 1,
    severity TEXT NOT NULL DEFAULT 'HIGH',
    injected_at REAL NOT NULL,
    recovery_observed INTEGER NOT NULL DEFAULT 0,
    recovery_details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sim_fault_sim ON simulation_faults(simulation_id);

CREATE TABLE IF NOT EXISTS simulation_fidelity_records (
    record_id TEXT PRIMARY KEY,
    simulation_id TEXT NOT NULL,
    twin_id TEXT,
    fidelity_level TEXT NOT NULL,
    reality_observation_id TEXT,
    deviation_metrics_json TEXT NOT NULL DEFAULT '{}',
    failed_assumptions_json TEXT NOT NULL DEFAULT '[]',
    unexplained_deviations_json TEXT NOT NULL DEFAULT '[]',
    assessed_at REAL NOT NULL,
    recommended_learning_signal INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sfr_sim ON simulation_fidelity_records(simulation_id);
"""
MIGRATION_V17 = """
-- Schema Version 17: Autonomous Cybersecurity, Threat Intelligence & Runtime Defense Engine

CREATE TABLE IF NOT EXISTS security_telemetry_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source_component TEXT NOT NULL,
    action_category TEXT NOT NULL,
    outcome TEXT NOT NULL,
    severity TEXT NOT NULL,
    timestamp REAL NOT NULL,
    schema_version INTEGER NOT NULL,
    source_identity TEXT,
    node_identity TEXT,
    correlation_id TEXT,
    resource_reference TEXT,
    details TEXT NOT NULL,
    data_classification TEXT NOT NULL,
    signature TEXT
);

CREATE INDEX IF NOT EXISTS idx_sec_tel_time ON security_telemetry_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_sec_tel_source ON security_telemetry_events(source_component);
CREATE INDEX IF NOT EXISTS idx_sec_tel_ident ON security_telemetry_events(source_identity);

CREATE TABLE IF NOT EXISTS threat_intelligence_indicators (
    indicator_id TEXT PRIMARY KEY,
    indicator_type TEXT NOT NULL,
    indicator_value TEXT NOT NULL,
    source TEXT NOT NULL,
    source_reliability REAL NOT NULL,
    confidence REAL NOT NULL,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    expires_at REAL,
    context TEXT NOT NULL,
    threat_classification TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    applicable_scope TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ti_val ON threat_intelligence_indicators(indicator_value);
CREATE INDEX IF NOT EXISTS idx_ti_status ON threat_intelligence_indicators(validation_status);

CREATE TABLE IF NOT EXISTS security_detection_rules (
    rule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    threat_classification TEXT NOT NULL,
    severity TEXT NOT NULL,
    required_telemetry_types TEXT NOT NULL,
    matching_criteria TEXT NOT NULL,
    confidence REAL NOT NULL,
    version INTEGER NOT NULL,
    is_active INTEGER NOT NULL,
    suppression_window_sec REAL NOT NULL,
    expected_response_level INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS security_incidents (
    incident_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    threat_classification TEXT NOT NULL,
    severity TEXT NOT NULL,
    confidence REAL NOT NULL,
    detection_source TEXT NOT NULL,
    affected_assets TEXT NOT NULL,
    related_event_ids TEXT NOT NULL,
    evidence_ids TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_owner TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    containment_action_ids TEXT NOT NULL,
    resolution_summary TEXT,
    audit_history TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inc_status ON security_incidents(status);
CREATE INDEX IF NOT EXISTS idx_inc_sev ON security_incidents(severity);

CREATE TABLE IF NOT EXISTS security_containment_actions (
    action_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target_resource TEXT NOT NULL,
    scope TEXT NOT NULL,
    reason TEXT NOT NULL,
    response_level INTEGER NOT NULL,
    status TEXT NOT NULL,
    is_reversible INTEGER NOT NULL,
    approval_request_id TEXT,
    approval_token TEXT,
    requested_at REAL NOT NULL,
    executed_at REAL,
    verified_at REAL,
    verification_evidence TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS forensic_evidence_records (
    evidence_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    source_identifier TEXT NOT NULL,
    collector_identity TEXT NOT NULL,
    integrity_digest TEXT NOT NULL,
    raw_payload_redacted TEXT NOT NULL,
    collected_at REAL NOT NULL,
    data_classification TEXT NOT NULL,
    chain_of_custody TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS security_posture_assessments (
    assessment_id TEXT PRIMARY KEY,
    overall_state TEXT NOT NULL,
    score REAL NOT NULL,
    active_incidents_count INTEGER NOT NULL,
    critical_alerts_count INTEGER NOT NULL,
    monitored_sources_count INTEGER NOT NULL,
    missing_sources TEXT NOT NULL,
    component_posture TEXT NOT NULL,
    recommended_remediations TEXT NOT NULL,
    timestamp REAL NOT NULL
);
"""




MIGRATION_V18 = """
-- Schema Version 18: Autonomous Observability, Diagnostics and Self-Healing Engine

CREATE TABLE IF NOT EXISTS observability_metrics (
    metric_id TEXT PRIMARY KEY,
    component_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    timestamp REAL NOT NULL,
    labels TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_obs_metrics_comp ON observability_metrics(component_id);
CREATE INDEX IF NOT EXISTS idx_obs_metrics_name ON observability_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_obs_metrics_time ON observability_metrics(timestamp);

CREATE TABLE IF NOT EXISTS observability_traces (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    operation_name TEXT NOT NULL,
    component_id TEXT NOT NULL,
    parent_span_id TEXT,
    start_time REAL NOT NULL,
    end_time REAL,
    duration_ms REAL NOT NULL,
    status TEXT NOT NULL,
    tags TEXT NOT NULL,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_obs_traces_trace ON observability_traces(trace_id);
CREATE INDEX IF NOT EXISTS idx_obs_traces_comp ON observability_traces(component_id);
CREATE INDEX IF NOT EXISTS idx_obs_traces_status ON observability_traces(status);

CREATE TABLE IF NOT EXISTS component_health_registry (
    component_id TEXT PRIMARY KEY,
    component_name TEXT NOT NULL,
    module_ownership TEXT NOT NULL,
    version TEXT NOT NULL,
    current_status TEXT NOT NULL,
    status_message TEXT NOT NULL,
    critical_dependencies TEXT NOT NULL,
    last_check_timestamp REAL,
    last_healthy_timestamp REAL,
    last_failure_timestamp REAL,
    consecutive_failures INTEGER NOT NULL,
    liveness_ok INTEGER NOT NULL,
    readiness_ok INTEGER NOT NULL,
    functional_ok INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chr_status ON component_health_registry(current_status);

CREATE TABLE IF NOT EXISTS health_check_definitions (
    check_id TEXT PRIMARY KEY,
    target_component_id TEXT NOT NULL,
    name TEXT NOT NULL,
    check_type TEXT NOT NULL,
    interval_seconds REAL NOT NULL,
    timeout_seconds REAL NOT NULL,
    is_active INTEGER NOT NULL,
    metadata TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hcd_target ON health_check_definitions(target_component_id);

CREATE TABLE IF NOT EXISTS infrastructure_dependencies (
    edge_id TEXT PRIMARY KEY,
    source_component_id TEXT NOT NULL,
    target_component_id TEXT NOT NULL,
    dependency_type TEXT NOT NULL,
    criticality REAL NOT NULL,
    failure_propagation_probability REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inf_dep_src ON infrastructure_dependencies(source_component_id);
CREATE INDEX IF NOT EXISTS idx_inf_dep_tgt ON infrastructure_dependencies(target_component_id);

CREATE TABLE IF NOT EXISTS diagnostic_hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    suspected_component_id TEXT NOT NULL,
    failure_category TEXT NOT NULL,
    confidence REAL NOT NULL,
    explanation TEXT NOT NULL,
    supporting_evidence TEXT NOT NULL,
    contradicting_evidence TEXT NOT NULL,
    cascading_impact_components TEXT NOT NULL,
    recommended_remediation_action TEXT,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_diag_hyp_comp ON diagnostic_hypotheses(suspected_component_id);
CREATE INDEX IF NOT EXISTS idx_diag_hyp_cat ON diagnostic_hypotheses(failure_category);

CREATE TABLE IF NOT EXISTS infrastructure_remediations (
    action_id TEXT PRIMARY KEY,
    target_component_id TEXT NOT NULL,
    proposed_action TEXT NOT NULL,
    failure_category TEXT NOT NULL,
    reason TEXT NOT NULL,
    autonomy_level INTEGER NOT NULL,
    status TEXT NOT NULL,
    is_reversible INTEGER NOT NULL,
    approval_request_id TEXT,
    approval_token TEXT,
    retry_budget INTEGER NOT NULL,
    retry_count INTEGER NOT NULL,
    verification_window_seconds REAL NOT NULL,
    created_at REAL NOT NULL,
    executed_at REAL,
    verified_at REAL,
    verification_evidence TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_inf_rem_target ON infrastructure_remediations(target_component_id);
CREATE INDEX IF NOT EXISTS idx_inf_rem_status ON infrastructure_remediations(status);
"""



MIGRATION_V19 = """
-- Schema Version 19: Autonomous Deployment, Release Engineering & Rollback Engine

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

CREATE INDEX IF NOT EXISTS idx_releases_app ON releases(app_id);
CREATE INDEX IF NOT EXISTS idx_releases_state ON releases(state);

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

CREATE INDEX IF NOT EXISTS idx_release_art_app ON release_artifacts(app_id, version);
CREATE INDEX IF NOT EXISTS idx_release_art_digest ON release_artifacts(digest_sha256);

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

CREATE INDEX IF NOT EXISTS idx_rel_env_app ON release_environments(app_id);

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

CREATE INDEX IF NOT EXISTS idx_dep_release ON deployments(release_id);
CREATE INDEX IF NOT EXISTS idx_dep_env ON deployments(environment_id);

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

CREATE INDEX IF NOT EXISTS idx_rb_env ON rollback_records(environment_id);
"""



MIGRATION_V20 = """
-- Schema Version 20: Autonomous Research, Scientific Discovery & Hypothesis Testing Engine

CREATE TABLE IF NOT EXISTS research_requests (
    research_id TEXT PRIMARY KEY,
    original_question TEXT NOT NULL,
    normalized_objective TEXT NOT NULL,
    domain TEXT NOT NULL,
    scope TEXT NOT NULL,
    state TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    requires_approval INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_research_req_state ON research_requests(state);

CREATE TABLE IF NOT EXISTS research_knowledge_gaps (
    gap_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    description TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    evidence_required TEXT NOT NULL,
    possible_acquisition_method TEXT NOT NULL,
    priority TEXT NOT NULL,
    resolution_status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rkg_research ON research_knowledge_gaps(research_id);

CREATE TABLE IF NOT EXISTS research_hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    statement TEXT NOT NULL,
    hypothesis_type TEXT NOT NULL,
    scope TEXT NOT NULL,
    assumptions TEXT NOT NULL,
    supporting_evidence TEXT NOT NULL,
    contradictory_evidence TEXT NOT NULL,
    expected_observations TEXT NOT NULL,
    falsification_conditions TEXT NOT NULL,
    state TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rh_research ON research_hypotheses(research_id);
CREATE INDEX IF NOT EXISTS idx_rh_state ON research_hypotheses(state);

CREATE TABLE IF NOT EXISTS research_experiments (
    experiment_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    hypothesis_id TEXT NOT NULL,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    experiment_type TEXT NOT NULL,
    independent_variables TEXT NOT NULL,
    dependent_variables TEXT NOT NULL,
    controlled_variables TEXT NOT NULL,
    sampling_strategy TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    baseline_condition TEXT NOT NULL,
    treatment_condition TEXT NOT NULL,
    measurement_protocol TEXT NOT NULL,
    stopping_conditions TEXT NOT NULL,
    success_criteria TEXT NOT NULL,
    failure_criteria TEXT NOT NULL,
    requires_approval INTEGER NOT NULL,
    approval_token TEXT,
    isolation_environment TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_re_research ON research_experiments(research_id);
CREATE INDEX IF NOT EXISTS idx_re_hypothesis ON research_experiments(hypothesis_id);

CREATE TABLE IF NOT EXISTS research_hypothesis_tests (
    test_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    method TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    test_statistic REAL,
    p_value REAL,
    effect_size REAL NOT NULL,
    confidence_interval TEXT,
    evaluated_state TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    limitations TEXT NOT NULL,
    tested_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rht_hypothesis ON research_hypothesis_tests(hypothesis_id);

CREATE TABLE IF NOT EXISTS research_conclusions (
    conclusion_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    state TEXT NOT NULL,
    summary TEXT NOT NULL,
    direct_observations TEXT NOT NULL,
    supported_claims TEXT NOT NULL,
    rejected_hypotheses TEXT NOT NULL,
    unresolved_uncertainties TEXT NOT NULL,
    scope_limitations TEXT NOT NULL,
    evidence_trail TEXT NOT NULL,
    concluded_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rc_research ON research_conclusions(research_id);

CREATE TABLE IF NOT EXISTS research_reproducibility (
    manifest_id TEXT PRIMARY KEY,
    research_id TEXT NOT NULL,
    dataset_digest_sha256 TEXT NOT NULL,
    methodology_version TEXT NOT NULL,
    code_digest_sha256 TEXT NOT NULL,
    random_seed INTEGER,
    environment_metadata TEXT NOT NULL,
    replay_instructions TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rr_research ON research_reproducibility(research_id);
"""

MIGRATION_V21 = """
-- Schema Version 21: Autonomous Knowledge Synthesis & Intelligence Briefing Engine

CREATE TABLE IF NOT EXISTS intelligence_products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    product_type TEXT NOT NULL,
    domain TEXT NOT NULL,
    intended_audience TEXT NOT NULL,
    authorized_scope TEXT NOT NULL,
    required_sources TEXT NOT NULL,
    update_cadence TEXT NOT NULL,
    max_length_words INTEGER DEFAULT 1500,
    freshness_window_sec REAL DEFAULT 86400.0,
    retention_days INTEGER DEFAULT 90,
    approval_required INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    state TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intel_prod_domain ON intelligence_products(domain);
CREATE INDEX IF NOT EXISTS idx_intel_prod_state ON intelligence_products(state);

CREATE TABLE IF NOT EXISTS intelligence_briefing_versions (
    version_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    audience_level TEXT NOT NULL,
    executive_summary TEXT NOT NULL,
    rendered_content_markdown TEXT NOT NULL,
    content_digest_sha256 TEXT NOT NULL,
    evidence_sources_count INTEGER NOT NULL,
    claims_count INTEGER NOT NULL,
    quality_score TEXT NOT NULL,
    approval_token TEXT,
    is_stale INTEGER DEFAULT 0,
    generated_at REAL NOT NULL,
    FOREIGN KEY (product_id) REFERENCES intelligence_products(product_id)
);

CREATE INDEX IF NOT EXISTS idx_ibv_product ON intelligence_briefing_versions(product_id);

CREATE TABLE IF NOT EXISTS intelligence_claims (
    claim_id TEXT PRIMARY KEY,
    briefing_version_id TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    supporting_evidence_refs TEXT NOT NULL,
    contradictory_evidence_refs TEXT NOT NULL,
    confidence_assessment TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    temporal_scope TEXT NOT NULL,
    known_assumptions TEXT NOT NULL,
    limitations TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (briefing_version_id) REFERENCES intelligence_briefing_versions(version_id)
);

CREATE INDEX IF NOT EXISTS idx_ic_bver ON intelligence_claims(briefing_version_id);

CREATE TABLE IF NOT EXISTS intelligence_contradictions (
    contradiction_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    source_a_ref TEXT NOT NULL,
    source_b_ref TEXT NOT NULL,
    divergence_reason TEXT NOT NULL,
    status TEXT NOT NULL,
    resolution_evidence_needed TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (product_id) REFERENCES intelligence_products(product_id)
);

CREATE INDEX IF NOT EXISTS idx_icontra_prod ON intelligence_contradictions(product_id);

CREATE TABLE IF NOT EXISTS intelligence_developments (
    development_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT,
    source_refs TEXT NOT NULL,
    significance_score REAL NOT NULL,
    detected_at REAL NOT NULL,
    FOREIGN KEY (product_id) REFERENCES intelligence_products(product_id)
);

CREATE INDEX IF NOT EXISTS idx_idev_prod ON intelligence_developments(product_id);

CREATE TABLE IF NOT EXISTS intelligence_deliveries (
    delivery_id TEXT PRIMARY KEY,
    briefing_version_id TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    error_message TEXT,
    delivered_at REAL,
    created_at REAL NOT NULL,
    FOREIGN KEY (briefing_version_id) REFERENCES intelligence_briefing_versions(version_id)
);

CREATE INDEX IF NOT EXISTS idx_ideliv_bver ON intelligence_deliveries(briefing_version_id);
"""

MIGRATION_V22 = """
-- Schema Version 22: Decision Support, Strategic Options & Trade-off Analysis Engine

CREATE TABLE IF NOT EXISTS strategy_cases (
    case_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    category TEXT NOT NULL,
    deadline_ts REAL,
    context_json TEXT NOT NULL,
    desired_outcomes_json TEXT NOT NULL,
    constraints_json TEXT NOT NULL,
    available_resources_json TEXT NOT NULL,
    stakeholders_json TEXT NOT NULL,
    risk_tolerance TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    state TEXT NOT NULL,
    selected_option_id TEXT,
    decided_by TEXT,
    approval_token TEXT,
    review_date_ts REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_strat_case_owner ON strategy_cases(owner_id);
CREATE INDEX IF NOT EXISTS idx_strat_case_state ON strategy_cases(state);

CREATE TABLE IF NOT EXISTS strategy_options (
    option_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    is_baseline INTEGER NOT NULL,
    expected_outcome TEXT NOT NULL,
    estimated_cost REAL NOT NULL,
    implementation_complexity TEXT NOT NULL,
    reversibility_score REAL NOT NULL,
    time_horizon_days INTEGER NOT NULL,
    dependencies_json TEXT NOT NULL,
    benefits_json TEXT NOT NULL,
    disadvantages_json TEXT NOT NULL,
    critical_assumptions_json TEXT NOT NULL,
    known_limitations_json TEXT NOT NULL,
    origin TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_strat_opt_case ON strategy_options(case_id);

CREATE TABLE IF NOT EXISTS strategy_criteria (
    criterion_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    name TEXT NOT NULL,
    weight REAL NOT NULL,
    direction TEXT NOT NULL,
    is_mandatory INTEGER NOT NULL DEFAULT 0,
    minimum_threshold REAL,
    acceptable_range_json TEXT,
    description TEXT,
    FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_strat_crit_case ON strategy_criteria(case_id);

CREATE TABLE IF NOT EXISTS strategy_assessments (
    assessment_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    option_id TEXT NOT NULL,
    criterion_scores_json TEXT NOT NULL,
    normalized_score REAL NOT NULL,
    is_pareto_dominated INTEGER NOT NULL DEFAULT 0,
    violates_mandatory_constraint INTEGER NOT NULL DEFAULT 0,
    constraint_violations_json TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id),
    FOREIGN KEY (option_id) REFERENCES strategy_options(option_id)
);

CREATE INDEX IF NOT EXISTS idx_strat_ass_case ON strategy_assessments(case_id);

CREATE TABLE IF NOT EXISTS strategy_risk_assessments (
    assessment_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    option_id TEXT NOT NULL,
    probability_of_failure REAL NOT NULL,
    severity_of_failure REAL NOT NULL,
    financial_exposure REAL NOT NULL,
    operational_disruption TEXT NOT NULL,
    security_risk TEXT NOT NULL,
    opportunity_cost_notes TEXT NOT NULL,
    mitigation_strategy TEXT NOT NULL,
    residual_risk_score REAL NOT NULL,
    is_acceptable INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id),
    FOREIGN KEY (option_id) REFERENCES strategy_options(option_id)
);

CREATE INDEX IF NOT EXISTS idx_strat_risk_case ON strategy_risk_assessments(case_id);

CREATE TABLE IF NOT EXISTS strategy_recommendations (
    recommendation_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    recommended_option_id TEXT,
    primary_justification TEXT NOT NULL,
    key_tradeoffs_json TEXT NOT NULL,
    major_risks_json TEXT NOT NULL,
    critical_assumptions_json TEXT NOT NULL,
    conditions_for_invalidation_json TEXT NOT NULL,
    confidence_level TEXT NOT NULL,
    suggested_review_date_ts REAL NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_strat_rec_case ON strategy_recommendations(case_id);

CREATE TABLE IF NOT EXISTS strategy_outcomes (
    monitoring_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    selected_option_id TEXT NOT NULL,
    actual_cost REAL,
    expected_vs_actual_variance_pct REAL NOT NULL DEFAULT 0.0,
    assumptions_still_valid INTEGER NOT NULL DEFAULT 1,
    invalidated_assumptions_json TEXT NOT NULL,
    reassessment_triggered INTEGER NOT NULL DEFAULT 0,
    reassessment_reason TEXT,
    observed_at REAL NOT NULL,
    FOREIGN KEY (case_id) REFERENCES strategy_cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_strat_out_case ON strategy_outcomes(case_id);
"""


MIGRATION_V23 = """
-- Schema Version 23: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence

CREATE TABLE IF NOT EXISTS goal_definitions (
    goal_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    purpose TEXT NOT NULL,
    owner TEXT NOT NULL,
    goal_type TEXT NOT NULL,
    priority TEXT NOT NULL,
    state TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    parent_goal_id TEXT,
    start_date TEXT,
    target_date TEXT,
    success_criteria_json TEXT NOT NULL DEFAULT '[]',
    constraints_json TEXT NOT NULL DEFAULT '[]',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    resources_json TEXT NOT NULL DEFAULT '{}',
    review_schedule TEXT DEFAULT 'WEEKLY',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (parent_goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_owner ON goal_definitions(owner);
CREATE INDEX IF NOT EXISTS idx_goal_state ON goal_definitions(state);
CREATE INDEX IF NOT EXISTS idx_goal_parent ON goal_definitions(parent_goal_id);

CREATE TABLE IF NOT EXISTS goal_versions (
    snapshot_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    state TEXT NOT NULL,
    target_date TEXT,
    success_criteria_json TEXT NOT NULL DEFAULT '[]',
    constraints_json TEXT NOT NULL DEFAULT '[]',
    changed_by TEXT NOT NULL,
    change_reason TEXT NOT NULL,
    snapshot_at TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_version_goal ON goal_versions(goal_id);

CREATE TABLE IF NOT EXISTS goal_key_results (
    key_result_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    baseline_value REAL NOT NULL,
    target_value REAL NOT NULL,
    current_reported_value REAL NOT NULL DEFAULT 0.0,
    current_verified_value REAL NOT NULL DEFAULT 0.0,
    measurement_frequency TEXT NOT NULL DEFAULT 'DAILY',
    calculation_method TEXT NOT NULL DEFAULT 'DIRECT',
    required_verification_tier TEXT NOT NULL DEFAULT 'SYSTEM_OBSERVED',
    confidence REAL NOT NULL DEFAULT 1.0,
    is_satisfied INTEGER NOT NULL DEFAULT 0,
    last_updated TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_kr_goal ON goal_key_results(goal_id);

CREATE TABLE IF NOT EXISTS goal_evidence_records (
    evidence_id TEXT PRIMARY KEY,
    key_result_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    verification_tier TEXT NOT NULL,
    data_source TEXT NOT NULL,
    observed_value REAL NOT NULL,
    evidence_summary TEXT NOT NULL,
    evidence_payload_json TEXT NOT NULL DEFAULT '{}',
    evidence_hash TEXT NOT NULL,
    verified_by TEXT NOT NULL,
    approval_token TEXT,
    verified_at TEXT NOT NULL,
    is_valid INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (key_result_id) REFERENCES goal_key_results(key_result_id),
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_evidence_kr ON goal_evidence_records(key_result_id);

CREATE TABLE IF NOT EXISTS goal_initiatives (
    initiative_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    title TEXT NOT NULL,
    scope TEXT NOT NULL,
    expected_outcome TEXT NOT NULL,
    owner TEXT NOT NULL,
    required_capabilities_json TEXT NOT NULL DEFAULT '[]',
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    resources_json TEXT NOT NULL DEFAULT '{}',
    target_date TEXT,
    status TEXT NOT NULL DEFAULT 'PLANNED',
    task_graph_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_init_goal ON goal_initiatives(goal_id);

CREATE TABLE IF NOT EXISTS goal_milestones (
    milestone_id TEXT PRIMARY KEY,
    initiative_id TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    target_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    completed_at TEXT,
    verification_evidence_id TEXT,
    FOREIGN KEY (initiative_id) REFERENCES goal_initiatives(initiative_id),
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_milestone_init ON goal_milestones(initiative_id);

CREATE TABLE IF NOT EXISTS goal_progress_snapshots (
    assessment_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    reported_task_progress REAL NOT NULL,
    verified_outcome_progress REAL NOT NULL,
    activity_to_outcome_variance REAL NOT NULL,
    schedule_variance_days REAL NOT NULL DEFAULT 0.0,
    budget_variance_ratio REAL NOT NULL DEFAULT 0.0,
    assessed_at TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_prog_goal ON goal_progress_snapshots(goal_id);

CREATE TABLE IF NOT EXISTS goal_health_assessments (
    health_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    health_state TEXT NOT NULL,
    primary_reason TEXT NOT NULL,
    progress_trajectory TEXT NOT NULL,
    risk_factors_json TEXT NOT NULL DEFAULT '[]',
    stale_metric_count INTEGER NOT NULL DEFAULT 0,
    blocked_dependency_count INTEGER NOT NULL DEFAULT 0,
    confidence_score REAL NOT NULL DEFAULT 1.0,
    assessed_at TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_health_goal ON goal_health_assessments(goal_id);

CREATE TABLE IF NOT EXISTS goal_corrective_actions (
    proposal_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    title TEXT NOT NULL,
    rationale TEXT NOT NULL,
    expected_benefit TEXT NOT NULL,
    potential_cost TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    supporting_evidence_json TEXT NOT NULL DEFAULT '[]',
    requires_human_approval INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    approval_token TEXT,
    approved_by TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_action_goal ON goal_corrective_actions(goal_id);

CREATE TABLE IF NOT EXISTS goal_change_audit (
    audit_id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value_json TEXT,
    new_value_json TEXT,
    author TEXT NOT NULL,
    rationale TEXT NOT NULL,
    approval_token TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (goal_id) REFERENCES goal_definitions(goal_id)
);

CREATE INDEX IF NOT EXISTS idx_goal_audit_goal ON goal_change_audit(goal_id);
"""


MIGRATION_V24 = """
-- Schema Version 24: Autonomous Workflow Optimization & Process Intelligence Engine

CREATE TABLE IF NOT EXISTS proc_execution_traces (
    trace_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    total_duration_sec REAL NOT NULL DEFAULT 0.0,
    total_waiting_sec REAL NOT NULL DEFAULT 0.0,
    total_active_sec REAL NOT NULL DEFAULT 0.0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    is_complete INTEGER NOT NULL DEFAULT 0,
    events_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_proc_trace_workflow ON proc_execution_traces(workflow_id);
CREATE INDEX IF NOT EXISTS idx_proc_trace_status ON proc_execution_traces(status);

CREATE TABLE IF NOT EXISTS proc_events (
    event_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    parent_task_id TEXT,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    duration_sec REAL NOT NULL DEFAULT 0.0,
    waiting_time_sec REAL NOT NULL DEFAULT 0.0,
    error_category TEXT,
    resource_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (trace_id) REFERENCES proc_execution_traces(trace_id)
);

CREATE INDEX IF NOT EXISTS idx_proc_event_trace ON proc_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_proc_event_task ON proc_events(task_id);

CREATE TABLE IF NOT EXISTS proc_graphs (
    graph_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    nodes_json TEXT NOT NULL DEFAULT '{}',
    edges_json TEXT NOT NULL DEFAULT '[]',
    common_paths_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_proc_graph_workflow ON proc_graphs(workflow_id);

CREATE TABLE IF NOT EXISTS proc_performance_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    trace_count INTEGER NOT NULL DEFAULT 0,
    mean_duration_sec REAL NOT NULL DEFAULT 0.0,
    median_duration_sec REAL NOT NULL DEFAULT 0.0,
    p90_duration_sec REAL NOT NULL DEFAULT 0.0,
    p95_duration_sec REAL NOT NULL DEFAULT 0.0,
    p99_duration_sec REAL NOT NULL DEFAULT 0.0,
    mean_waiting_time_sec REAL NOT NULL DEFAULT 0.0,
    active_to_wait_ratio REAL NOT NULL DEFAULT 0.0,
    overall_failure_rate REAL NOT NULL DEFAULT 0.0,
    retry_frequency_per_trace REAL NOT NULL DEFAULT 0.0,
    assessed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_proc_perf_workflow ON proc_performance_snapshots(workflow_id);

CREATE TABLE IF NOT EXISTS proc_bottleneck_findings (
    finding_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    component_id TEXT NOT NULL,
    bottleneck_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    estimated_delay_sec REAL NOT NULL DEFAULT 0.0,
    frequency_ratio REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 1.0,
    potential_causes_json TEXT NOT NULL DEFAULT '[]',
    recommended_action TEXT NOT NULL DEFAULT '',
    supporting_trace_ids_json TEXT NOT NULL DEFAULT '[]',
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_proc_bottle_workflow ON proc_bottleneck_findings(workflow_id);

CREATE TABLE IF NOT EXISTS proc_deviations (
    deviation_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    deviation_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    policy_rule_violated TEXT,
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_proc_dev_workflow ON proc_deviations(workflow_id);

CREATE TABLE IF NOT EXISTS proc_failure_patterns (
    pattern_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    error_type TEXT NOT NULL,
    affected_tasks_json TEXT NOT NULL DEFAULT '[]',
    occurrence_count INTEGER NOT NULL DEFAULT 0,
    total_rework_duration_sec REAL NOT NULL DEFAULT 0.0,
    estimated_rework_cost REAL NOT NULL DEFAULT 0.0,
    identified_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_proc_fail_workflow ON proc_failure_patterns(workflow_id);

CREATE TABLE IF NOT EXISTS proc_optimization_candidates (
    candidate_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    current_version INTEGER NOT NULL DEFAULT 1,
    optimization_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    current_behavior TEXT NOT NULL,
    proposed_behavior TEXT NOT NULL,
    expected_time_reduction_pct REAL NOT NULL DEFAULT 0.0,
    expected_cost_reduction_pct REAL NOT NULL DEFAULT 0.0,
    reversibility_score REAL NOT NULL DEFAULT 1.0,
    validation_strategy TEXT NOT NULL,
    rollback_strategy TEXT NOT NULL,
    supporting_evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_proc_opt_workflow ON proc_optimization_candidates(workflow_id);

CREATE TABLE IF NOT EXISTS proc_experiments (
    experiment_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    baseline_trace_count INTEGER NOT NULL DEFAULT 0,
    target_trace_count INTEGER NOT NULL DEFAULT 0,
    guardrail_metrics_json TEXT NOT NULL DEFAULT '{}',
    observed_improvement_pct REAL NOT NULL DEFAULT 0.0,
    is_guardrail_breached INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (candidate_id) REFERENCES proc_optimization_candidates(candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_proc_exp_candidate ON proc_experiments(candidate_id);

CREATE TABLE IF NOT EXISTS proc_change_governance (
    governance_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL,
    approved_by TEXT,
    approval_token TEXT,
    change_status TEXT NOT NULL DEFAULT 'PENDING_APPROVAL',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES proc_optimization_candidates(candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_proc_gov_workflow ON proc_change_governance(workflow_id);
"""


MIGRATION_V25 = """
-- Schema Version 25: Autonomous Operations Center, System Observability & Incident Intelligence

CREATE TABLE IF NOT EXISTS ops_service_inventory (
    service_id TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    description TEXT NOT NULL,
    version TEXT NOT NULL,
    environment TEXT NOT NULL,
    owner TEXT NOT NULL,
    criticality TEXT NOT NULL,
    health_endpoint TEXT,
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    current_state TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_observed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_svc_owner ON ops_service_inventory(owner);
CREATE INDEX IF NOT EXISTS idx_ops_svc_crit ON ops_service_inventory(criticality);

CREATE TABLE IF NOT EXISTS ops_health_observations (
    observation_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    health_state TEXT NOT NULL,
    latency_ms REAL NOT NULL DEFAULT 0.0,
    error_rate REAL NOT NULL DEFAULT 0.0,
    status_message TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    is_stale INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (service_id) REFERENCES ops_service_inventory(service_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_obs_svc ON ops_health_observations(service_id);
CREATE INDEX IF NOT EXISTS idx_ops_obs_time ON ops_health_observations(observed_at);

CREATE TABLE IF NOT EXISTS ops_telemetry_metrics (
    metric_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES ops_service_inventory(service_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_met_svc ON ops_telemetry_metrics(service_id, metric_name);

CREATE TABLE IF NOT EXISTS ops_telemetry_logs (
    log_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    error_category TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES ops_service_inventory(service_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_log_svc ON ops_telemetry_logs(service_id);

CREATE TABLE IF NOT EXISTS ops_telemetry_spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    operation_name TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    status_code INTEGER NOT NULL DEFAULT 200,
    parent_span_id TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES ops_service_inventory(service_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_span_trace ON ops_telemetry_spans(trace_id);

CREATE TABLE IF NOT EXISTS ops_slo_definitions (
    slo_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    name TEXT NOT NULL,
    target_pct REAL NOT NULL,
    current_sli_pct REAL NOT NULL DEFAULT 100.0,
    error_budget_remaining_pct REAL NOT NULL DEFAULT 100.0,
    burn_rate REAL NOT NULL DEFAULT 0.0,
    assessed_at TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES ops_service_inventory(service_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_slo_svc ON ops_slo_definitions(service_id);

CREATE TABLE IF NOT EXISTS ops_incident_alerts (
    alert_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    alert_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    symptom_description TEXT NOT NULL,
    supporting_metric_value REAL NOT NULL DEFAULT 0.0,
    correlated_incident_id TEXT,
    detected_at TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES ops_service_inventory(service_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_alert_corr ON ops_incident_alerts(correlated_incident_id);

CREATE TABLE IF NOT EXISTS ops_incidents (
    incident_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    state TEXT NOT NULL,
    primary_service_id TEXT NOT NULL,
    affected_services_json TEXT NOT NULL DEFAULT '[]',
    correlated_alert_ids_json TEXT NOT NULL DEFAULT '[]',
    assigned_to TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (primary_service_id) REFERENCES ops_service_inventory(service_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_inc_state ON ops_incidents(state);
CREATE INDEX IF NOT EXISTS idx_ops_inc_sev ON ops_incidents(severity);

CREATE TABLE IF NOT EXISTS ops_root_cause_findings (
    finding_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    candidate_cause TEXT NOT NULL,
    confidence REAL NOT NULL,
    supporting_evidence_json TEXT NOT NULL DEFAULT '[]',
    contradictory_evidence_json TEXT NOT NULL DEFAULT '[]',
    investigated_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES ops_incidents(incident_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_rc_inc ON ops_root_cause_findings(incident_id);

CREATE TABLE IF NOT EXISTS ops_impact_assessments (
    assessment_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    blast_radius_score REAL NOT NULL,
    affected_workflows_json TEXT NOT NULL DEFAULT '[]',
    data_integrity_risk TEXT NOT NULL DEFAULT 'LOW',
    operational_disruption TEXT NOT NULL DEFAULT 'LOW',
    financial_exposure_estimate REAL NOT NULL DEFAULT 0.0,
    assessed_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES ops_incidents(incident_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_imp_inc ON ops_impact_assessments(incident_id);

CREATE TABLE IF NOT EXISTS ops_recovery_proposals (
    proposal_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    target_service_id TEXT NOT NULL,
    action_name TEXT NOT NULL,
    rationale TEXT NOT NULL,
    expected_benefit TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    requires_human_approval INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    approval_token TEXT,
    approved_by TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES ops_incidents(incident_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_rec_inc ON ops_recovery_proposals(incident_id);

CREATE TABLE IF NOT EXISTS ops_postmortem_reports (
    report_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    root_cause TEXT NOT NULL,
    timeline_events_json TEXT NOT NULL DEFAULT '[]',
    what_went_well_json TEXT NOT NULL DEFAULT '[]',
    what_failed_json TEXT NOT NULL DEFAULT '[]',
    action_items_json TEXT NOT NULL DEFAULT '[]',
    published_at TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES ops_incidents(incident_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_pm_inc ON ops_postmortem_reports(incident_id);
"""


MIGRATION_V26 = """
-- Schema Version 26: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery

CREATE TABLE IF NOT EXISTS rel_components (
    component_id TEXT PRIMARY KEY,
    component_name TEXT NOT NULL,
    criticality TEXT NOT NULL,
    owner TEXT NOT NULL,
    failure_domain TEXT NOT NULL,
    data_ownership TEXT NOT NULL,
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    recovery_procedure TEXT NOT NULL DEFAULT 'DEFAULT_RESTART',
    backup_strategy TEXT NOT NULL DEFAULT 'SNAPSHOT',
    redundancy_config TEXT NOT NULL DEFAULT 'N+1',
    failover_readiness TEXT NOT NULL DEFAULT 'READY',
    last_assessment_at TEXT,
    last_recovery_drill_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rel_comp_crit ON rel_components(criticality);

CREATE TABLE IF NOT EXISTS rel_failure_modes (
    mode_id TEXT PRIMARY KEY,
    component_id TEXT NOT NULL,
    failure_mode_name TEXT NOT NULL,
    potential_causes_json TEXT NOT NULL DEFAULT '[]',
    local_impact TEXT NOT NULL,
    downstream_impact TEXT NOT NULL,
    detectability_score INTEGER NOT NULL DEFAULT 5,
    severity_score INTEGER NOT NULL DEFAULT 5,
    probability_score INTEGER NOT NULL DEFAULT 5,
    risk_priority_number INTEGER NOT NULL DEFAULT 125,
    is_spof INTEGER NOT NULL DEFAULT 0,
    existing_controls_json TEXT NOT NULL DEFAULT '[]',
    recommended_mitigation TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (component_id) REFERENCES rel_components(component_id)
);

CREATE INDEX IF NOT EXISTS idx_rel_fm_comp ON rel_failure_modes(component_id);
CREATE INDEX IF NOT EXISTS idx_rel_fm_spof ON rel_failure_modes(is_spof);

CREATE TABLE IF NOT EXISTS rel_resilience_objectives (
    objective_id TEXT PRIMARY KEY,
    component_id TEXT NOT NULL,
    objective_type TEXT NOT NULL,
    target_value REAL NOT NULL,
    unit TEXT NOT NULL,
    demonstrated_value REAL,
    is_demonstrated INTEGER NOT NULL DEFAULT 0,
    verification_evidence TEXT,
    last_verified_at TEXT,
    FOREIGN KEY (component_id) REFERENCES rel_components(component_id)
);

CREATE INDEX IF NOT EXISTS idx_rel_obj_comp ON rel_resilience_objectives(component_id);

CREATE TABLE IF NOT EXISTS rel_failure_scenarios (
    scenario_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    target_environment TEXT NOT NULL,
    affected_components_json TEXT NOT NULL DEFAULT '[]',
    preconditions_json TEXT NOT NULL DEFAULT '[]',
    injection_method TEXT NOT NULL DEFAULT 'SIMULATION',
    safety_constraints_json TEXT NOT NULL DEFAULT '[]',
    expected_behavior TEXT NOT NULL,
    abort_conditions_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rel_fault_experiments (
    experiment_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    target_environment TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL DEFAULT 'DEFINED',
    max_duration_sec REAL NOT NULL DEFAULT 300.0,
    actual_duration_sec REAL NOT NULL DEFAULT 0.0,
    containment_successful INTEGER NOT NULL DEFAULT 0,
    cascading_failure_detected INTEGER NOT NULL DEFAULT 0,
    approval_token TEXT,
    approved_by TEXT,
    started_at TEXT,
    completed_at TEXT,
    observations_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (scenario_id) REFERENCES rel_failure_scenarios(scenario_id)
);

CREATE INDEX IF NOT EXISTS idx_rel_exp_state ON rel_fault_experiments(lifecycle_state);

CREATE TABLE IF NOT EXISTS rel_backups (
    backup_id TEXT PRIMARY KEY,
    data_source TEXT NOT NULL,
    backup_type TEXT NOT NULL,
    version TEXT NOT NULL,
    storage_reference TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    is_encrypted INTEGER NOT NULL DEFAULT 1,
    retention_days INTEGER NOT NULL DEFAULT 30,
    record_count INTEGER NOT NULL DEFAULT 0,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    validation_status TEXT NOT NULL DEFAULT 'PENDING',
    last_validated_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rel_bak_source ON rel_backups(data_source);
CREATE INDEX IF NOT EXISTS idx_rel_bak_status ON rel_backups(validation_status);

CREATE TABLE IF NOT EXISTS rel_backup_validations (
    validation_id TEXT PRIMARY KEY,
    backup_id TEXT NOT NULL,
    status TEXT NOT NULL,
    checksum_verified INTEGER NOT NULL DEFAULT 0,
    schema_compatible INTEGER NOT NULL DEFAULT 0,
    isolated_restore_tested INTEGER NOT NULL DEFAULT 0,
    record_count_matches INTEGER NOT NULL DEFAULT 0,
    validation_notes TEXT,
    validated_at TEXT NOT NULL,
    FOREIGN KEY (backup_id) REFERENCES rel_backups(backup_id)
);

CREATE INDEX IF NOT EXISTS idx_rel_val_bak ON rel_backup_validations(backup_id);

CREATE TABLE IF NOT EXISTS rel_dr_plans (
    plan_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    disaster_scenario TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    affected_services_json TEXT NOT NULL DEFAULT '[]',
    recovery_priority INTEGER NOT NULL DEFAULT 1,
    strategy TEXT NOT NULL,
    dependency_order_json TEXT NOT NULL DEFAULT '[]',
    target_rto_sec REAL NOT NULL DEFAULT 300.0,
    target_rpo_sec REAL NOT NULL DEFAULT 60.0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rel_dr_executions (
    execution_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    target_environment TEXT NOT NULL,
    status TEXT NOT NULL,
    approval_token TEXT,
    approved_by TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_sec REAL NOT NULL DEFAULT 0.0,
    steps_executed_json TEXT NOT NULL DEFAULT '[]',
    errors_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (plan_id) REFERENCES rel_dr_plans(plan_id)
);

CREATE TABLE IF NOT EXISTS rel_recovery_verifications (
    verification_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    component_id TEXT NOT NULL,
    service_responsive INTEGER NOT NULL DEFAULT 0,
    data_integrity_verified INTEGER NOT NULL DEFAULT 0,
    distributed_state_reconciled INTEGER NOT NULL DEFAULT 0,
    actual_rto_sec REAL NOT NULL,
    actual_rpo_sec REAL NOT NULL,
    rto_compliant INTEGER NOT NULL DEFAULT 0,
    rpo_compliant INTEGER NOT NULL DEFAULT 0,
    findings_json TEXT NOT NULL DEFAULT '[]',
    verified_at TEXT NOT NULL,
    FOREIGN KEY (execution_id) REFERENCES rel_dr_executions(execution_id)
);

CREATE TABLE IF NOT EXISTS rel_state_integrity_reports (
    finding_id TEXT PRIMARY KEY,
    subsystem TEXT NOT NULL,
    divergence_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    details TEXT,
    detected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rel_resilience_regressions (
    regression_id TEXT PRIMARY KEY,
    component_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    baseline_value REAL NOT NULL,
    current_value REAL NOT NULL,
    degradation_pct REAL NOT NULL,
    detected_at TEXT NOT NULL
);
"""

MIGRATION_V27 = """
-- Schema Version 27: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence

CREATE TABLE IF NOT EXISTS cap_resources (
    resource_id TEXT PRIMARY KEY,
    resource_name TEXT NOT NULL,
    dimension TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    source TEXT NOT NULL,
    total_capacity REAL NOT NULL,
    unit TEXT NOT NULL,
    associated_service TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cap_res_dim ON cap_resources(dimension);
CREATE INDEX IF NOT EXISTS idx_cap_res_svc ON cap_resources(associated_service);

CREATE TABLE IF NOT EXISTS cap_measurements (
    measurement_id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    current_value REAL NOT NULL,
    configured_capacity REAL NOT NULL,
    available_headroom REAL NOT NULL,
    utilization_pct REAL NOT NULL,
    unit TEXT NOT NULL,
    collection_status TEXT NOT NULL,
    data_confidence REAL NOT NULL,
    FOREIGN KEY(resource_id) REFERENCES cap_resources(resource_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cap_meas_res_ts ON cap_measurements(resource_id, timestamp);

CREATE TABLE IF NOT EXISTS cap_workload_demands (
    profile_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    workload_name TEXT NOT NULL,
    avg_cpu_consumption REAL NOT NULL,
    avg_memory_mb REAL NOT NULL,
    avg_duration_sec REAL NOT NULL,
    request_rate_per_sec REAL DEFAULT 0.0,
    burstiness_index REAL DEFAULT 1.0,
    concurrency_requirement INTEGER DEFAULT 1,
    sample_count INTEGER DEFAULT 1,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cap_dem_cat ON cap_workload_demands(category);

CREATE TABLE IF NOT EXISTS cap_forecasts (
    forecast_id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL,
    horizon TEXT NOT NULL,
    forecasted_demand REAL NOT NULL,
    current_capacity REAL NOT NULL,
    projected_headroom REAL NOT NULL,
    projected_utilization_pct REAL NOT NULL,
    estimated_saturation_hours REAL,
    confidence_lower_bound REAL NOT NULL,
    confidence_upper_bound REAL NOT NULL,
    confidence_score REAL NOT NULL,
    model_method TEXT NOT NULL,
    data_quality TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY(resource_id) REFERENCES cap_resources(resource_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cap_fc_res_hor ON cap_forecasts(resource_id, horizon);

CREATE TABLE IF NOT EXISTS cap_risks (
    risk_id TEXT PRIMARY KEY,
    resource_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    observed_utilization_pct REAL NOT NULL,
    estimated_time_to_saturation_hours REAL,
    likely_cause TEXT,
    expected_operational_impact TEXT,
    recommended_mitigation TEXT,
    confidence_level REAL NOT NULL,
    is_resolved INTEGER DEFAULT 0,
    detected_at TEXT NOT NULL,
    FOREIGN KEY(resource_id) REFERENCES cap_resources(resource_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cap_risk_res ON cap_risks(resource_id);

CREATE TABLE IF NOT EXISTS cap_scenarios (
    scenario_id TEXT PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    workload_multiplier REAL NOT NULL,
    unavailable_resources_json TEXT DEFAULT '[]',
    quota_reduction_pct REAL DEFAULT 0.0,
    description TEXT
);

CREATE TABLE IF NOT EXISTS cap_simulations (
    simulation_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    max_projected_utilization_pct REAL NOT NULL,
    bottleneck_resources_json TEXT DEFAULT '[]',
    throughput_degradation_pct REAL DEFAULT 0.0,
    latency_increase_factor REAL DEFAULT 1.0,
    estimated_additional_cost_hr REAL DEFAULT 0.0,
    recommended_scaling_action TEXT,
    is_resilient INTEGER DEFAULT 1,
    simulated_at TEXT NOT NULL,
    FOREIGN KEY(scenario_id) REFERENCES cap_scenarios(scenario_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cap_plans (
    plan_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    horizon TEXT NOT NULL,
    current_health_posture TEXT NOT NULL,
    identified_gaps_json TEXT DEFAULT '[]',
    recommended_strategies_json TEXT DEFAULT '[]',
    estimated_total_cost_delta REAL DEFAULT 0.0,
    required_governance_mode TEXT NOT NULL,
    approval_token TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cap_scaling_proposals (
    proposal_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    strategy_type TEXT NOT NULL,
    from_capacity REAL NOT NULL,
    to_capacity REAL NOT NULL,
    cost_impact_per_hr REAL NOT NULL,
    status TEXT NOT NULL,
    approval_token TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES cap_plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cap_scaling_executions (
    execution_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    applied_capacity REAL NOT NULL,
    previous_capacity REAL NOT NULL,
    status TEXT NOT NULL,
    executed_by TEXT NOT NULL,
    execution_notes TEXT,
    executed_at TEXT NOT NULL,
    FOREIGN KEY(proposal_id) REFERENCES cap_scaling_proposals(proposal_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cap_forecast_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    forecast_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    predicted_demand REAL NOT NULL,
    actual_demand REAL NOT NULL,
    absolute_error REAL NOT NULL,
    percentage_error REAL NOT NULL,
    within_confidence_bounds INTEGER NOT NULL,
    evaluated_at TEXT NOT NULL
);
"""

MIGRATION_V28 = """
-- Schema Version 28: Autonomous Infrastructure Provisioning, Deployment & Environment Lifecycle Management

CREATE TABLE IF NOT EXISTS infra_providers (
    provider_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    supported_capabilities_json TEXT DEFAULT '[]',
    auth_secret_ref TEXT,
    is_active INTEGER DEFAULT 1,
    metadata_json TEXT DEFAULT '{}',
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS infra_blueprints (
    blueprint_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    environment_type TEXT NOT NULL,
    resource_definitions_json TEXT DEFAULT '[]',
    dependencies_json TEXT DEFAULT '[]',
    network_spec_json TEXT DEFAULT '{}',
    storage_spec_json TEXT DEFAULT '{}',
    compute_spec_json TEXT DEFAULT '{}',
    required_secrets_json TEXT DEFAULT '[]',
    lifecycle_ttl_hours REAL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_infra_bp_env ON infra_blueprints(environment_type);

CREATE TABLE IF NOT EXISTS infra_environments (
    environment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    environment_type TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    blueprint_id TEXT NOT NULL,
    current_state TEXT NOT NULL,
    region TEXT NOT NULL,
    owner TEXT NOT NULL,
    active_release_version TEXT,
    active_configuration_version TEXT NOT NULL,
    expiration_timestamp TEXT,
    last_verified_at TEXT,
    is_locked INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(provider_id) REFERENCES infra_providers(provider_id),
    FOREIGN KEY(blueprint_id) REFERENCES infra_blueprints(blueprint_id)
);
CREATE INDEX IF NOT EXISTS idx_infra_env_state ON infra_environments(current_state);

CREATE TABLE IF NOT EXISTS infra_environment_resources (
    resource_id TEXT PRIMARY KEY,
    environment_id TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    status TEXT NOT NULL,
    provider_resource_ref TEXT,
    capacity_allocated REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(environment_id) REFERENCES infra_environments(environment_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_infra_env_res ON infra_environment_resources(environment_id);

CREATE TABLE IF NOT EXISTS infra_provisioning_plans (
    plan_id TEXT PRIMARY KEY,
    environment_id TEXT NOT NULL,
    blueprint_id TEXT NOT NULL,
    actions_json TEXT DEFAULT '[]',
    dependency_order_json TEXT DEFAULT '[]',
    capacity_verified INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0.0,
    requires_approval INTEGER DEFAULT 1,
    approval_token TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(environment_id) REFERENCES infra_environments(environment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS infra_provisioning_executions (
    execution_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    status TEXT NOT NULL,
    executed_actions_json TEXT DEFAULT '[]',
    errors_json TEXT DEFAULT '[]',
    executed_at TEXT NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES infra_provisioning_plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS infra_releases (
    release_id TEXT PRIMARY KEY,
    application_name TEXT NOT NULL,
    version TEXT NOT NULL,
    artifact_uri TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS infra_deployments (
    deployment_id TEXT PRIMARY KEY,
    environment_id TEXT NOT NULL,
    release_id TEXT NOT NULL,
    strategy TEXT NOT NULL,
    status TEXT NOT NULL,
    previous_release_id TEXT,
    approval_token TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(environment_id) REFERENCES infra_environments(environment_id) ON DELETE CASCADE,
    FOREIGN KEY(release_id) REFERENCES infra_releases(release_id)
);
CREATE INDEX IF NOT EXISTS idx_infra_dep_env ON infra_deployments(environment_id);

CREATE TABLE IF NOT EXISTS infra_verifications (
    verification_id TEXT PRIMARY KEY,
    deployment_id TEXT NOT NULL,
    environment_id TEXT NOT NULL,
    infrastructure_ready INTEGER NOT NULL,
    application_ready INTEGER NOT NULL,
    operational_ready INTEGER NOT NULL,
    is_fully_verified INTEGER NOT NULL,
    check_results_json TEXT DEFAULT '{}',
    verified_at TEXT NOT NULL,
    FOREIGN KEY(deployment_id) REFERENCES infra_deployments(deployment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS infra_rollbacks (
    rollback_id TEXT PRIMARY KEY,
    deployment_id TEXT NOT NULL,
    target_environment_id TEXT NOT NULL,
    from_release_id TEXT NOT NULL,
    to_release_id TEXT NOT NULL,
    approval_token TEXT,
    status TEXT NOT NULL,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS infra_drift_findings (
    drift_id TEXT PRIMARY KEY,
    environment_id TEXT NOT NULL,
    drift_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    expected_state TEXT NOT NULL,
    actual_state TEXT NOT NULL,
    remediation_suggestion TEXT NOT NULL,
    is_reconciled INTEGER DEFAULT 0,
    detected_at TEXT NOT NULL,
    FOREIGN KEY(environment_id) REFERENCES infra_environments(environment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS infra_decommission_plans (
    decommission_id TEXT PRIMARY KEY,
    environment_id TEXT NOT NULL,
    resources_to_delete_json TEXT DEFAULT '[]',
    data_retention_preserved INTEGER DEFAULT 1,
    approval_token TEXT,
    status TEXT NOT NULL,
    executed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(environment_id) REFERENCES infra_environments(environment_id) ON DELETE CASCADE
);
"""

MIGRATION_V29 = """
-- Schema Version 29: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering

CREATE TABLE IF NOT EXISTS delivery_repositories (
    repository_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    clone_url TEXT NOT NULL,
    default_branch TEXT DEFAULT 'main',
    is_active INTEGER DEFAULT 1,
    metadata_json TEXT DEFAULT '{}',
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_revisions (
    revision_id TEXT PRIMARY KEY,
    repository_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    branch TEXT NOT NULL,
    author TEXT NOT NULL,
    commit_message TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    parent_commits_json TEXT DEFAULT '[]',
    FOREIGN KEY(repository_id) REFERENCES delivery_repositories(repository_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_impact_reports (
    report_id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    changed_files_json TEXT DEFAULT '[]',
    change_categories_json TEXT DEFAULT '[]',
    impacted_modules_json TEXT DEFAULT '[]',
    relevant_test_suites_json TEXT DEFAULT '[]',
    migration_detected INTEGER DEFAULT 0,
    security_sensitive INTEGER DEFAULT 0,
    confidence_score REAL DEFAULT 1.0,
    evidence_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(revision_id) REFERENCES delivery_revisions(revision_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_pipeline_definitions (
    pipeline_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    repository_id TEXT NOT NULL,
    stages_json TEXT DEFAULT '[]',
    triggers_json TEXT DEFAULT '[]',
    env_vars_json TEXT DEFAULT '{}',
    timeout_seconds INTEGER DEFAULT 1800,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY(repository_id) REFERENCES delivery_repositories(repository_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_pipeline_executions (
    execution_id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    status TEXT NOT NULL,
    stages_executed_json TEXT DEFAULT '[]',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    total_duration_seconds REAL DEFAULT 0.0,
    error_summary TEXT,
    FOREIGN KEY(pipeline_id) REFERENCES delivery_pipeline_definitions(pipeline_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_stage_executions (
    stage_id TEXT PRIMARY KEY,
    pipeline_execution_id TEXT NOT NULL,
    stage_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_seconds REAL DEFAULT 0.0,
    exit_code INTEGER DEFAULT 0,
    logs TEXT DEFAULT '',
    error_message TEXT,
    FOREIGN KEY(pipeline_execution_id) REFERENCES delivery_pipeline_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_build_executions (
    build_id TEXT PRIMARY KEY,
    pipeline_execution_id TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL,
    artifact_paths_json TEXT DEFAULT '[]',
    logs TEXT DEFAULT '',
    duration_seconds REAL DEFAULT 0.0,
    executed_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_execution_id) REFERENCES delivery_pipeline_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_test_executions (
    test_run_id TEXT PRIMARY KEY,
    pipeline_execution_id TEXT NOT NULL,
    suite_name TEXT NOT NULL,
    total_tests INTEGER DEFAULT 0,
    passed_tests INTEGER DEFAULT 0,
    failed_tests INTEGER DEFAULT 0,
    skipped_tests INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0.0,
    coverage_pct REAL,
    status TEXT NOT NULL,
    failure_details_json TEXT DEFAULT '[]',
    executed_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_execution_id) REFERENCES delivery_pipeline_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_quality_gate_results (
    gate_id TEXT PRIMARY KEY,
    pipeline_execution_id TEXT NOT NULL,
    status TEXT NOT NULL,
    score REAL DEFAULT 1.0,
    metrics_json TEXT DEFAULT '{}',
    violations_json TEXT DEFAULT '[]',
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_execution_id) REFERENCES delivery_pipeline_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_dependency_assessments (
    assessment_id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL,
    direct_dependency_count INTEGER DEFAULT 0,
    transitive_dependency_count INTEGER DEFAULT 0,
    vulnerabilities_detected INTEGER DEFAULT 0,
    deprecated_dependencies_json TEXT DEFAULT '[]',
    outdated_dependencies_json TEXT DEFAULT '[]',
    findings_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(revision_id) REFERENCES delivery_revisions(revision_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_security_assessments (
    assessment_id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL,
    secrets_found_count INTEGER DEFAULT 0,
    sast_violations_count INTEGER DEFAULT 0,
    highest_severity TEXT DEFAULT 'INFO',
    findings_json TEXT DEFAULT '[]',
    is_passing INTEGER DEFAULT 1,
    scanned_at TEXT NOT NULL,
    FOREIGN KEY(revision_id) REFERENCES delivery_revisions(revision_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_artifacts (
    artifact_id TEXT PRIMARY KEY,
    pipeline_execution_id TEXT NOT NULL,
    name TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    storage_uri TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_execution_id) REFERENCES delivery_pipeline_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_attestations (
    attestation_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    predicate_type TEXT DEFAULT 'https://slsa.dev/provenance/v1',
    builder_id TEXT NOT NULL,
    source_repository TEXT NOT NULL,
    source_commit TEXT NOT NULL,
    build_config_json TEXT DEFAULT '{}',
    is_signed INTEGER DEFAULT 0,
    signature_ref TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(artifact_id) REFERENCES delivery_artifacts(artifact_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_regression_findings (
    regression_id TEXT PRIMARY KEY,
    pipeline_execution_id TEXT NOT NULL,
    component_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    baseline_value REAL NOT NULL,
    current_value REAL NOT NULL,
    delta_pct REAL NOT NULL,
    severity TEXT DEFAULT 'MEDIUM',
    description TEXT,
    detected_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_execution_id) REFERENCES delivery_pipeline_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_repair_attempts (
    repair_id TEXT PRIMARY KEY,
    pipeline_execution_id TEXT NOT NULL,
    failure_type TEXT NOT NULL,
    proposed_patch TEXT NOT NULL,
    applied INTEGER DEFAULT 0,
    retest_success INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 1,
    max_retries_allowed INTEGER DEFAULT 3,
    approval_token TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_execution_id) REFERENCES delivery_pipeline_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_release_candidates (
    candidate_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    source_revision_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    release_notes TEXT,
    approval_token TEXT,
    approver TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(artifact_id) REFERENCES delivery_artifacts(artifact_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS delivery_deployment_handoffs (
    handoff_id TEXT PRIMARY KEY,
    release_candidate_id TEXT NOT NULL,
    target_environment_id TEXT NOT NULL,
    deployment_strategy TEXT DEFAULT 'DIRECT',
    status TEXT NOT NULL,
    module43_deployment_id TEXT,
    verification_evidence_json TEXT DEFAULT '{}',
    requested_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(release_candidate_id) REFERENCES delivery_release_candidates(candidate_id) ON DELETE CASCADE
);
"""

MIGRATION_V30 = """
-- Schema Version 30: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence

CREATE TABLE IF NOT EXISTS qa_projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    repository_ref TEXT NOT NULL,
    framework TEXT DEFAULT 'python-unittest',
    is_active INTEGER DEFAULT 1,
    metadata_json TEXT DEFAULT '{}',
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_requirements (
    requirement_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    requirement_type TEXT NOT NULL,
    source_reference TEXT DEFAULT '',
    is_ambiguous INTEGER DEFAULT 0,
    ambiguity_notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES qa_projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_acceptance_criteria (
    criterion_id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL,
    expected_behavior TEXT NOT NULL,
    preconditions_json TEXT DEFAULT '[]',
    inputs_json TEXT DEFAULT '{}',
    expected_outputs_json TEXT DEFAULT '{}',
    failure_conditions_json TEXT DEFAULT '[]',
    priority INTEGER DEFAULT 1,
    confidence REAL DEFAULT 1.0,
    FOREIGN KEY(requirement_id) REFERENCES qa_requirements(requirement_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_test_strategies (
    strategy_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    target_categories_json TEXT DEFAULT '[]',
    risk_weighting_json TEXT DEFAULT '{}',
    allocated_budget_seconds REAL DEFAULT 600.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES qa_projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_test_cases (
    test_case_id TEXT PRIMARY KEY,
    criterion_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    objective TEXT NOT NULL,
    inputs_json TEXT DEFAULT '{}',
    assertions_json TEXT DEFAULT '[]',
    is_edge_case INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(criterion_id) REFERENCES qa_acceptance_criteria(criterion_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_missions (
    mission_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(project_id) REFERENCES qa_projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_executions (
    execution_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    test_case_id TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_seconds REAL DEFAULT 0.0,
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    executed_at TEXT NOT NULL,
    FOREIGN KEY(mission_id) REFERENCES qa_missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_results (
    result_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    observed_output_json TEXT DEFAULT '{}',
    discrepancies_json TEXT DEFAULT '[]',
    evidence_ids_json TEXT DEFAULT '[]',
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY(execution_id) REFERENCES qa_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_evidence (
    evidence_id TEXT PRIMARY KEY,
    execution_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    FOREIGN KEY(execution_id) REFERENCES qa_executions(execution_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_coverage_records (
    coverage_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    requirements_total INTEGER DEFAULT 0,
    requirements_covered INTEGER DEFAULT 0,
    coverage_pct REAL DEFAULT 0.0,
    gap_details_json TEXT DEFAULT '[]',
    calculated_at TEXT NOT NULL,
    FOREIGN KEY(mission_id) REFERENCES qa_missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_defects (
    defect_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    reproduction_steps_json TEXT DEFAULT '[]',
    stack_trace TEXT,
    is_reproduced INTEGER DEFAULT 1,
    is_resolved INTEGER DEFAULT 0,
    detected_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES qa_projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_regressions (
    regression_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    defect_id TEXT NOT NULL,
    component_name TEXT NOT NULL,
    baseline_revision TEXT NOT NULL,
    current_revision TEXT NOT NULL,
    description TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES qa_projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_flaky_tests (
    flaky_id TEXT PRIMARY KEY,
    test_case_id TEXT NOT NULL,
    runs_evaluated INTEGER DEFAULT 0,
    passes INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    variance_score REAL DEFAULT 0.0,
    classification TEXT NOT NULL,
    assessed_at TEXT NOT NULL,
    FOREIGN KEY(test_case_id) REFERENCES qa_test_cases(test_case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_mutations (
    mutation_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    mutant_type TEXT NOT NULL,
    killed INTEGER NOT NULL,
    surviving_details TEXT,
    executed_at TEXT NOT NULL,
    FOREIGN KEY(mission_id) REFERENCES qa_missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_performance_assessments (
    assessment_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    latency_p50_ms REAL DEFAULT 0.0,
    latency_p95_ms REAL DEFAULT 0.0,
    latency_p99_ms REAL DEFAULT 0.0,
    throughput_rps REAL DEFAULT 0.0,
    error_rate_pct REAL DEFAULT 0.0,
    cpu_utilization_pct REAL DEFAULT 0.0,
    memory_mb REAL DEFAULT 0.0,
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY(mission_id) REFERENCES qa_missions(mission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_quality_assessments (
    assessment_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    mission_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    overall_score REAL DEFAULT 1.0,
    functional_pass_rate REAL DEFAULT 1.0,
    coverage_score REAL DEFAULT 1.0,
    unresolved_defects_count INTEGER DEFAULT 0,
    regressions_count INTEGER DEFAULT 0,
    flaky_tests_count INTEGER DEFAULT 0,
    dimension_scores_json TEXT DEFAULT '{}',
    summary_notes TEXT DEFAULT '',
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES qa_projects(project_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_repair_verifications (
    repair_verification_id TEXT PRIMARY KEY,
    defect_id TEXT NOT NULL,
    patch_ref TEXT NOT NULL,
    retest_passed INTEGER NOT NULL,
    regressions_found INTEGER DEFAULT 0,
    verification_evidence_json TEXT DEFAULT '{}',
    verified_at TEXT NOT NULL,
    FOREIGN KEY(defect_id) REFERENCES qa_defects(defect_id) ON DELETE CASCADE
);
"""



MIGRATION_V31 = """
-- Schema Version 31: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation Engine

CREATE TABLE IF NOT EXISTS sec_assets (
    asset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL, -- APPLICATION, SERVICE, API, REPOSITORY, CONTAINER, INFRA_CONFIG
    owner TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'STAGING', -- DEV, STAGING, PRODUCTION, LAB
    discovery_source TEXT NOT NULL DEFAULT 'MANUAL',
    authorization_id TEXT,
    technology_stack_json TEXT DEFAULT '[]',
    exposure_tier TEXT NOT NULL DEFAULT 'INTERNAL', -- INTERNAL, RESTRICTED, PUBLIC
    criticality TEXT NOT NULL DEFAULT 'MEDIUM', -- LOW, MEDIUM, HIGH, MISSION_CRITICAL
    security_posture_score REAL DEFAULT 100.0,
    last_assessed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sec_authorizations (
    authorization_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    operator TEXT NOT NULL,
    owner_approval_ref TEXT NOT NULL,
    assessment_purpose TEXT NOT NULL,
    environment_tier TEXT NOT NULL,
    permitted_techniques_json TEXT DEFAULT '[]',
    allow_destructive INTEGER DEFAULT 0,
    rate_limit_rps INTEGER DEFAULT 10,
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    is_revoked INTEGER DEFAULT 0,
    revoked_reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sec_scopes (
    scope_id TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    permitted_endpoints_json TEXT DEFAULT '[]',
    excluded_endpoints_json TEXT DEFAULT '[]',
    permitted_components_json TEXT DEFAULT '[]',
    excluded_components_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(authorization_id) REFERENCES sec_authorizations(authorization_id) ON DELETE CASCADE,
    FOREIGN KEY(asset_id) REFERENCES sec_assets(asset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_assessments (
    assessment_id TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    assessment_type TEXT NOT NULL, -- STATIC_ANALYSIS, API_AUDIT, DEPENDENCY_SCA, SECRET_DETECTION, CONFIG_AUDIT, FULL_ASSESSMENT
    status TEXT NOT NULL DEFAULT 'INITIALIZED', -- INITIALIZED, RUNNING, COMPLETED, ABORTED, FAILED
    started_at TEXT NOT NULL,
    completed_at TEXT,
    findings_count INTEGER DEFAULT 0,
    critical_findings_count INTEGER DEFAULT 0,
    high_findings_count INTEGER DEFAULT 0,
    raw_telemetry_json TEXT DEFAULT '{}',
    FOREIGN KEY(authorization_id) REFERENCES sec_authorizations(authorization_id) ON DELETE CASCADE,
    FOREIGN KEY(asset_id) REFERENCES sec_assets(asset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_findings (
    finding_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL, -- INJECTION, AUTH_BYPASS, SECRET_LEAK, VULN_DEPENDENCY, MISCONFIG, XSS, CSRF, SSRF, CRYPTO
    severity TEXT NOT NULL, -- LOW, MEDIUM, HIGH, CRITICAL
    cwe_id TEXT,
    component_ref TEXT NOT NULL,
    location_ref TEXT,
    evidence_redacted_json TEXT DEFAULT '{}',
    fingerprint_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW', -- NEW, VALIDATED, FALSE_POSITIVE, MITIGATED, RESOLVED
    created_at TEXT NOT NULL,
    FOREIGN KEY(assessment_id) REFERENCES sec_assessments(assessment_id) ON DELETE CASCADE,
    FOREIGN KEY(asset_id) REFERENCES sec_assets(asset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_vulnerability_sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL, -- NVD_CVE, GITHUB_ADVISORY, CISA_KEV, OSV
    feed_url TEXT,
    confidence_weight REAL DEFAULT 1.0,
    last_synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sec_vulnerability_records (
    vulnerability_id TEXT PRIMARY KEY, -- CVE-XXXX-XXXX or GHSA-XXXX
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT NOT NULL,
    cvss_score REAL,
    cwe_id TEXT,
    affected_package TEXT NOT NULL,
    affected_version_ranges_json TEXT DEFAULT '[]',
    fixed_versions_json TEXT DEFAULT '[]',
    is_known_exploited INTEGER DEFAULT 0, -- CISA KEV
    published_at TEXT,
    modified_at TEXT,
    provenance_metadata_json TEXT DEFAULT '{}',
    FOREIGN KEY(source_id) REFERENCES sec_vulnerability_sources(source_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_validations (
    validation_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    method TEXT NOT NULL, -- STATIC_CONFIRM, SAFE_DYNAMIC_PROBE, TEST_HARNESS, REPRODUCTION
    outcome TEXT NOT NULL, -- CONFIRMED, LIKELY, UNCONFIRMED, FALSE_POSITIVE, NOT_SAFELY_TESTABLE
    is_destructive INTEGER DEFAULT 0,
    executed_at TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES sec_findings(finding_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_validation_evidence (
    evidence_id TEXT PRIMARY KEY,
    validation_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL, -- REDACTED_PAYLOAD, AST_NODE, HTTP_RESPONSE, CONFIG_SNIPPET
    redacted_content TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    FOREIGN KEY(validation_id) REFERENCES sec_validations(validation_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_attack_paths (
    path_id TEXT PRIMARY KEY,
    assessment_id TEXT NOT NULL,
    entry_asset_id TEXT NOT NULL,
    target_asset_id TEXT NOT NULL,
    path_hops_json TEXT DEFAULT '[]', -- Ordered list of hops crossing trust boundaries
    aggregate_risk_score REAL DEFAULT 0.0,
    is_validated INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(assessment_id) REFERENCES sec_assessments(assessment_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_risk_assessments (
    risk_assessment_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    technical_severity TEXT NOT NULL,
    exploitability_score REAL NOT NULL,
    asset_criticality_weight REAL NOT NULL,
    exposure_multiplier REAL NOT NULL,
    contextual_risk_score REAL NOT NULL, -- 0.0 to 100.0
    priority_level TEXT NOT NULL, -- P0_IMMEDIATE, P1_URGENT, P2_STANDARD, P3_LOW
    urgency_recommendation TEXT,
    calculated_at TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES sec_findings(finding_id) ON DELETE CASCADE,
    FOREIGN KEY(asset_id) REFERENCES sec_assets(asset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_remediation_plans (
    plan_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    recommended_action TEXT NOT NULL, -- UPGRADE_DEPENDENCY, REVISE_AST_PATTERN, RECONFIGURE, ROTATE_SECRET
    action_details_json TEXT DEFAULT '{}',
    breaking_change_risk TEXT DEFAULT 'LOW',
    estimated_complexity TEXT DEFAULT 'SIMPLE',
    patch_diff TEXT,
    status TEXT NOT NULL DEFAULT 'PROPOSED', -- PROPOSED, APPROVED, APPLIED, REJECTED
    created_at TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES sec_findings(finding_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_remediation_executions (
    execution_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    applied_by TEXT NOT NULL,
    patch_commit_ref TEXT,
    applied_at TEXT NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES sec_remediation_plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_fix_verifications (
    verification_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    module45_mission_id TEXT,
    original_probe_passed INTEGER NOT NULL, -- 1 means the exploit/weakness probe now fails safely
    regressions_found INTEGER DEFAULT 0,
    is_fully_resolved INTEGER NOT NULL,
    verified_at TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES sec_findings(finding_id) ON DELETE CASCADE,
    FOREIGN KEY(plan_id) REFERENCES sec_remediation_plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_exceptions (
    exception_id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    justification TEXT NOT NULL,
    compensating_controls TEXT,
    valid_until TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, EXPIRED, REVOKED
    granted_at TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES sec_findings(finding_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_posture_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    posture_score REAL NOT NULL,
    open_findings_count INTEGER DEFAULT 0,
    critical_count INTEGER DEFAULT 0,
    high_count INTEGER DEFAULT 0,
    active_exceptions_count INTEGER DEFAULT 0,
    snapshot_at TEXT NOT NULL,
    FOREIGN KEY(asset_id) REFERENCES sec_assets(asset_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sec_audit_records (
    audit_id TEXT PRIMARY KEY,
    authorization_id TEXT,
    asset_id TEXT,
    action_type TEXT NOT NULL, -- AUTH_CHECK, SCAN_START, VALIDATION_EXEC, SECRET_DETECT, FIX_APPLIED, KILL_SWITCH
    actor TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    timestamp TEXT NOT NULL
);
"""


MIGRATION_V32 = """
-- Schema Version 32: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence (Module 47)

CREATE TABLE IF NOT EXISTS soc_telemetry_sources (
    source_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    environment TEXT NOT NULL,
    asset_scope_json TEXT DEFAULT '[]',
    event_types_supported_json TEXT DEFAULT '[]',
    collection_method TEXT NOT NULL,
    auth_method TEXT NOT NULL,
    last_successful_ingestion TEXT,
    health_status TEXT NOT NULL DEFAULT 'HEALTHY',
    retention_days INTEGER DEFAULT 90,
    coverage_limitations_json TEXT DEFAULT '[]',
    registered_at TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS soc_security_events (
    event_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_category TEXT NOT NULL, -- IDENTITY, API, WORKLOAD, NETWORK, CONFIG, CLOUD
    event_timestamp TEXT NOT NULL,
    ingestion_timestamp TEXT NOT NULL,
    environment TEXT NOT NULL,
    asset_id TEXT,
    actor_id TEXT,
    target_id TEXT,
    source_address TEXT,
    destination_address TEXT,
    action TEXT NOT NULL,
    result TEXT NOT NULL, -- SUCCESS, FAILURE, BLOCKED, UNKNOWN
    severity TEXT NOT NULL DEFAULT 'INFO',
    confidence REAL DEFAULT 1.0,
    metadata_json TEXT DEFAULT '{}',
    correlation_ids_json TEXT DEFAULT '[]',
    raw_payload_hash TEXT NOT NULL,
    quarantine_reason TEXT,
    is_quarantined INTEGER DEFAULT 0,
    FOREIGN KEY(source_id) REFERENCES soc_telemetry_sources(source_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_soc_events_timestamp ON soc_security_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_soc_events_actor ON soc_security_events(actor_id);
CREATE INDEX IF NOT EXISTS idx_soc_events_asset ON soc_security_events(asset_id);
CREATE INDEX IF NOT EXISTS idx_soc_events_type ON soc_security_events(event_type);

CREATE TABLE IF NOT EXISTS soc_behavioral_baselines (
    baseline_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL, -- USER, SERVICE_ACCOUNT, API_CLIENT, WORKLOAD, ASSET
    metric_name TEXT NOT NULL,
    rolling_mean REAL NOT NULL DEFAULT 0.0,
    rolling_stddev REAL NOT NULL DEFAULT 0.0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    confidence_level REAL NOT NULL DEFAULT 0.1, -- 0.0 to 1.0
    status TEXT NOT NULL DEFAULT 'COLD_START', -- COLD_START, LEARNING, ESTABLISHED, EXPIRED
    seasonality_model_json TEXT DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    UNIQUE(entity_id, metric_name)
);

CREATE TABLE IF NOT EXISTS soc_baseline_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    baseline_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    snapshot_data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(baseline_id) REFERENCES soc_behavioral_baselines(baseline_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS soc_detection_rules (
    rule_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    rule_type TEXT NOT NULL, -- DETERMINISTIC, ANOMALY, MODEL_ASSISTED
    required_telemetry_sources_json TEXT DEFAULT '[]',
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    confidence_score REAL DEFAULT 0.8,
    threshold_params_json TEXT DEFAULT '{}',
    suppression_conditions_json TEXT DEFAULT '[]',
    mitre_attack_technique TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    is_enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS soc_rule_executions (
    execution_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    matched_event_ids_json TEXT DEFAULT '[]',
    findings_count INTEGER DEFAULT 0,
    execution_duration_ms REAL DEFAULT 0.0,
    executed_at TEXT NOT NULL,
    FOREIGN KEY(rule_id) REFERENCES soc_detection_rules(rule_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS soc_alerts (
    alert_id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    confidence REAL DEFAULT 0.8,
    asset_id TEXT,
    actor_id TEXT,
    status TEXT NOT NULL DEFAULT 'NEW', -- NEW, TRIAGED, INVESTIGATING, CONFIRMED, FALSE_POSITIVE, RESOLVED
    dedup_key TEXT NOT NULL,
    contributing_event_ids_json TEXT DEFAULT '[]',
    explanation_json TEXT DEFAULT '{}',
    suppression_expires_at TEXT,
    assigned_to TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_soc_alerts_dedup ON soc_alerts(dedup_key);
CREATE INDEX IF NOT EXISTS idx_soc_alerts_status ON soc_alerts(status);

CREATE TABLE IF NOT EXISTS soc_correlation_graphs (
    correlation_id TEXT PRIMARY KEY,
    correlation_title TEXT NOT NULL,
    affected_entities_json TEXT DEFAULT '[]',
    participating_alert_ids_json TEXT DEFAULT '[]',
    participating_event_ids_json TEXT DEFAULT '[]',
    attack_chain_sequence_json TEXT DEFAULT '[]',
    correlation_confidence REAL DEFAULT 0.7,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS soc_threat_intel_indicators (
    indicator_id TEXT PRIMARY KEY,
    indicator_type TEXT NOT NULL, -- IP, DOMAIN, HASH, CVE
    indicator_value TEXT NOT NULL,
    threat_actor TEXT,
    campaign TEXT,
    confidence REAL DEFAULT 0.8,
    mitre_techniques_json TEXT DEFAULT '[]',
    source_provider TEXT NOT NULL,
    published_at TEXT NOT NULL,
    expires_at TEXT,
    is_active INTEGER DEFAULT 1,
    UNIQUE(indicator_type, indicator_value)
);

CREATE TABLE IF NOT EXISTS soc_investigations (
    investigation_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    assigned_analyst TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN', -- OPEN, IN_PROGRESS, CLOSED
    primary_hypothesis TEXT NOT NULL,
    competing_hypotheses_json TEXT DEFAULT '[]',
    supporting_event_ids_json TEXT DEFAULT '[]',
    contradictory_evidence_json TEXT DEFAULT '[]',
    affected_assets_json TEXT DEFAULT '[]',
    affected_identities_json TEXT DEFAULT '[]',
    open_questions_json TEXT DEFAULT '[]',
    findings_summary TEXT,
    confidence REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS soc_incidents (
    incident_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    priority TEXT NOT NULL DEFAULT 'P2_STANDARD', -- P0_IMMEDIATE, P1_URGENT, P2_STANDARD, P3_LOW
    status TEXT NOT NULL DEFAULT 'DETECTED', -- DETECTED, TRIAGED, INVESTIGATING, RESPONSE_PENDING, CONTAINMENT_IN_PROGRESS, CONTAINED, RECOVERY, RESOLVED, POST_INCIDENT_REVIEW
    affected_assets_json TEXT DEFAULT '[]',
    affected_identities_json TEXT DEFAULT '[]',
    related_alert_ids_json TEXT DEFAULT '[]',
    investigation_id TEXT,
    assigned_owner TEXT,
    resolution_summary TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS soc_incident_timelines (
    timeline_entry_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    entry_timestamp TEXT NOT NULL,
    entry_type TEXT NOT NULL, -- ALERT, EVENT, ANALYST_NOTE, CONTAINMENT, APPROVAL, RECOVERY
    description TEXT NOT NULL,
    evidence_reference TEXT,
    actor TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES soc_incidents(incident_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS soc_response_plans (
    plan_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    recommended_action TEXT NOT NULL, -- REVOKE_SESSION, DISABLE_ACCOUNT, BLOCK_INDICATOR, ISOLATE_ENDPOINT, ROLLBACK_CONFIG
    target_identifier TEXT NOT NULL,
    justification TEXT NOT NULL,
    operational_risk TEXT NOT NULL DEFAULT 'LOW', -- LOW, MEDIUM, HIGH, CRITICAL
    requires_approval INTEGER DEFAULT 1,
    approval_token_ref TEXT,
    status TEXT NOT NULL DEFAULT 'PROPOSED', -- PROPOSED, APPROVED, REJECTED, EXECUTED, FAILED
    created_at TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES soc_incidents(incident_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS soc_containment_actions (
    action_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target TEXT NOT NULL,
    approval_token TEXT,
    status TEXT NOT NULL DEFAULT 'EXECUTED', -- EXECUTED, FAILED, ROLLED_BACK
    execution_result_json TEXT DEFAULT '{}',
    executed_at TEXT NOT NULL,
    verified_at TEXT,
    FOREIGN KEY(plan_id) REFERENCES soc_response_plans(plan_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS soc_evidence_packages (
    package_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    investigation_id TEXT,
    package_digest_sha256 TEXT NOT NULL,
    evidence_manifest_json TEXT NOT NULL,
    sealed_at TEXT NOT NULL,
    sealed_by TEXT NOT NULL,
    FOREIGN KEY(incident_id) REFERENCES soc_incidents(incident_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS soc_detection_evaluations (
    eval_id TEXT PRIMARY KEY,
    dataset_name TEXT NOT NULL,
    total_samples INTEGER NOT NULL,
    true_positives INTEGER NOT NULL,
    false_positives INTEGER NOT NULL,
    false_negatives INTEGER NOT NULL,
    true_negatives INTEGER NOT NULL,
    precision_score REAL NOT NULL,
    recall_score REAL NOT NULL,
    f1_score REAL NOT NULL,
    evaluated_at TEXT NOT NULL
);
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


# ---------------------------------------------------------------------------
# Migration v33: Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence
# ---------------------------------------------------------------------------
MIGRATION_V33 = """
-- Forensic investigation cases
CREATE TABLE IF NOT EXISTS for_cases (
    case_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    incident_id TEXT,
    scope_definition TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    lead_investigator TEXT NOT NULL,
    retention_days INTEGER NOT NULL DEFAULT 365,
    legal_hold_active INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    closed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_for_cases_status ON for_cases(status);
CREATE INDEX IF NOT EXISTS idx_for_cases_incident_id ON for_cases(incident_id);

-- Forensic evidence artifacts
CREATE TABLE IF NOT EXISTS for_evidence_artifacts (
    artifact_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_identifier TEXT NOT NULL,
    artifact_name TEXT NOT NULL,
    classification TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    storage_uri TEXT NOT NULL,
    parser_type TEXT NOT NULL,
    metadata_json TEXT,
    acquired_at REAL NOT NULL,
    acquired_by TEXT NOT NULL,
    integrity_status TEXT NOT NULL DEFAULT 'VERIFIED',
    FOREIGN KEY(case_id) REFERENCES for_cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_for_artifacts_case_id ON for_evidence_artifacts(case_id);
CREATE INDEX IF NOT EXISTS idx_for_artifacts_sha256 ON for_evidence_artifacts(sha256_hash);

-- Append-only chain of custody records
CREATE TABLE IF NOT EXISTS for_chain_of_custody (
    custody_id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    sha256_verified TEXT NOT NULL,
    integrity_ok INTEGER NOT NULL DEFAULT 1,
    approval_token TEXT,
    recorded_at REAL NOT NULL,
    FOREIGN KEY(artifact_id) REFERENCES for_evidence_artifacts(artifact_id),
    FOREIGN KEY(case_id) REFERENCES for_cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_for_custody_artifact ON for_chain_of_custody(artifact_id);
CREATE INDEX IF NOT EXISTS idx_for_custody_case ON for_chain_of_custody(case_id);

-- Evidence acquisition jobs
CREATE TABLE IF NOT EXISTS for_acquisition_jobs (
    job_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    target_source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    parameters_json TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    artifacts_collected INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    approval_token TEXT,
    initiated_by TEXT NOT NULL,
    started_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY(case_id) REFERENCES for_cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_for_acq_case ON for_acquisition_jobs(case_id);

-- Normalized timeline events
CREATE TABLE IF NOT EXISTS for_timeline_events (
    event_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    artifact_id TEXT,
    timestamp_utc REAL NOT NULL,
    raw_timestamp TEXT NOT NULL,
    clock_drift_seconds REAL NOT NULL DEFAULT 0.0,
    event_category TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT,
    source_entity TEXT,
    target_entity TEXT,
    summary TEXT NOT NULL,
    details_json TEXT,
    reliability_tier TEXT NOT NULL DEFAULT 'CONFIRMED',
    FOREIGN KEY(case_id) REFERENCES for_cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_for_timeline_case_time ON for_timeline_events(case_id, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_for_timeline_actor ON for_timeline_events(actor);

-- Cross-source evidence correlations
CREATE TABLE IF NOT EXISTS for_evidence_correlations (
    correlation_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    source_artifact_id TEXT NOT NULL,
    target_artifact_id TEXT NOT NULL,
    correlation_type TEXT NOT NULL,
    correlation_key TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    notes TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY(case_id) REFERENCES for_cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_for_correl_case ON for_evidence_correlations(case_id);

-- Investigation hypotheses
CREATE TABLE IF NOT EXISTS for_hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    title TEXT NOT NULL,
    theory_description TEXT NOT NULL,
    competing_with_id TEXT,
    status TEXT NOT NULL DEFAULT 'PROPOSED',
    support_score REAL NOT NULL DEFAULT 0.0,
    refutation_score REAL NOT NULL DEFAULT 0.0,
    supporting_evidence_json TEXT,
    contradictory_evidence_json TEXT,
    verdict_rationale TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY(case_id) REFERENCES for_cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_for_hypo_case ON for_hypotheses(case_id);

-- Structured forensic reports
CREATE TABLE IF NOT EXISTS for_reports (
    report_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    title TEXT NOT NULL,
    executive_summary TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    inferences_json TEXT NOT NULL,
    hypotheses_json TEXT NOT NULL,
    unknowns_json TEXT NOT NULL,
    recommendations_json TEXT NOT NULL,
    sign_off_investigator TEXT NOT NULL,
    cryptographic_seal TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(case_id) REFERENCES for_cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_for_reports_case ON for_reports(case_id);

-- Legal holds and retention extensions
CREATE TABLE IF NOT EXISTS for_legal_holds (
    hold_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    hold_reason TEXT NOT NULL,
    applied_by TEXT NOT NULL,
    approval_token TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    applied_at REAL NOT NULL,
    released_at REAL,
    released_by TEXT,
    FOREIGN KEY(case_id) REFERENCES for_cases(case_id)
);
CREATE INDEX IF NOT EXISTS idx_for_holds_case ON for_legal_holds(case_id);
"""

# ---------------------------------------------------------------------------
# Migration v34: Autonomous Malware Analysis, Reverse Engineering & Behavioral Classification Intelligence
# ---------------------------------------------------------------------------
MIGRATION_V34 = """
-- Malware samples repository
CREATE TABLE IF NOT EXISTS mal_samples (
    sample_id TEXT PRIMARY KEY,
    sha256_hash TEXT NOT NULL UNIQUE,
    sha1_hash TEXT NOT NULL,
    md5_hash TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    file_type TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    classification TEXT NOT NULL DEFAULT 'UNKNOWN',
    is_quarantined INTEGER NOT NULL DEFAULT 0,
    submission_source TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mal_samples_sha256 ON mal_samples(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_mal_samples_classification ON mal_samples(classification);

-- Quarantine records and secure isolation tracking
CREATE TABLE IF NOT EXISTS mal_quarantine_records (
    quarantine_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL,
    quarantine_path TEXT NOT NULL,
    original_path TEXT NOT NULL,
    reason TEXT NOT NULL,
    isolated_by TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'QUARANTINED',
    is_legal_hold INTEGER NOT NULL DEFAULT 0,
    quarantined_at REAL NOT NULL,
    released_at REAL,
    released_by TEXT,
    FOREIGN KEY(sample_id) REFERENCES mal_samples(sample_id)
);
CREATE INDEX IF NOT EXISTS idx_mal_quarantine_sample ON mal_quarantine_records(sample_id);

-- Analysis jobs workflow
CREATE TABLE IF NOT EXISTS mal_analysis_jobs (
    job_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL,
    profile TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'SUBMITTED',
    status TEXT NOT NULL DEFAULT 'QUEUED',
    progress REAL NOT NULL DEFAULT 0.0,
    timeout_seconds INTEGER NOT NULL DEFAULT 300,
    error_message TEXT,
    worker_id TEXT,
    created_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY(sample_id) REFERENCES mal_samples(sample_id)
);
CREATE INDEX IF NOT EXISTS idx_mal_jobs_sample ON mal_analysis_jobs(sample_id);
CREATE INDEX IF NOT EXISTS idx_mal_jobs_status ON mal_analysis_jobs(status);

-- Static reverse engineering analysis results
CREATE TABLE IF NOT EXISTS mal_static_analyses (
    analysis_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL,
    format_detected TEXT NOT NULL,
    entropy REAL NOT NULL,
    headers_json TEXT,
    sections_json TEXT,
    imports_json TEXT,
    exports_json TEXT,
    strings_summary_json TEXT,
    anomalies_json TEXT,
    analyzed_at REAL NOT NULL,
    FOREIGN KEY(sample_id) REFERENCES mal_samples(sample_id)
);
CREATE INDEX IF NOT EXISTS idx_mal_static_sample ON mal_static_analyses(sample_id);

-- Extracted indicators of compromise (IOCs)
CREATE TABLE IF NOT EXISTS mal_extracted_indicators (
    indicator_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL,
    indicator_type TEXT NOT NULL,
    indicator_value TEXT NOT NULL,
    context TEXT,
    mitre_technique TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    extracted_at REAL NOT NULL,
    FOREIGN KEY(sample_id) REFERENCES mal_samples(sample_id)
);
CREATE INDEX IF NOT EXISTS idx_mal_indicators_sample ON mal_extracted_indicators(sample_id);
CREATE INDEX IF NOT EXISTS idx_mal_indicators_type_val ON mal_extracted_indicators(indicator_type, indicator_value);

-- Behavioral classifications and MITRE ATT&CK mapping
CREATE TABLE IF NOT EXISTS mal_behavioral_classifications (
    classification_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL,
    category TEXT NOT NULL,
    behavior_name TEXT NOT NULL,
    mitre_technique TEXT,
    supporting_evidence_json TEXT,
    confidence REAL NOT NULL,
    observed_status TEXT NOT NULL DEFAULT 'STATIC_INFERRED',
    created_at REAL NOT NULL,
    FOREIGN KEY(sample_id) REFERENCES mal_samples(sample_id)
);
CREATE INDEX IF NOT EXISTS idx_mal_behaviors_sample ON mal_behavioral_classifications(sample_id);
CREATE INDEX IF NOT EXISTS idx_mal_behaviors_cat ON mal_behavioral_classifications(category);

-- Defensive detection rules (YARA / Sigma)
CREATE TABLE IF NOT EXISTS mal_detection_rules (
    rule_id TEXT PRIMARY KEY,
    sample_id TEXT,
    rule_type TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    rule_content TEXT NOT NULL,
    test_fixture_json TEXT,
    validation_status TEXT NOT NULL DEFAULT 'VALIDATED',
    created_at REAL NOT NULL,
    FOREIGN KEY(sample_id) REFERENCES mal_samples(sample_id)
);
CREATE INDEX IF NOT EXISTS idx_mal_rules_sample ON mal_detection_rules(sample_id);
CREATE INDEX IF NOT EXISTS idx_mal_rules_type ON mal_detection_rules(rule_type);

-- Comprehensive forensic and malware intelligence reports
CREATE TABLE IF NOT EXISTS mal_reports (
    report_id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL,
    title TEXT NOT NULL,
    executive_summary TEXT NOT NULL,
    verdict TEXT NOT NULL,
    risk_score REAL NOT NULL,
    findings_json TEXT NOT NULL,
    indicators_json TEXT NOT NULL,
    recommendations_json TEXT NOT NULL,
    cryptographic_seal TEXT NOT NULL,
    generated_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(sample_id) REFERENCES mal_samples(sample_id)
);
CREATE INDEX IF NOT EXISTS idx_mal_reports_sample ON mal_reports(sample_id);
CREATE INDEX IF NOT EXISTS idx_mal_reports_verdict ON mal_reports(verdict);
"""


MIGRATION_V35 = """
-- Schema Version 35: Autonomous Privacy Engineering, Data Governance & Information Protection Intelligence Tables

-- 1. Data Asset Inventory
CREATE TABLE IF NOT EXISTS priv_data_assets (
    asset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    storage_location TEXT NOT NULL,
    owner TEXT NOT NULL,
    residency_country TEXT NOT NULL,
    sensitivity_tier TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_priv_assets_type ON priv_data_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_priv_assets_residency ON priv_data_assets(residency_country);
CREATE INDEX IF NOT EXISTS idx_priv_assets_tier ON priv_data_assets(sensitivity_tier);

-- 2. Sensitive Data Classifications
CREATE TABLE IF NOT EXISTS priv_data_classifications (
    class_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    category TEXT NOT NULL,
    sensitivity_tier TEXT NOT NULL,
    confidence REAL NOT NULL,
    rule_matched TEXT NOT NULL,
    classified_at REAL NOT NULL,
    FOREIGN KEY(asset_id) REFERENCES priv_data_assets(asset_id)
);
CREATE INDEX IF NOT EXISTS idx_priv_class_asset ON priv_data_classifications(asset_id);
CREATE INDEX IF NOT EXISTS idx_priv_class_category ON priv_data_classifications(category);
CREATE INDEX IF NOT EXISTS idx_priv_class_tier ON priv_data_classifications(sensitivity_tier);

-- 3. Sensitive Data Discovery Scans
CREATE TABLE IF NOT EXISTS priv_discovery_scans (
    scan_id TEXT PRIMARY KEY,
    target_scope TEXT NOT NULL,
    scanner_identity TEXT NOT NULL,
    findings_count INTEGER DEFAULT 0,
    sensitive_fields_json TEXT DEFAULT '[]',
    started_at REAL NOT NULL,
    completed_at REAL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_scans_status ON priv_discovery_scans(status);
CREATE INDEX IF NOT EXISTS idx_priv_scans_started ON priv_discovery_scans(started_at);

-- 4. Data Lineage Records
CREATE TABLE IF NOT EXISTS priv_lineage_records (
    lineage_id TEXT PRIMARY KEY,
    source_asset_id TEXT NOT NULL,
    dest_asset_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    purpose TEXT NOT NULL,
    transformation_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    timestamp REAL NOT NULL,
    FOREIGN KEY(source_asset_id) REFERENCES priv_data_assets(asset_id),
    FOREIGN KEY(dest_asset_id) REFERENCES priv_data_assets(asset_id)
);
CREATE INDEX IF NOT EXISTS idx_priv_lineage_src ON priv_lineage_records(source_asset_id);
CREATE INDEX IF NOT EXISTS idx_priv_lineage_dest ON priv_lineage_records(dest_asset_id);

-- 5. Processing Activities (RoPA)
CREATE TABLE IF NOT EXISTS priv_processing_activities (
    activity_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL,
    lawful_basis TEXT NOT NULL,
    owner TEXT NOT NULL,
    data_categories_json TEXT DEFAULT '[]',
    retention_schedule TEXT NOT NULL,
    is_approved INTEGER DEFAULT 0,
    review_date REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_proc_purpose ON priv_processing_activities(purpose);
CREATE INDEX IF NOT EXISTS idx_priv_proc_approved ON priv_processing_activities(is_approved);

-- 6. Consent Records
CREATE TABLE IF NOT EXISTS priv_consent_records (
    consent_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    granted_at REAL NOT NULL,
    withdrawn_at REAL,
    policy_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_consent_sub_purp ON priv_consent_records(subject_id, purpose);
CREATE INDEX IF NOT EXISTS idx_priv_consent_status ON priv_consent_records(status);

-- 7. Retention Policies
CREATE TABLE IF NOT EXISTS priv_retention_policies (
    policy_id TEXT PRIMARY KEY,
    purpose TEXT NOT NULL,
    max_retention_days INTEGER NOT NULL,
    legal_basis TEXT NOT NULL,
    legal_hold_exempt INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_retention_purpose ON priv_retention_policies(purpose);

-- 8. Deletion Requests & Multi-Store Orchestration
CREATE TABLE IF NOT EXISTS priv_deletion_requests (
    request_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    target_selector TEXT NOT NULL,
    reason TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    approval_token TEXT,
    status TEXT NOT NULL,
    verified INTEGER DEFAULT 0,
    requested_at REAL NOT NULL,
    completed_at REAL,
    FOREIGN KEY(asset_id) REFERENCES priv_data_assets(asset_id)
);
CREATE INDEX IF NOT EXISTS idx_priv_del_asset ON priv_deletion_requests(asset_id);
CREATE INDEX IF NOT EXISTS idx_priv_del_status ON priv_deletion_requests(status);

-- 9. Data Subject Requests (DSR/DSAR)
CREATE TABLE IF NOT EXISTS priv_dsr_requests (
    dsr_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL,
    verification_token TEXT,
    requester_email TEXT NOT NULL,
    deadline REAL NOT NULL,
    created_at REAL NOT NULL,
    resolved_at REAL
);
CREATE INDEX IF NOT EXISTS idx_priv_dsr_subject ON priv_dsr_requests(subject_id);
CREATE INDEX IF NOT EXISTS idx_priv_dsr_status ON priv_dsr_requests(status);
CREATE INDEX IF NOT EXISTS idx_priv_dsr_type ON priv_dsr_requests(request_type);

-- 10. Privacy Impact Assessments (PIA/DPIA)
CREATE TABLE IF NOT EXISTS priv_assessments (
    assessment_id TEXT PRIMARY KEY,
    activity_id TEXT NOT NULL,
    assessment_type TEXT NOT NULL,
    risk_score REAL NOT NULL,
    findings_json TEXT DEFAULT '[]',
    safeguards_json TEXT DEFAULT '[]',
    approval_status TEXT NOT NULL,
    assessed_at REAL NOT NULL,
    FOREIGN KEY(activity_id) REFERENCES priv_processing_activities(activity_id)
);
CREATE INDEX IF NOT EXISTS idx_priv_assess_act ON priv_assessments(activity_id);
CREATE INDEX IF NOT EXISTS idx_priv_assess_status ON priv_assessments(approval_status);

-- 11. Access & Disclosure Governance
CREATE TABLE IF NOT EXISTS priv_access_disclosures (
    log_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    purpose TEXT NOT NULL,
    action TEXT NOT NULL,
    authorized INTEGER NOT NULL,
    justification TEXT,
    timestamp REAL NOT NULL,
    FOREIGN KEY(asset_id) REFERENCES priv_data_assets(asset_id)
);
CREATE INDEX IF NOT EXISTS idx_priv_access_actor ON priv_access_disclosures(actor_id);
CREATE INDEX IF NOT EXISTS idx_priv_access_asset ON priv_access_disclosures(asset_id);
CREATE INDEX IF NOT EXISTS idx_priv_access_auth ON priv_access_disclosures(authorized);

-- 12. Vendor & Processor Governance
CREATE TABLE IF NOT EXISTS priv_vendor_processors (
    vendor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    service_type TEXT NOT NULL,
    dpa_status TEXT NOT NULL,
    residency TEXT NOT NULL,
    subprocessors_json TEXT DEFAULT '[]',
    assessment_status TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_vendor_dpa ON priv_vendor_processors(dpa_status);

-- 13. Cross-Border Data Transfers
CREATE TABLE IF NOT EXISTS priv_cross_border_transfers (
    transfer_id TEXT PRIMARY KEY,
    source_country TEXT NOT NULL,
    dest_country TEXT NOT NULL,
    recipient TEXT NOT NULL,
    purpose TEXT NOT NULL,
    transfer_mechanism TEXT NOT NULL,
    is_approved INTEGER DEFAULT 0,
    reviewed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_cbt_dest ON priv_cross_border_transfers(dest_country);
CREATE INDEX IF NOT EXISTS idx_priv_cbt_approved ON priv_cross_border_transfers(is_approved);

-- 14. Privacy Incidents
CREATE TABLE IF NOT EXISTS priv_incidents (
    incident_id TEXT PRIMARY KEY,
    incident_type TEXT NOT NULL,
    affected_assets_json TEXT DEFAULT '[]',
    affected_categories_json TEXT DEFAULT '[]',
    severity TEXT NOT NULL,
    containment_status TEXT NOT NULL,
    reportable INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_inc_severity ON priv_incidents(severity);
CREATE INDEX IF NOT EXISTS idx_priv_inc_status ON priv_incidents(containment_status);

-- 15. AI & Model Privacy Governance
CREATE TABLE IF NOT EXISTS priv_ai_governance (
    ai_gov_id TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    inference_logging_allowed INTEGER DEFAULT 0,
    training_permitted INTEGER DEFAULT 0,
    prompt_redaction_enabled INTEGER DEFAULT 1,
    retention_policy TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_ai_model ON priv_ai_governance(model_id);

-- 16. Privacy Audit Logs
CREATE TABLE IF NOT EXISTS priv_audit_logs (
    audit_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    details_json TEXT DEFAULT '{}',
    timestamp REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_priv_audit_event ON priv_audit_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_priv_audit_ts ON priv_audit_logs(timestamp);
"""

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

        if current_version < 12:
            logger.info("Applying Migration v12 (Knowledge Graph & Entity Resolution Tables)...")
            cursor.executescript(MIGRATION_V12)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (12, time.time(), "Knowledge Graph and Entity Resolution tables")
            )
            conn.commit()
            logger.info("Migration v12 applied successfully.")
            current_version = 12

        if current_version < 13:
            logger.info("Applying Migration v13 (Temporal Knowledge & Causal State Tables)...")
            cursor.executescript(MIGRATION_V13)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (13, time.time(), "Temporal Knowledge and Causal State Engine tables")
            )
            conn.commit()
            logger.info("Migration v13 applied successfully.")
            current_version = 13

        if current_version < 14:
            logger.info("Applying Migration v14 (Predictive Intelligence & Risk Forecasting Tables)...")
            cursor.executescript(MIGRATION_V14)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (14, time.time(), "Predictive Intelligence and Risk Forecasting Engine tables")
            )
            conn.commit()
            logger.info("Migration v14 applied successfully.")
            current_version = 14

        if current_version < 15:
            logger.info("Applying Migration v15 (Adaptive Learning & Model Lifecycle Governance Tables)...")
            cursor.executescript(MIGRATION_V15)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (15, time.time(), "Adaptive Learning and Model Lifecycle Governance Engine tables")
            )
            conn.commit()
            logger.info("Migration v15 applied successfully.")
            current_version = 15

        if current_version < 16:
            logger.info("Applying Migration v16 (Autonomous Simulation, Digital Twin & Scenario Testing Tables)...")
            cursor.executescript(MIGRATION_V16)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (16, time.time(), "Autonomous Simulation, Digital Twin & Scenario Testing Engine tables")
            )
            conn.commit()
            logger.info("Migration v16 applied successfully.")
            current_version = 16



        if current_version < 17:
            logger.info("Applying Migration v17 (Autonomous Cybersecurity, Threat Intelligence & Runtime Defense Tables)...")
            cursor.executescript(MIGRATION_V17)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (17, time.time(), "Autonomous Cybersecurity, Threat Intelligence and Runtime Defense Engine tables")
            )
            conn.commit()
            logger.info("Migration v17 applied successfully.")
            current_version = 17

        if current_version < 18:
            logger.info("Applying Migration v18 (Autonomous Observability, Diagnostics & Self-Healing Infrastructure Tables)...")
            cursor.executescript(MIGRATION_V18)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (18, time.time(), "Autonomous Observability, Diagnostics and Self-Healing Infrastructure Engine tables")
            )
            conn.commit()
            logger.info("Migration v18 applied successfully.")
            current_version = 18

        if current_version < 19:
            logger.info("Applying Migration v19 (Autonomous Deployment, Release Engineering & Rollback Engine Tables)...")
            cursor.executescript(MIGRATION_V19)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (19, time.time(), "Autonomous Deployment, Release Engineering and Rollback Engine tables")
            )
            conn.commit()
            logger.info("Migration v19 applied successfully.")
            current_version = 19

        if current_version < 20:
            logger.info("Applying Migration v20 (Autonomous Research, Scientific Discovery & Hypothesis Testing Tables)...")
            cursor.executescript(MIGRATION_V20)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (20, time.time(), "Autonomous Research, Scientific Discovery and Hypothesis Testing Engine tables")
            )
            conn.commit()
            logger.info("Migration v20 applied successfully.")
            current_version = 20

        if current_version < 21:
            logger.info("Applying Migration v21 (Autonomous Knowledge Synthesis & Intelligence Briefing Tables)...")
            cursor.executescript(MIGRATION_V21)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (21, time.time(), "Autonomous Knowledge Synthesis and Intelligence Briefing Engine tables")
            )
            conn.commit()
            logger.info("Migration v21 applied successfully.")
            current_version = 21

        if current_version < 22:
            logger.info("Applying Migration v22 (Decision Support, Strategic Options & Trade-off Analysis Tables)...")
            cursor.executescript(MIGRATION_V22)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (22, time.time(), "Decision Support, Strategic Options and Trade-off Analysis Engine tables")
            )
            conn.commit()
            logger.info("Migration v22 applied successfully.")
            current_version = 22

        if current_version < 23:
            logger.info("Applying Migration v23 (Autonomous Goal Management & Outcome Tracking Tables)...")
            cursor.executescript(MIGRATION_V23)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (23, time.time(), "Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence tables")
            )
            conn.commit()
            logger.info("Migration v23 applied successfully.")
            current_version = 23

        if current_version < 24:
            logger.info("Applying Migration v24 (Autonomous Workflow Optimization & Process Intelligence Tables)...")
            cursor.executescript(MIGRATION_V24)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (24, time.time(), "Autonomous Workflow Optimization and Process Intelligence Engine tables")
            )
            conn.commit()
            logger.info("Migration v24 applied successfully.")
            current_version = 24

        if current_version < 25:
            logger.info("Applying Migration v25 (Autonomous Operations Center & Incident Intelligence Tables)...")
            cursor.executescript(MIGRATION_V25)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (25, time.time(), "Autonomous Operations Center, System Observability & Incident Intelligence Engine tables")
            )
            conn.commit()
            logger.info("Migration v25 applied successfully.")
            current_version = 25

        
        if current_version < 26:
            logger.info("Applying Migration v26 (Autonomous Reliability Engineering & Disaster Recovery Tables)...")
            cursor.executescript(MIGRATION_V26)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (26, time.time(), "Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery Engine tables")
            )
            conn.commit()
            logger.info("Migration v26 applied successfully.")
            current_version = 26

        if current_version < 27:
            logger.info("Applying Migration v27 (Autonomous Capacity Planning & Infrastructure Forecasting Tables)...")
            cursor.executescript(MIGRATION_V27)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (27, time.time(), "Autonomous Capacity Planning, Infrastructure Forecasting and Elastic Resource Intelligence tables")
            )
            conn.commit()
            logger.info("Migration v27 applied successfully.")
            current_version = 27

        if current_version < 28:
            logger.info("Applying Migration v28 (Autonomous Infrastructure Provisioning & Environment Lifecycle Management Tables)...")
            cursor.executescript(MIGRATION_V28)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (28, time.time(), "Autonomous Infrastructure Provisioning, Deployment and Environment Lifecycle Management tables")
            )
            conn.commit()
            logger.info("Migration v28 applied successfully.")
            current_version = 28

        if current_version < 29:
            logger.info("Applying Migration v29 (Autonomous Software Delivery & CI/CD Intelligence Tables)...")
            cursor.executescript(MIGRATION_V29)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (29, time.time(), "Autonomous Software Delivery, CI/CD Intelligence and Release Engineering tables")
            )
            conn.commit()
            logger.info("Migration v29 applied successfully.")
            current_version = 29

        if current_version < 30:
            logger.info("Applying Migration v30 (Autonomous QA & Software Verification Engine Tables)...")
            cursor.executescript(MIGRATION_V30)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (30, time.time(), "Autonomous Quality Assurance, Software Verification and Continuous Testing Intelligence tables")
            )
            conn.commit()
            logger.info("Migration v30 applied successfully.")
            current_version = 30

        if current_version < 31:
            logger.info("Applying Migration v31 (Autonomous AppSec & Vulnerability Intelligence Tables)...")
            cursor.executescript(MIGRATION_V31)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (31, time.time(), "Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation Engine tables")
            )
            conn.commit()
            logger.info("Migration v31 applied successfully.")
            current_version = 31

        if current_version < 32:
            logger.info("Applying Migration v32 (Autonomous Threat Detection & SecOps Tables)...")
            cursor.executescript(MIGRATION_V32)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (32, time.time(), "Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence Engine tables")
            )
            conn.commit()
            logger.info("Migration v32 applied successfully.")
            current_version = 32

        if current_version < 33:
            logger.info("Applying Migration v33 (Autonomous Digital Forensics & Evidence Preservation Tables)...")
            cursor.executescript(MIGRATION_V33)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (33, time.time(), "Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence Engine tables")
            )
            conn.commit()
            logger.info("Migration v33 applied successfully.")
            current_version = 33

        if current_version < 34:
            logger.info("Applying Migration v34 (Autonomous Malware Analysis, Reverse Engineering & Behavioral Classification Tables)...")
            cursor.executescript(MIGRATION_V34)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (34, time.time(), "Autonomous Malware Analysis, Reverse Engineering & Behavioral Classification Intelligence tables")
            )
            conn.commit()
            logger.info("Migration v34 applied successfully.")
            current_version = 34


        if current_version < 35:
            logger.info("Applying Migration v35 (Autonomous Privacy Engineering, Data Governance & Information Protection Intelligence Tables)...")
            cursor.executescript(MIGRATION_V35)
            cursor.execute(
                "INSERT INTO schema_migrations (version, applied_at, description) VALUES (?, ?, ?)",
                (35, time.time(), "Autonomous Privacy Engineering, Data Governance & Information Protection Intelligence tables")
            )
            conn.commit()
            logger.info("Migration v35 applied successfully.")
            current_version = 35

        return current_version
    except Exception as e:
        conn.rollback()
        logger.error(f"MIGRATION_FAILED: Migration rolled back. Reason: {e}")
        raise RuntimeError(f"MIGRATION_FAILED: {e}")
    finally:
        conn.close()
