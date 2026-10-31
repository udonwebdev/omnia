"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Goal Decomposition Engine: Initiatives, Milestones & Task Graph Integration.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from goals.models import (
    InitiativeRecord,
    MilestoneRecord,
)
from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Decomposition")


class GoalDecompositionEngine:
    """
    Decomposes strategic objectives into executable initiatives and verifiable milestones.
    Integrates with Module 14 TaskGraph to bridge task execution to outcome metrics.
    """

    def __init__(self, repository: Optional[GoalRepository] = None):
        self.repo = repository or GoalRepository()

    def create_initiative(
        self,
        goal_id: str,
        title: str,
        scope: str,
        expected_outcome: str,
        owner: str,
        required_capabilities: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        estimated_resources: Optional[Dict[str, Any]] = None,
        target_date: Optional[str] = None,
        task_graph_id: Optional[str] = None,
        initiative_id: Optional[str] = None,
    ) -> InitiativeRecord:
        """Creates an executable initiative under a goal."""
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        iid = initiative_id or f"init-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        init = InitiativeRecord(
            initiative_id=iid,
            goal_id=goal_id,
            title=title,
            scope=scope,
            expected_outcome=expected_outcome,
            owner=owner,
            required_capabilities=required_capabilities or [],
            dependencies=dependencies or [],
            estimated_resources=estimated_resources or {},
            target_date=target_date,
            status="PLANNED",
            task_graph_id=task_graph_id,
            created_at=now,
        )
        self.repo.save_initiative(init)
        logger.info(f"Created initiative '{iid}' under goal '{goal_id}': '{title}'")
        return init

    def create_milestone(
        self,
        initiative_id: str,
        title: str,
        description: str,
        target_date: str,
        milestone_id: Optional[str] = None,
    ) -> MilestoneRecord:
        """Defines a critical milestone gate within an initiative."""
        with self.repo._get_connection() as conn:
            cursor = conn.execute("SELECT goal_id FROM goal_initiatives WHERE initiative_id = ?", (initiative_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Initiative '{initiative_id}' not found.")
            goal_id = row["goal_id"]

        mid = milestone_id or f"ms-{uuid.uuid4().hex[:8]}"
        ms = MilestoneRecord(
            milestone_id=mid,
            initiative_id=initiative_id,
            goal_id=goal_id,
            title=title,
            description=description,
            target_date=target_date,
            status="PENDING",
            completed_at=None,
            verification_evidence_id=None,
        )
        self.repo.save_milestone(ms)
        logger.info(f"Registered milestone '{mid}' for initiative '{initiative_id}': '{title}'")
        return ms

    def complete_milestone(
        self,
        milestone_id: str,
        verification_evidence_id: Optional[str] = None,
    ) -> MilestoneRecord:
        """Marks a milestone as achieved backed by verification evidence."""
        with self.repo._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM goal_milestones WHERE milestone_id = ?", (milestone_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Milestone '{milestone_id}' not found.")

        now = datetime.now(timezone.utc).isoformat()
        ms = MilestoneRecord(
            milestone_id=row["milestone_id"],
            initiative_id=row["initiative_id"],
            goal_id=row["goal_id"],
            title=row["title"],
            description=row["description"],
            target_date=row["target_date"],
            status="ACHIEVED",
            completed_at=now,
            verification_evidence_id=verification_evidence_id,
        )
        self.repo.save_milestone(ms)
        logger.info(f"Milestone '{milestone_id}' achieved at {now}")
        return ms
