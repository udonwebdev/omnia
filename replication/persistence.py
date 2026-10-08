import sqlite3
import json
import time
import logging
from typing import Optional, List, Dict, Any

from persistence.store import persistence_store, sanitize_payload
from replication.models import (
    StateRecord,
    StateDelta,
    Snapshot,
    SyncCursor,
    PeerSyncStatus,
    DeltaOperation
)

logger = logging.getLogger("Omnia.Replication.Persistence")

class ReplicationPersistenceManager:
    """Manages transactional durability and querying for replication state, deltas, snapshots, and cursors."""

    def __init__(self, store=None):
        self.store = store or persistence_store
        self.ensure_default_namespaces()

    def save_namespace(self, ns):
        conn = self.store._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO replication_namespaces (
                        namespace_id, name, owner_type, replication_policy,
                        consistency_policy, sensitivity, schema_version, enabled,
                        created_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace_id) DO UPDATE SET
                        name = excluded.name,
                        replication_policy = excluded.replication_policy,
                        consistency_policy = excluded.consistency_policy,
                        sensitivity = excluded.sensitivity,
                        enabled = excluded.enabled
                """, (
                    ns.namespace_id, ns.name, ns.owner_type, ns.replication_policy.value,
                    ns.consistency_policy.value, ns.sensitivity.value, ns.schema_version,
                    1 if ns.enabled else 0, ns.created_at, json.dumps(ns.metadata)
                ))
        finally:
            conn.close()

    def ensure_default_namespaces(self):
        from replication.namespaces import DEFAULT_NAMESPACES
        for ns in DEFAULT_NAMESPACES.values():
            self.save_namespace(ns)

    def save_state_record(self, record: StateRecord):
        conn = self.store._get_connection()
        try:
            with conn:
                sanitized_payload = sanitize_payload(record.payload)
                conn.execute("""
                    INSERT INTO replication_state_records (
                        state_id, namespace_id, entity_type, entity_id, owner_node,
                        owner_epoch, revision, payload_json, schema_version, created_at,
                        updated_at, integrity_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace_id, entity_type, entity_id) DO UPDATE SET
                        owner_node = excluded.owner_node,
                        owner_epoch = excluded.owner_epoch,
                        revision = excluded.revision,
                        payload_json = excluded.payload_json,
                        schema_version = excluded.schema_version,
                        updated_at = excluded.updated_at,
                        integrity_hash = excluded.integrity_hash
                """, (
                    record.state_id, record.namespace_id, record.entity_type,
                    record.entity_id, record.owner_node, record.owner_epoch,
                    record.revision, json.dumps(sanitized_payload), record.schema_version,
                    record.created_at, record.updated_at, record.integrity_hash
                ))
        finally:
            conn.close()

    def get_state_record(self, namespace_id: str, entity_id: str, entity_type: str = "ENTITY") -> Optional[StateRecord]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM replication_state_records 
                WHERE namespace_id = ? AND entity_id = ? AND entity_type = ?
            """, (namespace_id, entity_id, entity_type))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_record(row)
        finally:
            conn.close()

    def list_records_for_namespace(self, namespace_id: str) -> List[StateRecord]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM replication_state_records 
                WHERE namespace_id = ? 
                ORDER BY entity_id ASC
            """, (namespace_id,))
            return [self._row_to_record(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def save_delta(self, delta: StateDelta):
        conn = self.store._get_connection()
        try:
            with conn:
                sanitized_payload = sanitize_payload(delta.payload)
                conn.execute("""
                    INSERT INTO replication_deltas (
                        delta_id, namespace_id, entity_id, source_node, source_epoch,
                        base_revision, target_revision, operation, payload_json,
                        causal_metadata_json, integrity_hash, created_at, applied_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(delta_id) DO NOTHING
                """, (
                    delta.delta_id, delta.namespace_id, delta.entity_id, delta.source_node,
                    delta.source_epoch, delta.base_revision, delta.target_revision,
                    delta.operation.value, json.dumps(sanitized_payload),
                    json.dumps(delta.causal_metadata), delta.integrity_hash,
                    delta.created_at, time.time()
                ))
        finally:
            conn.close()

    def get_deltas_since(self, namespace_id: str, since_revision: int) -> List[StateDelta]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM replication_deltas 
                WHERE namespace_id = ? AND target_revision > ? 
                ORDER BY target_revision ASC
            """, (namespace_id, since_revision))
            return [self._row_to_delta(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def save_snapshot(self, snapshot: Snapshot):
        conn = self.store._get_connection()
        try:
            with conn:
                records_data = [
                    {
                        "state_id": r.state_id, "namespace_id": r.namespace_id,
                        "entity_type": r.entity_type, "entity_id": r.entity_id,
                        "owner_node": r.owner_node, "owner_epoch": r.owner_epoch,
                        "revision": r.revision, "payload": r.payload,
                        "schema_version": r.schema_version, "created_at": r.created_at,
                        "updated_at": r.updated_at, "integrity_hash": r.integrity_hash
                    }
                    for r in snapshot.records
                ]
                conn.execute("""
                    INSERT INTO replication_snapshots (
                        snapshot_id, namespace_id, source_node, source_epoch, revision,
                        created_at, schema_version, record_count, content_hash, records_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(snapshot_id) DO UPDATE SET
                        content_hash = excluded.content_hash,
                        records_json = excluded.records_json
                """, (
                    snapshot.snapshot_id, snapshot.namespace_id, snapshot.source_node,
                    snapshot.source_epoch, snapshot.revision, snapshot.created_at,
                    snapshot.schema_version, snapshot.record_count, snapshot.content_hash,
                    json.dumps(records_data)
                ))
        finally:
            conn.close()

    def save_sync_cursor(self, cursor_obj: SyncCursor):
        conn = self.store._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO replication_sync_cursors (
                        peer_node, namespace_id, last_applied_revision,
                        last_acknowledged_revision, last_verified_revision,
                        last_sync_time, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(peer_node, namespace_id) DO UPDATE SET
                        last_applied_revision = excluded.last_applied_revision,
                        last_acknowledged_revision = excluded.last_acknowledged_revision,
                        last_verified_revision = excluded.last_verified_revision,
                        last_sync_time = excluded.last_sync_time,
                        status = excluded.status
                """, (
                    cursor_obj.peer_node, cursor_obj.namespace_id,
                    cursor_obj.last_applied_revision, cursor_obj.last_acknowledged_revision,
                    cursor_obj.last_verified_revision, cursor_obj.last_sync_time,
                    cursor_obj.status.value
                ))
        finally:
            conn.close()

    def get_sync_cursor(self, peer_node: str, namespace_id: str) -> Optional[SyncCursor]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM replication_sync_cursors 
                WHERE peer_node = ? AND namespace_id = ?
            """, (peer_node, namespace_id))
            row = cursor.fetchone()
            if not row:
                return None
            return SyncCursor(
                peer_node=row["peer_node"],
                namespace_id=row["namespace_id"],
                last_applied_revision=row["last_applied_revision"],
                last_acknowledged_revision=row["last_acknowledged_revision"],
                last_verified_revision=row["last_verified_revision"],
                last_sync_time=row["last_sync_time"],
                status=PeerSyncStatus(row["status"])
            )
        finally:
            conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> StateRecord:
        return StateRecord(
            state_id=row["state_id"],
            namespace_id=row["namespace_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            owner_node=row["owner_node"],
            owner_epoch=row["owner_epoch"],
            revision=row["revision"],
            payload=json.loads(row["payload_json"] or "{}"),
            schema_version=row["schema_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            integrity_hash=row["integrity_hash"]
        )

    def _row_to_delta(self, row: sqlite3.Row) -> StateDelta:
        return StateDelta(
            delta_id=row["delta_id"],
            namespace_id=row["namespace_id"],
            entity_id=row["entity_id"],
            source_node=row["source_node"],
            source_epoch=row["source_epoch"],
            base_revision=row["base_revision"],
            target_revision=row["target_revision"],
            operation=DeltaOperation(row["operation"]),
            payload=json.loads(row["payload_json"] or "{}"),
            causal_metadata=json.loads(row["causal_metadata_json"] or "{}"),
            integrity_hash=row["integrity_hash"],
            created_at=row["created_at"]
        )

replication_persistence = ReplicationPersistenceManager()
