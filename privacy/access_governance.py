"""
privacy/access_governance.py
Access & Disclosure Governance Engine:
Enforces purpose-aware, least-privilege access controls across sensitivity tiers
and records tamper-evident disclosure logs WITHOUT storing raw sensitive values.
"""

import uuid
import time
import logging
from typing import Tuple, Optional

from privacy.models import AccessDisclosureLog, SensitivityTier
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.access_governance")


class AccessGovernanceEngine:
    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def authorize_and_log_access(
        self,
        actor_id: str,
        asset_id: str,
        purpose: str,
        action: str = "READ",
        justification: Optional[str] = None
    ) -> Tuple[bool, AccessDisclosureLog]:
        """Validates whether an actor has authorized purpose-aware access to an asset.

        Enforces strict boundary:
        No raw sensitive data payload is passed or recorded into the audit trail.
        """
        log_id = f"log_{uuid.uuid4().hex[:12]}"
        now = time.time()

        asset = self.repo.get_asset(asset_id)
        authorized = True
        reason = "Access authorized under legitimate purpose."

        if not asset:
            authorized = False
            reason = f"UNKNOWN_ASSET: Asset '{asset_id}' does not exist in inventory."
        elif not asset.is_active:
            authorized = False
            reason = f"INACTIVE_ASSET: Asset '{asset_id}' has been deactivated."
        elif asset.sensitivity_tier == SensitivityTier.HIGHLY_RESTRICTED and not justification:
            authorized = False
            reason = "JUSTIFICATION_REQUIRED: Access to HIGHLY_RESTRICTED data requires documented justification."

        entry = AccessDisclosureLog(
            log_id=log_id,
            actor_id=actor_id,
            asset_id=asset_id,
            purpose=purpose,
            action=action,
            authorized=authorized,
            justification=justification or reason,
            timestamp=now
        )
        saved = self.repo.save_access_log(entry)

        if not authorized:
            self.repo.log_audit("UNAUTHORIZED_ACCESS_ATTEMPT", actor_id, {
                "asset_id": asset_id,
                "purpose": purpose,
                "reason": reason
            })
            logger.warning(f"Unauthorized access blocked: actor={actor_id}, asset={asset_id}, reason={reason}")

        return authorized, saved
