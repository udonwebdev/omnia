import logging
from typing import Dict, Any, Tuple

from events.models import Event

logger = logging.getLogger("Omnia.Events.Schemas")

# Core Event Schema Registry
EVENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "system.started": {
        "required_fields": ["node_id", "version"]
    },
    "system.health_changed": {
        "required_fields": ["subsystem", "old_health", "new_health"]
    },
    "device.discovered": {
        "required_fields": ["device_id", "device_type", "platform"]
    },
    "device.connected": {
        "required_fields": ["device_id", "platform"]
    },
    "device.disconnected": {
        "required_fields": ["device_id"]
    },
    "device.screen_changed": {
        "required_fields": ["device_id", "timestamp"]
    },
    "browser.started": {
        "required_fields": ["browser_type"]
    },
    "browser.navigation_started": {
        "required_fields": ["url"]
    },
    "browser.navigation_completed": {
        "required_fields": ["url", "status_code"]
    },
    "browser.navigation_failed": {
        "required_fields": ["url", "error"]
    },
    "vision.capture_completed": {
        "required_fields": ["frame_id", "width", "height"]
    },
    "vision.element_detected": {
        "required_fields": ["element_type", "confidence"]
    },
    "vision.verification_completed": {
        "required_fields": ["status", "strategy"]
    },
    "vision.verification_failed": {
        "required_fields": ["reason", "strategy"]
    },
    "task.created": {
        "required_fields": ["task_id", "goal"]
    },
    "task.started": {
        "required_fields": ["task_id"]
    },
    "task.node_started": {
        "required_fields": ["task_id", "node_id"]
    },
    "task.node_completed": {
        "required_fields": ["task_id", "node_id"]
    },
    "task.node_failed": {
        "required_fields": ["task_id", "node_id", "error"]
    },
    "task.recovery_started": {
        "required_fields": ["task_id", "strategy"]
    },
    "task.replanned": {
        "required_fields": ["task_id", "replan_count"]
    },
    "task.completed": {
        "required_fields": ["task_id", "progress"]
    },
    "task.cancelled": {
        "required_fields": ["task_id"]
    },
    "capability.registered": {
        "required_fields": ["capability_id", "category"]
    },
    "capability.available": {
        "required_fields": ["capability_id"]
    },
    "capability.degraded": {
        "required_fields": ["capability_id", "reason"]
    },
    "capability.unavailable": {
        "required_fields": ["capability_id", "reason"]
    },
    "intent.received": {
        "required_fields": ["intent_id", "raw_text"]
    },
    "intent.compiled": {
        "required_fields": ["intent_id", "plan_id", "steps_count"]
    },
    "intent.ambiguous": {
        "required_fields": ["intent_id", "clarification_question"]
    },
    "security.policy_evaluated": {
        "required_fields": ["action", "risk_level"]
    },
    "security.policy_blocked": {
        "required_fields": ["action", "reason"]
    },
    "security.approval_required": {
        "required_fields": ["action", "risk_level"]
    },
    "mission.started": {
        "required_fields": ["mission_id", "status"]
    },
    "mission.progress": {
        "required_fields": ["mission_id", "status", "decision"]
    },
    "mission.degraded": {
        "required_fields": ["mission_id", "status"]
    },
    "mission.stalled": {
        "required_fields": ["mission_id", "status"]
    },
    "mission.recovery_started": {
        "required_fields": ["mission_id", "status", "decision"]
    },
    "mission.replanned": {
        "required_fields": ["mission_id", "status", "decision"]
    },
    "mission.approval_required": {
        "required_fields": ["mission_id", "status", "decision"]
    },
    "mission.aborted": {
        "required_fields": ["mission_id", "status"]
    },
    "mission.completed": {
        "required_fields": ["mission_id", "status"]
    },
    "mission.failed": {
        "required_fields": ["mission_id", "status"]
    },
    "approval.created": {
        "required_fields": ["approval_id", "request_type", "risk_level"]
    },
    "approval.presented": {
        "required_fields": ["approval_id", "channel"]
    },
    "approval.waiting": {
        "required_fields": ["approval_id", "expires_in_sec"]
    },
    "approval.approved": {
        "required_fields": ["approval_id", "decision_id", "decided_by"]
    },
    "approval.rejected": {
        "required_fields": ["approval_id", "decision_id", "reason"]
    },
    "approval.deferred": {
        "required_fields": ["approval_id", "decision_id"]
    },
    "approval.expired": {
        "required_fields": ["approval_id"]
    },
    "approval.cancelled": {
        "required_fields": ["approval_id", "reason"]
    },
    "approval.invalidated": {
        "required_fields": ["approval_id", "reason"]
    },
    "approval.released": {
        "required_fields": ["approval_id", "release_token", "fingerprint"]
    },
    "approval.execution_blocked": {
        "required_fields": ["approval_id", "reason"]
    },
    "schedule.created": {
        "required_fields": ["schedule_id", "task_id"]
    },
    "schedule.admitted": {
        "required_fields": ["schedule_id", "slot_id"]
    },
    "schedule.deferred": {
        "required_fields": ["schedule_id", "reason"]
    },
    "schedule.waiting": {
        "required_fields": ["schedule_id", "conflict_type"]
    },
    "schedule.rejected": {
        "required_fields": ["schedule_id", "reason"]
    },
    "schedule.preempted": {
        "required_fields": ["schedule_id", "preempted_by", "reason"]
    },
    "schedule.completed": {
        "required_fields": ["schedule_id"]
    },
    "resource.reserved": {
        "required_fields": ["reservation_id", "schedule_id", "resource_id"]
    },
    "resource.released": {
        "required_fields": ["reservation_id", "resource_id"]
    },
    "resource.expired": {
        "required_fields": ["reservation_id", "resource_id"]
    },
    "resource.conflict": {
        "required_fields": ["schedule_id", "resource_id", "conflict_type"]
    },
    "resource.starvation": {
        "required_fields": ["schedule_id", "wait_duration_sec"]
    },
    "resource.deadlock": {
        "required_fields": ["cycle_tasks", "victim_task"]
    },
    "scheduler.pressure_changed": {
        "required_fields": ["old_pressure", "new_pressure"]
    },
    "coordination.started": {
        "required_fields": ["node_id", "epoch"]
    },
    "coordination.epoch_changed": {
        "required_fields": ["old_epoch", "new_epoch", "leader_id"]
    },
    "leader.election_started": {
        "required_fields": ["candidate_id", "epoch"]
    },
    "leader.elected": {
        "required_fields": ["leader_id", "epoch", "lease_expires_at"]
    },
    "leader.lost": {
        "required_fields": ["leader_id", "epoch", "reason"]
    },
    "node.joined": {
        "required_fields": ["node_id", "epoch"]
    },
    "node.left": {
        "required_fields": ["node_id", "reason"]
    },
    "node.suspected": {
        "required_fields": ["node_id", "last_seen_sec"]
    },
    "ownership.claimed": {
        "required_fields": ["claim_id", "subject_type", "subject_id", "owner_node_id", "epoch", "fencing_token"]
    },
    "ownership.released": {
        "required_fields": ["claim_id", "subject_id"]
    },
    "ownership.expired": {
        "required_fields": ["claim_id", "subject_id"]
    },
    "ownership.rejected": {
        "required_fields": ["subject_id", "attempted_by", "current_owner"]
    },
    "failover.started": {
        "required_fields": ["subject_id", "from_node", "to_node"]
    },
    "split_brain.detected": {
        "required_fields": ["competing_leaders", "epoch"]
    },
    "replication.started": {
        "required_fields": ["node_id", "peer_node"]
    },
    "replication.delta_received": {
        "required_fields": ["delta_id", "namespace_id", "entity_id", "revision"]
    },
    "replication.delta_applied": {
        "required_fields": ["delta_id", "namespace_id", "entity_id", "revision"]
    },
    "replication.delta_rejected": {
        "required_fields": ["delta_id", "namespace_id", "reason"]
    },
    "replication.snapshot_started": {
        "required_fields": ["snapshot_id", "namespace_id", "source_node"]
    },
    "replication.snapshot_applied": {
        "required_fields": ["snapshot_id", "namespace_id", "record_count"]
    },
    "replication.sync_completed": {
        "required_fields": ["peer_node", "namespace_id", "revision"]
    },
    "replication.sync_failed": {
        "required_fields": ["peer_node", "namespace_id", "reason"]
    },
    "replication.peer_lagging": {
        "required_fields": ["peer_node", "lag_revisions"]
    },
    "replication.conflict_detected": {
        "required_fields": ["conflict_id", "namespace_id", "entity_id"]
    },
    "replication.reconciliation_completed": {
        "required_fields": ["namespace_id", "status"]
    },
    "replication.state_diverged": {
        "required_fields": ["namespace_id", "local_hash", "remote_hash"]
    },
    "config.created": {
        "required_fields": ["version", "scope", "content_hash", "author"]
    },
    "config.validated": {
        "required_fields": ["version", "key_count", "status"]
    },
    "config.staged": {
        "required_fields": ["version", "scope"]
    },
    "config.rollout_started": {
        "required_fields": ["rollout_id", "version", "strategy", "target_nodes"]
    },
    "config.node_activated": {
        "required_fields": ["node_id", "version", "applied_keys"]
    },
    "config.node_failed": {
        "required_fields": ["node_id", "version", "error"]
    },
    "config.rollout_paused": {
        "required_fields": ["rollout_id", "version", "reason"]
    },
    "config.rollout_completed": {
        "required_fields": ["rollout_id", "version", "strategy"]
    },
    "config.rollback_started": {
        "required_fields": ["rollout_id", "from_version", "to_version", "reason"]
    },
    "config.rollback_completed": {
        "required_fields": ["rollout_id", "restored_version"]
    },
    "config.drift_detected": {
        "required_fields": ["drift_id", "node_id", "key", "expected_version"]
    },
    "config.drift_resolved": {
        "required_fields": ["drift_id", "node_id", "key"]
    },
    "config.approval_required": {
        "required_fields": ["version", "risk_level", "changes"]
    },
    # Video Studio Subsystem Events (Module 0)
    "video_studio.status_changed": {
        "required_fields": ["old_state", "new_state", "reason"]
    },
    "video_studio.job_queued": {
        "required_fields": ["job_id", "job_type", "project_id"]
    },
    "video_studio.job_completed": {
        "required_fields": ["job_id", "job_type", "duration_ms"]
    },
    "video_studio.job_failed": {
        "required_fields": ["job_id", "job_type", "error_type", "error_message"]
    },
    # Secrets & Credential Lifecycle Events (Module 25)
    "secret.created": {
        "required_fields": ["secret_id", "version", "secret_type", "scope", "provider"]
    },
    "secret.access_requested": {
        "required_fields": ["secret_id", "version", "requester", "purpose", "capability"]
    },
    "secret.access_granted": {
        "required_fields": ["lease_id", "secret_id", "version", "requester", "expires_at"]
    },
    "secret.access_denied": {
        "required_fields": ["secret_id", "requester", "purpose", "reason"]
    },
    "secret.rotation_started": {
        "required_fields": ["secret_id", "from_version", "to_version", "strategy"]
    },
    "secret.rotation_completed": {
        "required_fields": ["secret_id", "active_version"]
    },
    "secret.rotation_failed": {
        "required_fields": ["secret_id", "failed_version", "reason"]
    },
    "secret.revoked": {
        "required_fields": ["secret_id", "version", "reason"]
    },
    "secret.compromised": {
        "required_fields": ["secret_id", "version", "incident_id", "action_taken"]
    },
    "secret.expiring": {
        "required_fields": ["secret_id", "version", "expires_in_sec"]
    },
    "secret.expired": {
        "required_fields": ["secret_id", "version"]
    },
    "secret.provider_health_changed": {
        "required_fields": ["provider_id", "old_health", "new_health"]
    }
}

class EventSchemaValidator:
    """Validates that published events conform to expected contract schemas."""

    def validate_event(self, event: Event) -> Tuple[bool, str]:
        etype = event.type
        if not etype:
            return False, "SCHEMA_ERROR: Event type is missing or empty."

        # If schema is registered, enforce presence of required payload fields
        schema = EVENT_SCHEMAS.get(etype)
        if schema:
            req_fields = schema.get("required_fields", [])
            for rf in req_fields:
                if rf not in event.payload:
                    return False, f"SCHEMA_ERROR: Event '{etype}' missing required payload field '{rf}'."

        return True, "VALID"

event_schema_validator = EventSchemaValidator()
