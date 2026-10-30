"""
Omnia Module 32: Forecaster Registry & Model Selection
Manages available forecasting algorithms, provides safe baseline fallback,
and transparently reports unsupported or unavailable models.
"""

from typing import Dict, Any, Optional, List

from prediction.models import ForecastType
from prediction.baselines import (
    BaseForecaster,
    LastObservationBaseline,
    MovingAverageForecaster,
    TrendForecaster,
    FrequencyClassificationForecaster,
    DurationForecaster,
    RuleBasedRiskForecaster,
)


class ForecasterRegistry:
    """Registry of implemented, validated forecasting engines."""

    def __init__(self):
        self._forecasters: Dict[str, BaseForecaster] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(LastObservationBaseline())
        self.register(MovingAverageForecaster())
        self.register(TrendForecaster())
        self.register(FrequencyClassificationForecaster())
        self.register(DurationForecaster())
        self.register(RuleBasedRiskForecaster())

    def register(self, forecaster: BaseForecaster):
        self._forecasters[forecaster.name.upper()] = forecaster

    def get(self, name: str) -> Optional[BaseForecaster]:
        return self._forecasters.get(name.upper())

    def select_forecaster(
        self,
        target_type: ForecastType,
        method_override: Optional[str] = None,
    ) -> BaseForecaster:
        """
        Selects the best available forecaster based on target type,
        or respects an explicit method override.
        """
        if method_override and method_override.upper() in self._forecasters:
            return self._forecasters[method_override.upper()]

        # Map target types to validated forecasters
        if target_type == ForecastType.CLASSIFICATION:
            return self._forecasters["FREQUENCYCLASSIFICATIONFORECASTER"]
        elif target_type in (ForecastType.REGRESSION, ForecastType.TIME_SERIES):
            return self._forecasters["TRENDFORECASTER"]
        elif target_type == ForecastType.DURATION_ESTIMATION:
            return self._forecasters["DURATIONFORECASTER"]
        elif target_type == ForecastType.ANOMALY_RISK:
            return self._forecasters["RULEBASEDRISKFORECASTER"]
        elif target_type == ForecastType.SCENARIO_COMPARISON:
            return self._forecasters["TRENDFORECASTER"]
        else:
            return self._forecasters["LASTOBSERVATIONBASELINE"]

    def list_supported_methods(self) -> List[str]:
        return list(self._forecasters.keys())

    @staticmethod
    def list_unsupported_methods() -> List[str]:
        """Explicitly declares models not implemented or trained in this environment."""
        return [
            "ARIMA_SEASONAL",
            "PROPHET_DEEP_LEARNING",
            "TRANSFORMER_TEMPORAL_FUSION",
            "BAYESIAN_NEURAL_NETWORK",
        ]


# Default global registry
forecaster_registry = ForecasterRegistry()
