import sqlite3
import json
import time
import os
import re
import uuid
import logging
from typing import Optional, List, Dict, Any, Tuple

from persistence.models import (
    PersistedTaskRecord,
    PersistedNodeRecord,
    PersistedCheckpoint,
    PersistedJournalEvent,
    PersistedResourceLock,
    TaskHeartbeat
)
from persistence.migrations import apply_migrations

logger = logging.getLogger("Omnia.Persistence.Store")

DEFAULT_DB_PATH = "omnia_tasks.db"

# Sensitive data sanitization regexes
SENSITIVE_PATTERNS = [
    (re.compile(r'(password|passwd|pwd|secret|api_key|token|auth_token|cookie|access_token|private_key)["\']?\s*[:=]\s*["\']?([^"\'\s&,]+)', re.IGNORECASE), r'\1: "[REDACTED]"'),
    (re.compile(r'(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(cvv|card_number|credit_card)["\']?\s*[:=]\s*["\']?(\d+)', re.IGNORECASE), r'\1: "[REDACTED]"')
]

def sanitize_payload(payload: Any) -> Any:
    """Recursively redacts credentials, authorization tokens, cookies, and sensitive values."""
    if isinstance(payload, dict):
        cleaned = {}
        for k, v in payload.items():
            if any(term in k.lower() for term in ["pass", "token", "secret", "auth", "key", "cookie", "cvv", "card"]):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_payload(v)
        return cleaned
    elif isinstance(payload, list):
        return [sanitize_payload(i) for i in payload]
    elif isinstance(payload, str):
        res = payload
        for pat, repl in SENSITIVE_PATTERNS:
            res = pat.sub(repl, res)
        return res
    return payload

class TaskPersistenceStore:
    """Thread-safe SQLite store managing durable tasks, nodes, events, checkpoints, and locks."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._ensure_initialized()

    def _ensure_initialized(self):
        apply_migrations(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # --- Task Operations ---

    def save_task(self, record: PersistedTaskRecord):
        """Inserts or updates a task record."""
        conn = self._get_connection()
        try:
            with conn:
                sanitized_meta = sanitize_payload(record.metadata)
                conn.execute("""
                    INSERT INTO tasks (
                        task_id, goal, status, current_node_id, created_at, started_at,
                        updated_at, completed_at, deadline_ts, task_timeout_sec,
                        attempt_count, replan_count, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        status = excluded.status,
                        current_node_id = excluded.current_node_id,
                        started_at = COALESCE(tasks.started_at, excluded.started_at),
                        updated_at = excluded.updated_at,
                        completed_at = excluded.completed_at,
                        attempt_count = excluded.attempt_count,
                        replan_count = excluded.replan_count,
                        metadata_json = excluded.metadata_json
                """, (
                    record.task_id, record.goal, record.status, record.current_node_id,
                    record.created_at, record.started_at, record.updated_at,
                    record.completed_at, record.deadline_ts, record.task_timeout_sec,
                    record.attempt_count, record.replan_count, json.dumps(sanitized_meta)
                ))
        finally:
            conn.close()

    def load_task(self, task_id: str) -> Optional[PersistedTaskRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return PersistedTaskRecord(
                task_id=row["task_id"],
                goal=row["goal"],
                status=row["status"],
                current_node_id=row["current_node_id"],
                created_at=row["created_at"],
                started_at=row["started_at"],
                updated_at=row["updated_at"],
                completed_at=row["completed_at"],
                deadline_ts=row["deadline_ts"],
                task_timeout_sec=row["task_timeout_sec"],
                attempt_count=row["attempt_count"],
                replan_count=row["replan_count"],
                metadata=json.loads(row["metadata_json"] or "{}")
            )
        finally:
            conn.close()

    def list_interrupted_tasks(self, heartbeat_timeout_sec: float = 30.0) -> List[Dict[str, Any]]:
        """Finds tasks that were left in active states without recent heartbeats."""
        cutoff = time.time() - heartbeat_timeout_sec
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.task_id, t.goal, t.status, t.current_node_id, t.updated_at,
                       h.heartbeat_ts, h.process_id
                FROM tasks t
                LEFT JOIN task_heartbeats h ON t.task_id = h.task_id
                WHERE t.status IN ('RUNNING', 'VERIFYING', 'PLANNING', 'RECOVERING')
                  AND (h.heartbeat_ts IS NULL OR h.heartbeat_ts < ?)
            """, (cutoff,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # --- Node Operations ---

    def save_node(self, node: PersistedNodeRecord):
        conn = self._get_connection()
        try:
            with conn:
                sanitized_meta = sanitize_payload(node.metadata)
                conn.execute("""
                    INSERT INTO task_nodes (
                        node_id, task_id, name, description, status, attempt_count,
                        started_at, completed_at, expected_state, idempotency,
                        required_resources_json, dependencies_json, last_error_category,
                        last_error_message, last_verification_status, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_id, node_id) DO UPDATE SET
                        status = excluded.status,
                        attempt_count = excluded.attempt_count,
                        started_at = COALESCE(task_nodes.started_at, excluded.started_at),
                        completed_at = excluded.completed_at,
                        last_error_category = excluded.last_error_category,
                        last_error_message = excluded.last_error_message,
                        last_verification_status = excluded.last_verification_status,
                        metadata_json = excluded.metadata_json
                """, (
                    node.node_id, node.task_id, node.name, node.description, node.status,
                    node.attempt_count, node.started_at, node.completed_at, node.expected_state,
                    node.idempotency, json.dumps(node.required_resources),
                    json.dumps(node.dependencies), node.last_error_category,
                    sanitize_payload(node.last_error_message) if node.last_error_message else None,
                    node.last_verification_status, json.dumps(sanitized_meta)
                ))
        finally:
            conn.close()

    def load_nodes_for_task(self, task_id: str) -> List[PersistedNodeRecord]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM task_nodes WHERE task_id = ?", (task_id,))
            rows = cursor.fetchall()
            nodes = []
            for r in rows:
                nodes.append(PersistedNodeRecord(
                    node_id=r["node_id"],
                    task_id=r["task_id"],
                    name=r["name"],
                    description=r["description"] or "",
                    status=r["status"],
                    attempt_count=r["attempt_count"],
                    started_at=r["started_at"],
                    completed_at=r["completed_at"],
                    expected_state=r["expected_state"],
                    idempotency=r["idempotency"],
                    required_resources=json.loads(r["required_resources_json"] or "[]"),
                    dependencies=json.loads(r["dependencies_json"] or "[]"),
                    last_error_category=r["last_error_category"],
                    last_error_message=r["last_error_message"],
                    last_verification_status=r["last_verification_status"],
                    metadata=json.loads(r["metadata_json"] or "{}")
                ))
            return nodes
        finally:
            conn.close()

    # --- Append-Only Task Journal ---

    def append_event(self, task_id: str, event_type: str, payload: Dict[str, Any]) -> int:
        """Appends a new event ensuring monotonic sequence number per task."""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                # Ensure parent task entry exists to satisfy foreign key constraint
                now = time.time()
                cursor.execute("""
                    INSERT OR IGNORE INTO tasks (
                        task_id, goal, status, created_at, updated_at, deadline_ts, task_timeout_sec
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (task_id, f"Auto-created task stub for {task_id}", "RUNNING", now, now, now + 86400, 86400.0))

                cursor.execute("SELECT COALESCE(MAX(sequence_number), 0) FROM task_events WHERE task_id = ?", (task_id,))
                max_seq = cursor.fetchone()[0]
                next_seq = max_seq + 1

                event_id = str(uuid.uuid4())[:8]
                clean_payload = sanitize_payload(payload)

                cursor.execute("""
                    INSERT INTO task_events (event_id, task_id, sequence_number, timestamp, event_type, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (event_id, task_id, next_seq, time.time(), event_type, json.dumps(clean_payload)))
                return next_seq
        finally:
            conn.close()

    def get_task_events(self, task_id: str) -> List[PersistedJournalEvent]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM task_events WHERE task_id = ? ORDER BY sequence_number ASC", (task_id,))
            rows = cursor.fetchall()
            events = []
            for r in rows:
                events.append(PersistedJournalEvent(
                    event_id=r["event_id"],
                    task_id=r["task_id"],
                    sequence_number=r["sequence_number"],
                    timestamp=r["timestamp"],
                    event_type=r["event_type"],
                    payload=json.loads(r["payload_json"] or "{}")
                ))
            return events
        finally:
            conn.close()

    # --- Checkpoint Operations ---

    def save_checkpoint(self, checkpoint: PersistedCheckpoint):
        """Atomically saves checkpoint and updates task record."""
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                clean_vars = sanitize_payload(checkpoint.variables)
                clean_obs = sanitize_payload(checkpoint.last_verified_observations)

                cursor.execute("""
                    INSERT INTO task_checkpoints (
                        checkpoint_id, task_id, node_id, timestamp, task_state,
                        node_states_json, variables_json, resource_state_json,
                        last_verified_observations_json, policy_trigger,
                        browser_state_ref, device_state_ref, vision_frame_ref, checksum
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    checkpoint.checkpoint_id, checkpoint.task_id, checkpoint.node_id,
                    checkpoint.timestamp, checkpoint.task_state, json.dumps(checkpoint.node_states),
                    json.dumps(clean_vars), json.dumps(checkpoint.resource_state),
                    json.dumps(clean_obs), checkpoint.policy_trigger,
                    checkpoint.browser_state_ref, checkpoint.device_state_ref,
                    checkpoint.vision_frame_ref, checkpoint.checksum
                ))
        finally:
            conn.close()

    def get_latest_checkpoint(self, task_id: str) -> Optional[PersistedCheckpoint]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM task_checkpoints
                WHERE task_id = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (task_id,))
            r = cursor.fetchone()
            if not r:
                return None
            return PersistedCheckpoint(
                checkpoint_id=r["checkpoint_id"],
                task_id=r["task_id"],
                node_id=r["node_id"],
                timestamp=r["timestamp"],
                task_state=r["task_state"],
                node_states=json.loads(r["node_states_json"] or "{}"),
                variables=json.loads(r["variables_json"] or "{}"),
                resource_state=json.loads(r["resource_state_json"] or "[]"),
                last_verified_observations=json.loads(r["last_verified_observations_json"] or "[]"),
                policy_trigger=r["policy_trigger"],
                browser_state_ref=r["browser_state_ref"],
                device_state_ref=r["device_state_ref"],
                vision_frame_ref=r["vision_frame_ref"],
                checksum=r["checksum"]
            )
        finally:
            conn.close()

    # --- Heartbeat & Locks ---

    def update_heartbeat(self, task_id: str, current_node_id: Optional[str] = None):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO task_heartbeats (task_id, heartbeat_ts, current_node_id, process_id)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(task_id) DO UPDATE SET
                        heartbeat_ts = excluded.heartbeat_ts,
                        current_node_id = excluded.current_node_id,
                        process_id = excluded.process_id
                """, (task_id, time.time(), current_node_id, os.getpid()))
        finally:
            conn.close()

    def delete_heartbeat(self, task_id: str):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM task_heartbeats WHERE task_id = ?", (task_id,))
        finally:
            conn.close()

    def get_heartbeat(self, task_id: str) -> Optional[TaskHeartbeat]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM task_heartbeats WHERE task_id = ?", (task_id,))
            r = cursor.fetchone()
            if not r:
                return None
            return TaskHeartbeat(
                task_id=r["task_id"],
                timestamp=r["heartbeat_ts"],
                current_node_id=r["current_node_id"],
                process_id=r["process_id"]
            )
        finally:
            conn.close()

    def persist_resource_lock(self, resource_id: str, task_id: str):
        conn = self._get_connection()
        try:
            with conn:
                lock_id = str(uuid.uuid4())[:8]
                now = time.time()
                conn.execute("""
                    INSERT INTO task_resource_locks (lock_id, resource_id, task_id, acquired_at, heartbeat_ts, process_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(resource_id) DO UPDATE SET
                        task_id = excluded.task_id,
                        heartbeat_ts = excluded.heartbeat_ts,
                        process_id = excluded.process_id
                """, (lock_id, resource_id, task_id, now, now, os.getpid()))
        finally:
            conn.close()

    def release_resource_lock(self, resource_id: str, task_id: str):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM task_resource_locks WHERE resource_id = ? AND task_id = ?", (resource_id, task_id))
        finally:
            conn.close()

    def release_all_task_locks(self, task_id: str):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM task_resource_locks WHERE task_id = ?", (task_id,))
        finally:
            conn.close()

    def reclaim_stale_locks(self, timeout_sec: float = 30.0) -> List[str]:
        """Detects and releases resource locks owned by dead processes or dead tasks."""
        cutoff = time.time() - timeout_sec
        conn = self._get_connection()
        reclaimed = []
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("SELECT resource_id, task_id, process_id FROM task_resource_locks WHERE heartbeat_ts < ?", (cutoff,))
                stale = cursor.fetchall()
                for row in stale:
                    res_id = row["resource_id"]
                    reclaimed.append(res_id)
                    cursor.execute("DELETE FROM task_resource_locks WHERE resource_id = ?", (res_id,))
            return reclaimed
        finally:
            conn.close()

    # --- Retention & Cleanup ---

    def prune_history(self, completed_task_retention_days: int = 7) -> int:
        """Deletes completed or cancelled tasks older than retention threshold without affecting active state."""
        cutoff = time.time() - (completed_task_retention_days * 86400)
        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM tasks
                    WHERE status IN ('COMPLETED', 'FAILED', 'CANCELLED', 'TIMED_OUT')
                      AND updated_at < ?
                """, (cutoff,))
                return cursor.rowcount
        finally:
            conn.close()

# Singleton instance
persistence_store = TaskPersistenceStore()
