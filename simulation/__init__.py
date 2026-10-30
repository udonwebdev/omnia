"""
Omnia Module 34: Autonomous Simulation, Digital Twin & Scenario Testing Engine
Public API exports.
"""

from simulation.actions import ActionSimulator
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
    SimulationStatus,
    StateFidelity,
    StateSnapshot,
    TwinStatus,
    TwinSyncMode,
)
from simulation.persistence import SimulationRepository
from simulation.service import SimulationService, simulation_service
from simulation.snapshots import SnapshotManager
from simulation.twins import DigitalTwinManager

__all__ = [
    "SimulationService",
    "simulation_service",
    "SimulationRepository",
    "SimulationEngine",
    "DigitalTwinManager",
    "SnapshotManager",
    "ScenarioCompiler",
    "ActionSimulator",
    "FaultInjector",
    "AlternativePathExplorer",
    "FidelityService",
    "EnvironmentType",
    "EnvironmentClassification",
    "TwinStatus",
    "TwinSyncMode",
    "StateFidelity",
    "ScenarioType",
    "SimulationStatus",
    "FaultType",
    "AlternativeSearchStrategy",
    "SimulationEnvironment",
    "DigitalTwin",
    "StateSnapshot",
    "ScenarioDefinition",
    "SimulationExecutionRecord",
    "FaultInjectionSpec",
    "FidelityAssessment",
]
