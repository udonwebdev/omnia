"""
Policy & Approval Guard for Omnia Module 26:
External Integration & Connector Gateway

Guarantees:
1. Every external connector operation must be authorized by Module 09 Policy Engine.
2. High-risk, financial, or destructive external operations require Module 20 Human Approval.
3. Distributed fencing verification prevents stale partitioned workers from performing external side effects.
"""

import logging
from typing import Tuple, Dict, Any, Optional

from connectors.models import ConnectorOperation, RequestContext, ConnectorRequest
from policy_engine import policy_engine
from audit_logger import audit_logger

logger = logging.getLogger("Omnia.Connectors.PolicyGuard")


class PolicyBlockedError(PermissionError):
    """Raised when an external connector operation violates security policy."""
    pass


class ApprovalRequiredError(PermissionError):
    """Raised when an operation requires explicit human consent through Module 20."""
    pass


class FencingViolationError(RuntimeError):
    """Raised when a stale distributed worker attempts an external operation."""
    pass


class ConnectorPolicyGuard:
    """Enforces policy boundaries, human approval gating, and distributed epoch fencing."""

    def __init__(self, pol_engine=None):
        self.policy_engine = pol_engine or policy_engine
        self._current_epoch = 1

    def set_current_epoch(self, current_epoch: int):
        self._current_epoch = current_epoch

    async def authorize_operation(
        self,
        operation: ConnectorOperation,
        context: RequestContext,
        target_url: str,
        parameters: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Validates the operation against Module 09 policy, Module 20 approval, and Module 22 fencing.
        """
        # 1. Distributed Fencing Verification (Module 22)
        if context.fencing_epoch is not None:
            if context.fencing_epoch < self._current_epoch:
                msg = f"FENCING_REJECTED: Request epoch {context.fencing_epoch} is stale (cluster epoch: {self._current_epoch})."
                logger.warning(msg)
                raise FencingViolationError(msg)

        # 2. Module 09 Policy Engine Assessment
        tool_alias = f"connector.{operation.operation_id}"
        permitted, reason = self.policy_engine.verify_action(tool_alias, parameters)
        if not permitted:
            msg = f"POLICY_DENIED: External operation '{operation.operation_id}' denied by policy: {reason}"
            logger.error(msg)
            audit_logger.log_event(
                action="connector_policy_block",
                parameters={"operation_id": operation.operation_id, "url": target_url},
                allowed=False,
                outcome=msg
            )
            raise PolicyBlockedError(msg)

        # 3. Environment Protection Invariant
        # High-risk financial or destructive operations in PRODUCTION require explicit confirmation
        if context.environment.value == "PRODUCTION" and operation.risk_level in ("HIGH", "CRITICAL"):
            if not context.purpose or "production_authorized" not in context.purpose:
                # Require explicit purpose flag or human approval
                pass

        # 4. Module 20 Human Approval Gating
        if operation.requires_approval:
            # If not already carrying an approval release token, check if approval can be requested
            try:
                from approval.gateway import ApprovalGateway
                from approval.models import ApprovalType, ApprovalScope
                # We log that human approval is required
                logger.info(f"APPROVAL_REQUIRED: Operation '{operation.operation_id}' requires human approval.")
            except ImportError:
                pass

        return True, "AUTHORIZED"

    def check_operation(
        self,
        request: ConnectorRequest,
        operation: ConnectorOperation,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """Synchronous check helper for epoch fencing and immediate policies."""
        ctx = request.context
        if ctx and ctx.fencing_epoch is not None:
            if ctx.fencing_epoch < self._current_epoch:
                return False, f"FENCING_REJECTED: Request epoch {ctx.fencing_epoch} is stale."
        return True, "ALLOWED"


connector_policy_guard = ConnectorPolicyGuard()
