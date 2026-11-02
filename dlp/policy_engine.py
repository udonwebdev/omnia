"""
dlp/policy_engine.py
Policy-Driven DLP Engine for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import uuid
import time
from typing import List, Dict, Any, Optional, Tuple

from dlp.models import (
    DLPPolicy, DLPPolicyVersion, TransferDecision, MovementEvent,
    SensitiveFinding, ExfiltrationAlert, ProtectedFingerprint,
    DLPDecision, EnforcementMode, SensitivityTier, DLPChannel
)
from dlp.persistence import DLPRepository


class DLPPolicyEngine:
    """
    Evaluates data movement events against prioritized DLP policies.
    Determines transfer decisions: ALLOW, BLOCK, QUARANTINE, APPROVAL_REQUIRED, REDACT.
    """

    def __init__(self, repo: DLPRepository):
        self.repo = repo

    def create_policy(
        self,
        name: str,
        category: str,
        min_sensitivity_tier: str,
        channel: str,
        mode: str,
        description: str = "",
        priority: int = 100,
        conditions: Optional[Dict[str, Any]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        created_by: str = "security_admin",
        policy_id: Optional[str] = None
    ) -> DLPPolicy:
        """Creates and registers a new DLP policy, versioning initial snapshot v1."""
        pid = policy_id or f"pol_{uuid.uuid4().hex[:10]}"
        now = time.time()
        policy = DLPPolicy(
            policy_id=pid,
            name=name,
            description=description,
            category=category,
            min_sensitivity_tier=min_sensitivity_tier,
            channel=channel,
            mode=mode,
            priority=priority,
            is_active=True,
            created_at=now,
            updated_at=now,
            conditions=conditions or {},
            actions=actions or [],
        )
        saved = self.repo.save_policy(policy)

        # Record initial version
        version = DLPPolicyVersion(
            version_id=f"pver_{uuid.uuid4().hex[:10]}",
            policy_id=saved.policy_id,
            version_num=1,
            changes_summary="Initial policy registration",
            created_at=now,
            created_by=created_by,
            snapshot=saved.to_dict(),
        )
        self.repo.save_policy_version(version)
        return saved

    def update_policy(
        self,
        policy_id: str,
        name: Optional[str] = None,
        mode: Optional[str] = None,
        priority: Optional[int] = None,
        is_active: Optional[bool] = None,
        conditions: Optional[Dict[str, Any]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        changes_summary: str = "Policy configuration update",
        updated_by: str = "security_admin"
    ) -> Tuple[DLPPolicy, DLPPolicyVersion]:
        """Updates an existing DLP policy and increments its immutable version history."""
        existing = self.repo.get_policy(policy_id)
        if not existing:
            raise ValueError(f"DLP Policy '{policy_id}' not found.")

        if name is not None:
            existing.name = name
        if mode is not None:
            existing.mode = mode
        if priority is not None:
            existing.priority = priority
        if is_active is not None:
            existing.is_active = is_active
        if conditions is not None:
            existing.conditions = conditions
        if actions is not None:
            existing.actions = actions

        existing.updated_at = time.time()
        saved = self.repo.save_policy(existing)

        # Get current version count
        versions = self.repo.list_policy_versions(policy_id)
        next_ver = len(versions) + 1

        version = DLPPolicyVersion(
            version_id=f"pver_{uuid.uuid4().hex[:10]}",
            policy_id=policy_id,
            version_num=next_ver,
            changes_summary=changes_summary,
            created_at=existing.updated_at,
            created_by=updated_by,
            snapshot=saved.to_dict(),
        )
        self.repo.save_policy_version(version)
        return saved, version

    def evaluate_movement(
        self,
        event: MovementEvent,
        findings: Optional[List[SensitiveFinding]] = None,
        alert: Optional[ExfiltrationAlert] = None,
        matched_fingerprints: Optional[List[Tuple[ProtectedFingerprint, float]]] = None
    ) -> TransferDecision:
        """
        Evaluates a movement event against active policies, producing an authoritative TransferDecision.
        Prioritized: lower priority number evaluates first (e.g., 10 before 100).
        """
        findings_list = findings or []
        fps_list = matched_fingerprints or []

        # Find active policies for this channel or wildcard ANY
        active_policies = self.repo.list_policies(active_only=True)
        relevant_policies = [
            p for p in active_policies
            if p.channel in (event.channel, "ANY")
        ]
        # Sort by priority ascending (1 highest, then 10, then 100)
        relevant_policies.sort(key=lambda p: (p.priority, p.created_at))

        for policy in relevant_policies:
            if self._matches_policy(policy, event, findings_list, alert, fps_list):
                decision_type, reason = self._resolve_decision(policy, event, findings_list, alert, fps_list)
                dec = TransferDecision(
                    decision_id=f"dec_{uuid.uuid4().hex[:12]}",
                    event_id=event.event_id,
                    policy_id=policy.policy_id,
                    decision=decision_type.value,
                    reason=reason,
                    evaluated_at=time.time(),
                )
                return self.repo.save_transfer_decision(dec)

        # Default fallback: ALLOW
        default_dec = TransferDecision(
            decision_id=f"dec_{uuid.uuid4().hex[:12]}",
            event_id=event.event_id,
            policy_id=None,
            decision=DLPDecision.ALLOW.value,
            reason="No restrictive DLP policy matched; transfer permitted under baseline policy.",
            evaluated_at=time.time(),
        )
        return self.repo.save_transfer_decision(default_dec)

    def _matches_policy(
        self,
        policy: DLPPolicy,
        event: MovementEvent,
        findings: List[SensitiveFinding],
        alert: Optional[ExfiltrationAlert],
        matched_fps: List[Tuple[ProtectedFingerprint, float]]
    ) -> bool:
        """Determines if the event and its findings satisfy all conditions of a policy."""
        # 1. Category check
        if policy.category != "ANY":
            has_matching_finding = any(f.data_category == policy.category for f in findings)
            has_matching_fp = any(fp.data_category == policy.category for fp, _ in matched_fps)
            if not has_matching_finding and not has_matching_fp:
                return False

        # 2. Sensitivity Tier threshold check
        policy_rank = SensitivityTier.rank(SensitivityTier(policy.min_sensitivity_tier))
        # If policy specifies tier, verify findings or fingerprints meet the tier
        if findings:
            max_finding_rank = max(
                (SensitivityTier.rank(SensitivityTier(f.sensitivity_tier)) for f in findings),
                default=1
            )
            if max_finding_rank < policy_rank:
                return False
        elif matched_fps:
            # Protected fingerprints are treated as RESTRICTED by default (rank 4)
            if policy_rank > SensitivityTier.rank(SensitivityTier.RESTRICTED):
                return False
        else:
            # No findings and no fingerprints: matches only if min_sensitivity_tier is PUBLIC or INTERNAL
            if policy_rank > SensitivityTier.rank(SensitivityTier.INTERNAL):
                return False

        # 3. Fine-grained conditions evaluation
        conds = policy.conditions
        if not conds:
            return True

        # Volume threshold condition
        if "max_volume_bytes" in conds:
            if event.volume_bytes < conds["max_volume_bytes"]:
                return False

        # Unauthorized flag condition
        if conds.get("unapproved_only", False) and event.is_authorized:
            return False

        # Destination filter
        if "destinations" in conds:
            dest_list = conds["destinations"]
            if not any(d.lower() in event.destination_location.lower() for d in dest_list):
                return False

        # Min risk score condition
        if "min_risk_score" in conds:
            if not alert or alert.risk_score < conds["min_risk_score"]:
                return False

        return True

    def _resolve_decision(
        self,
        policy: DLPPolicy,
        event: MovementEvent,
        findings: List[SensitiveFinding],
        alert: Optional[ExfiltrationAlert],
        matched_fps: List[Tuple[ProtectedFingerprint, float]]
    ) -> Tuple[DLPDecision, str]:
        """Maps policy enforcement mode to TransferDecision and explanatory reason."""
        mode = policy.mode
        findings_summary = f"{len(findings)} sensitive finding(s)" if findings else ""
        fp_summary = f"{len(matched_fps)} protected fingerprint(s)" if matched_fps else ""
        data_desc = ", ".join(filter(None, [findings_summary, fp_summary])) or "movement context"

        if mode == EnforcementMode.BLOCK.value:
            return (
                DLPDecision.BLOCK,
                f"Policy '{policy.name}' [{policy.policy_id}] triggered BLOCK enforcement due to {data_desc} on channel {event.channel}."
            )
        elif mode == EnforcementMode.QUARANTINE.value:
            return (
                DLPDecision.QUARANTINE,
                f"Policy '{policy.name}' [{policy.policy_id}] initiated payload QUARANTINE for security review."
            )
        elif mode == EnforcementMode.REQUIRE_APPROVAL.value:
            return (
                DLPDecision.APPROVAL_REQUIRED,
                f"Policy '{policy.name}' [{policy.policy_id}] requires explicit M20 human-in-the-loop authorization token."
            )
        elif mode == EnforcementMode.REDACT.value:
            return (
                DLPDecision.REDACT,
                f"Policy '{policy.name}' [{policy.policy_id}] enforced content REDACTION before transfer allowed."
            )
        elif mode == EnforcementMode.ALERT.value:
            return (
                DLPDecision.ALLOW,
                f"Policy '{policy.name}' [{policy.policy_id}] alerted on {data_desc}; transfer permitted under ALERT mode."
            )
        else:  # OBSERVE
            return (
                DLPDecision.ALLOW,
                f"Policy '{policy.name}' [{policy.policy_id}] logged telemetry in OBSERVE mode."
            )
