"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Central Orchestrator Facade - service.py
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app_security.models import (
    AssetType, Criticality, EnvironmentTier, ExposureTier, FindingCategory,
    FindingStatus, PriorityLevel, SecurityAsset, SecurityAssessment,
    SecurityAuditRecord, SecurityAuthorization, SecurityFinding, SecurityFixVerification,
    SecurityRiskAssessment, Severity, ValidationExecution, ValidationOutcome
)
from app_security.persistence import AppSecurityRepository
from app_security.authorization_registry import (
    AuthorizationExpiredError, AuthorizationRegistry, ScopeViolationError
)
from app_security.asset_inventory import AssetInventory
from app_security.application_analyzer import ApplicationSecurityAnalyzer
from app_security.api_security_analyzer import APISecurityAnalyzer
from app_security.dependency_analyzer import DependencyVulnerabilityAnalyzer
from app_security.secret_detector import SecretExposureDetector
from app_security.configuration_analyzer import ConfigurationSecurityAnalyzer
from app_security.vulnerability_intel import VulnerabilityIntelligenceEngine
from app_security.safe_validation import SafeValidationEngine
from app_security.attack_path_analyzer import AttackPathAnalyzer
from app_security.risk_prioritizer import RiskPrioritizer
from app_security.remediation_planner import RemediationPlanner
from app_security.regression_monitor import SecurityRegressionMonitor
from app_security.security_audit import SecurityAuditEngine

try:
    from events import event_fabric, EventFabric
except Exception:
    event_fabric = None
    EventFabric = Any

logger = logging.getLogger("Omnia.AppSecurity.Service")


class AppSecurityOrchestrator:
    """
    Unified entry point coordinating security authorization, scanning, validation,
    attack path modeling, risk evaluation, and verified remediation.
    """

    def __init__(self, db_path: str = "omnia.db", event_fabric_instance: Optional[EventFabric] = None):
        self.repo = AppSecurityRepository(db_path=db_path)
        self.event_fabric = event_fabric_instance

        self.auth_registry = AuthorizationRegistry(self.repo)
        self.inventory = AssetInventory(self.repo)
        self.app_analyzer = ApplicationSecurityAnalyzer(self.repo)
        self.api_analyzer = APISecurityAnalyzer(self.repo)
        self.dep_analyzer = DependencyVulnerabilityAnalyzer(self.repo)
        self.secret_detector = SecretExposureDetector(self.repo)
        self.config_analyzer = ConfigurationSecurityAnalyzer(self.repo)
        self.vulnerability_intel = VulnerabilityIntelligenceEngine(self.repo)
        self.safe_validation = SafeValidationEngine(self.repo)
        self.attack_path_analyzer = AttackPathAnalyzer(self.repo)
        self.risk_prioritizer = RiskPrioritizer(self.repo)
        self.remediation_planner = RemediationPlanner(self.repo)
        self.regression_monitor = SecurityRegressionMonitor(self.repo)
        self.audit_engine = SecurityAuditEngine(self.repo)

    def register_authorized_asset(
        self,
        name: str,
        asset_type: AssetType,
        owner: str,
        environment: EnvironmentTier = EnvironmentTier.STAGING,
        exposure_tier: ExposureTier = ExposureTier.INTERNAL,
        criticality: Criticality = Criticality.MEDIUM,
        technology_stack: Optional[List[str]] = None
    ) -> SecurityAsset:
        asset = self.inventory.register_asset(
            name=name,
            asset_type=asset_type,
            owner=owner,
            environment=environment,
            exposure_tier=exposure_tier,
            criticality=criticality,
            technology_stack=technology_stack
        )
        self._emit_event("security.asset_registered", {"asset_id": asset.asset_id, "name": name})
        return asset

    def create_assessment_authorization(
        self,
        name: str,
        operator: str,
        owner_approval_ref: str,
        assessment_purpose: str,
        environment_tier: EnvironmentTier,
        valid_until: str,
        permitted_techniques: Optional[List[str]] = None,
        allow_destructive: bool = False
    ) -> SecurityAuthorization:
        auth = self.auth_registry.grant_authorization(
            name=name,
            operator=operator,
            owner_approval_ref=owner_approval_ref,
            assessment_purpose=assessment_purpose,
            environment_tier=environment_tier,
            valid_until=valid_until,
            permitted_techniques=permitted_techniques,
            allow_destructive=allow_destructive
        )
        self._emit_event("security.authorization_granted", {
            "authorization_id": auth.authorization_id,
            "operator": operator
        })
        return auth

    def execute_security_assessment(
        self,
        authorization_id: str,
        asset_id: str,
        assessment_type: str = "FULL_ASSESSMENT",
        source_code_files: Optional[Dict[str, str]] = None,
        api_specs: Optional[List[Dict[str, Any]]] = None,
        requirements_txt: Optional[str] = None
    ) -> SecurityAssessment:
        # 1. Enforce Scope and Authorization pre-check
        self.auth_registry.validate_target_access(
            authorization_id=authorization_id,
            asset_id=asset_id,
            target_endpoint_or_file="*",
            requested_technique=assessment_type
        )

        aid = f"asm-{uuid.uuid4().hex[:8]}"
        assessment = SecurityAssessment(
            assessment_id=aid,
            authorization_id=authorization_id,
            asset_id=asset_id,
            assessment_type=assessment_type,
            status="RUNNING"
        )
        self.repo.save_assessment(assessment)
        self._emit_event("security.assessment_started", {"assessment_id": aid, "asset_id": asset_id})

        all_findings: List[SecurityFinding] = []

        # 2. Source Code & Secret Scanning
        if source_code_files:
            for fname, content in source_code_files.items():
                # Static AST Analysis
                ast_findings = self.app_analyzer.analyze_source_code(aid, asset_id, fname, content)
                all_findings.extend(ast_findings)
                # Secret Exposure Detection
                secret_findings = self.secret_detector.scan_content_for_secrets(aid, asset_id, fname, content)
                all_findings.extend(secret_findings)

        # 3. API Contract Auditing
        if api_specs:
            for spec in api_specs:
                path = spec.get("path", "/api")
                method = spec.get("method", "GET")
                api_findings = self.api_analyzer.audit_api_endpoint_spec(aid, asset_id, path, method, spec)
                all_findings.extend(api_findings)

        # 4. Dependency Vulnerability Analysis
        if requirements_txt:
            dep_findings = self.dep_analyzer.analyze_requirements_txt(aid, asset_id, requirements_txt)
            all_findings.extend(dep_findings)

        # 5. Finalize Assessment Record
        critical_count = sum(1 for f in all_findings if f.severity == Severity.CRITICAL)
        high_count = sum(1 for f in all_findings if f.severity == Severity.HIGH)

        assessment.status = "COMPLETED"
        assessment.completed_at = datetime.now(timezone.utc).isoformat()
        assessment.findings_count = len(all_findings)
        assessment.critical_findings_count = critical_count
        assessment.high_findings_count = high_count
        self.repo.save_assessment(assessment)

        # 6. Update Asset Posture
        deduction = (critical_count * 25.0) + (high_count * 10.0)
        new_posture = max(0.0, 100.0 - deduction)
        self.inventory.update_asset_posture(asset_id, new_posture)

        self._emit_event("security.assessment_completed", {
            "assessment_id": aid,
            "asset_id": asset_id,
            "findings_count": len(all_findings),
            "posture_score": new_posture
        })
        return assessment

    def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_fabric:
            try:
                self.event_fabric.publish(
                    event_type=event_type,
                    payload=payload,
                    source="app_security_service"
                )
            except Exception:
                pass


# Global singleton instance
app_security_service = AppSecurityOrchestrator()
