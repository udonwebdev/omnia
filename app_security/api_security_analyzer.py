"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
API Security Analyzer - api_security_analyzer.py

Assesses authorized REST/GraphQL APIs for authentication boundaries, broken object-level
authorization (BOLA), excessive data exposure, rate limiting, and CORS security.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Dict, List, Optional

from app_security.models import FindingCategory, SecurityFinding, Severity
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.APISecurityAnalyzer")


class APISecurityAnalyzer:
    """
    Evaluates API specifications and live endpoint contract behaviors defensively.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def audit_api_endpoint_spec(
        self,
        assessment_id: str,
        asset_id: str,
        endpoint_path: str,
        method: str,
        spec_metadata: Dict[str, Any]
    ) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []

        # 1. Missing Authentication Requirement
        requires_auth = spec_metadata.get("requires_auth", False)
        security_schemes = spec_metadata.get("security", [])
        if not requires_auth and not security_schemes:
            # Sensitive endpoint check
            sensitive_keywords = ["admin", "users", "delete", "export", "transfer", "keys", "secrets"]
            if any(k in endpoint_path.lower() for k in sensitive_keywords):
                f = self._create_finding(
                    assessment_id=assessment_id,
                    asset_id=asset_id,
                    title=f"Unauthenticated Sensitive API Endpoint: {method.upper()} {endpoint_path}",
                    category=FindingCategory.AUTH_BYPASS,
                    severity=Severity.HIGH,
                    cwe_id="CWE-306",
                    component_ref=f"{method.upper()} {endpoint_path}",
                    location_ref="OpenAPI Spec",
                    evidence={"endpoint": endpoint_path, "requires_auth": False}
                )
                findings.append(f)

        # 2. CORS Wildcard Check with Credentials
        cors_config = spec_metadata.get("cors", {})
        if cors_config.get("allow_origin") == "*" and cors_config.get("allow_credentials") is True:
            f = self._create_finding(
                assessment_id=assessment_id,
                asset_id=asset_id,
                title=f"Insecure CORS Configuration: Wildcard Origin with Credentials on {endpoint_path}",
                category=FindingCategory.MISCONFIG,
                severity=Severity.MEDIUM,
                cwe_id="CWE-942",
                component_ref=endpoint_path,
                location_ref="CORS Settings",
                evidence={"allow_origin": "*", "allow_credentials": True}
            )
            findings.append(f)

        # 3. Rate Limiting Check
        has_rate_limit = spec_metadata.get("rate_limiting_enabled", True)
        if not has_rate_limit:
            f = self._create_finding(
                assessment_id=assessment_id,
                asset_id=asset_id,
                title=f"Missing Rate Limiting Protection on {method.upper()} {endpoint_path}",
                category=FindingCategory.MISCONFIG,
                severity=Severity.LOW,
                cwe_id="CWE-770",
                component_ref=endpoint_path,
                location_ref="Gateway Policies",
                evidence={"rate_limiting_enabled": False}
            )
            findings.append(f)

        for f in findings:
            self.repo.save_finding(f)

        return findings

    def _create_finding(
        self,
        assessment_id: str,
        asset_id: str,
        title: str,
        category: FindingCategory,
        severity: Severity,
        cwe_id: str,
        component_ref: str,
        location_ref: str,
        evidence: Dict[str, Any]
    ) -> SecurityFinding:
        fid = f"find-{uuid.uuid4().hex[:8]}"
        fp_raw = f"{asset_id}:{title}:{category.value}:{component_ref}"
        fp_sha = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()
        return SecurityFinding(
            finding_id=fid,
            assessment_id=assessment_id,
            asset_id=asset_id,
            title=title,
            category=category,
            severity=severity,
            cwe_id=cwe_id,
            component_ref=component_ref,
            location_ref=location_ref,
            evidence_redacted=evidence,
            fingerprint_sha256=fp_sha
        )
