import time
import logging
from typing import Tuple, Dict, Any, Optional

from secrets.models import (
    SecretRecord,
    SecretAccessRequest,
    SecretStatus,
    TrustLevel
)

logger = logging.getLogger("Omnia.Secrets.AccessControl")

class AccessDeniedError(PermissionError):
    """Raised when secret access request fails authorization checks."""
    pass

class SecretAccessAuthorizer:
    """
    Evaluates contextual authorization requests for secret access:
    Identity + Capability + Permission + Purpose + Scope + Node Trust + Expiration.
    """

    def __init__(self, node_trust_levels: Optional[Dict[str, TrustLevel]] = None):
        self._node_trust_levels = node_trust_levels or {
            "local_node": TrustLevel.TRUSTED,
            "root_controller": TrustLevel.SYSTEM_ROOT
        }

    def set_node_trust(self, node_id: str, trust: TrustLevel):
        self._node_trust_levels[node_id] = trust

    def get_node_trust(self, node_id: str) -> TrustLevel:
        return self._node_trust_levels.get(node_id, TrustLevel.UNTRUSTED)

    def authorize_request(
        self,
        request: SecretAccessRequest,
        secret: SecretRecord
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates all dimensions of access.
        Returns: (is_authorized, denial_reason)
        """
        # 1. Secret Status
        if not secret.status.is_usable:
            return False, f"SECRET_INACTIVE: Secret '{secret.secret_id}' status is '{secret.status.value}'."

        # 2. Expiration Check
        if secret.expires_at and time.time() >= secret.expires_at:
            return False, f"SECRET_EXPIRED: Secret '{secret.secret_id}' expired at {secret.expires_at}."

        policy = secret.access_policy or {}

        # 3. Node Trust Level
        node_trust = self.get_node_trust(request.node_id)
        min_trust_str = policy.get("min_trust_level", "TRUSTED")
        try:
            min_trust = TrustLevel(min_trust_str)
        except ValueError:
            min_trust = TrustLevel.TRUSTED

        if node_trust.level_score < min_trust.level_score:
            return False, (
                f"NODE_UNTRUSTED: Node '{request.node_id}' trust level '{node_trust.value}' "
                f"is below required '{min_trust.value}'."
            )

        # 4. Scope Alignment
        allowed_scopes = policy.get("allowed_scopes", ["CLUSTER", "GLOBAL", "NODE"])
        if request.scope not in allowed_scopes:
            return False, f"SCOPE_MISMATCH: Requested scope '{request.scope}' not in allowed scopes: {allowed_scopes}."

        # 5. Purpose Binding
        allowed_purposes = policy.get("allowed_purposes")
        if allowed_purposes is not None and request.purpose not in allowed_purposes:
            return False, (
                f"PURPOSE_VIOLATION: Purpose '{request.purpose}' is not bound to secret '{secret.secret_id}'. "
                f"Allowed purposes: {allowed_purposes}."
            )

        # 6. Capability Boundary
        allowed_capabilities = policy.get("allowed_capabilities")
        if allowed_capabilities is not None and request.capability not in allowed_capabilities:
            return False, (
                f"CAPABILITY_VIOLATION: Capability '{request.capability}' is not permitted to access '{secret.secret_id}'. "
                f"Allowed capabilities: {allowed_capabilities}."
            )

        # 7. Requester Identity
        allowed_requesters = policy.get("allowed_requesters")
        if allowed_requesters is not None and request.requester_identity not in allowed_requesters:
            return False, f"REQUESTER_DENIED: Identity '{request.requester_identity}' not in allowed requesters."

        # 8. Human Approval Gating (Integration with Module 20)
        if policy.get("requires_human_approval", False):
            # If human approval is strictly required, check if valid release token was supplied
            approval_token = policy.get("approval_token")
            if not approval_token:
                return False, f"APPROVAL_REQUIRED: Access to '{secret.secret_id}' requires explicit Module 20 human approval."

        return True, None
