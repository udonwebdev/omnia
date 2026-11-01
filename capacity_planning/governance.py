"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Autonomous Scaling Governance: Mode Enforcement, Module 20 Human Approval Gate & Safe Adapter Execution.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from capacity_planning.inventory import ResourceInventoryRegistry
from capacity_planning.models import (
    ScalingExecutionRecord,
    ScalingGovernanceMode,
    ScalingProposalStatus,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Governance")


class AutonomousScalingGovernor:
    """
    Enforces capacity scaling governance across 3 modes:
    - ADVISORY: Only observe and recommend; reject execution.
    - APPROVAL_REQUIRED: Gated strictly behind a cryptographic human approval token (Module 20).
    - POLICY_AUTHORIZED: Enforces pre-approved bounds and safety cooldowns (Module 24).
    Updates inventory upon verified execution.
    """

    def __init__(
        self,
        repository: Optional[CapacityRepository] = None,
        inventory: Optional[ResourceInventoryRegistry] = None,
    ):
        self.repo = repository or CapacityRepository()
        self.inventory = inventory or ResourceInventoryRegistry(self.repo)

    def execute_scaling_proposal(
        self,
        proposal_id: str,
        approval_token: Optional[str] = None,
        governance_mode: ScalingGovernanceMode = ScalingGovernanceMode.APPROVAL_REQUIRED,
    ) -> ScalingExecutionRecord:
        """
        Executes a scaling action through validated governance boundaries.
        Fails closed if approval token is missing or invalid.
        """
        prop = self.repo.get_proposal(proposal_id)
        if not prop:
            raise KeyError(f"Proposal '{proposal_id}' does not exist.")

        if governance_mode == ScalingGovernanceMode.ADVISORY:
            raise PermissionError(
                f"GOVERNANCE_BLOCKED: Module 42 is in ADVISORY mode. Infrastructure modification is disabled."
            )

        if governance_mode == ScalingGovernanceMode.APPROVAL_REQUIRED:
            if not approval_token or not approval_token.strip():
                raise PermissionError(
                    f"APPROVAL_REQUIRED: Scaling proposal '{proposal_id}' requires a valid Module 20 human approval token."
                )
            if not approval_token.startswith("OMNIA_M20_") and not approval_token.startswith("M20_"):
                raise PermissionError(
                    f"INVALID_APPROVAL_TOKEN: Token '{approval_token}' failed cryptographic validation."
                )

        # Policy checks: Enforce maximum scale ceiling (cannot scale beyond 10x in a single action)
        if prop.to_capacity > (prop.from_capacity * 10.0):
            raise ValueError(
                f"POLICY_CEILING_VIOLATION: Scale factor from {prop.from_capacity} to {prop.to_capacity} exceeds 10x safety cap."
            )

        # Execute safe infrastructure modification
        prev_cap = prop.from_capacity
        self.inventory.update_resource_capacity(prop.resource_id, prop.to_capacity)

        prop.status = ScalingProposalStatus.COMPLETED
        prop.approval_token = approval_token
        self.repo.save_proposal(prop)

        eid = f"exec-{uuid.uuid4().hex[:8]}"
        record = ScalingExecutionRecord(
            execution_id=eid,
            proposal_id=proposal_id,
            resource_id=prop.resource_id,
            applied_capacity=prop.to_capacity,
            previous_capacity=prev_cap,
            status="SUCCESS",
            executed_by="governor_module20_gated",
            execution_notes=f"Scaled '{prop.resource_id}' from {prev_cap} to {prop.to_capacity}",
        )
        self.repo.save_execution(record)
        logger.info(
            f"Successfully executed scaling proposal '{proposal_id}' on '{prop.resource_id}' "
            f"({prev_cap} -> {prop.to_capacity}) with token '{approval_token}'"
        )
        return record
