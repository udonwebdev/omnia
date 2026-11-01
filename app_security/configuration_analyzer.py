"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Infrastructure & Configuration Security Analyzer - configuration_analyzer.py

Assesses Dockerfiles, cloud infrastructure configurations, security policies, and environment definitions
for misconfigurations, unconfined capabilities, and overly permissive exposure.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Dict, List, Optional

from app_security.models import FindingCategory, SecurityFinding, Severity
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.ConfigurationAnalyzer")


class ConfigurationSecurityAnalyzer:
    """
    Evaluates infrastructure blueprints, Dockerfiles, and runtime configurations.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def audit_dockerfile(
        self,
        assessment_id: str,
        asset_id: str,
        dockerfile_content: str,
        filename: str = "Dockerfile"
    ) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []

        lines = dockerfile_content.splitlines()
        has_user_instruction = False
        uses_latest_tag = False

        for lineno, line in enumerate(lines, start=1):
            line_clean = line.strip()

            if line_clean.upper().startswith("USER "):
                has_user_instruction = True

            if line_clean.upper().startswith("FROM "):
                if ":latest" in line_clean or ":" not in line_clean:
                    uses_latest_tag = True

            # Exposed dangerous ports (e.g. 22 SSH in app container)
            if line_clean.upper().startswith("EXPOSE "):
                if "22" in line_clean:
                    f = self._create_finding(
                        assessment_id=assessment_id,
                        asset_id=asset_id,
                        title="Container Exposes SSH Port 22",
                        category=FindingCategory.MISCONFIG,
                        severity=Severity.HIGH,
                        cwe_id="CWE-284",
                        component_ref=filename,
                        location_ref=f"Line {lineno}",
                        evidence={"instruction": line_clean, "line": lineno}
                    )
                    findings.append(f)

        if not has_user_instruction:
            f = self._create_finding(
                assessment_id=assessment_id,
                asset_id=asset_id,
                title="Container Image Runs as Default Root User (Missing USER directive)",
                category=FindingCategory.MISCONFIG,
                severity=Severity.MEDIUM,
                cwe_id="CWE-250",
                component_ref=filename,
                location_ref="File End",
                evidence={"has_user": False}
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
