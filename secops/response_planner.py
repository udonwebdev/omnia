"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Defensive Response Planner - response_planner.py
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from secops.models import DefensiveResponsePlan, OperationalRisk, ResponseActionType, SecurityIncident
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.ResponsePlanner")


class DefensiveResponsePlanner:
    """
    Synthesizes proportionate, evidence-backed defensive remediation proposals.
    Evaluates operational blast radius and enforces Module 20 human approval requirements.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def generate_response_plan(
        self,
        incident_id: str,
        action_type: ResponseActionType,
        target_identifier: str,
        justification: str,
        operational_risk: OperationalRisk = OperationalRisk.LOW,
    ) -> DefensiveResponsePlan:
        inc = self.repo.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident {incident_id} not found.")

        pid = f"plan-{uuid.uuid4().hex[:8]}"

        # Actions on critical identities or endpoints require mandatory Module 20 approval
        requires_approval = True
        if operational_risk == OperationalRisk.LOW and action_type == ResponseActionType.REVOKE_SESSION:
            requires_approval = False

        plan = DefensiveResponsePlan(
            plan_id=pid,
            incident_id=incident_id,
            recommended_action=action_type,
            target_identifier=target_identifier,
            justification=justification,
            operational_risk=operational_risk,
            requires_approval=requires_approval,
            approval_token_ref=None,
            status="PROPOSED",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        self.repo.save_response_plan(plan)
        logger.info(
            f"Formulated response plan {pid} for Incident {incident_id}: "
            f"{action_type.value} on {target_identifier} (Risk: {operational_risk.value}, RequiresApproval: {requires_approval})"
        )
        return plan
