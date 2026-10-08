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
