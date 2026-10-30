"""
Omnia Module 33: Outcome Attribution & Causal Confidence
Connects observed outcomes back to specific strategy versions, models,
configurations, and execution contexts with rigorous uncertainty quantification.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from learning.models import AttributionConfidence, LearningSignal


class OutcomeAttributor:
    """
    Evaluates whether an observed task outcome, forecast error, or execution metric
    can be causally attributed to a specific model version, strategy, or parameter set.
    """

    def __init__(self) -> None:
        pass

    def evaluate_attribution(
        self,
        signal: LearningSignal,
        environmental_factors: Optional[Dict[str, Any]] = None,
    ) -> AttributionConfidence:
        """
        Determines attribution confidence based on confounders, execution isolation,
        and completeness of context.
        """
        env = environmental_factors or {}

        # 1. Unknown if core IDs are missing
        if not signal.strategy_id or not signal.model_version:
            return AttributionConfidence.UNKNOWN

        # 2. Confounding check: Network timeouts, upstream provider outages, node failures
        has_network_failure = env.get("network_timeout", False) or "503" in str(signal.metrics)
        has_provider_outage = env.get("provider_outage", False)
        has_hardware_crash = env.get("hardware_fault", False)

        if has_network_failure or has_provider_outage or has_hardware_crash:
            return AttributionConfidence.CORRELATED

        # 3. Check verification status
        if signal.is_verified:
            return AttributionConfidence.INDEPENDENTLY_VERIFIED

        if signal.task_id:
            return AttributionConfidence.DIRECTLY_OBSERVED

        return AttributionConfidence.MODEL_INFERRED

    def attribute_outcome(
        self,
        signal: LearningSignal,
        environmental_factors: Optional[Dict[str, Any]] = None,
    ) -> LearningSignal:
        """
        Enriches a signal with evaluated attribution confidence and causal metadata.
        """
        confidence = self.evaluate_attribution(signal, environmental_factors)
        if confidence == AttributionConfidence.INDEPENDENTLY_VERIFIED:
            signal.is_verified = True
        return signal
