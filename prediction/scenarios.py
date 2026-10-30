"""
Omnia Module 32: Scenario Analysis & Counterfactual Integrity
Enables bounded 'what-if' comparisons between explicit scenarios.
All results are strictly tagged as HYPOTHETICAL conditional estimates,
preserving counterfactual integrity without asserting causal inevitability.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import copy
import uuid
import time

from prediction.models import (
    Forecast,
    ForecastRequest,
    ForecastInput,
    ForecastScenario,
    ForecastType,
    ForecastAssumption,
)
from prediction.methods import forecaster_registry
from prediction.features import FeaturePipeline


@dataclass
class ScenarioComparisonResult:
    comparison_id: str
    target_id: str
    baseline_forecast: Forecast
    scenario_forecasts: Dict[str, Forecast]
    differences: Dict[str, Dict[str, Any]]
    is_hypothetical: bool = True
    assumptions_summary: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    evaluated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparison_id": self.comparison_id,
            "target_id": self.target_id,
            "baseline_forecast": self.baseline_forecast.to_dict(),
            "scenario_forecasts": {k: v.to_dict() for k, v in self.scenario_forecasts.items()},
            "differences": self.differences,
            "is_hypothetical": self.is_hypothetical,
            "assumptions_summary": self.assumptions_summary,
            "limitations": self.limitations,
            "evaluated_at": self.evaluated_at,
        }


class ScenarioAnalyzer:
    """Evaluates and compares explicit hypothetical scenarios against baseline projections."""

    @staticmethod
    def compare_scenarios(
        base_request: ForecastRequest,
        base_inputs: List[ForecastInput],
        scenarios: List[ForecastScenario],
        method_name: Optional[str] = None,
    ) -> ScenarioComparisonResult:
        cid = f"scncmp-{uuid.uuid4().hex[:10]}"
        forecaster = forecaster_registry.select_forecaster(base_request.target.target_type, method_name)

        # 1. Generate baseline forecast
        base_features = FeaturePipeline.extract_features(base_inputs, base_request.as_of_time)
        base_forecast = forecaster.forecast(base_request, base_inputs, base_features)

        scenario_forecasts: Dict[str, Forecast] = {}
        differences: Dict[str, Dict[str, Any]] = {}
        all_assumptions: List[str] = []

        for scn in scenarios:
            # Clone request and inputs for hypothetical manipulation
            scn_request = copy.deepcopy(base_request)
            scn_inputs = copy.deepcopy(base_inputs)

            # Apply modified variables to inputs or parameters
            for var_key, var_val in scn.modified_variables.items():
                if var_key in scn_request.parameters:
                    scn_request.parameters[var_key] = var_val
                # If modified variable corresponds to simulated last observation:
                if var_key == "simulated_last_value":
                    scn_inputs.append(ForecastInput(
                        input_id=f"hypo_inp_{uuid.uuid4().hex[:6]}",
                        timestamp=base_request.as_of_time,
                        value=var_val,
                        source="HYPOTHETICAL_SCENARIO",
                    ))

            scn_features = FeaturePipeline.extract_features(scn_inputs, scn_request.as_of_time)
            # Recompute forecast under hypothetical conditions
            scn_fc = forecaster.forecast(scn_request, scn_inputs, scn_features)
            scn_fc.scenario = scn
            scn_fc.limitations.append("HYPOTHETICAL CONDITIONAL ESTIMATE: Does not constitute causal proof.")
            scenario_forecasts[scn.scenario_id] = scn_fc

            # Calculate difference vs baseline
            diff: Dict[str, Any] = {
                "scenario_name": scn.name,
                "is_hypothetical": True,
            }
            if base_forecast.predicted_value is not None and scn_fc.predicted_value is not None:
                val_diff = round(scn_fc.predicted_value - base_forecast.predicted_value, 4)
                diff["value_delta"] = val_diff
                diff["percent_change"] = round((val_diff / base_forecast.predicted_value) * 100, 2) if base_forecast.predicted_value != 0 else 0.0
            if base_forecast.predicted_class != scn_fc.predicted_class:
                diff["class_shift"] = f"{base_forecast.predicted_class} -> {scn_fc.predicted_class}"

            differences[scn.scenario_id] = diff
            for asm in scn.assumptions:
                all_assumptions.append(f"[{scn.name}] {asm.description}")

        limitations = [
            "Counterfactual estimates assume ceteris paribus (all other variables unchanged).",
            "Outputs are purely conditional projections and must not be treated as historical facts or causal certainty.",
        ]

        return ScenarioComparisonResult(
            comparison_id=cid,
            target_id=base_request.target.target_id,
            baseline_forecast=base_forecast,
            scenario_forecasts=scenario_forecasts,
            differences=differences,
            is_hypothetical=True,
            assumptions_summary=all_assumptions,
            limitations=limitations,
            evaluated_at=time.time(),
        )
