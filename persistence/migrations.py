import sqlite3
import os
import shutil
import time
import logging
from typing import List, Tuple

logger = logging.getLogger("Omnia.Persistence.Migrations")

CURRENT_SCHEMA_VERSION = 3

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

        return current_version
    except Exception as e:
        conn.rollback()
        logger.error(f"MIGRATION_FAILED: Migration rolled back. Reason: {e}")
        raise RuntimeError(f"MIGRATION_FAILED: {e}")
    finally:
        conn.close()
