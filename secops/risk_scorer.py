"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Transparent Security Risk Scorer - risk_scorer.py
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from secops.models import IncidentPriority, SecuritySeverity
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.RiskScorer")


class SecurityRiskScorer:
    """
    Computes transparent, multi-dimensional risk scores:
    Risk = SeverityWeight * Confidence * AssetCriticality * PrivilegeMultiplier * CorrelationFactor
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def evaluate_risk(
        self,
        severity: SecuritySeverity,
        confidence: float,
        asset_criticality: str = "MEDIUM",
        actor_is_privileged: bool = False,
        correlated_events_count: int = 1,
    ) -> Dict[str, Any]:
        severity_weights = {
            SecuritySeverity.INFO: 1.0,
            SecuritySeverity.LOW: 2.0,
            SecuritySeverity.MEDIUM: 4.5,
            SecuritySeverity.HIGH: 7.5,
            SecuritySeverity.CRITICAL: 10.0,
        }
        base_sev = severity_weights.get(severity, 3.0)

        crit_multipliers = {
            "LOW": 0.8,
            "MEDIUM": 1.0,
            "HIGH": 1.4,
            "MISSION_CRITICAL": 1.8,
            "TIER_0": 2.0,
        }
        crit_mult = crit_multipliers.get(asset_criticality.upper(), 1.0)

        priv_mult = 1.5 if actor_is_privileged else 1.0
        corr_mult = min(2.0, 1.0 + (max(0, correlated_events_count - 1) * 0.15))

        raw_score = base_sev * confidence * crit_mult * priv_mult * corr_mult * 5.0
        contextual_score = min(100.0, round(raw_score, 1))

        # Determine Incident Priority
        if contextual_score >= 80.0:
            priority = IncidentPriority.P0_IMMEDIATE
        elif contextual_score >= 60.0:
            priority = IncidentPriority.P1_URGENT
        elif contextual_score >= 35.0:
            priority = IncidentPriority.P2_STANDARD
        else:
            priority = IncidentPriority.P3_LOW

        explanation = (
            f"Risk Score {contextual_score}/100: BaseSeverity({severity.value})={base_sev}, "
            f"Confidence={confidence:.2f}, AssetCrit({asset_criticality})={crit_mult}x, "
            f"Privileged={priv_mult}x, CorrelatedEvents({correlated_events_count})={corr_mult:.2f}x."
        )

        return {
            "risk_score": contextual_score,
            "priority": priority,
            "explanation": explanation,
            "factors": {
                "base_severity": base_sev,
                "confidence": confidence,
                "asset_criticality_multiplier": crit_mult,
                "privileged_actor_multiplier": priv_mult,
                "correlation_multiplier": corr_mult,
            },
        }
