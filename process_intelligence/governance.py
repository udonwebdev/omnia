"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Workflow Change Governance: Module 20 Human Approval & Controlled Versioning.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from process_intelligence.models import (
    OptimizationStatus,
    WorkflowChangeGovernanceRecord,
)
from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Governance")


class WorkflowChangeGovernance:
    """
    Guards workflow modifications behind Module 20 human approval tokens.
    Prevents unauthorized automated changes from altering production behavior.
    """

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def submit_change_for_approval(
        self,
        workflow_id: str,
        candidate_id: str,
        from_version: int,
        to_version: int,
    ) -> WorkflowChangeGovernanceRecord:
        """Registers a formal change governance proposal awaiting human sign-off."""
        gid = f"gov-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        gov = WorkflowChangeGovernanceRecord(
            governance_id=gid,
            workflow_id=workflow_id,
            candidate_id=candidate_id,
            from_version=from_version,
            to_version=to_version,
            approved_by=None,
            approval_token=None,
            change_status="PENDING_APPROVAL",
            created_at=now,
            updated_at=now,
        )
        self.repo.save_governance_record(gov)
        logger.info(f"Submitted change governance request '{gid}' for workflow '{workflow_id}' (v{from_version}->v{to_version})")
        return gov

    def approve_workflow_change(
        self,
        governance_id: str,
        approver_id: str,
        approval_token: str,
    ) -> WorkflowChangeGovernanceRecord:
        """Approves and authorizes a workflow revision with a mandatory Module 20 human approval token."""
        if not approval_token or not approval_token.strip():
            raise PermissionError("APPROVAL_REQUIRED: Workflow changes require a valid Module 20 human approval token.")

        gov = self.repo.get_governance_record(governance_id)
        if not gov:
            raise ValueError(f"Change governance record '{governance_id}' not found.")

        now = datetime.now(timezone.utc).isoformat()
        gov.approved_by = approver_id
        gov.approval_token = approval_token
        gov.change_status = "APPROVED"
        gov.updated_at = now
        self.repo.save_governance_record(gov)

        # Update candidate status
        with self.repo._get_connection() as conn:
            conn.execute(
                "UPDATE proc_optimization_candidates SET status = ? WHERE candidate_id = ?",
                (OptimizationStatus.APPROVED.value, gov.candidate_id),
            )
            conn.commit()

        logger.info(f"Approved workflow change '{governance_id}' by '{approver_id}'")
        return gov
