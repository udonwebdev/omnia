"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
"""

from .models import (
    AssetType, Criticality, EnvironmentTier, ExposureTier, FindingCategory,
    FindingStatus, PriorityLevel, Severity, ValidationOutcome,
    SecurityAsset, SecurityAuthorization, AssessmentScope, SecurityAssessment,
    SecurityFinding, VulnerabilitySource, VulnerabilityRecord, ValidationExecution,
    ValidationEvidence, AttackPath, SecurityRiskAssessment, RemediationPlan,
    RemediationExecution, SecurityFixVerification, SecurityException,
    SecurityPostureSnapshot, SecurityAuditRecord
)
from .persistence import AppSecurityRepository
from .authorization_registry import (
    AuthorizationExpiredError, AuthorizationRegistry, ScopeViolationError
)
from .asset_inventory import AssetInventory
from .application_analyzer import ApplicationSecurityAnalyzer
from .api_security_analyzer import APISecurityAnalyzer
from .dependency_analyzer import DependencyVulnerabilityAnalyzer
from .secret_detector import SecretExposureDetector
from .configuration_analyzer import ConfigurationSecurityAnalyzer
from .vulnerability_intel import VulnerabilityIntelligenceEngine
from .safe_validation import SafeValidationEngine
from .attack_path_analyzer import AttackPathAnalyzer
from .risk_prioritizer import RiskPrioritizer
from .remediation_planner import RemediationPlanner
from .regression_monitor import SecurityRegressionMonitor
from .security_audit import SecurityAuditEngine
from .service import AppSecurityOrchestrator, app_security_service

__all__ = [
    "AssetType", "Criticality", "EnvironmentTier", "ExposureTier", "FindingCategory",
    "FindingStatus", "PriorityLevel", "Severity", "ValidationOutcome",
    "SecurityAsset", "SecurityAuthorization", "AssessmentScope", "SecurityAssessment",
    "SecurityFinding", "VulnerabilitySource", "VulnerabilityRecord", "ValidationExecution",
    "ValidationEvidence", "AttackPath", "SecurityRiskAssessment", "RemediationPlan",
    "RemediationExecution", "SecurityFixVerification", "SecurityException",
    "SecurityPostureSnapshot", "SecurityAuditRecord",
    "AppSecurityRepository", "AuthorizationExpiredError", "AuthorizationRegistry",
    "ScopeViolationError", "AssetInventory", "ApplicationSecurityAnalyzer",
    "APISecurityAnalyzer", "DependencyVulnerabilityAnalyzer", "SecretExposureDetector",
    "ConfigurationSecurityAnalyzer", "VulnerabilityIntelligenceEngine",
    "SafeValidationEngine", "AttackPathAnalyzer", "RiskPrioritizer",
    "RemediationPlanner", "SecurityRegressionMonitor", "SecurityAuditEngine",
    "AppSecurityOrchestrator", "app_security_service"
]
