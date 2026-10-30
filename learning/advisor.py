"""
Omnia Module 33: Adaptive Parameter Advisor
Recommends bounded tuning adjustments for system parameters,
strictly enforcing non-negotiable architectural boundaries.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from learning.models import ParameterRecommendation


FORBIDDEN_KEY_PATTERNS = [
    re.compile(r"^security\.", re.IGNORECASE),
    re.compile(r"^auth\.", re.IGNORECASE),
    re.compile(r"^policy\.", re.IGNORECASE),
    re.compile(r"^secrets\.", re.IGNORECASE),
    re.compile(r"^keys\.", re.IGNORECASE),
    re.compile(r"^credentials\.", re.IGNORECASE),
    re.compile(r"^approvals?\.", re.IGNORECASE),
    re.compile(r"^audit\.", re.IGNORECASE),
    re.compile(r"^guardrails?\.", re.IGNORECASE),
]

TUNABLE_PARAMETER_BOUNDS = {
    "retrieval.dense_weight": (0.0, 1.0),
    "retrieval.sparse_weight": (0.0, 1.0),
    "retrieval.top_k": (1, 100),
    "retrieval.rrf_k": (10, 200),
    "planning.timeout_seconds": (10, 600),
    "planning.max_replan_depth": (1, 10),
    "prediction.horizon_days": (1, 90),
    "prediction.anomaly_threshold": (1.0, 5.0),
    "caching.ttl_seconds": (30, 86400),
    "worker.batch_size": (1, 500),
}


class ParameterAdvisor:
    """
    Evaluates parameter performance signals and recommends adjustments
    within strictly enforced boundaries.
    """

    def __init__(self) -> None:
        pass

    def is_forbidden_parameter(self, parameter_key: str) -> bool:
        """
        Returns True if parameter touches security, auth, policy, or approvals.
        """
        for pat in FORBIDDEN_KEY_PATTERNS:
            if pat.search(parameter_key):
                return True
        return False

    def recommend_adjustment(
        self,
        recommendation_id: str,
        parameter_key: str,
        current_value: Any,
        proposed_value: Any,
        subsystem: str,
        justification: str,
        supporting_signal_ids: List[str],
        expected_improvement: str,
    ) -> Tuple[bool, Optional[ParameterRecommendation], str]:
        """
        Validates whether parameter is tunable and within bounds.
        Returns (is_allowed, recommendation_object, rejection_reason).
        """
        if self.is_forbidden_parameter(parameter_key):
            return (
                False,
                None,
                f"Autonomous modification of security/policy parameter '{parameter_key}' is strictly forbidden",
            )

        if parameter_key not in TUNABLE_PARAMETER_BOUNDS:
            return (
                False,
                None,
                f"Parameter '{parameter_key}' is not in the approved tunable parameter catalog",
            )

        min_val, max_val = TUNABLE_PARAMETER_BOUNDS[parameter_key]
        if not (min_val <= proposed_value <= max_val):
            return (
                False,
                None,
                f"Proposed value {proposed_value} violates allowable bounds [{min_val}, {max_val}] for '{parameter_key}'",
            )

        rec = ParameterRecommendation(
            recommendation_id=recommendation_id,
            parameter_key=parameter_key,
            current_value=current_value,
            proposed_value=proposed_value,
            supporting_evidence=justification,
            baseline_comparison=f"Current: {current_value}, Proposed: {proposed_value}",
            expected_benefit=0.05,
            uncertainty=0.02,
            potential_regressions=[],
            required_authorization="HUMAN_OPERATOR",
            expires_at=time.time() + 86400 * 7,
            status="PROPOSED",
            created_at=time.time(),
        )

        return True, rec, ""
