"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Corrective Action Advisor: Intelligent Remediation & Module 37 Strategic Option Integration.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from goals.models import (
    CorrectiveActionProposal,
    CorrectiveActionType,
    GoalHealthState,
)
from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Corrective")


class CorrectiveActionAdvisor:
    """
    Formulates explainable corrective proposals when goals are AT_RISK or OFF_TRACK.
    Integrates with Module 37 for structured trade-off evaluation and Module 20 for human approval.
    """

    def __init__(self, repository: Optional[GoalRepository] = None):
        self.repo = repository or GoalRepository()

    def generate_corrective_proposals(self, goal_id: str) -> List[CorrectiveActionProposal]:
        """Generates actionable proposals to bring an off-track or at-risk goal back into tolerance."""
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        health = self.repo.get_latest_health_record(goal_id)
        prog = self.repo.get_latest_progress_assessment(goal_id)

        proposals: List[CorrectiveActionProposal] = []
        now = datetime.now(timezone.utc).isoformat()

        # Proposal 1: If severe activity-to-outcome divergence (busywork), gather missing evidence
        if prog and prog.activity_to_outcome_variance > 0.30:
            prop = CorrectiveActionProposal(
                proposal_id=f"act-{uuid.uuid4().hex[:8]}",
                goal_id=goal_id,
                action_type=CorrectiveActionType.GATHER_MISSING_EVIDENCE,
                title="Verify Unproven Task Outcomes",
                rationale="Reported task completion significantly exceeds verified metrics. Independent evidence auditing required.",
                expected_benefit="Validates real system state and eliminates false progress illusion.",
                potential_cost="Low engineering effort to run automated test & verification telemetry.",
                risk_level="LOW",
                dependencies=[],
                supporting_evidence=["Activity-to-outcome variance exceeds 30%."],
                requires_human_approval=False,
                status="PROPOSED",
                created_at=now,
            )
            self.repo.save_corrective_action(prop)
            proposals.append(prop)

        # Proposal 2: Schedule slippage -> Revise deadline or reduce scope
        if prog and prog.schedule_variance_days > 14:
            prop2 = CorrectiveActionProposal(
                proposal_id=f"act-{uuid.uuid4().hex[:8]}",
                goal_id=goal_id,
                action_type=CorrectiveActionType.REVISE_DEADLINE,
                title="Extend Target Completion Date",
                rationale=f"Current timeline has slipped by {prog.schedule_variance_days:.1f} days due to downstream blockers.",
                expected_benefit="Realistically aligns delivery expectation with observed delivery velocity.",
                potential_cost="Delayed strategic realization.",
                risk_level="MEDIUM",
                dependencies=["Operator schedule approval"],
                supporting_evidence=[f"Observed schedule variance: {prog.schedule_variance_days} days."],
                requires_human_approval=True,
                status="PROPOSED",
                created_at=now,
            )
            self.repo.save_corrective_action(prop2)
            proposals.append(prop2)

        # Proposal 3: General off-track -> Reprioritize initiative
        if health and health.health_state in (GoalHealthState.OFF_TRACK, GoalHealthState.AT_RISK):
            prop3 = CorrectiveActionProposal(
                proposal_id=f"act-{uuid.uuid4().hex[:8]}",
                goal_id=goal_id,
                action_type=CorrectiveActionType.REPRIORITIZE_INITIATIVE,
                title="Reallocate Focused Resources to Critical Path",
                rationale="Critical milestones missed; non-essential peripheral tasks must be paused to focus on bottleneck.",
                expected_benefit="Accelerates achievement of core bottleneck milestones.",
                potential_cost="Peripheral features temporarily delayed.",
                risk_level="LOW",
                dependencies=[],
                supporting_evidence=health.risk_factors,
                requires_human_approval=True,
                status="PROPOSED",
                created_at=now,
            )
            self.repo.save_corrective_action(prop3)
            proposals.append(prop3)

        return proposals

    def approve_corrective_action(
        self,
        proposal_id: str,
        approver_id: str,
        approval_token: str,
    ) -> CorrectiveActionProposal:
        """Approves a corrective proposal with a mandatory Module 20 human approval token."""
        if not approval_token or not approval_token.strip():
            raise PermissionError("APPROVAL_REQUIRED: Corrective actions require a valid Module 20 approval token.")

        with self.repo._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM goal_corrective_actions WHERE proposal_id = ?", (proposal_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Corrective proposal '{proposal_id}' not found.")

        now = datetime.now(timezone.utc).isoformat()
        prop = CorrectiveActionProposal(
            proposal_id=row["proposal_id"],
            goal_id=row["goal_id"],
            action_type=CorrectiveActionType(row["action_type"]),
            title=row["title"],
            rationale=row["rationale"],
            expected_benefit=row["expected_benefit"],
            potential_cost=row["potential_cost"],
            risk_level=row["risk_level"],
            dependencies=[],
            supporting_evidence=[],
            requires_human_approval=bool(row["requires_human_approval"]),
            status="APPROVED",
            approval_token=approval_token,
            approved_by=approver_id,
            created_at=row["created_at"],
        )
        self.repo.save_corrective_action(prop)
        logger.info(f"Approved corrective action '{proposal_id}' by '{approver_id}'")
        return prop
