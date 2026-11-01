"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Evidence-Driven Risk Prioritizer - risk_prioritizer.py

Evaluates contextual risk by combining technical severity, actual exploitability,
asset criticality, network exposure, and reachable attack paths.
Avoids simplistic ranking of CVEs without real architectural context.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app_security.models import (
    Criticality, ExposureTier, PriorityLevel, SecurityFinding, SecurityRiskAssessment, Severity
)
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.RiskPrioritizer")


class RiskPrioritizer:
    """
    Contextual risk engine computing transparent priority rankings.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def evaluate_finding_risk(
        self,
        finding_id: str,
        is_known_exploited: bool = False,
        compensating_controls_active: bool = False
    ) -> SecurityRiskAssessment:
        finding = self.repo.get_finding(finding_id)
        if not finding:
            raise ValueError(f"Finding {finding_id} not found.")

        asset = self.repo.get_asset(finding.asset_id)
        criticality = asset.criticality if asset else Criticality.MEDIUM
        exposure = asset.exposure_tier if asset else ExposureTier.INTERNAL

        # Base technical severity score
        tech_score_map = {
            Severity.LOW: 2.0,
            Severity.MEDIUM: 5.0,
            Severity.HIGH: 8.0,
            Severity.CRITICAL: 10.0
        }
        base_score = tech_score_map.get(finding.severity, 5.0)

        # Asset criticality weight
        crit_weight_map = {
            Criticality.LOW: 0.8,
            Criticality.MEDIUM: 1.0,
            Criticality.HIGH: 1.3,
            Criticality.MISSION_CRITICAL: 1.6
        }
        crit_weight = crit_weight_map.get(criticality, 1.0)

        # Exposure multiplier
        expo_map = {
            ExposureTier.INTERNAL: 0.8,
            ExposureTier.RESTRICTED: 1.1,
            ExposureTier.PUBLIC: 1.5
        }
        expo_mult = expo_map.get(exposure, 1.0)

        # Exploitability factor
        exploit_score = 1.4 if is_known_exploited else 1.0
        if compensating_controls_active:
            exploit_score *= 0.6  # Downward adjustment for effective controls

        # Contextual calculation: base * crit * expo * exploit * 10 capped at 100
        raw_contextual = base_score * crit_weight * expo_mult * exploit_score * 5.0
        contextual_risk_score = min(100.0, round(raw_contextual, 2))

        # Assign priority tier
        if contextual_risk_score >= 80.0:
            priority = PriorityLevel.P0_IMMEDIATE
            urgency = "Immediate remediation required within 24 hours."
        elif contextual_risk_score >= 55.0:
            priority = PriorityLevel.P1_URGENT
            urgency = "Remediate in current sprint / within 7 days."
        elif contextual_risk_score >= 30.0:
            priority = PriorityLevel.P2_STANDARD
            urgency = "Standard security patch cycle."
        else:
            priority = PriorityLevel.P3_LOW
            urgency = "Low priority / address during routine maintenance."

        rid = f"risk-{uuid.uuid4().hex[:8]}"
        risk = SecurityRiskAssessment(
            risk_assessment_id=rid,
            finding_id=finding_id,
            asset_id=finding.asset_id,
            technical_severity=finding.severity,
            exploitability_score=exploit_score,
            asset_criticality_weight=crit_weight,
            exposure_multiplier=expo_mult,
            contextual_risk_score=contextual_risk_score,
            priority_level=priority,
            urgency_recommendation=urgency
        )
        self.repo.save_risk_assessment(risk)
        logger.info(f"Evaluated risk for finding {finding_id}: Score={contextual_risk_score}, Priority={priority.value}")
        return risk
