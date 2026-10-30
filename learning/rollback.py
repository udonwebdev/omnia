"""
Omnia Module 33: Verified Runtime Rollback Coordinator
Executes deterministic, atomic rollback to verified baseline versions
when regressions, safety anomalies, or policy violations occur.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from learning.models import RolloutRecord, RolloutStatus


class RollbackCoordinator:
    """
    Handles immediate emergency and policy-driven rollbacks of active models/strategies.
    """

    def __init__(self) -> None:
        pass

    def execute_rollback(
        self,
        rollout_record: RolloutRecord,
        trigger_reason: str,
        initiated_by: str = "system",
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Rolls back candidate traffic immediately to the baseline version.
        """
        if rollout_record.status == RolloutStatus.ROLLED_BACK:
            return True, "Rollout already rolled back", {"status": "ALREADY_ROLLED_BACK"}

        # 1. Zero out candidate traffic
        previous_traffic = rollout_record.traffic_percentage
        previous_stage = rollout_record.current_stage

        rollout_record.traffic_percentage = 0.0
        rollout_record.status = RolloutStatus.ROLLED_BACK
        rollout_record.health_status = "ROLLED_BACK"
        rollout_record.ended_at = datetime.now(timezone.utc)
        rollout_record.metadata["rollback_info"] = {
            "trigger_reason": trigger_reason,
            "initiated_by": initiated_by,
            "previous_stage": previous_stage.value,
            "previous_traffic_percent": previous_traffic,
            "restored_baseline_version": rollout_record.baseline_version_id,
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        }

        audit_entry = {
            "rollout_id": rollout_record.rollout_id,
            "subsystem": rollout_record.target_subsystem,
            "candidate_version_id": rollout_record.candidate_version_id,
            "restored_baseline_version_id": rollout_record.baseline_version_id,
            "trigger_reason": trigger_reason,
            "success": True,
        }

        return True, f"Successfully rolled back {rollout_record.target_subsystem} to {rollout_record.baseline_version_id}", audit_entry
