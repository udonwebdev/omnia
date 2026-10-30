"""
Omnia Module 34: Digital Twin Manager
Manages versioned digital representations of real systems,
distinguishing observed, inferred, and simulated states with freshness tracking.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from simulation.models import DigitalTwin, StateFidelity, TwinStatus, TwinSyncMode


class DigitalTwinManager:
    """
    Manages static and dynamic digital twin representations of real-world or logical subsystems.
    Strictly preserves state provenance (OBSERVED vs INFERRED vs SIMULATED).
    """

    def __init__(self) -> None:
        pass

    def create_twin(
        self,
        twin_id: str,
        source_system_id: str,
        source_system_type: str,
        version: str = "1.0.0",
        sync_mode: TwinSyncMode = TwinSyncMode.STATIC,
        initial_observed_state: Optional[Dict[str, Any]] = None,
        capability_model: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
        known_omissions: Optional[List[str]] = None,
    ) -> DigitalTwin:
        """
        Initializes a new digital twin representation.
        """
        obs = initial_observed_state or {}
        provenance = self._compute_provenance(source_system_id, obs)

        return DigitalTwin(
            twin_id=twin_id,
            source_system_id=source_system_id,
            source_system_type=source_system_type,
            version=version,
            sync_mode=sync_mode,
            state_schema_version="1.0.0",
            observed_state=copy.deepcopy(obs),
            inferred_state={},
            simulated_state={},
            capability_model=capability_model or {},
            constraints=constraints or {},
            dependencies=dependencies or [],
            known_omissions=known_omissions or [],
            last_sync_time=time.time(),
            freshness_seconds=0.0,
            fidelity_status=StateFidelity.LOW if not obs else StateFidelity.MODERATE,
            provenance_hash=provenance,
            created_at=time.time(),
            updated_at=time.time(),
        )

    def synchronize_twin(
        self,
        twin: DigitalTwin,
        new_observations: Dict[str, Any],
        inferred_updates: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """
        Applies live observations to the digital twin, updating freshness and provenance.
        """
        now = time.time()
        twin.observed_state.update(copy.deepcopy(new_observations))
        if inferred_updates:
            twin.inferred_state.update(copy.deepcopy(inferred_updates))

        twin.freshness_seconds = round(now - twin.last_sync_time, 2)
        twin.last_sync_time = now
        twin.provenance_hash = self._compute_provenance(twin.source_system_id, twin.observed_state)
        twin.updated_at = now
        return True, "Digital twin synchronized successfully"

    def record_simulated_transition(
        self,
        twin: DigitalTwin,
        simulated_state_delta: Dict[str, Any],
    ) -> None:
        """
        Updates the simulated state partition without corrupting observed facts.
        """
        twin.simulated_state.update(copy.deepcopy(simulated_state_delta))
        twin.updated_at = time.time()

    def assess_freshness(self, twin: DigitalTwin, max_stale_seconds: float = 3600.0) -> Tuple[bool, str]:
        """
        Evaluates whether twin observations are stale.
        """
        age = time.time() - twin.last_sync_time
        if age > max_stale_seconds:
            twin.fidelity_status = StateFidelity.LOW
            return False, f"Digital twin is stale: {round(age, 1)}s since last synchronization (threshold: {max_stale_seconds}s)"
        return True, f"Digital twin is fresh: {round(age, 1)}s old"

    def _compute_provenance(self, source_id: str, state: Dict[str, Any]) -> str:
        serialized = json.dumps({"source": source_id, "state": state}, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
