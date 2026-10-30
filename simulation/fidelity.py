"""
Omnia Module 34: Simulation Fidelity & Reality Comparison
Evaluates correspondence between digital twin predictions and real-world observations.
Measures model deviation and feeds verified evidence to Module 33.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from simulation.models import FidelityAssessment, StateFidelity


class FidelityService:
    """
    Assesses model fidelity and compares simulation outcomes against real-world observations.
    Never conflates simulation results with live observations.
    """

    def __init__(self) -> None:
        pass

    def evaluate_fidelity(
        self,
        simulation_id: str,
        twin_id: Optional[str],
        simulated_metrics: Dict[str, float],
        observed_real_metrics: Optional[Dict[str, float]] = None,
        reality_observation_id: Optional[str] = None,
        tolerance: float = 0.1,
    ) -> FidelityAssessment:
        """
        Calculates deviation between simulated and real metrics.
        Classifies model fidelity based on empirical correspondence.
        """
        now = time.time()
        record_id = f"fid-{simulation_id}-{int(now)}"

        if not observed_real_metrics:
            return FidelityAssessment(
                record_id=record_id,
                simulation_id=simulation_id,
                twin_id=twin_id,
                fidelity_level=StateFidelity.UNVALIDATED,
                reality_observation_id=None,
                deviation_metrics={},
                failed_assumptions=["No real-world observations available for calibration"],
                unexplained_deviations=[],
                assessed_at=now,
                recommended_learning_signal=False,
            )

        deviations: Dict[str, float] = {}
        failed_assumptions: List[str] = []
        unexplained: List[str] = []

        for key, real_val in observed_real_metrics.items():
            if key in simulated_metrics:
                sim_val = simulated_metrics[key]
                diff = abs(sim_val - real_val)
                rel_err = diff / (real_val if real_val != 0 else 1.0)
                deviations[key] = round(rel_err, 4)
                if rel_err > tolerance:
                    failed_assumptions.append(f"Metric '{key}' exceeded tolerance: error={round(rel_err*100, 1)}%")
            else:
                unexplained.append(f"Metric '{key}' present in reality but unmodeled in simulation")

        avg_error = (sum(deviations.values()) / len(deviations)) if deviations else 1.0

        if avg_error <= 0.05 and not unexplained:
            level = StateFidelity.HIGH
        elif avg_error <= 0.15:
            level = StateFidelity.MODERATE
        else:
            level = StateFidelity.LOW

        should_learn = len(failed_assumptions) > 0 or avg_error > tolerance

        return FidelityAssessment(
            record_id=record_id,
            simulation_id=simulation_id,
            twin_id=twin_id,
            fidelity_level=level,
            reality_observation_id=reality_observation_id,
            deviation_metrics=deviations,
            failed_assumptions=failed_assumptions,
            unexplained_deviations=unexplained,
            assessed_at=now,
            recommended_learning_signal=should_learn,
        )
