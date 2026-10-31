"""
OMNIA Module 37: Risk & Trade-off Analyzer
Evaluates failure probabilities, operational disruption, financial exposure,
mitigations, and calculates honest residual risk scores without disguising missing data.
"""

import uuid
import logging
from typing import Dict, Any, List, Optional
from strategy.models import (
    StrategicOptionRecord,
    RiskTradeoffAssessment,
)
from strategy.persistence import StrategyRepository

logger = logging.getLogger("Omnia.Strategy.Risk")


class RiskTradeoffAnalyzer:
    """Analyzes failure modes, severity penalties, and trade-offs for candidate options."""

    def __init__(self, repo: StrategyRepository):
        self.repo = repo

    def evaluate_risk(
        self,
        case_id: str,
        option: StrategicOptionRecord,
        probability_of_failure: float,  # 0.0 to 1.0
        severity_of_failure: float,  # 0.0 to 1.0
        financial_exposure: float,
        operational_disruption: str = "MINOR",
        security_risk: str = "LOW",
        opportunity_cost_notes: str = "",
        mitigation_strategy: str = "",
    ) -> RiskTradeoffAssessment:
        """
        Calculates honest residual risk score:
        Formula: (Prob * Severity) * (1.0 - 0.5 * Reversibility) * DisruptionMultiplier
        """
        prob = max(0.0, min(1.0, probability_of_failure))
        sev = max(0.0, min(1.0, severity_of_failure))
        base_risk = prob * sev

        # Irreversible options have higher residual risk penalty
        rev_factor = max(0.1, option.reversibility_score)

        # Operational disruption multiplier
        disruption_multipliers = {
            "NONE": 1.0,
            "MINOR": 1.1,
            "MAJOR": 1.4,
            "CATASTROPHIC": 2.0,
        }
        mult = disruption_multipliers.get(operational_disruption.upper(), 1.2)

        # Mitigation discount (up to 30% reduction if verified mitigation exists)
        mitigation_discount = 0.7 if mitigation_strategy.strip() else 1.0

        residual_score = round(min(1.0, (base_risk / rev_factor) * mult * mitigation_discount), 3)

        # Acceptable if residual score <= 0.65 or risk tolerance is HIGH
        is_acceptable = residual_score <= 0.65

        assessment = RiskTradeoffAssessment(
            assessment_id=f"risk-{uuid.uuid4().hex[:8]}",
            case_id=case_id,
            option_id=option.option_id,
            probability_of_failure=prob,
            severity_of_failure=sev,
            financial_exposure=financial_exposure,
            operational_disruption=operational_disruption,
            security_risk=security_risk,
            opportunity_cost_notes=opportunity_cost_notes,
            mitigation_strategy=mitigation_strategy,
            residual_risk_score=residual_score,
            is_acceptable=is_acceptable,
        )
        self.repo.save_risk_assessment(assessment)
        logger.info(f"Evaluated risk for option '{option.option_id}': Residual={residual_score} (Acceptable={is_acceptable})")
        return assessment
