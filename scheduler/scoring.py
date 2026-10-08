import time
from typing import Dict
from scheduler.models import ScheduleRequest, SchedulingPriority

class PriorityScorer:
    """Computes deterministic, explainable priority, deadline, and fairness scores."""

    @staticmethod
    def compute_priority_score(req: ScheduleRequest, fairness_credits: Dict[str, float]) -> float:
        """Calculates total scheduling weight based on priority, aging, deadline, and fairness debt.
        
        Formula:
            Score = (BasePriority * 100) + (Age_seconds * 0.5) + DeadlineUrgency + FairnessBonus
        """
        now = time.time()
        base_weight = req.priority.value * 100.0

        # Aging: Older ready tasks gain priority to prevent starvation
        age_sec = max(0.0, now - req.ready_at)
        aging_score = min(200.0, age_sec * 0.5)

        # Deadline urgency
        deadline_score = 0.0
        if req.deadline:
            time_left = req.deadline - now
            if time_left <= 0:
                deadline_score = 300.0  # Critical deadline breach
            elif time_left < req.estimated_duration_sec:
                deadline_score = 200.0
            elif time_left < req.estimated_duration_sec * 2:
                deadline_score = 100.0

        # Fairness bonus from mission/user debt
        mission_key = req.mission_id or "default"
        fairness_score = fairness_credits.get(mission_key, 0.0)

        total_score = base_weight + aging_score + deadline_score + fairness_score
        req.priority_score = round(total_score, 2)
        return total_score

priority_scorer = PriorityScorer()
