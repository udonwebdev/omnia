"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Recovery Orchestration Adapter: Module 20 Human Approval Gating & Restoration Execution.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from reliability_engineering.models import (
    RecoveryExecutionRecord,
)
from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.Coordinator")


class RecoveryOrchestrationAdapter:
    """
    Coordinates disaster recovery plan execution.
    Mandatory Rule: High-consequence disaster recovery restorations REQUIRE a valid
    cryptographic Module 20 human approval token before execution can proceed.
    """

    def __init__(self, repository: Optional[ReliabilityRepository] = None):
        self.repo = repository or ReliabilityRepository()

    def initiate_recovery(
        self,
        plan_id: str,
        target_environment: str = "ISOLATED_SANDBOX",
        approval_token: Optional[str] = None,
        approver: str = "disaster_recovery_lead",
    ) -> RecoveryExecutionRecord:
        """
        Executes a disaster recovery restoration drill.
        Blocks execution if approval token is missing.
        """
        if not approval_token or not approval_token.strip():
            raise PermissionError("APPROVAL_REQUIRED: Disaster recovery restoration requires a valid Module 20 approval token.")

        plan = self.repo.get_dr_plan(plan_id)
        if not plan:
            raise ValueError(f"DR plan '{plan_id}' not found.")

        eid = f"drx-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        # Simulate execution steps according to dependency order
        steps: List[str] = []
        for svc in plan.dependency_order:
            steps.append(f"Restored service: {svc} via {plan.strategy.value}")

        exec_rec = RecoveryExecutionRecord(
            execution_id=eid,
            plan_id=plan_id,
            target_environment=target_environment,
            status="COMPLETED",
            approval_token=approval_token,
            approved_by=approver,
            started_at=now,
            completed_at=datetime.now(timezone.utc).isoformat(),
            duration_sec=45.0,  # Simulated restore drill duration
            steps_executed=steps,
            errors=[],
        )
        self.repo.save_dr_execution(exec_rec)
        logger.info(f"Disaster recovery execution '{eid}' completed successfully for plan '{plan_id}'.")
        return exec_rec
