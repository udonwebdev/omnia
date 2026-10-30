"""
Omnia Module 34: Simulation & Digital Twin Service Facade
Primary production facade orchestrating environments, digital twins,
snapshots, scenarios, execution, fault injection, and Event Fabric integration.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from events.fabric import EventFabric, event_fabric
from events.models import Event, EventEnvelope
from simulation.compiler import ScenarioCompiler
from simulation.engine import SimulationEngine
from simulation.exploration import AlternativePathExplorer
from simulation.faults import FaultInjector
from simulation.fidelity import FidelityService
from simulation.models import (
    AlternativeSearchStrategy,
    DigitalTwin,
    EnvironmentClassification,
    EnvironmentType,
    FaultInjectionSpec,
    FaultType,
    FidelityAssessment,
    ScenarioDefinition,
    ScenarioType,
    SimulationEnvironment,
    SimulationExecutionRecord,
    StateFidelity,
    StateSnapshot,
    TwinSyncMode,
)
from simulation.persistence import SimulationRepository
from simulation.snapshots import SnapshotManager
from simulation.twins import DigitalTwinManager

logger = logging.getLogger(__name__)


class SimulationService:
    """
    Unified production facade for Module 34: Simulation, Digital Twin & Scenario Testing.
    """

    def __init__(
        self,
        repository: Optional[SimulationRepository] = None,
        event_bus: Optional[EventFabric] = None,
    ) -> None:
        self.repository = repository or SimulationRepository()
        self.event_bus = event_bus or event_fabric

        self.twin_manager = DigitalTwinManager()
        self.snapshot_manager = SnapshotManager()
        self.compiler = ScenarioCompiler()
        self.engine = SimulationEngine()
        self.fault_injector = FaultInjector()
        self.explorer = AlternativePathExplorer()
        self.fidelity_service = FidelityService()

    # -------------------------------------------------------------
    # 1. ENVIRONMENT MANAGEMENT
    # -------------------------------------------------------------
    def create_environment(
        self,
        environment_id: str,
        name: str,
        env_type: EnvironmentType,
        classification: EnvironmentClassification = EnvironmentClassification.TEST,
        supported_capabilities: Optional[List[str]] = None,
        supported_action_types: Optional[List[str]] = None,
        resource_limits: Optional[Dict[str, Any]] = None,
        owner: str = "system",
    ) -> SimulationEnvironment:
        """
        Registers an isolated simulation environment.
        """
        env = SimulationEnvironment(
            environment_id=environment_id,
            name=name,
            env_type=env_type,
            classification=classification,
            version="1.0.0",
            owner=owner,
            supported_capabilities=supported_capabilities or [],
            supported_action_types=supported_action_types or ["task.complete", "task.fail", "node.failover", "resource.allocate", "api.request"],
            resource_limits=resource_limits or {"max_steps": 100, "timeout_seconds": 300},
            fidelity_classification=StateFidelity.MODERATE,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.repository.save_environment(env)

        self._emit_event(
            event_type="simulation.environment.created",
            source="simulation.environments",
            payload={"environment_id": environment_id, "name": name, "classification": env.classification.value},
        )
        return env

    # -------------------------------------------------------------
    # 2. DIGITAL TWIN MANAGEMENT
    # -------------------------------------------------------------
    def register_digital_twin(
        self,
        twin_id: str,
        source_system_id: str,
        source_system_type: str,
        initial_observed_state: Optional[Dict[str, Any]] = None,
        sync_mode: TwinSyncMode = TwinSyncMode.STATIC,
        capability_model: Optional[Dict[str, Any]] = None,
    ) -> DigitalTwin:
        """
        Registers a digital twin representation with state provenance.
        """
        twin = self.twin_manager.create_twin(
            twin_id=twin_id,
            source_system_id=source_system_id,
            source_system_type=source_system_type,
            sync_mode=sync_mode,
            initial_observed_state=initial_observed_state,
            capability_model=capability_model,
        )
        self.repository.save_digital_twin(twin)

        self._emit_event(
            event_type="simulation.twin.created",
            source="simulation.twins",
            payload={"twin_id": twin_id, "source_id": source_system_id, "sync_mode": twin.sync_mode.value},
        )
        return twin

    # -------------------------------------------------------------
    # 3. STATE SNAPSHOTS
    # -------------------------------------------------------------
    def capture_snapshot(
        self,
        snapshot_id: str,
        environment_id: str,
        raw_state: Dict[str, Any],
        known_limitations: Optional[List[str]] = None,
        created_by: str = "system",
    ) -> StateSnapshot:
        """
        Captures an immutable, sanitized state snapshot with SHA-256 digest.
        """
        snapshot = self.snapshot_manager.create_snapshot(
            snapshot_id=snapshot_id,
            environment_id=environment_id,
            raw_state=raw_state,
            known_limitations=known_limitations,
            created_by=created_by,
        )
        self.repository.save_snapshot(snapshot)

        self._emit_event(
            event_type="simulation.snapshot.created",
            source="simulation.snapshots",
            payload={"snapshot_id": snapshot_id, "digest": snapshot.integrity_digest},
        )
        return snapshot

    # -------------------------------------------------------------
    # 4. SCENARIOS & COMPILATION
    # -------------------------------------------------------------
    def register_scenario(
        self,
        scenario_id: str,
        name: str,
        scenario_type: ScenarioType,
        environment_id: str,
        initial_snapshot_id: str,
        proposed_actions: List[Dict[str, Any]],
        preconditions: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        time_horizon_seconds: float = 60.0,
        resource_budget: Optional[Dict[str, Any]] = None,
    ) -> ScenarioDefinition:
        """
        Registers a scenario and verifies its compilation preconditions.
        """
        scen = ScenarioDefinition(
            scenario_id=scenario_id,
            name=name,
            scenario_type=scenario_type,
            environment_id=environment_id,
            initial_snapshot_id=initial_snapshot_id,
            proposed_actions=proposed_actions,
            preconditions=preconditions or {},
            constraints=constraints or {},
            time_horizon_seconds=time_horizon_seconds,
            resource_budget=resource_budget or {"max_duration_seconds": time_horizon_seconds},
            created_at=time.time(),
        )

        env = self.repository.get_environment(environment_id)
        snap = self.repository.get_snapshot(initial_snapshot_id)

        if env and snap:
            ok, plan, err = self.compiler.compile_scenario(scen, env, snap)
            if not ok:
                raise ValueError(f"Scenario compilation failed: {err}")

        self.repository.save_scenario(scen)
        self._emit_event(
            event_type="simulation.scenario.registered",
            source="simulation.scenarios",
            payload={"scenario_id": scenario_id, "name": name, "actions_count": len(proposed_actions)},
        )
        return scen

    # -------------------------------------------------------------
    # 5. SIMULATION EXECUTION
    # -------------------------------------------------------------
    def run_simulation(
        self,
        simulation_id: str,
        scenario_id: str,
        twin_id: Optional[str] = None,
        fault_specs: Optional[List[FaultInjectionSpec]] = None,
    ) -> SimulationExecutionRecord:
        """
        Executes a deterministic simulation run.
        """
        scen = self.repository.get_scenario(scenario_id)
        if not scen:
            raise ValueError(f"Scenario not found: {scenario_id}")

        snap = self.repository.get_snapshot(scen.initial_snapshot_id)
        if not snap:
            raise ValueError(f"Initial snapshot not found: {scen.initial_snapshot_id}")

        self._emit_event(
            event_type="simulation.started",
            source="simulation.engine",
            payload={"simulation_id": simulation_id, "scenario_id": scenario_id},
        )

        record = self.engine.run_simulation(
            simulation_id=simulation_id,
            scenario=scen,
            snapshot=snap,
            twin_id=twin_id,
            fault_specs=fault_specs,
        )

        # Update twin simulated state if twin provided
        if twin_id:
            twin = self.repository.get_digital_twin(twin_id)
            if twin and record.result_summary.get("final_state"):
                self.twin_manager.record_simulated_transition(twin, record.result_summary["final_state"])
                self.repository.save_digital_twin(twin)

        self.repository.save_execution(record)

        self._emit_event(
            event_type="simulation.completed" if record.status.value == "COMPLETED" else "simulation.failed",
            source="simulation.engine",
            payload={"simulation_id": simulation_id, "status": record.status.value},
        )
        return record

    # -------------------------------------------------------------
    # 6. FAULT INJECTION
    # -------------------------------------------------------------
    def inject_fault(
        self,
        fault_id: str,
        simulation_id: str,
        fault_type: FaultType,
        target_component: str,
        activation_step: int = 1,
        duration_steps: int = 1,
    ) -> FaultInjectionSpec:
        """
        Registers an isolated fault injection into a simulation plan.
        """
        fault = self.fault_injector.create_fault_spec(
            fault_id=fault_id,
            simulation_id=simulation_id,
            fault_type=fault_type,
            target_component=target_component,
            activation_step=activation_step,
            duration_steps=duration_steps,
        )
        self.repository.save_fault(fault)

        self._emit_event(
            event_type="simulation.fault.injected",
            source="simulation.faults",
            payload={"fault_id": fault_id, "fault_type": fault.fault_type.value, "target": target_component},
        )
        return fault

    # -------------------------------------------------------------
    # 7. ALTERNATIVE EXPLORATION
    # -------------------------------------------------------------
    def explore_alternatives(
        self,
        initial_state: Dict[str, Any],
        candidate_action_sequences: List[List[Dict[str, Any]]],
        strategy: AlternativeSearchStrategy = AlternativeSearchStrategy.RELIABILITY_OPTIMIZED,
    ) -> Dict[str, Any]:
        """
        Explores candidate execution paths within bounded limits.
        """
        return self.explorer.explore_paths(
            initial_state=initial_state,
            candidate_action_sequences=candidate_action_sequences,
            strategy=strategy,
        )

    # -------------------------------------------------------------
    # 8. FIDELITY & REALITY COMPARISON
    # -------------------------------------------------------------
    def compare_with_reality(
        self,
        simulation_id: str,
        twin_id: Optional[str],
        simulated_metrics: Dict[str, float],
        observed_real_metrics: Dict[str, float],
        reality_observation_id: Optional[str] = None,
    ) -> FidelityAssessment:
        """
        Compares simulation results against live observations and produces fidelity classification.
        """
        assessment = self.fidelity_service.evaluate_fidelity(
            simulation_id=simulation_id,
            twin_id=twin_id,
            simulated_metrics=simulated_metrics,
            observed_real_metrics=observed_real_metrics,
            reality_observation_id=reality_observation_id,
        )
        self.repository.save_fidelity(assessment)

        self._emit_event(
            event_type="simulation.reality.comparison.completed",
            source="simulation.fidelity",
            payload={"record_id": assessment.record_id, "fidelity_level": assessment.fidelity_level.value},
        )
        return assessment

    # -------------------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------------------
    def _emit_event(self, event_type: str, source: str, payload: Dict[str, Any]) -> None:
        try:
            envelope = EventEnvelope(
                event_type=event_type,
                source=f"omnia.{source}",
            )
            event = Event(
                envelope=envelope,
                payload=payload,
            )
            self.event_bus.publish(event)
        except Exception as e:
            logger.debug("Failed to publish event %s: %s", event_type, e)


# Global singleton instance
simulation_service = SimulationService()
