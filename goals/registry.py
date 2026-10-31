"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Goal Registry and Strategic Objective Manager.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from goals.models import (
    GoalChangeAuditRecord,
    GoalDefinition,
    GoalLifecycleState,
    GoalPriority,
    GoalType,
    GoalVersionSnapshot,
)
from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Registry")


class GoalRegistry:
    """Manages creation, retrieval, hierarchical relationships, and versioning of goals."""

    def __init__(self, repository: Optional[GoalRepository] = None):
        self.repo = repository or GoalRepository()

    def register_goal(
        self,
        title: str,
        description: str,
        purpose: str,
        owner: str,
        goal_type: GoalType = GoalType.STRATEGIC,
        priority: GoalPriority = GoalPriority.HIGH,
        parent_goal_id: Optional[str] = None,
        start_date: Optional[str] = None,
        target_date: Optional[str] = None,
        success_criteria: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        resource_requirements: Optional[Dict[str, Any]] = None,
        review_schedule: str = "WEEKLY",
        goal_id: Optional[str] = None,
    ) -> GoalDefinition:
        """Creates and stores a new goal definition in DRAFT state."""
        # Cycle prevention in parent hierarchy
        if parent_goal_id:
            parent = self.repo.get_goal(parent_goal_id)
            if not parent:
                raise ValueError(f"Parent goal '{parent_goal_id}' does not exist.")

        gid = goal_id or f"goal-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        goal = GoalDefinition(
            goal_id=gid,
            title=title,
            description=description,
            purpose=purpose,
            owner=owner,
            goal_type=goal_type,
            priority=priority,
            state=GoalLifecycleState.DRAFT,
            version=1,
            parent_goal_id=parent_goal_id,
            start_date=start_date or now,
            target_date=target_date,
            success_criteria=success_criteria or [],
            constraints=constraints or [],
            dependencies=dependencies or [],
            resource_requirements=resource_requirements or {},
            review_schedule=review_schedule,
            created_at=now,
            updated_at=now,
        )
        self.repo.save_goal(goal)

        # Audit record
        audit = GoalChangeAuditRecord(
            audit_id=f"audit-{uuid.uuid4().hex[:8]}",
            goal_id=gid,
            change_type="CREATED",
            field_name="state",
            old_value=None,
            new_value="DRAFT",
            author=owner,
            rationale="Initial creation of goal definition",
            timestamp=now,
        )
        self.repo.save_audit_record(audit)
        logger.info(f"Registered goal '{gid}': '{title}' [{goal_type.value}]")
        return goal

    def activate_goal(self, goal_id: str, operator_id: str) -> GoalDefinition:
        """Transitions a goal from DRAFT or PAUSED to ACTIVE."""
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")
        if goal.state in (GoalLifecycleState.COMPLETED, GoalLifecycleState.CANCELLED):
            raise ValueError(f"Cannot activate goal in terminal state '{goal.state.value}'.")

        old_state = goal.state.value
        goal.state = GoalLifecycleState.ACTIVE
        goal.updated_at = datetime.now(timezone.utc).isoformat()
        self.repo.save_goal(goal)

        audit = GoalChangeAuditRecord(
            audit_id=f"audit-{uuid.uuid4().hex[:8]}",
            goal_id=goal_id,
            change_type="STATUS_CHANGED",
            field_name="state",
            old_value=old_state,
            new_value="ACTIVE",
            author=operator_id,
            rationale="Activated goal for execution",
            timestamp=goal.updated_at,
        )
        self.repo.save_audit_record(audit)
        return goal

    def revise_goal(
        self,
        goal_id: str,
        author: str,
        rationale: str,
        new_title: Optional[str] = None,
        new_description: Optional[str] = None,
        new_target_date: Optional[str] = None,
        new_success_criteria: Optional[List[str]] = None,
        new_constraints: Optional[List[str]] = None,
        approval_token: Optional[str] = None,
    ) -> GoalDefinition:
        """
        Creates an immutable snapshot of current goal state and increments version number.
        Material revisions to target date, criteria, or constraints require documented rationale.
        """
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        # Create version snapshot of current state
        snapshot = GoalVersionSnapshot(
            snapshot_id=f"snap-{uuid.uuid4().hex[:8]}",
            goal_id=goal.goal_id,
            version=goal.version,
            title=goal.title,
            description=goal.description,
            state=goal.state.value,
            target_date=goal.target_date,
            success_criteria=list(goal.success_criteria),
            constraints=list(goal.constraints),
            changed_by=author,
            change_reason=rationale,
            snapshot_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_version_snapshot(snapshot)

        # Apply changes
        old_data = {
            "title": goal.title,
            "target_date": goal.target_date,
            "success_criteria": goal.success_criteria,
            "constraints": goal.constraints,
        }

        if new_title is not None:
            goal.title = new_title
        if new_description is not None:
            goal.description = new_description
        if new_target_date is not None:
            goal.target_date = new_target_date
        if new_success_criteria is not None:
            goal.success_criteria = new_success_criteria
        if new_constraints is not None:
            goal.constraints = new_constraints

        goal.version += 1
        goal.updated_at = datetime.now(timezone.utc).isoformat()
        self.repo.save_goal(goal)

        # Audit record
        audit = GoalChangeAuditRecord(
            audit_id=f"audit-{uuid.uuid4().hex[:8]}",
            goal_id=goal_id,
            change_type="TARGET_REVISED" if new_target_date else "SCOPE_CHANGED",
            field_name="version",
            old_value=old_data,
            new_value={
                "title": goal.title,
                "target_date": goal.target_date,
                "success_criteria": goal.success_criteria,
                "constraints": goal.constraints,
            },
            author=author,
            rationale=rationale,
            approval_token=approval_token,
            timestamp=goal.updated_at,
        )
        self.repo.save_audit_record(audit)
        logger.info(f"Revised goal '{goal_id}' to v{goal.version} by '{author}'")
        return goal

    def get_goal_hierarchy(self, root_goal_id: str) -> Dict[str, Any]:
        """Traverses down the tree to build the complete hierarchical structure of a goal."""
        root = self.repo.get_goal(root_goal_id)
        if not root:
            raise ValueError(f"Goal '{root_goal_id}' not found.")

        def _build_tree(node: GoalDefinition) -> Dict[str, Any]:
            children = self.repo.list_goals(parent_goal_id=node.goal_id)
            krs = self.repo.list_key_results(node.goal_id)
            inits = self.repo.list_initiatives(node.goal_id)
            return {
                "goal_id": node.goal_id,
                "title": node.title,
                "goal_type": node.goal_type.value,
                "state": node.state.value,
                "priority": node.priority.value,
                "version": node.version,
                "target_date": node.target_date,
                "key_results_count": len(krs),
                "initiatives_count": len(inits),
                "children": [_build_tree(c) for c in children],
            }

        return _build_tree(root)
