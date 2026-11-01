"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
"""
from .models import (
    RequirementType, VerificationStatus, TestCategory, DefectSeverity,
    DefectCategory, FlakyClassification, QualityTier, VerificationProject,
    VerificationRequirement, AcceptanceCriterion, TestStrategy, GeneratedTestCase,
    VerificationMission, VerificationExecution, VerificationResult, TestEvidence,
    CoverageRecord, DefectRecord, RegressionRecord, FlakyTestRecord,
    MutationTestResult, PerformanceAssessment, QualityAssessment, RepairVerification
)
from .persistence import QAVerificationRepository
from .requirement_analyzer import RequirementAnalyzer
from .test_intelligence import TestIntelligenceEngine
from .test_generator import TestGenerator
from .test_data_manager import TestDataManager
from .api_verifier import APIContractVerifier
from .frontend_verifier import FrontendVerifier
from .database_verifier import DatabaseIntegrityVerifier
from .performance_verifier import PerformanceVerifier
from .property_fuzz import PropertyFuzzEngine
from .defect_intelligence import DefectIntelligenceEngine
from .flaky_detector import FlakyTestDetector
from .mutation_engine import MutationEngine
from .quality_score import QualityScoreEngine
from .repair_verifier import RepairVerifier
from .qa_reporter import QAReporter
from .service import QAVerificationOrchestrator, qa_verification_service

__all__ = [
    "RequirementType", "VerificationStatus", "TestCategory", "DefectSeverity",
    "DefectCategory", "FlakyClassification", "QualityTier", "VerificationProject",
    "VerificationRequirement", "AcceptanceCriterion", "TestStrategy", "GeneratedTestCase",
    "VerificationMission", "VerificationExecution", "VerificationResult", "TestEvidence",
    "CoverageRecord", "DefectRecord", "RegressionRecord", "FlakyTestRecord",
    "MutationTestResult", "PerformanceAssessment", "QualityAssessment", "RepairVerification",
    "QAVerificationRepository", "RequirementAnalyzer", "TestIntelligenceEngine",
    "TestGenerator", "TestDataManager", "APIContractVerifier", "FrontendVerifier",
    "DatabaseIntegrityVerifier", "PerformanceVerifier", "PropertyFuzzEngine",
    "DefectIntelligenceEngine", "FlakyTestDetector", "MutationEngine",
    "QualityScoreEngine", "RepairVerifier", "QAReporter",
    "QAVerificationOrchestrator", "qa_verification_service"
]
