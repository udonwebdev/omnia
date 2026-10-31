"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Strategic Alignment Evaluator: Parent-Child Alignment, Contradiction & Orphan Detection.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from goals.models import (
    AlignmentStatus,
    GoalDefinition,
)
from goals.persistence import GoalRepository

logger = logging.getLogger("Omnia.Goals.Alignment")


class StrategicAlignmentEvaluator:
    """
    Evaluates whether lower-level initiatives and child goals actively contribute to
    higher-level strategic objectives, detecting orphans, contradictory targets, and unmeasured goals.
    """

    def __init__(self, repository: Optional[GoalRepository] = None):
        self.repo = repository or GoalRepository()

    def evaluate_goal_alignment(self, goal_id: str) -> Dict[str, Any]:
        """Evaluates strategic alignment for a specific goal."""
        goal = self.repo.get_goal(goal_id)
        if not goal:
            raise ValueError(f"Goal '{goal_id}' not found.")

        issues: List[str] = []
        status = AlignmentStatus.ALIGNED

        # 1. Check if unmeasured (no key results defined)
        krs = self.repo.list_key_results(goal_id)
        if not krs:
            issues.append("Unmeasured strategic objective: No Key Results defined.")
            status = AlignmentStatus.UNMEASURED

        # 2. Check for orphan initiatives (initiatives without milestones or tasks)
        initiatives = self.repo.list_initiatives(goal_id)
        for init in initiatives:
            # check milestones
            with self.repo._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM goal_milestones WHERE initiative_id = ?", (init.initiative_id,))
                cnt = cursor.fetchone()["cnt"]
                if cnt == 0 and not init.task_graph_id:
                    issues.append(f"Orphan initiative '{init.initiative_id}': No milestones or task graph attached.")

        # 3. Check Parent-Child alignment & contradictions
        if goal.parent_goal_id:
            parent = self.repo.get_goal(goal.parent_goal_id)
            if parent:
                # Contradiction check: deadline after parent target date
                if goal.target_date and parent.target_date and goal.target_date > parent.target_date:
                    issues.append(
                        f"Schedule contradiction: Child target date ({goal.target_date}) exceeds parent target date ({parent.target_date})."
                    )
                    status = AlignmentStatus.CONFLICTING

                # Priority inversion: critical child under low priority parent
                if goal.priority.value == "CRITICAL" and parent.priority.value == "LOW":
                    issues.append("Priority mismatch: CRITICAL child objective assigned to LOW priority parent.")
                    if status != AlignmentStatus.CONFLICTING:
                        status = AlignmentStatus.PARTIALLY_ALIGNED
            else:
                issues.append(f"Missing parent goal '{goal.parent_goal_id}'.")
                status = AlignmentStatus.ORPHAN

        return {
            "goal_id": goal_id,
            "title": goal.title,
            "status": status.value,
            "is_aligned": status in (AlignmentStatus.ALIGNED, AlignmentStatus.PARTIALLY_ALIGNED),
            "issues": issues,
            "key_results_count": len(krs),
            "initiatives_count": len(initiatives),
        }
