"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Failure Mode and Effects Analysis (FMEA) & Single Point of Failure (SPOF) Detection.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from reliability_engineering.models import (
    FailureModeRecord,
)
from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.FMEA")


class FailureModeAndEffectsAnalyzer:
    """
    Performs structured Failure Mode and Effects Analysis (FMEA).
    Calculates Risk Priority Numbers (RPN) and automatically identifies Single Points of Failure (SPOFs).
    """

    def __init__(self, repository: Optional[ReliabilityRepository] = None):
        self.repo = repository or ReliabilityRepository()

    def analyze_failure_mode(
        self,
        component_id: str,
        failure_mode_name: str,
        potential_causes: List[str],
        local_impact: str,
        downstream_impact: str,
        detectability_score: int,  # 1 to 10
        severity_score: int,       # 1 to 10
        probability_score: int,    # 1 to 10
        existing_controls: Optional[List[str]] = None,
        recommended_mitigation: str = "",
        mode_id: Optional[str] = None,
    ) -> FailureModeRecord:
        """
        Calculates RPN = Detectability * Severity * Probability.
        Flags as SPOF if severity >= 8, redundancy is absent or dependent count > 0, and controls < 2.
        """
        det = max(1, min(10, detectability_score))
        sev = max(1, min(10, severity_score))
        prob = max(1, min(10, probability_score))
        rpn = det * sev * prob

        comp = self.repo.get_component(component_id)
        redundancy = comp.redundancy_config if comp else "NONE"
        is_spof = False
        if sev >= 8 and (redundancy in ("NONE", "1", "STANDALONE") or not existing_controls):
            is_spof = True

        mid = mode_id or f"fm-{uuid.uuid4().hex[:8]}"
        record = FailureModeRecord(
            mode_id=mid,
            component_id=component_id,
            failure_mode_name=failure_mode_name,
            potential_causes=potential_causes,
            local_impact=local_impact,
            downstream_impact=downstream_impact,
            detectability_score=det,
            severity_score=sev,
            probability_score=prob,
            risk_priority_number=rpn,
            is_spof=is_spof,
            existing_controls=existing_controls or [],
            recommended_mitigation=recommended_mitigation,
        )
        self.repo.save_failure_mode(record)
        logger.info(f"FMEA evaluated '{mid}' on '{component_id}': RPN={rpn}, SPOF={is_spof}")
        return record

    def list_spofs(self) -> List[FailureModeRecord]:
        return self.repo.list_all_spofs()

    def get_component_risk_summary(self, component_id: str) -> List[FailureModeRecord]:
        return self.repo.list_failure_modes_for_component(component_id)
