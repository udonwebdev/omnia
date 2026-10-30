"""
Omnia Module 33: Adaptive Learning & Model Lifecycle Governance
Public API exports.
"""

from learning.advisor import ParameterAdvisor
from learning.attribution import OutcomeAttributor
from learning.datasets import DatasetBuilder
from learning.drift import DriftMonitor
from learning.experiments import ExperimentEngine
from learning.gates import PromotionGatekeeper
from learning.models import (
    AttributionConfidence,
    DatasetPurpose,
    DriftRecord,
    DriftSeverity,
    DriftType,
    ExperimentConfig,
    ExperimentStatus,
    ExperimentType,
    GateResult,
    LearningDataset,
    LearningSignal,
    ModelLifecycleStatus,
    ModelVersion,
    ParameterRecommendation,
    PromotionRequest,
    RolloutRecord,
    RolloutStage,
    RolloutStatus,
    SignalQualityStatus,
    SignalType,
)
from learning.persistence import LearningRepository
from learning.registry import ModelRegistry
from learning.rollback import RollbackCoordinator
from learning.rollout import RolloutCoordinator
from learning.service import AdaptiveLearningService, adaptive_learning_service
from learning.tracking import StrategyPerformanceTracker
from learning.validation import SignalValidator

__all__ = [
    "AdaptiveLearningService",
    "adaptive_learning_service",
    "SignalValidator",
    "OutcomeAttributor",
    "DatasetBuilder",
    "StrategyPerformanceTracker",
    "ExperimentEngine",
    "ParameterAdvisor",
    "ModelRegistry",
    "PromotionGatekeeper",
    "RolloutCoordinator",
    "RollbackCoordinator",
    "DriftMonitor",
    "LearningRepository",
    "SignalType",
    "SignalQualityStatus",
    "AttributionConfidence",
    "DatasetPurpose",
    "ModelLifecycleStatus",
    "ExperimentType",
    "ExperimentStatus",
    "RolloutStage",
    "RolloutStatus",
    "DriftType",
    "DriftSeverity",
    "LearningSignal",
    "LearningDataset",
    "ModelVersion",
    "ExperimentConfig",
    "GateResult",
    "PromotionRequest",
    "RolloutRecord",
    "DriftRecord",
    "ParameterRecommendation",
]
