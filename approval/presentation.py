import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from approval.models import ApprovalRequest, ApprovalPresentation, ApprovalDecisionType

logger = logging.getLogger("Omnia.Approval.Presentation")

class ApprovalPresentationManager:
    """Formats approval requests across multiple presentation channels (HUD, Voice, CLI, Desktop).
    Also interprets voice confirmation responses conservatively.
    """

    @staticmethod
    def format_for_channel(request: ApprovalRequest, channel: str = "HUD") -> ApprovalPresentation:
        """Constructs channel-tailored presentation payload."""
        channel_upper = channel.upper()
        now = time.time()
        expires_in = max(0.0, request.expires_at - now)

        reversible_str = "Yes" if request.is_reversible else "No (Irreversible)"
        priority = "CRITICAL" if request.risk_level in {"CRITICAL", "HIGH"} else "NORMAL"

        if channel_upper == "VOICE":
            # Terse, human conversational voice prompt
            formatted_prompt = (
                f"Omnia requires your confirmation to {request.title or request.requested_action}. "
                f"Risk level is {request.risk_level}. "
                f"Do you approve or reject?"
            )
        elif channel_upper == "CLI":
            formatted_prompt = (
                f"\n=== [APPROVAL REQUIRED: {request.approval_id}] ===\n"
                f"Title:       {request.title}\n"
                f"Action:      {request.requested_action}\n"
                f"Risk Level:  {request.risk_level}\n"
                f"Target:      {request.target_resource or request.target_device or 'N/A'}\n"
                f"Reversible:  {reversible_str}\n"
                f"Summary:     {request.summary}\n"
                f"Expires In:  {int(expires_in)}s\n"
                f"----------------------------------------------------\n"
                f"Enter: APPROVE / REJECT / DEFER\n"
            )
        else:
            # HUD / Desktop JSON structured representation
            formatted_prompt = (
                f"Approval Request [{request.approval_id}]: {request.title or request.requested_action} "
                f"({request.risk_level}). Summary: {request.summary}"
            )

        context = {
            "requested_action": request.requested_action,
            "action_params": request.action_params,
            "target_resource": request.target_resource,
            "target_device": request.target_device,
            "target_application": request.target_application,
            "expected_effect": request.expected_effect,
            "potential_side_effects": request.potential_side_effects,
            "policy_reference": request.policy_reference,
            "task_id": request.task_id,
            "mission_id": request.mission_id
        }

        return ApprovalPresentation(
            approval_id=request.approval_id,
            channel=channel_upper,
            priority=priority,
            title=request.title or request.requested_action,
            summary=request.summary or request.reason,
            risk_level=request.risk_level,
            target_resource=request.target_resource,
            is_reversible=request.is_reversible,
            expires_in_sec=round(expires_in, 1),
            context=context,
            formatted_prompt=formatted_prompt
        )

    @staticmethod
    def interpret_voice_response(
        voice_transcript: str,
        pending_requests: List[ApprovalRequest]
    ) -> Tuple[Optional[ApprovalDecisionType], Optional[str], float, str]:
        """Interprets human voice input for approvals.
        
        Invariant: Ambiguous voice responses are NEVER treated as approval.
        If more than one approval request is pending, generic 'yes' is ambiguous
        and must specify which approval or be rejected.
        
        Returns: (DecisionType or None, TargetApprovalId or None, Confidence, Explanation)
        """
        raw = (voice_transcript or "").strip().lower()
        if not raw:
            return None, None, 0.0, "Empty voice response."

        if not pending_requests:
            return None, None, 0.0, "No pending approval requests to respond to."

        # Explicit rejection phrases
        reject_keywords = ["no", "reject", "deny", "stop", "abort", "cancel", "do not", "don't"]
        # Explicit defer phrases
        defer_keywords = ["later", "defer", "hold on", "wait", "pause"]
        # Explicit approve phrases
        approve_keywords = ["yes", "approve", "confirm", "proceed", "go ahead", "authorized", "authorize"]

        # Check for specific approval ID mention in the transcript
        matched_request = None
        for req in pending_requests:
            clean_id = req.approval_id.lower().replace("_", " ")
            if req.approval_id.lower() in raw or clean_id in raw:
                matched_request = req
                break

        # If exactly 1 pending request, target is unambiguously that request
        if not matched_request:
            if len(pending_requests) == 1:
                matched_request = pending_requests[0]
            else:
                # Multiple pending requests without specific identifier
                return None, None, 0.0, f"Ambiguous voice response: {len(pending_requests)} pending approvals. Specify which request to answer."

        # Evaluate decision
        for kw in reject_keywords:
            if kw in raw:
                return ApprovalDecisionType.REJECT, matched_request.approval_id, 0.95, f"Matched voice rejection keyword '{kw}'."

        for kw in defer_keywords:
            if kw in raw:
                return ApprovalDecisionType.DEFER, matched_request.approval_id, 0.90, f"Matched voice defer keyword '{kw}'."

        for kw in approve_keywords:
            if kw in raw:
                return ApprovalDecisionType.APPROVE, matched_request.approval_id, 0.95, f"Matched voice approval keyword '{kw}'."

        return None, matched_request.approval_id, 0.0, f"Unrecognized or ambiguous voice input '{voice_transcript}'."

approval_presentation_manager = ApprovalPresentationManager()
