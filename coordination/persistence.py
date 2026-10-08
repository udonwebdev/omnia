import sqlite3
import json
import time
import logging
from typing import Optional, List, Dict, Any

from persistence.store import persistence_store, sanitize_payload
from coordination.models import (
    NodeIdentity,
    NodeTrustState,
    NodeMembershipState,
    LeadershipLease,
    OwnershipClaim,
    OwnershipState,
    DistributedLock,
    LockState
)

logger = logging.getLogger("Omnia.Coordination.Persistence")

class CoordinationPersistenceManager:
    """Manages transactional durability, querying, and crash recovery for distributed coordination."""

    def __init__(self, store=None):
        self.store = store or persistence_store

    def save_node(self, node: NodeIdentity):
        conn = self.store._get_connection()
        try:
            with conn:
                sanitized_meta = sanitize_payload(node.metadata)
                conn.execute("""
                    INSERT INTO cluster_nodes (
                        node_id, node_name, node_version, public_key, identity_fingerprint,
                        platform, architecture, endpoint_url, trust_state, membership_state,
                        created_at, last_seen, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(node_id) DO UPDATE SET
                        node_name = excluded.node_name,
                        node_version = excluded.node_version,
                        endpoint_url = excluded.endpoint_url,
                        trust_state = excluded.trust_state,
                        membership_state = excluded.membership_state,
                        last_seen = excluded.last_seen,
                        metadata_json = excluded.metadata_json
                """, (
                    node.node_id, node.node_name, node.node_version, node.public_key,
                    node.identity_fingerprint, node.platform, node.architecture,
                    node.endpoint_url, node.trust_state.value, node.membership_state.value,
                    node.created_at, node.last_seen, json.dumps(sanitized_meta)
                ))
        finally:
            conn.close()

    def get_node(self, node_id: str) -> Optional[NodeIdentity]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cluster_nodes WHERE node_id = ?", (node_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_node(row)
        finally:
            conn.close()

    def list_nodes(self) -> List[NodeIdentity]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cluster_nodes ORDER BY created_at ASC")
            return [self._row_to_node(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def save_leadership_lease(self, lease: LeadershipLease):
        conn = self.store._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO leadership_leases (
                        lease_id, leader_id, epoch, issued_at, expires_at,
                        renewal_sequence, state, fencing_token
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(lease_id) DO UPDATE SET
                        leader_id = excluded.leader_id,
                        epoch = excluded.epoch,
                        issued_at = excluded.issued_at,
                        expires_at = excluded.expires_at,
                        renewal_sequence = excluded.renewal_sequence,
                        state = excluded.state,
                        fencing_token = excluded.fencing_token
                """, (
                    lease.lease_id, lease.leader_id, lease.epoch, lease.issued_at,
                    lease.expires_at, lease.renewal_sequence,
                    "ACTIVE" if not lease.is_expired() else "EXPIRED",
                    lease.fencing_token
                ))
        finally:
            conn.close()

    def get_active_leadership_lease(self) -> Optional[LeadershipLease]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            now = time.time()
            cursor.execute("""
                SELECT * FROM leadership_leases 
                WHERE expires_at > ? AND state = 'ACTIVE'
                ORDER BY epoch DESC, expires_at DESC LIMIT 1
            """, (now,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_lease(row)
        finally:
            conn.close()

    def save_ownership_claim(self, claim: OwnershipClaim):
        conn = self.store._get_connection()
        try:
            with conn:
                sanitized_meta = sanitize_payload(claim.metadata)
                conn.execute("""
                    INSERT INTO distributed_ownership_claims (
                        claim_id, subject_type, subject_id, owner_node_id, epoch,
                        issued_at, expires_at, fencing_token, state, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(subject_type, subject_id) DO UPDATE SET
                        claim_id = excluded.claim_id,
                        owner_node_id = excluded.owner_node_id,
                        epoch = excluded.epoch,
                        issued_at = excluded.issued_at,
                        expires_at = excluded.expires_at,
                        fencing_token = excluded.fencing_token,
                        state = excluded.state,
                        metadata_json = excluded.metadata_json
                """, (
                    claim.claim_id, claim.subject_type, claim.subject_id, claim.owner_node_id,
                    claim.epoch, claim.issued_at, claim.expires_at, claim.fencing_token,
                    claim.state.value, json.dumps(sanitized_meta)
                ))
        finally:
            conn.close()

    def get_ownership_claim(self, subject_type: str, subject_id: str) -> Optional[OwnershipClaim]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM distributed_ownership_claims 
                WHERE subject_type = ? AND subject_id = ?
            """, (subject_type, subject_id))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_claim(row)
        finally:
            conn.close()

    def list_active_claims(self) -> List[OwnershipClaim]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            now = time.time()
            cursor.execute("""
                SELECT * FROM distributed_ownership_claims 
                WHERE expires_at > ? AND state = 'ACTIVE'
            """, (now,))
            return [self._row_to_claim(r) for r in cursor.fetchall()]
        finally:
            conn.close()

    def save_lock(self, lock: DistributedLock):
        conn = self.store._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO distributed_locks (
                        lock_id, resource_id, owner_node_id, epoch, fencing_token,
                        created_at, expires_at, state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(resource_id) DO UPDATE SET
                        lock_id = excluded.lock_id,
                        owner_node_id = excluded.owner_node_id,
                        epoch = excluded.epoch,
                        fencing_token = excluded.fencing_token,
                        created_at = excluded.created_at,
                        expires_at = excluded.expires_at,
                        state = excluded.state
                """, (
                    lock.lock_id, lock.resource_id, lock.owner_node_id, lock.epoch,
                    lock.fencing_token, lock.created_at, lock.expires_at, lock.state.value
                ))
        finally:
            conn.close()

    def get_lock(self, resource_id: str) -> Optional[DistributedLock]:
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM distributed_locks WHERE resource_id = ?", (resource_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_lock(row)
        finally:
            conn.close()

    def reconcile_on_startup(self) -> Dict[str, int]:
        """Reaps expired leadership leases and marks stale ownership claims as EXPIRED."""
        now = time.time()
        conn = self.store._get_connection()
        reaped_leases = 0
        reaped_claims = 0
        reaped_locks = 0
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE leadership_leases 
                    SET state = 'EXPIRED' 
                    WHERE expires_at <= ? AND state = 'ACTIVE'
                """, (now,))
                reaped_leases = cur.rowcount

                cur.execute("""
                    UPDATE distributed_ownership_claims 
                    SET state = 'EXPIRED' 
                    WHERE expires_at <= ? AND state = 'ACTIVE'
                """, (now,))
                reaped_claims = cur.rowcount

                cur.execute("""
                    UPDATE distributed_locks 
                    SET state = 'EXPIRED' 
                    WHERE expires_at <= ? AND state = 'ACQUIRED'
                """, (now,))
                reaped_locks = cur.rowcount
        finally:
            conn.close()

        logger.info(f"Coordination startup reconciliation complete: {reaped_leases} leases, {reaped_claims} claims, {reaped_locks} locks reaped.")
        return {
            "reaped_leases": reaped_leases,
            "reaped_claims": reaped_claims,
            "reaped_locks": reaped_locks
        }

    def _row_to_node(self, row: sqlite3.Row) -> NodeIdentity:
        return NodeIdentity(
            node_id=row["node_id"],
            node_name=row["node_name"],
            node_version=row["node_version"],
            public_key=row["public_key"],
            identity_fingerprint=row["identity_fingerprint"],
            platform=row["platform"],
            architecture=row["architecture"],
            endpoint_url=row["endpoint_url"],
            trust_state=NodeTrustState(row["trust_state"]),
            membership_state=NodeMembershipState(row["membership_state"]),
            created_at=row["created_at"],
            last_seen=row["last_seen"],
            metadata=json.loads(row["metadata_json"] or "{}")
        )

    def _row_to_lease(self, row: sqlite3.Row) -> LeadershipLease:
        return LeadershipLease(
            lease_id=row["lease_id"],
            leader_id=row["leader_id"],
            epoch=row["epoch"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            renewal_sequence=row["renewal_sequence"],
            fencing_token=row["fencing_token"]
        )

    def _row_to_claim(self, row: sqlite3.Row) -> OwnershipClaim:
        return OwnershipClaim(
            claim_id=row["claim_id"],
            subject_type=row["subject_type"],
            subject_id=row["subject_id"],
            owner_node_id=row["owner_node_id"],
            epoch=row["epoch"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            fencing_token=row["fencing_token"],
            state=OwnershipState(row["state"]),
            metadata=json.loads(row["metadata_json"] or "{}")
        )

    def _row_to_lock(self, row: sqlite3.Row) -> DistributedLock:
        return DistributedLock(
            lock_id=row["lock_id"],
            resource_id=row["resource_id"],
            owner_node_id=row["owner_node_id"],
            epoch=row["epoch"],
            fencing_token=row["fencing_token"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            state=LockState(row["state"])
        )
