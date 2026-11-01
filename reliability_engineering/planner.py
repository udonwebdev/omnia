"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Disaster Recovery Planner: Versioned Runbooks, Dependency Sequencing & RTO/RPO Targets.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from reliability_engineering.models import (
    DisasterRecoveryPlanRecord,
    RecoveryStrategy,
)
from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.Planner")


class DisasterRecoveryPlanner:
    """
    Creates and maintains versioned Disaster Recovery (DR) plans.
    Defines dependency-ordered restoration sequences, failover strategies, and target RTO/RPO.
    """

    def __init__(self, repository: Optional[ReliabilityRepository] = None):
        self.repo = repository or ReliabilityRepository()

    def create_dr_plan(
        self,
        title: str,
        disaster_scenario: str,
        affected_services: List[str],
        dependency_order: List[str],
        strategy: RecoveryStrategy = RecoveryStrategy.RESTORE_FROM_BACKUP,
        target_rto_sec: float = 300.0,
        target_rpo_sec: float = 60.0,
        recovery_priority: int = 1,
        plan_id: Optional[str] = None,
        version: int = 1,
    ) -> DisasterRecoveryPlanRecord:
        """Authors a structured DR plan with explicit dependency ordering."""
        pid = plan_id or f"drp-{uuid.uuid4().hex[:8]}"
        plan = DisasterRecoveryPlanRecord(
            plan_id=pid,
            title=title,
            disaster_scenario=disaster_scenario,
            version=version,
            affected_services=affected_services,
            recovery_priority=recovery_priority,
            strategy=strategy,
            dependency_order=dependency_order,
            target_rto_sec=target_rto_sec,
            target_rpo_sec=target_rpo_sec,
            is_active=True,
        )
        self.repo.save_dr_plan(plan)
        logger.info(f"Created DR plan '{pid}': {title} (v{version}, Strategy={strategy.value})")
        return plan

    def get_dr_plan(self, plan_id: str) -> Optional[DisasterRecoveryPlanRecord]:
        return self.repo.get_dr_plan(plan_id)
