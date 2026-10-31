"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Goal Audit and Provenance Service: Immutable History & Change Tracking.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from goals.models import GoalChangeAuditRecord
from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Audit")


class GoalAuditService:
    """Manages immutable audit logging and provenance for goal mutations."""

    def __init__(self, repository: Optional[GoalRepository] = None):
        self.repo = repository or GoalRepository()

    def get_goal_provenance(self, goal_id: str) -> List[GoalChangeAuditRecord]:
        """Returns the complete, chronological audit trail for a goal."""
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")
        return self.repo.get_audit_trail(goal_id)
