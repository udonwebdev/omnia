"""
OMNIA Module 36: Controlled Remediation Planner & Self-Healing Coordinator
Formulates scoped remediation actions governed by Autonomy Levels 0 to 5.
Enforces retry budgets, reversibility, approval bindings (Module 20), and fails closed.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional
from observability.models import (
    InfrastructureRemediationAction,
    RemediationAutonomyLevel,
    RecoveryVerificationStatus,
    FailureCategory,
    DiagnosticHypothesis,
)
from observability.persistence import ObservabilityRepository

logger = logging.getLogger("Omnia.Observability.Remediation")


class RemediationPlanner:
    """Plans and coordinates self-healing actions within strict autonomy policies."""

    def __init__(self, repo: ObservabilityRepository):
        self.repo = repo

    def plan_remediation(
        self,
        target_component_id: str,
        hypothesis: DiagnosticHypothesis,
        autonomy_level: RemediationAutonomyLevel = RemediationAutonomyLevel.LEVEL_3_LOW_RISK_AUTO,
        proposed_action: Optional[str] = None,
        verification_window_seconds: float = 10.0,
    ) -> InfrastructureRemediationAction:
        """
        Creates an InfrastructureRemediationAction with explicit autonomy bounds.
        Level 4 actions (e.g. restarts, schema reloads) mandate human approval.
        """
        action_name = proposed_action or self._select_default_action(hypothesis.failure_category)
        
        # Enforce autonomy elevation rules:
        # High-impact actions require Level 4 approval
        if action_name in ("restart_service", "restart_worker", "rebuild_index", "reset_database_connections"):
            if int(autonomy_level) < int(RemediationAutonomyLevel.LEVEL_4_APPROVAL_REQUIRED):
                autonomy_level = RemediationAutonomyLevel.LEVEL_4_APPROVAL_REQUIRED

        action_id = f"rem-{uuid.uuid4().hex[:8]}"
        approval_req_id = None
        if int(autonomy_level) >= int(RemediationAutonomyLevel.LEVEL_4_APPROVAL_REQUIRED):
            approval_req_id = f"appr-{uuid.uuid4().hex[:8]}"

        action = InfrastructureRemediationAction(
            action_id=action_id,
            target_component_id=target_component_id,
            proposed_action=action_name,
            failure_category=hypothesis.failure_category,
            reason=hypothesis.explanation,
            autonomy_level=autonomy_level,
            status=RecoveryVerificationStatus.NOT_STARTED,
            is_reversible=True,
            approval_request_id=approval_req_id,
            retry_budget=2,
            retry_count=0,
            verification_window_seconds=verification_window_seconds,
            created_at=time.time(),
        )

        self.repo.save_remediation_action(action)
        logger.info(f"Planned remediation '{action.proposed_action}' (ID: {action_id}) under Autonomy Level {int(autonomy_level)}")
        return action

    def _select_default_action(self, category: FailureCategory) -> str:
        """Maps failure categories to standard remediation procedures."""
        if category == FailureCategory.NETWORK_FAILURE:
            return "reconnect_service"
        elif category == FailureCategory.RESOURCE_EXHAUSTION:
            return "clear_cache"
        elif category == FailureCategory.PROCESS_FAILURE:
            return "restart_worker"
        elif category == FailureCategory.DATABASE_FAILURE:
            return "reset_database_connections"
        elif category == FailureCategory.EVENT_PIPELINE_FAILURE:
            return "flush_queue_deadletters"
        return "reconnect_service"

    def authorize_remediation(self, action_id: str, approval_token: str) -> bool:
        """Attaches an authorized approval token to an approval-gated remediation action."""
        action = self.repo.get_remediation_action(action_id)
        if not action:
            return False
        if not approval_token or len(approval_token) < 8:
            logger.warning(f"Invalid approval token provided for action {action_id}")
            return False

        action.approval_token = approval_token
        self.repo.save_remediation_action(action)
        logger.info(f"Remediation action {action_id} authorized with token {approval_token[:8]}...")
        return True
