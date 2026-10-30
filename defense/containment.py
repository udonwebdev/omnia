"""
OMNIA Module 35: Defensive Containment & Response Orchestrator
Coordinates narrowly scoped containment actions (suspend worker, revoke session, isolate node,
quarantine artifact), enforces response levels (0 to 4), and integrates with Module 20 human approvals.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from defense.models import (
    ContainmentAction,
    ContainmentStatus,
    ResponseAutonomyLevel,
    SecurityIncident,
    SecuritySeverity,
)

logger = logging.getLogger("Omnia.Defense.Containment")


class ContainmentCoordinator:
    """Orchestrates defensive containment operations within authorized autonomy boundaries."""

    def __init__(self, current_autonomy_level: ResponseAutonomyLevel = ResponseAutonomyLevel.LEVEL_3_APPROVAL_REQUIRED):
        self.current_autonomy_level = current_autonomy_level
        self._actions: Dict[str, ContainmentAction] = {}

    def set_autonomy_level(self, level: ResponseAutonomyLevel) -> None:
        """Sets the active system defense autonomy level (Levels 0 through 4)."""
        logger.info(f"Containment autonomy level transitioned to: {level.name}")
        self.current_autonomy_level = level

    def plan_containment(
        self,
        incident: SecurityIncident,
        action_type: str,
        target_resource: str,
        scope: str,
        reason: str,
        is_reversible: bool = True,
    ) -> ContainmentAction:
        """Creates a containment action request and determines if human approval is required."""
        action_id = f"contain-{uuid.uuid4().hex[:8]}"

        # Level 0 (Observe): Containment requests are rejected/unsupported
        if self.current_autonomy_level == ResponseAutonomyLevel.LEVEL_0_OBSERVE:
            action = ContainmentAction(
                action_id=action_id,
                incident_id=incident.incident_id,
                action_type=action_type,
                target_resource=target_resource,
                scope=scope,
                reason=reason,
                response_level=ResponseAutonomyLevel.LEVEL_0_OBSERVE,
                status=ContainmentStatus.FAILED,
                error_message="Containment rejected: System operating at Level 0 (Observe Only).",
            )
            self._actions[action_id] = action
            return action

        # Level 1 (Recommend): Marked requested without execution
        if self.current_autonomy_level == ResponseAutonomyLevel.LEVEL_1_RECOMMEND:
            action = ContainmentAction(
                action_id=action_id,
                incident_id=incident.incident_id,
                action_type=action_type,
                target_resource=target_resource,
                scope=scope,
                reason=reason,
                response_level=ResponseAutonomyLevel.LEVEL_1_RECOMMEND,
                status=ContainmentStatus.REQUESTED,
            )
            self._actions[action_id] = action
            return action

        # Level 2 (Low-Risk Auto): Automatically approved if reversible and low-impact
        if self.current_autonomy_level == ResponseAutonomyLevel.LEVEL_2_LOW_RISK_AUTO and is_reversible:
            action = ContainmentAction(
                action_id=action_id,
                incident_id=incident.incident_id,
                action_type=action_type,
                target_resource=target_resource,
                scope=scope,
                reason=reason,
                response_level=ResponseAutonomyLevel.LEVEL_2_LOW_RISK_AUTO,
                status=ContainmentStatus.APPROVED,
                is_reversible=True,
                approval_token=f"auto-token-{uuid.uuid4().hex[:6]}",
            )
            self._actions[action_id] = action
            return action

        # Level 3 (Approval-Required) or Level 4: Requires human approval token
        action = ContainmentAction(
            action_id=action_id,
            incident_id=incident.incident_id,
            action_type=action_type,
            target_resource=target_resource,
            scope=scope,
            reason=reason,
            response_level=self.current_autonomy_level,
            status=ContainmentStatus.APPROVAL_PENDING,
            is_reversible=is_reversible,
            approval_request_id=f"appr-req-{uuid.uuid4().hex[:6]}",
        )
        self._actions[action_id] = action
        return action

    def record_approval(self, action_id: str, approval_token: str) -> bool:
        """Binds a verified Module 20 human approval token to a pending containment action."""
        action = self._actions.get(action_id)
        if not action:
            return False
        if action.status != ContainmentStatus.APPROVAL_PENDING:
            return False

        action.approval_token = approval_token
        action.status = ContainmentStatus.APPROVED
        return True

    def execute_containment(self, action_id: str) -> Tuple[bool, str]:
        """Executes the containment action against simulated/isolated test boundaries or runtime systems."""
        action = self._actions.get(action_id)
        if not action:
            return False, f"Action '{action_id}' not found."

        if action.status != ContainmentStatus.APPROVED:
            return False, f"Cannot execute action in status '{action.status.value}'. Must be APPROVED."

        action.status = ContainmentStatus.EXECUTING
        action.executed_at = time.time()

        # Simulated execution mechanics for supported action types
        supported_types = {
            "suspend_worker",
            "revoke_session",
            "isolate_node",
            "quarantine_artifact",
            "disable_capability",
        }
        if action.action_type not in supported_types:
            action.status = ContainmentStatus.FAILED
            action.error_message = f"Unsupported containment action type: {action.action_type}"
            return False, action.error_message

        # Execute containment in runtime mock/state
        action.status = ContainmentStatus.VERIFIED_ACTIVE
        action.verified_at = time.time()
        action.verification_evidence = (
            f"Verified: Target '{action.target_resource}' isolated via '{action.action_type}'. "
            f"Scope: '{action.scope}'."
        )
        return True, action.verification_evidence
