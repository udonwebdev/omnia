"""
Omnia Module 33: Controlled Rollout Coordinator
Manages staged model/strategy deployment:
OFFLINE_BENCHMARK -> SHADOW_EVALUATION -> STAGED -> CANARY -> PRODUCTION.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from learning.models import RolloutRecord, RolloutStage, RolloutStatus


class RolloutCoordinator:
    """
    Coordinates traffic distribution and stage progression during rollout.
    """

    def __init__(self) -> None:
        pass

    def initiate_rollout(
        self,
        rollout_id: str,
        candidate_version_id: str,
        baseline_version_id: str,
        target_subsystem: str,
        initial_traffic_percent: float = 0.0,
        stage: RolloutStage = RolloutStage.SHADOW,
    ) -> RolloutRecord:
        """
        Creates a new controlled rollout record.
        """
        return RolloutRecord(
            rollout_id=rollout_id,
            candidate_version_id=candidate_version_id,
            baseline_version_id=baseline_version_id,
            target_subsystem=target_subsystem,
            current_stage=stage,
            traffic_percentage=initial_traffic_percent,
            status=RolloutStatus.PENDING,
            health_status="HEALTHY",
            started_at=datetime.now(timezone.utc),
        )

    def advance_stage(
        self,
        record: RolloutRecord,
        target_stage: RolloutStage,
        traffic_percent: float,
        health_check_passed: bool = True,
    ) -> Tuple[bool, str]:
        """
        Advances rollout stage if health checks pass and progression is valid.
        """
        if not health_check_passed:
            record.status = RolloutStatus.PAUSED
            record.health_status = "DEGRADED"
            return False, "Health check failed; rollout paused"

        # Valid stage progressions
        progression = {
            RolloutStage.OFFLINE: [RolloutStage.SHADOW],
            RolloutStage.SHADOW: [RolloutStage.STAGED, RolloutStage.CANARY],
            RolloutStage.STAGED: [RolloutStage.CANARY, RolloutStage.PRODUCTION],
            RolloutStage.CANARY: [RolloutStage.PRODUCTION],
            RolloutStage.PRODUCTION: [],
        }

        if target_stage not in progression.get(record.current_stage, []):
            return False, f"Illegal stage transition from {record.current_stage.value} to {target_stage.value}"

        record.current_stage = target_stage
        record.traffic_percentage = traffic_percent
        record.status = RolloutStatus.ACTIVE if target_stage != RolloutStage.PRODUCTION else RolloutStatus.COMPLETED
        record.health_status = "HEALTHY"

        if target_stage == RolloutStage.PRODUCTION:
            record.ended_at = datetime.now(timezone.utc)

        return True, f"Successfully advanced to {target_stage.value} with {traffic_percent}% traffic"
