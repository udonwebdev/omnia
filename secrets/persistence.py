import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional
from secrets.models import (
    SecretRecord,
    SecretVersionRecord,
    SecretLease,
    SecretAuditRecord,
    SecretStatus,
    SecretType
)

logger = logging.getLogger("Omnia.Secrets.Persistence")

class SecretPersistence:
    """SQLite persistence repository for secret metadata, encrypted versions, leases, and audit logs."""

    def __init__(self, db_path: str = "persistence/omnia_tasks.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Secret Metadata ---
    def save_secret_metadata(self, meta: SecretRecord) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO secret_metadata (
                    secret_id, name, secret_type, provider, scope, version,
                    status, created_at, updated_at, expires_at, last_rotated_at,
                    last_used_at, rotation_policy_json, access_policy_json, integrity_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                meta.secret_id,
                meta.name,
                meta.secret_type.value,
                meta.provider,
                meta.scope,
                meta.version,
                meta.status.value,
                meta.created_at,
                meta.updated_at,
                meta.expires_at,
                meta.last_rotated_at,
                meta.last_used_at,
                json.dumps(meta.rotation_policy),
                json.dumps(meta.access_policy),
                meta.integrity_hash
            ))
            conn.commit()
            return True

    def get_secret_metadata(self, secret_id: str) -> Optional[SecretRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM secret_metadata WHERE secret_id = ?", (secret_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_metadata(row)

    def list_secrets_metadata(self, scope: Optional[str] = None) -> List[SecretRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if scope:
                cursor.execute("SELECT * FROM secret_metadata WHERE scope = ? ORDER BY created_at DESC", (scope,))
            else:
                cursor.execute("SELECT * FROM secret_metadata ORDER BY created_at DESC")
            return [self._row_to_metadata(r) for r in cursor.fetchall()]

    def _row_to_metadata(self, r: sqlite3.Row) -> SecretRecord:
        return SecretRecord(
            secret_id=r["secret_id"],
            name=r["name"],
            secret_type=SecretType(r["secret_type"]),
            provider=r["provider"],
            scope=r["scope"],
            version=r["version"],
            status=SecretStatus(r["status"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            expires_at=r["expires_at"],
            last_rotated_at=r["last_rotated_at"],
            last_used_at=r["last_used_at"],
            rotation_policy=json.loads(r["rotation_policy_json"]),
            access_policy=json.loads(r["access_policy_json"]),
            integrity_hash=r["integrity_hash"]
        )

    # --- Secret Versions ---
    def save_secret_version(self, ver: SecretVersionRecord) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO secret_versions (
                    secret_id, version, status, created_at, activated_at,
                    retired_at, fingerprint, ciphertext, key_id, salt, nonce
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ver.secret_id,
                ver.version,
                ver.status.value,
                ver.created_at,
                ver.activated_at,
                ver.retired_at,
                ver.fingerprint,
                ver.ciphertext,
                ver.key_id,
                ver.salt,
                ver.nonce
            ))
            conn.commit()
            return True

    def get_secret_version(self, secret_id: str, version: int) -> Optional[SecretVersionRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM secret_versions WHERE secret_id = ? AND version = ?", (secret_id, version))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_version(row)

    def list_secret_versions(self, secret_id: str) -> List[SecretVersionRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM secret_versions WHERE secret_id = ? ORDER BY version DESC", (secret_id,))
            return [self._row_to_version(r) for r in cursor.fetchall()]

    def _row_to_version(self, r: sqlite3.Row) -> SecretVersionRecord:
        return SecretVersionRecord(
            secret_id=r["secret_id"],
            version=r["version"],
            status=SecretStatus(r["status"]),
            created_at=r["created_at"],
            activated_at=r["activated_at"],
            retired_at=r["retired_at"],
            fingerprint=r["fingerprint"],
            ciphertext=r["ciphertext"],
            key_id=r["key_id"],
            salt=r["salt"],
            nonce=r["nonce"]
        )

    # --- Secret Leases ---
    def save_lease(self, lease: SecretLease) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO secret_leases (
                    lease_id, secret_id, version, requester, purpose,
                    capability, scope, node_id, issued_at, expires_at,
                    revoked_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lease.lease_id,
                lease.secret_id,
                lease.version,
                lease.requester,
                lease.purpose,
                lease.capability,
                lease.scope,
                lease.node_id,
                lease.issued_at,
                lease.expires_at,
                lease.revoked_at,
                lease.status
            ))
            conn.commit()
            return True

    def get_lease(self, lease_id: str) -> Optional[SecretLease]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM secret_leases WHERE lease_id = ?", (lease_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_lease(row)

    def list_active_leases(self, secret_id: Optional[str] = None) -> List[SecretLease]:
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if secret_id:
                cursor.execute("""
                    SELECT * FROM secret_leases 
                    WHERE status = 'ACTIVE' AND revoked_at IS NULL AND expires_at > ? AND secret_id = ?
                """, (now, secret_id))
            else:
                cursor.execute("""
                    SELECT * FROM secret_leases 
                    WHERE status = 'ACTIVE' AND revoked_at IS NULL AND expires_at > ?
                """, (now,))
            return [self._row_to_lease(r) for r in cursor.fetchall()]

    def revoke_lease(self, lease_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE secret_leases SET status = 'REVOKED', revoked_at = ? WHERE lease_id = ?",
                (time.time(), lease_id)
            )
            conn.commit()
            return True

    def _row_to_lease(self, r: sqlite3.Row) -> SecretLease:
        return SecretLease(
            lease_id=r["lease_id"],
            secret_id=r["secret_id"],
            version=r["version"],
            requester=r["requester"],
            purpose=r["purpose"],
            capability=r["capability"],
            scope=r["scope"],
            node_id=r["node_id"],
            issued_at=r["issued_at"],
            expires_at=r["expires_at"],
            revoked_at=r["revoked_at"],
            status=r["status"]
        )

    # --- Audit Logs ---
    def record_audit(self, record: SecretAuditRecord) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO secret_audit_log (
                    event_id, secret_id, version, requester, purpose,
                    capability, scope, node_id, action, result, timestamp, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.event_id,
                record.secret_id,
                record.version,
                record.requester,
                record.purpose,
                record.capability,
                record.scope,
                record.node_id,
                record.action,
                record.result,
                record.timestamp,
                json.dumps(record.details)
            ))
            conn.commit()
            return True

    def list_audit_logs(self, secret_id: Optional[str] = None, limit: int = 50) -> List[SecretAuditRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if secret_id:
                cursor.execute("SELECT * FROM secret_audit_log WHERE secret_id = ? ORDER BY timestamp DESC LIMIT ?", (secret_id, limit))
            else:
                cursor.execute("SELECT * FROM secret_audit_log ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [
                SecretAuditRecord(
                    event_id=r["event_id"],
                    secret_id=r["secret_id"],
                    version=r["version"],
                    requester=r["requester"],
                    purpose=r["purpose"],
                    capability=r["capability"],
                    scope=r["scope"],
                    node_id=r["node_id"],
                    action=r["action"],
                    result=r["result"],
                    timestamp=r["timestamp"],
                    details=json.loads(r["details_json"])
                )
                for r in cursor.fetchall()
            ]
