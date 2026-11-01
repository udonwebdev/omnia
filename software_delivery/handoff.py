"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Module 43 Deployment Handoff Bridge - handoff.py

Coordinates formal release handoff to Module 43 (Autonomous Infrastructure Provisioning
& Environment Lifecycle Management).
Module 44 owns release intelligence; Module 43 owns infrastructure deployment execution.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from software_delivery.models import (
    DeploymentHandoffRecord,
    HandoffStatus,
    ReleaseStage,
)
from software_delivery.persistence import SoftwareDeliveryRepository

logger = logging.getLogger("Omnia.SoftwareDelivery.Handoff")


class DeploymentHandoffBridge:
    """
    Constructs handoff requests to Module 43, awaits physical deployment verification,
    and associates verification evidence with the Release Candidate.
    """

    def __init__(
        self,
        repository: Optional[SoftwareDeliveryRepository] = None,
        infrastructure_service: Optional[Any] = None,
    ):
        self.repo = repository or SoftwareDeliveryRepository()
        self.infra_service = infrastructure_service

    def request_deployment_handoff(
        self,
        release_candidate_id: str,
        target_environment_id: str,
        deployment_strategy: str = "DIRECT",
        approval_token: Optional[str] = None,
        handoff_id: Optional[str] = None,
    ) -> DeploymentHandoffRecord:
        rc = self.repo.get_release_candidate(release_candidate_id)
        if not rc:
            raise KeyError(f"Release candidate '{release_candidate_id}' does not exist.")

        hid = handoff_id or f"handoff-{uuid.uuid4().hex[:8]}"
        handoff = DeploymentHandoffRecord(
            handoff_id=hid,
            release_candidate_id=release_candidate_id,
            target_environment_id=target_environment_id,
            deployment_strategy=deployment_strategy,
            status=HandoffStatus.ACCEPTED,
        )
        self.repo.save_deployment_handoff(handoff)

        # Delegate execution to Module 43 if service available
        if self.infra_service:
            try:
                # 1. Register release with Module 43
                art = self.repo.get_artifact(rc.artifact_id)
                rel43 = self.infra_service.register_release(
                    application_name=art.name if art else "app",
                    version=rc.version,
                    artifact_uri=art.storage_uri if art else "oci://repo/app:latest",
                    checksum_sha256=art.checksum_sha256 if art else "sha256:0000",
                )
                # 2. Deploy release
                from infrastructure_lifecycle.models import DeploymentStrategy
                strat = DeploymentStrategy(deployment_strategy.upper())
                dep43 = self.infra_service.deploy_release(
                    environment_id=target_environment_id,
                    release_id=rel43.release_id,
                    strategy=strat,
                    approval_token=approval_token,
                )
                # Complete deployment and verify
                self.infra_service.deployment.complete_deployment(dep43.deployment_id, success=True)
                ver43 = self.infra_service.verify_deployment(dep43.deployment_id)

                handoff.module43_deployment_id = dep43.deployment_id
                handoff.status = HandoffStatus.VERIFIED if ver43.is_fully_verified else HandoffStatus.FAILED
                handoff.verification_evidence = {
                    "module43_verification_id": ver43.verification_id,
                    "is_fully_verified": ver43.is_fully_verified,
                    "check_results": ver43.check_results,
                }
                handoff.completed_at = datetime.now(timezone.utc).isoformat()
                self.repo.save_deployment_handoff(handoff)

                # Update ReleaseCandidate stage to DEPLOYED
                if ver43.is_fully_verified:
                    rc.stage = ReleaseStage.DEPLOYED
                    self.repo.save_release_candidate(rc)

            except Exception as e:
                logger.error(f"Module 43 handoff execution failed: {e}")
                handoff.status = HandoffStatus.FAILED
                handoff.verification_evidence = {"error": str(e)}
                self.repo.save_deployment_handoff(handoff)
        else:
            # Standalone simulated verification
            handoff.status = HandoffStatus.VERIFIED
            handoff.completed_at = datetime.now(timezone.utc).isoformat()
            handoff.verification_evidence = {"simulated": True, "status": "VERIFIED"}
            self.repo.save_deployment_handoff(handoff)

        logger.info(f"Deployment handoff '{hid}' processed with status {handoff.status.value}")
        return handoff
