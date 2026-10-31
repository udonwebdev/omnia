"""
OMNIA Module 35: Autonomous Research, Scientific Discovery & Hypothesis Testing Engine
Package exports.
"""

from research.models import (
    ResearchState,
    HypothesisType,
    HypothesisState,
    MethodologyCategory,
    ExperimentType,
    ConclusionState,
    KnowledgeGapRecord,
    HypothesisRecord,
    ExperimentDefinition,
    ExperimentExecutionResult,
    HypothesisTestResult,
    ResearchConclusion,
    ReproducibilityManifest,
    ResearchRequest,
)
from research.persistence import ResearchRepository
from research.planner import ResearchPlanner
from research.hypotheses import HypothesisEngine
from research.experiments import ExperimentDesigner
from research.execution import InvestigationExecutor
from research.testing import HypothesisTestingEngine
from research.reproducibility import ReproducibilityManager
from research.service import ResearchOrchestrator, research_service

__all__ = [
    "ResearchState",
    "HypothesisType",
    "HypothesisState",
    "MethodologyCategory",
    "ExperimentType",
    "ConclusionState",
    "KnowledgeGapRecord",
    "HypothesisRecord",
    "ExperimentDefinition",
    "ExperimentExecutionResult",
    "HypothesisTestResult",
    "ResearchConclusion",
    "ReproducibilityManifest",
    "ResearchRequest",
    "ResearchRepository",
    "ResearchPlanner",
    "HypothesisEngine",
    "ExperimentDesigner",
    "InvestigationExecutor",
    "HypothesisTestingEngine",
    "ReproducibilityManager",
    "ResearchOrchestrator",
    "research_service",
]
