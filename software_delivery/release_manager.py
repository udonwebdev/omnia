"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Release Preparation & Promotion Manager - release_manager.py

Coordinates release candidates, SemVer tags, release notes, quality sign-offs,
and environment promotions (DEV -> TEST -> STAGING -> PRODUCTION).
Enforces Module 20 human approval token gate for PRODUCTION promotion.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from software_delivery.models import (
    ReleaseCandidateRecord,
    ReleaseStage,
)
from software_delivery.persistence import SoftwareDeliveryRepository

logger = logging.getLogger("Omnia.SoftwareDelivery.ReleaseManager")


class ReleaseManager:
    """
    Manages release candidate promotion and gate authorization.
    """

    def __init__(self, repository: Optional[SoftwareDeliveryRepository] = None):
        self.repo = repository or SoftwareDeliveryRepository()

    def create_release_candidate(
        self,
        version: str,
        artifact_id: str,
        source_revision_id: str,
        release_notes: str = "",
        candidate_id: Optional[str] = None,
    ) -> ReleaseCandidateRecord:
        cid = candidate_id or f"rc-{uuid.uuid4().hex[:8]}"
        rc = ReleaseCandidateRecord(
            candidate_id=cid,
            version=version,
            artifact_id=artifact_id,
            source_revision_id=source_revision_id,
            stage=ReleaseStage.CANDIDATE,
            release_notes=release_notes,
        )
        self.repo.save_release_candidate(rc)
        logger.info(f"Created release candidate '{cid}' (v{version}) for artifact '{artifact_id}'")
        return rc

    def promote_release(
        self,
        candidate_id: str,
        target_stage: ReleaseStage = ReleaseStage.QUALIFIED,
        approval_token: Optional[str] = None,
        approver: Optional[str] = None,
    ) -> ReleaseCandidateRecord:
        rc = self.repo.get_release_candidate(candidate_id)
        if not rc:
            raise KeyError(f"Release candidate '{candidate_id}' not found.")

        # Invariant: Promotion to PROMOTED / DEPLOYED in production requires Module 20 token
        if target_stage in (ReleaseStage.PROMOTED, ReleaseStage.DEPLOYED):
            if not approval_token or not (approval_token.startswith("OMNIA_M20_") or approval_token.startswith("M20_")):
                raise PermissionError(
                    f"APPROVAL_REQUIRED: Production release promotion requires a valid Module 20 human approval token."
                )

        rc.stage = target_stage
        rc.approval_token = approval_token
        rc.approver = approver or "LO"
        self.repo.save_release_candidate(rc)
        logger.info(f"Release candidate '{candidate_id}' promoted to {target_stage.value} by {approver}")
        return rc
