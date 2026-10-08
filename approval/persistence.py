import sqlite3
import json
import time
import logging
from typing import Optional, List, Dict, Any

from persistence.store import persistence_store, sanitize_payload
from approval.models import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalRelease,
    ApprovalStatus,
    ApprovalType,
    ApprovalScope,
    ApprovalDecisionType
)

logger = logging.getLogger("Omnia.Approval.Persistence")

class ApprovalPersistenceManager:
    """Manages transactional durability, querying, and crash recovery for approvals."""

    def __init__(self, store=None):
        self.store = store or persistence_store

    def save_approval_request(self, req: ApprovalRequest) -> None:
        """Inserts or updates an approval request."""
        conn = self.store._get_connection()
        try:
            with conn:
                sanitized_meta = sanitize_payload(req.metadata)
                sanitized_params = sanitize_payload(req.action_params)
                conn.execute("""
                    INSERT INTO approval_requests (
                        approval_id, version, created_at, updated_at, request_type,
                        title, summary, reason, mission_id, task_id, task_node_id,
                        plan_version, capability_id, provider_id, risk_level,
                        policy_reference, requested_action, action_params_json,
                        target_resource, target_device, target_application,
                        expected_effect, potential_side_effects, is_reversible,
                        expires_at, scope, fingerprint, status, created_by,
                        correlation_id, causation_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(approval_id) DO UPDATE SET
                        version = excluded.version,
                        updated_at = excluded.updated_at,
                        request_type = excluded.request_type,
                        title = excluded.title,
                        summary = excluded.summary,
                        reason = excluded.reason,
                        mission_id = excluded.mission_id,
                        task_id = excluded.task_id,
                        task_node_id = excluded.task_node_id,
                        plan_version = excluded.plan_version,
                        capability_id = excluded.capability_id,
                        provider_id = excluded.provider_id,
                        risk_level = excluded.risk_level,
                        policy_reference = excluded.policy_reference,
                        requested_action = excluded.requested_action,
                        action_params_json = excluded.action_params_json,
                        target_resource = excluded.target_resource,
                        target_device = excluded.target_device,
                        target_application = excluded.target_application,
                        expected_effect = excluded.expected_effect,
                        potential_side_effects = excluded.potential_side_effects,
                        is_reversible = excluded.is_reversible,
                        expires_at = excluded.expires_at,
                        scope = excluded.scope,
                        fingerprint = excluded.fingerprint,
                        status = excluded.status,
                        created_by = excluded.created_by,
                        correlation_id = excluded.correlation_id,
                        causation_id = excluded.causation_id,
                        metadata_json = excluded.metadata_json
                """, (
                    req.approval_id, req.version, req.created_at, req.updated_at,
                    req.request_type.value, req.title, req.summary, req.reason,
                    req.mission_id, req.task_id, req.task_node_id, req.plan_version,
                    req.capability_id, req.provider_id, req.risk_level,
                    req.policy_reference, req.requested_action,
                    json.dumps(sanitized_params), req.target_resource, req.target_device,
                    req.target_application, req.expected_effect, req.potential_side_effects,
                    1 if req.is_reversible else 0, req.expires_at, req.scope.value,
                    req.fingerprint, req.status.value, req.created_by,
                    req.correlation_id, req.causation_id, json.dumps(sanitized_meta)
                ))
        finally:
            conn.close()

    def get_approval_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Loads approval request by ID."""
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM approval_requests WHERE approval_id = ?", (approval_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_request(row)
        finally:
            conn.close()

    def list_pending_approvals(self) -> List[ApprovalRequest]:
        """Retrieves all non-terminal approval requests."""
        terminal_statuses = [
            ApprovalStatus.EXECUTION_RELEASED.value,
            ApprovalStatus.REJECTED.value,
            ApprovalStatus.EXPIRED.value,
            ApprovalStatus.CANCELLED.value,
            ApprovalStatus.SUPERSEDED.value,
            ApprovalStatus.INVALIDATED.value,
            ApprovalStatus.WITHDRAWN.value,
            ApprovalStatus.FAILED_TO_VALIDATE.value
        ]
        placeholders = ",".join(["?"] * len(terminal_statuses))
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT * FROM approval_requests WHERE status NOT IN ({placeholders}) ORDER BY created_at ASC",
                terminal_statuses
            )
            rows = cursor.fetchall()
            return [self._row_to_request(r) for r in rows]
        finally:
            conn.close()

    def save_approval_decision(self, dec: ApprovalDecision) -> None:
        """Records a human decision persistently."""
        conn = self.store._get_connection()
        try:
            with conn:
                sanitized_meta = sanitize_payload(dec.metadata)
                conn.execute("""
                    INSERT INTO approval_decisions (
                        decision_id, approval_id, decision, decided_at, decided_by,
                        decision_source, device_id, session_id, reason,
                        approval_version, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(decision_id) DO UPDATE SET
                        decision = excluded.decision,
                        decided_at = excluded.decided_at,
                        reason = excluded.reason,
                        metadata_json = excluded.metadata_json
                """, (
                    dec.decision_id, dec.approval_id, dec.decision.value,
                    dec.decided_at, dec.decided_by, dec.decision_source,
                    dec.device_id, dec.session_id, dec.reason,
                    dec.approval_version, json.dumps(sanitized_meta)
                ))
        finally:
            conn.close()

    def save_approval_release(self, rel: ApprovalRelease) -> None:
        """Saves execution release token."""
        conn = self.store._get_connection()
        try:
            with conn:
                conn.execute("""
                    INSERT INTO approval_releases (
                        release_token, approval_id, task_id, task_node_id,
                        mission_id, authorized_action, authorization_scope,
                        fingerprint, authorized_at, expires_at, policy_reference,
                        consumed, consumed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
                    ON CONFLICT(release_token) DO UPDATE SET
                        fingerprint = excluded.fingerprint,
                        expires_at = excluded.expires_at
                """, (
                    rel.release_token, rel.approval_id, rel.task_id, rel.task_node_id,
                    rel.mission_id, rel.authorized_action, rel.authorization_scope.value,
                    rel.fingerprint, rel.authorized_at, rel.expires_at, rel.policy_reference
                ))
        finally:
            conn.close()

    def get_approval_release(self, release_token: str) -> Optional[ApprovalRelease]:
        """Retrieves release authorization token."""
        conn = self.store._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM approval_releases WHERE release_token = ?", (release_token,))
            row = cursor.fetchone()
            if not row:
                return None
            return ApprovalRelease(
                release_token=row["release_token"],
                approval_id=row["approval_id"],
                task_id=row["task_id"],
                task_node_id=row["task_node_id"],
                mission_id=row["mission_id"],
                authorized_action=row["authorized_action"],
                authorization_scope=ApprovalScope(row["authorization_scope"]),
                fingerprint=row["fingerprint"],
                authorized_at=row["authorized_at"],
                expires_at=row["expires_at"],
                policy_reference=row["policy_reference"]
            )
        finally:
            conn.close()

    def mark_release_consumed(self, release_token: str) -> bool:
        """Marks a one-time release token as consumed."""
        conn = self.store._get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    "UPDATE approval_releases SET consumed = 1, consumed_at = ? WHERE release_token = ? AND consumed = 0",
                    (time.time(), release_token)
                )
                return cursor.rowcount > 0
        finally:
            conn.close()

    def reconcile_on_startup(self) -> Dict[str, int]:
        """Crash recovery reconciler: checks pending approvals, marks expired ones as EXPIRED,
        and marks active waiting ones as RECOVERY_REQUIRED if context was interrupted.
        """
        now = time.time()
        pending = self.list_pending_approvals()
        expired_count = 0
        recovering_count = 0

        for req in pending:
            if req.is_expired(now):
                req.transition_to(ApprovalStatus.EXPIRED)
                self.save_approval_request(req)
                expired_count += 1
            else:
                # Still within timeout window: mark for recovery review
                if req.status in {ApprovalStatus.WAITING, ApprovalStatus.PRESENTING, ApprovalStatus.DELIVERED}:
                    req.transition_to(ApprovalStatus.RECOVERY_REQUIRED)
                    self.save_approval_request(req)
                    recovering_count += 1

        logger.info(f"Startup approval reconciliation: {expired_count} expired, {recovering_count} recovery required.")
        return {"expired": expired_count, "recovering": recovering_count}

    def _row_to_request(self, row: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            approval_id=row["approval_id"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            request_type=ApprovalType(row["request_type"]),
            title=row["title"],
            summary=row["summary"],
            reason=row["reason"],
            mission_id=row["mission_id"],
            task_id=row["task_id"],
            task_node_id=row["task_node_id"],
            plan_version=row["plan_version"],
            capability_id=row["capability_id"],
            provider_id=row["provider_id"],
            risk_level=row["risk_level"],
            policy_reference=row["policy_reference"],
            requested_action=row["requested_action"],
            action_params=json.loads(row["action_params_json"] or "{}"),
            target_resource=row["target_resource"],
            target_device=row["target_device"],
            target_application=row["target_application"],
            expected_effect=row["expected_effect"] or "",
            potential_side_effects=row["potential_side_effects"] or "",
            is_reversible=bool(row["is_reversible"]),
            expires_at=row["expires_at"],
            scope=ApprovalScope(row["scope"]),
            fingerprint=row["fingerprint"],
            status=ApprovalStatus(row["status"]),
            created_by=row["created_by"],
            correlation_id=row["correlation_id"] or "",
            causation_id=row["causation_id"],
            metadata=json.loads(row["metadata_json"] or "{}")
        )

approval_persistence_manager = ApprovalPersistenceManager()
