"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Domain Models, Enums, and Value Objects - models.py
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class AssetType(str, enum.Enum):
    APPLICATION = "APPLICATION"
    SERVICE = "SERVICE"
    API = "API"
    REPOSITORY = "REPOSITORY"
    CONTAINER = "CONTAINER"
    INFRA_CONFIG = "INFRA_CONFIG"


class EnvironmentTier(str, enum.Enum):
    DEV = "DEV"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"
    LAB = "LAB"


class ExposureTier(str, enum.Enum):
    INTERNAL = "INTERNAL"
    RESTRICTED = "RESTRICTED"
    PUBLIC = "PUBLIC"


class Criticality(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    MISSION_CRITICAL = "MISSION_CRITICAL"


class FindingCategory(str, enum.Enum):
    INJECTION = "INJECTION"
    AUTH_BYPASS = "AUTH_BYPASS"
    SECRET_LEAK = "SECRET_LEAK"
    VULN_DEPENDENCY = "VULN_DEPENDENCY"
    MISCONFIG = "MISCONFIG"
    XSS = "XSS"
    CSRF = "CSRF"
    SSRF = "SSRF"
    CRYPTO = "CRYPTO"


class Severity(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, enum.Enum):
    NEW = "NEW"
    VALIDATED = "VALIDATED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    MITIGATED = "MITIGATED"
    RESOLVED = "RESOLVED"


class ValidationOutcome(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    LIKELY = "LIKELY"
    UNCONFIRMED = "UNCONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    NOT_SAFELY_TESTABLE = "NOT_SAFELY_TESTABLE"


class PriorityLevel(str, enum.Enum):
    P0_IMMEDIATE = "P0_IMMEDIATE"
    P1_URGENT = "P1_URGENT"
    P2_STANDARD = "P2_STANDARD"
    P3_LOW = "P3_LOW"


# ----------------------------------------------------------------------
# Dataclasses
# ----------------------------------------------------------------------

@dataclass
class SecurityAsset:
    asset_id: str
    name: str
    asset_type: AssetType
    owner: str
    environment: EnvironmentTier = EnvironmentTier.STAGING
    discovery_source: str = "MANUAL"
    authorization_id: Optional[str] = None
    technology_stack: List[str] = field(default_factory=list)
    exposure_tier: ExposureTier = ExposureTier.INTERNAL
    criticality: Criticality = Criticality.MEDIUM
    security_posture_score: float = 100.0
    last_assessed_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityAuthorization:
    authorization_id: str
    name: str
    operator: str
    owner_approval_ref: str
    assessment_purpose: str
    environment_tier: EnvironmentTier
    permitted_techniques: List[str] = field(default_factory=list)
    allow_destructive: bool = False
    rate_limit_rps: int = 10
    valid_from: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid_until: str = ""
    is_revoked: bool = False
    revoked_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AssessmentScope:
    scope_id: str
    authorization_id: str
    asset_id: str
    permitted_endpoints: List[str] = field(default_factory=list)
    excluded_endpoints: List[str] = field(default_factory=list)
    permitted_components: List[str] = field(default_factory=list)
    excluded_components: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityAssessment:
    assessment_id: str
    authorization_id: str
    asset_id: str
    assessment_type: str  # STATIC_ANALYSIS, API_AUDIT, DEPENDENCY_SCA, SECRET_DETECTION, CONFIG_AUDIT, FULL_ASSESSMENT
    status: str = "INITIALIZED"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    findings_count: int = 0
    critical_findings_count: int = 0
    high_findings_count: int = 0
    raw_telemetry: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityFinding:
    finding_id: str
    assessment_id: str
    asset_id: str
    title: str
    category: FindingCategory
    severity: Severity
    cwe_id: Optional[str]
    component_ref: str
    location_ref: Optional[str]
    evidence_redacted: Dict[str, Any] = field(default_factory=dict)
    fingerprint_sha256: str = ""
    status: FindingStatus = FindingStatus.NEW
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class VulnerabilitySource:
    source_id: str
    source_name: str
    feed_url: Optional[str] = None
    confidence_weight: float = 1.0
    last_synced_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class VulnerabilityRecord:
    vulnerability_id: str
    source_id: str
    title: str
    description: Optional[str]
    severity: Severity
    cvss_score: Optional[float]
    cwe_id: Optional[str]
    affected_package: str
    affected_version_ranges: List[str] = field(default_factory=list)
    fixed_versions: List[str] = field(default_factory=list)
    is_known_exploited: bool = False
    published_at: Optional[str] = None
    modified_at: Optional[str] = None
    provenance_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationExecution:
    validation_id: str
    finding_id: str
    method: str
    outcome: ValidationOutcome
    is_destructive: bool = False
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ValidationEvidence:
    evidence_id: str
    validation_id: str
    evidence_type: str
    redacted_content: str
    checksum_sha256: str
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AttackPath:
    path_id: str
    assessment_id: str
    entry_asset_id: str
    target_asset_id: str
    path_hops: List[Dict[str, Any]] = field(default_factory=list)
    aggregate_risk_score: float = 0.0
    is_validated: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityRiskAssessment:
    risk_assessment_id: str
    finding_id: str
    asset_id: str
    technical_severity: Severity
    exploitability_score: float
    asset_criticality_weight: float
    exposure_multiplier: float
    contextual_risk_score: float
    priority_level: PriorityLevel
    urgency_recommendation: Optional[str]
    calculated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RemediationPlan:
    plan_id: str
    finding_id: str
    recommended_action: str
    action_details: Dict[str, Any] = field(default_factory=dict)
    breaking_change_risk: str = "LOW"
    estimated_complexity: str = "SIMPLE"
    patch_diff: Optional[str] = None
    status: str = "PROPOSED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RemediationExecution:
    execution_id: str
    plan_id: str
    applied_by: str
    patch_commit_ref: Optional[str] = None
    applied_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityFixVerification:
    verification_id: str
    finding_id: str
    plan_id: str
    module45_mission_id: Optional[str]
    original_probe_passed: bool
    regressions_found: int = 0
    is_fully_resolved: bool = False
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityException:
    exception_id: str
    finding_id: str
    approved_by: str
    justification: str
    compensating_controls: Optional[str] = None
    valid_until: str = ""
    status: str = "ACTIVE"
    granted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityPostureSnapshot:
    snapshot_id: str
    asset_id: str
    posture_score: float
    open_findings_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    active_exceptions_count: int = 0
    snapshot_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SecurityAuditRecord:
    audit_id: str
    authorization_id: Optional[str]
    asset_id: Optional[str]
    action_type: str
    actor: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
