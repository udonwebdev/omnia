"""
Omnia Module 34: Controlled Fault Injection
Injects synthetic node crashes, network partitions, timeouts, and resource exhaustion
strictly inside isolated simulation runs to test resilience.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from simulation.models import FaultInjectionSpec, FaultType


class FaultInjector:
    """
    Manages isolated fault injection during simulation executions.
    Ensures faults remain strictly quarantined within simulation sandbox boundaries.
    """

    def __init__(self) -> None:
        pass

    def create_fault_spec(
        self,
        fault_id: str,
        simulation_id: str,
        fault_type: FaultType,
        target_component: str,
        activation_step: int = 1,
        duration_steps: int = 1,
        severity: str = "HIGH",
    ) -> FaultInjectionSpec:
        return FaultInjectionSpec(
            fault_id=fault_id,
            simulation_id=simulation_id,
            fault_type=fault_type,
            target_component=target_component,
            activation_step=activation_step,
            duration_steps=duration_steps,
            severity=severity,
            injected_at=time.time(),
            recovery_observed=False,
            recovery_details={},
        )

    def get_active_faults_for_step(
        self,
        fault_specs: List[FaultInjectionSpec],
        current_step: int,
    ) -> List[Dict[str, Any]]:
        """
        Returns active faults whose activation step <= current_step < activation_step + duration.
        """
        active = []
        for f in fault_specs:
            start = f.activation_step
            end = start + f.duration_steps
            if start <= current_step < end:
                active.append({
                    "fault_id": f.fault_id,
                    "fault_type": f.fault_type.value if isinstance(f.fault_type, FaultType) else str(f.fault_type),
                    "target_component": f.target_component,
                    "severity": f.severity,
                })
        return active

    def record_recovery(
        self,
        fault_spec: FaultInjectionSpec,
        recovery_step: int,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Marks that system recovered from this fault during simulation.
        """
        fault_spec.recovery_observed = True
        fault_spec.recovery_details = {
            "recovery_step": recovery_step,
            "recovered_at": time.time(),
            "details": details or {},
        }
