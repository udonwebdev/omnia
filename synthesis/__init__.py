"""
OMNIA Module 36: Autonomous Knowledge Synthesis & Intelligence Briefing Engine
"""

from synthesis.models import (
    IntelligenceProductRecord,
    ProductType,
    AudienceLevel,
    ProductLifecycleState,
    SynthesizedClaim,
    EpistemicClaimType,
    ContradictionRecord,
    ContradictionStatus,
    DevelopmentRecord,
    ChangeType,
    SignificanceAssessment,
    BriefingQualityScore,
    BriefingVersion,
    DeliveryRecord,
    DeliveryStatus,
)
from synthesis.persistence import SynthesisRepository
from synthesis.registry import IntelligenceProductRegistry
from synthesis.analyzer import DevelopmentDetector, ContradictionAnalyzer, SignificanceAssessmentService
from synthesis.engine import KnowledgeSynthesisEngine
from synthesis.generator import BriefingGenerator, BriefingQualityEvaluator
from synthesis.delivery import BriefingDeliveryCoordinator
from synthesis.service import IntelligenceOrchestrator, intelligence_service

__all__ = [
    "IntelligenceProductRecord",
    "ProductType",
    "AudienceLevel",
    "ProductLifecycleState",
    "SynthesizedClaim",
    "EpistemicClaimType",
    "ContradictionRecord",
    "ContradictionStatus",
    "DevelopmentRecord",
    "ChangeType",
    "SignificanceAssessment",
    "BriefingQualityScore",
    "BriefingVersion",
    "DeliveryRecord",
    "DeliveryStatus",
    "SynthesisRepository",
    "IntelligenceProductRegistry",
    "DevelopmentDetector",
    "ContradictionAnalyzer",
    "SignificanceAssessmentService",
    "KnowledgeSynthesisEngine",
    "BriefingGenerator",
    "BriefingQualityEvaluator",
    "BriefingDeliveryCoordinator",
    "IntelligenceOrchestrator",
    "intelligence_service",
]
