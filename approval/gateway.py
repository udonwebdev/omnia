import asyncio
import time
import uuid
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable, Tuple

from approval.models import (
    ApprovalRequest,
    ApprovalDecision,
    ApprovalRelease,
    ApprovalStatus,
    ApprovalType,
    ApprovalScope,
    ApprovalDecisionType,
    ApprovalPresentation
)
from approval.fingerprints import fingerprint_generator
from approval.presentation import approval_presentation_manager
from approval.persistence import approval_persistence_manager
from policy_engine import policy_engine

logger = logging.getLogger("Omnia.Approval.Gateway")

class ApprovalGateway:
    """Authoritative Human Approval Gateway and Consent Orchestrator for Omnia.
    
    Invariants:
    1. Silence, timeout, UI close, or ambiguous response is NEVER treated as approval (UNKNOWN = NOT APPROVED).
    2. Approval NEVER overrides policy (If policy rejects, human cannot approve execution).
    3. An approval token is bound cryptographically to its action fingerprint. Stale plan versions or modified arguments invalidate it.
    4. One-time tokens (ONCE scope) are consumed atomically on execution.
    """

    def __init__(self, persistence_mgr=None, presentation_mgr=None, fp_gen=None):
        self.persistence = persistence_mgr or approval_persistence_manager
        self.presentation = presentation_mgr or approval_presentation_manager
        self.fp_generator = fp_gen or fingerprint_generator
        self._active_requests: Dict[str, ApprovalRequest] = {}
        self._waiting_futures: Dict[str, asyncio.Future] = {}
        self._dedup_cache: Dict[str, str] = {}  # dedup_key -> approval_id

    async def create_request(
        self,
        requested_action: str,
        action_params: Dict[str, Any],
        title: str,
        summary: str,
        reason: str,
        risk_level: str = "HIGH",
        request_type: ApprovalType = ApprovalType.POLICY_REQUIRED,
        scope: ApprovalScope = ApprovalScope.ONCE,
        target_resource: Optional[str] = None,
        target_device: Optional[str] = None,
        target_application: Optional[str] = None,
        is_reversible: bool = False,
        timeout_sec: float = 120.0,
        task_id: Optional[str] = None,
        task_node_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        plan_version: int = 1,
        policy_reference: Optional[str] = None,
        dedup_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ApprovalRequest:
        """Creates and stages a human consent request."""
        # 1. Deduplication check
        if dedup_key and dedup_key in self._dedup_cache:
            existing_id = self._dedup_cache[dedup_key]
            existing = self.persistence.get_approval_request(existing_id)
            if existing and not existing.is_terminal() and not existing.is_expired():
                logger.info(f"Deduplication hit: Reusing existing approval request {existing_id}")
                return existing

        # 2. Check policy engine: Policy can block immediately regardless of human consent
        allowed, policy_msg = policy_engine.verify_action(requested_action, action_params)
        if not allowed and "Blocked:" in policy_msg:
            # Irrevocable hard block: Cannot ask for approval
            logger.error(f"HARD_POLICY_BLOCK: Action '{requested_action}' is strictly forbidden by policy. Approval creation aborted.")
            req = ApprovalRequest(
                approval_id=f"apr_{uuid.uuid4().hex[:8]}",
                request_type=request_type,
                title=title,
                summary=summary,
                reason=f"Policy Block: {policy_msg}",
                requested_action=requested_action,
                action_params=action_params,
                risk_level="CRITICAL",
                status=ApprovalStatus.FAILED_TO_VALIDATE
            )
            self.persistence.save_approval_request(req)
            await self._publish_event("approval.execution_blocked", {
                "approval_id": req.approval_id,
                "reason": f"Hard policy block: {policy_msg}"
            })
            return req

        # 3. Compute deterministic action fingerprint
        fp = self.fp_generator.compute_action_fingerprint(
            action=requested_action,
            params=action_params,
            target_resource=target_resource,
            target_device=target_device,
            task_id=task_id,
            task_node_id=task_node_id,
            plan_version=plan_version
        )

        now = time.time()
        req = ApprovalRequest(
            approval_id=f"apr_{uuid.uuid4().hex[:8]}",
            version=1,
            created_at=now,
            updated_at=now,
            request_type=request_type,
            title=title,
            summary=summary,
            reason=reason,
            mission_id=mission_id,
            task_id=task_id,
            task_node_id=task_node_id,
            plan_version=plan_version,
            risk_level=risk_level,
            policy_reference=policy_reference,
            requested_action=requested_action,
            action_params=action_params,
            target_resource=target_resource,
            target_device=target_device,
            target_application=target_application,
            is_reversible=is_reversible,
            expires_at=now + timeout_sec,
            scope=scope,
            fingerprint=fp,
            status=ApprovalStatus.CREATED,
            metadata=metadata or {}
        )

        # Transition to PENDING and persist
        req.transition_to(ApprovalStatus.PENDING)
        self.persistence.save_approval_request(req)
        self._active_requests[req.approval_id] = req

        if dedup_key:
            self._dedup_cache[dedup_key] = req.approval_id

        # Publish approval.created event
        await self._publish_event("approval.created", {
            "approval_id": req.approval_id,
            "request_type": req.request_type.value,
            "risk_level": req.risk_level,
            "title": req.title,
            "task_id": req.task_id,
            "mission_id": req.mission_id
        })

        return req

    async def present_request(self, approval_id: str, channel: str = "HUD") -> ApprovalPresentation:
        """Presents an approval request to the specified channel (HUD, Voice, CLI, Desktop)."""
        req = self._get_request(approval_id)
        if not req:
            raise ValueError(f"Approval request '{approval_id}' not found.")

        if req.is_terminal():
            raise RuntimeError(f"Cannot present terminal approval request {approval_id} ({req.status.value}).")

        req.transition_to(ApprovalStatus.PRESENTING)
        self.persistence.save_approval_request(req)

        presentation = self.presentation.format_for_channel(req, channel)

        req.transition_to(ApprovalStatus.DELIVERED)
        self.persistence.save_approval_request(req)

        await self._publish_event("approval.presented", {
            "approval_id": req.approval_id,
            "channel": channel.upper(),
            "priority": presentation.priority,
            "expires_in_sec": presentation.expires_in_sec
        })

        return presentation

    async def wait_for_decision(self, approval_id: str, timeout_sec: Optional[float] = None) -> ApprovalRequest:
        """Asynchronously waits for human decision or timeout. Enforces safe-by-default expiration."""
        req = self._get_request(approval_id)
        if not req:
            raise ValueError(f"Approval request '{approval_id}' not found.")

        if req.is_terminal():
            return req

        req.transition_to(ApprovalStatus.WAITING)
        self.persistence.save_approval_request(req)

        now = time.time()
        effective_timeout = timeout_sec if timeout_sec is not None else max(0.1, req.expires_at - now)

        await self._publish_event("approval.waiting", {
            "approval_id": req.approval_id,
            "expires_in_sec": round(effective_timeout, 1)
        })

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._waiting_futures[approval_id] = future

        try:
            await asyncio.wait_for(future, timeout=effective_timeout)
        except asyncio.TimeoutError:
            # Safe default: Silence/timeout -> EXPIRED (NOT approved)
            logger.warning(f"Approval '{approval_id}' timed out after {effective_timeout}s without human decision.")
            await self._handle_timeout(approval_id)
        finally:
            if approval_id in self._waiting_futures:
                del self._waiting_futures[approval_id]

        return self._get_request(approval_id)

    async def submit_decision(
        self,
        approval_id: str,
        decision_type: ApprovalDecisionType,
        decided_by: str = "user.primary",
        decision_source: str = "HUD",
        reason: str = "",
        device_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Tuple[bool, Optional[ApprovalRelease], str]:
        """Processes human approval decision. Validates integrity and issues release token if approved."""
        req = self._get_request(approval_id)
        if not req:
            return False, None, f"Approval request '{approval_id}' not found."

        if req.is_terminal():
            return False, None, f"Approval request is already in terminal state '{req.status.value}'."

        if req.is_expired():
            await self._handle_timeout(approval_id)
            return False, None, "Approval request has expired."

        # Record decision
        dec = ApprovalDecision(
            decision_id=f"dec_{uuid.uuid4().hex[:8]}",
            approval_id=approval_id,
            decision=decision_type,
            decided_at=time.time(),
            decided_by=decided_by,
            decision_source=decision_source,
            device_id=device_id,
            session_id=session_id,
            reason=reason,
            approval_version=req.version
        )
        self.persistence.save_approval_decision(dec)

        if decision_type == ApprovalDecisionType.APPROVE:
            # Policy double-check: Approval cannot override policy
            allowed, policy_msg = policy_engine.verify_action(req.requested_action, req.action_params)
            if not allowed and "Blocked:" in policy_msg:
                req.transition_to(ApprovalStatus.INVALIDATED)
                self.persistence.save_approval_request(req)
                self._resolve_waiter(approval_id, req)
                await self._publish_event("approval.invalidated", {
                    "approval_id": approval_id,
                    "reason": f"Approval invalid: Hard policy block: {policy_msg}"
                })
                return False, None, f"Policy violation: Action cannot be approved ({policy_msg})."

            req.transition_to(ApprovalStatus.APPROVED)
            self.persistence.save_approval_request(req)

            # Generate execution release token
            release = ApprovalRelease(
                release_token=f"rel_{uuid.uuid4().hex[:12]}",
                approval_id=req.approval_id,
                task_id=req.task_id,
                task_node_id=req.task_node_id,
                mission_id=req.mission_id,
                authorized_action=req.requested_action,
                authorization_scope=req.scope,
                fingerprint=req.fingerprint,
                authorized_at=time.time(),
                expires_at=req.expires_at,
                policy_reference=req.policy_reference
            )
            self.persistence.save_approval_release(release)

            req.transition_to(ApprovalStatus.EXECUTION_RELEASED)
            self.persistence.save_approval_request(req)

            await self._publish_event("approval.approved", {
                "approval_id": approval_id,
                "decision_id": dec.decision_id,
                "decided_by": decided_by
            })
            await self._publish_event("approval.released", {
                "approval_id": approval_id,
                "release_token": release.release_token,
                "fingerprint": release.fingerprint
            })

            self._resolve_waiter(approval_id, req)
            return True, release, "Approval granted and execution authorization released."

        elif decision_type == ApprovalDecisionType.REJECT:
            req.transition_to(ApprovalStatus.REJECTED)
            self.persistence.save_approval_request(req)

            await self._publish_event("approval.rejected", {
                "approval_id": approval_id,
                "decision_id": dec.decision_id,
                "reason": reason or "Explicit user rejection."
            })
            self._resolve_waiter(approval_id, req)
            return True, None, "Approval explicitly rejected by user."

        elif decision_type == ApprovalDecisionType.DEFER:
            req.transition_to(ApprovalStatus.DEFERRED)
            self.persistence.save_approval_request(req)

            await self._publish_event("approval.deferred", {
                "approval_id": approval_id,
                "decision_id": dec.decision_id
            })
            self._resolve_waiter(approval_id, req)
            return True, None, "Approval deferred."

        elif decision_type == ApprovalDecisionType.CANCEL:
            req.transition_to(ApprovalStatus.CANCELLED)
            self.persistence.save_approval_request(req)

            await self._publish_event("approval.cancelled", {
                "approval_id": approval_id,
                "reason": reason or "Cancelled by user."
            })
            self._resolve_waiter(approval_id, req)
            return True, None, "Approval cancelled."

        return False, None, "Unrecognized decision type."

    async def verify_and_consume_release(
        self,
        release_token: str,
        action: str,
        params: Dict[str, Any],
        target_resource: Optional[str] = None,
        target_device: Optional[str] = None,
        task_id: Optional[str] = None,
        task_node_id: Optional[str] = None,
        plan_version: int = 1
    ) -> Tuple[bool, str]:
        """Validates execution token against live action parameters, expiration, and plan version."""
        rel = self.persistence.get_approval_release(release_token)
        if not rel:
            return False, "INVALID_TOKEN: Release token does not exist."

        # Check expiration
        now = time.time()
        if now >= rel.expires_at:
            return False, "TOKEN_EXPIRED: Approval release token has expired."

        # Verify cryptographic fingerprint match
        is_match = self.fp_generator.verify_action_fingerprint(
            expected_fingerprint=rel.fingerprint,
            action=action,
            params=params,
            target_resource=target_resource,
            target_device=target_device,
            task_id=task_id,
            task_node_id=task_node_id,
            plan_version=plan_version
        )
        if not is_match:
            logger.error(f"FINGERPRINT_MISMATCH: Execution context deviated from approved fingerprint. Action={action}")
            return False, "FINGERPRINT_MISMATCH: Live action parameters or plan context differ from what was approved."

        # If scope is ONCE, consume atomically
        if rel.authorization_scope == ApprovalScope.ONCE:
            consumed = self.persistence.mark_release_consumed(release_token)
            if not consumed:
                return False, "TOKEN_ALREADY_USED: Single-use approval token was already consumed."

        return True, "VALID_RELEASE"

    async def emergency_invalidate(self, reason: str, task_id: Optional[str] = None, mission_id: Optional[str] = None) -> int:
        """Emergency invalidation: Cancels and invalidates pending approvals."""
        pending = self.persistence.list_pending_approvals()
        count = 0
        for req in pending:
            if task_id and req.task_id != task_id:
                continue
            if mission_id and req.mission_id != mission_id:
                continue

            req.transition_to(ApprovalStatus.INVALIDATED)
            self.persistence.save_approval_request(req)
            self._resolve_waiter(req.approval_id, req)
            await self._publish_event("approval.invalidated", {
                "approval_id": req.approval_id,
                "reason": reason
            })
            count += 1

        logger.warning(f"EMERGENCY_INVALIDATE: Invalidate {count} approvals. Reason: {reason}")
        return count

    def list_pending(self) -> List[ApprovalRequest]:
        """Lists active pending approval requests."""
        return self.persistence.list_pending_approvals()

    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Retrieves approval request by ID."""
        return self._get_request(approval_id)

    def _get_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        if approval_id in self._active_requests:
            return self._active_requests[approval_id]
        req = self.persistence.get_approval_request(approval_id)
        if req:
            self._active_requests[approval_id] = req
        return req

    async def _handle_timeout(self, approval_id: str):
        req = self._get_request(approval_id)
        if req and not req.is_terminal():
            req.transition_to(ApprovalStatus.EXPIRED)
            self.persistence.save_approval_request(req)
            await self._publish_event("approval.expired", {
                "approval_id": approval_id
            })
            self._resolve_waiter(approval_id, req)

    def _resolve_waiter(self, approval_id: str, req: ApprovalRequest):
        if approval_id in self._waiting_futures:
            future = self._waiting_futures[approval_id]
            if not future.done():
                future.set_result(req)

    async def _publish_event(self, event_type: str, payload: Dict[str, Any]):
        try:
            from events import event_fabric, Event, EventEnvelope, EventPriority, EventSeverity, EventDurability
            event = Event(
                envelope=EventEnvelope(
                    event_type=event_type,
                    source="module.20.approval_gateway",
                    priority=EventPriority.CRITICAL if "blocked" in event_type or "rejected" in event_type else EventPriority.HIGH,
                    severity=EventSeverity.WARNING if "blocked" in event_type or "invalidated" in event_type else EventSeverity.INFO,
                    durability=EventDurability.DURABLE
                ),
                payload=payload
            )
            await event_fabric.publish(event)
        except Exception as e:
            logger.debug(f"Event fabric publish skipped for {event_type}: {e}")

approval_gateway = ApprovalGateway()
