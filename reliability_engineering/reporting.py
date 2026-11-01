"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Disaster Recovery Reporting Service: Executive Reliability Scorecards & HUD Briefings.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.Reporting")


class DisasterRecoveryReporter:
    """Compiles reliability scorecards, SPOF vulnerability alerts, and disaster recovery posture."""

    def __init__(self, repository: ReliabilityRepository):
        self.repo = repository

    def generate_reliability_overview(self) -> Dict[str, Any]:
        """Synthesizes comprehensive system reliability, backup readiness, and DR drill metrics."""
        comps = self.repo.list_components()
        spofs = self.repo.list_all_spofs()
        regressions = self.repo.list_resilience_regressions()
        findings = self.repo.list_integrity_findings()

        # Component readiness breakdown
        readiness_counts = {"READY": 0, "DEGRADED": 0, "NOT_READY": 0, "UNKNOWN": 0}
        for c in comps:
            state = c.failover_readiness.value
            readiness_counts[state] = readiness_counts.get(state, 0) + 1

        posture = "NORMAL"
        if len(spofs) > 0 or len(findings) > 0:
            posture = "ELEVATED_RISK"
        if len(regressions) > 0:
            posture = "RESILIENCE_REGRESSION"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_posture": posture,
            "total_monitored_components": len(comps),
            "failover_readiness": readiness_counts,
            "single_points_of_failure_count": len(spofs),
            "single_points_of_failure": [
                {
                    "mode_id": s.mode_id,
                    "component_id": s.component_id,
                    "failure_mode": s.failure_mode_name,
                    "rpn": s.risk_priority_number,
                    "mitigation": s.recommended_mitigation,
                }
                for s in spofs
            ],
            "active_regressions_count": len(regressions),
            "open_integrity_findings_count": len(findings),
        }
