"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Authorization & Scope Registry - authorization_registry.py

Enforces zero-trust scope validation, time-bounded grants, technique restrictions,
out-of-scope target rejections, and emergency kill-switch controls.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app_security.models import (
    AssessmentScope, EnvironmentTier, SecurityAsset, SecurityAuditRecord,
    SecurityAuthorization
)
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.AuthorizationRegistry")


class ScopeViolationError(Exception):
    """Raised when an action or target violates authorized security testing boundaries."""
    pass


class AuthorizationExpiredError(Exception):
    """Raised when an authorization grant has expired or been revoked."""
    pass


class AuthorizationRegistry:
    """
    Manages explicit scope registration and strictly enforces authorization boundaries.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()
        self._emergency_kill_active: bool = False

    def activate_emergency_kill_switch(self, actor: str, reason: str) -> None:
        """Immediately halts all security testing across the entire system."""
        self._emergency_kill_active = True
        logger.critical(f"EMERGENCY KILL SWITCH ACTIVATED by {actor}. Reason: {reason}")
        self.repo.save_audit_record(
            SecurityAuditRecord(
                audit_id=f"audit-{uuid.uuid4().hex[:8]}",
                authorization_id=None,
                asset_id=None,
                action_type="KILL_SWITCH",
                actor=actor,
                details={"reason": reason, "active": True}
            )
        )

    def deactivate_emergency_kill_switch(self, actor: str) -> None:
        """Disengages the emergency stop after safety verification."""
        self._emergency_kill_active = False
        logger.warning(f"Emergency kill switch deactivated by {actor}")
        self.repo.save_audit_record(
            SecurityAuditRecord(
                audit_id=f"audit-{uuid.uuid4().hex[:8]}",
                authorization_id=None,
                asset_id=None,
                action_type="KILL_SWITCH_RESET",
                actor=actor,
                details={"active": False}
            )
        )

    def grant_authorization(
        self,
        name: str,
        operator: str,
        owner_approval_ref: str,
        assessment_purpose: str,
        environment_tier: EnvironmentTier,
        valid_until: str,
        permitted_techniques: Optional[List[str]] = None,
        allow_destructive: bool = False,
        rate_limit_rps: int = 10,
        authorization_id: Optional[str] = None
    ) -> SecurityAuthorization:
        aid = authorization_id or f"auth-{uuid.uuid4().hex[:8]}"
        auth = SecurityAuthorization(
            authorization_id=aid,
            name=name,
            operator=operator,
            owner_approval_ref=owner_approval_ref,
            assessment_purpose=assessment_purpose,
            environment_tier=environment_tier,
            permitted_techniques=permitted_techniques or ["STATIC_ANALYSIS", "DEPENDENCY_AUDIT", "SAFE_API_PROBE"],
            allow_destructive=allow_destructive,
            rate_limit_rps=rate_limit_rps,
            valid_until=valid_until
        )
        self.repo.save_authorization(auth)
        self.repo.save_audit_record(
            SecurityAuditRecord(
                audit_id=f"audit-{uuid.uuid4().hex[:8]}",
                authorization_id=aid,
                asset_id=None,
                action_type="AUTH_GRANTED",
                actor=operator,
                details={"owner_approval_ref": owner_approval_ref, "tier": environment_tier.value}
            )
        )
        logger.info(f"Granted security authorization {aid} for {environment_tier.value} (Valid until: {valid_until})")
        return auth

    def register_scope(
        self,
        authorization_id: str,
        asset_id: str,
        permitted_endpoints: Optional[List[str]] = None,
        excluded_endpoints: Optional[List[str]] = None,
        permitted_components: Optional[List[str]] = None,
        excluded_components: Optional[List[str]] = None,
        scope_id: Optional[str] = None
    ) -> AssessmentScope:
        auth = self.repo.get_authorization(authorization_id)
        if not auth or auth.is_revoked:
            raise ScopeViolationError(f"Authorization {authorization_id} does not exist or is revoked.")

        sid = scope_id or f"scope-{uuid.uuid4().hex[:8]}"
        scope = AssessmentScope(
            scope_id=sid,
            authorization_id=authorization_id,
            asset_id=asset_id,
            permitted_endpoints=permitted_endpoints or ["*"],
            excluded_endpoints=excluded_endpoints or [],
            permitted_components=permitted_components or ["*"],
            excluded_components=excluded_components or []
        )
        self.repo.save_scope(scope)
        logger.info(f"Registered assessment scope {sid} on asset {asset_id} under auth {authorization_id}")
        return scope

    def validate_target_access(
        self,
        authorization_id: str,
        asset_id: str,
        target_endpoint_or_file: str,
        requested_technique: str,
        is_destructive: bool = False
    ) -> bool:
        """
        Validates target access against active authorization and scopes.
        Fails closed on any discrepancy or out-of-scope path.
        """
        if self._emergency_kill_active:
            raise ScopeViolationError("EMERGENCY_KILL_SWITCH_ACTIVE: All assessment activities are locked down.")

        auth = self.repo.get_authorization(authorization_id)
        if not auth:
            raise ScopeViolationError(f"Authorization {authorization_id} not found.")

        if auth.is_revoked:
            raise AuthorizationExpiredError(f"Authorization {authorization_id} was revoked: {auth.revoked_reason}")

        # Check expiration
        now_iso = datetime.now(timezone.utc).isoformat()
        if auth.valid_until and auth.valid_until < now_iso:
            raise AuthorizationExpiredError(f"Authorization {authorization_id} expired at {auth.valid_until}")

        # Check technique
        if requested_technique not in auth.permitted_techniques:
            raise ScopeViolationError(f"Technique '{requested_technique}' is not permitted by authorization {authorization_id}.")

        # Check destructive testing
        if is_destructive and not auth.allow_destructive:
            raise ScopeViolationError("DESTRUCTIVE_PROBE_DENIED: Destructive testing is not permitted under this authorization.")

        # Check scope on asset
        scopes = self.repo.get_scopes_for_authorization(authorization_id)
        asset_scopes = [s for s in scopes if s.asset_id == asset_id]
        if not asset_scopes:
            raise ScopeViolationError(f"Target asset '{asset_id}' is not covered by authorization {authorization_id}.")

        for scope in asset_scopes:
            import fnmatch

            # Check exclusions
            if any(fnmatch.fnmatch(target_endpoint_or_file, excl) for excl in scope.excluded_endpoints + scope.excluded_components):
                raise ScopeViolationError(f"Target '{target_endpoint_or_file}' is explicitly excluded in scope {scope.scope_id}.")

            # Check permit
            permitted = any(
                fnmatch.fnmatch(target_endpoint_or_file, perm)
                for perm in scope.permitted_endpoints + scope.permitted_components
            )
            if not permitted:
                raise ScopeViolationError(f"Target '{target_endpoint_or_file}' is not in permitted scope list.")

        # Record successful authorization check
        self.repo.save_audit_record(
            SecurityAuditRecord(
                audit_id=f"audit-{uuid.uuid4().hex[:8]}",
                authorization_id=authorization_id,
                asset_id=asset_id,
                action_type="AUTH_VALIDATED",
                actor=auth.operator,
                details={"target": target_endpoint_or_file, "technique": requested_technique}
            )
        )
        return True
