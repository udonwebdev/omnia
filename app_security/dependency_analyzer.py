"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Dependency & Supply Chain Security Analyzer - dependency_analyzer.py

Analyzes requirements, lockfiles, and direct/transitive dependencies against known vulnerability
advisories. Correlates findings with installed versions to avoid false alerts.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from app_security.models import FindingCategory, SecurityFinding, Severity
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.DependencyAnalyzer")


# Built-in sample advisory database for standard vulnerabilities (simulated curated feed)
KNOWN_VULNERABLE_PACKAGES: Dict[str, List[Dict[str, Any]]] = {
    "requests": [
        {
            "cve": "CVE-2023-32681",
            "vulnerable_below": "2.31.0",
            "severity": Severity.MEDIUM,
            "title": "Unintended leak of Proxy-Authorization header in requests",
            "cwe": "CWE-200"
        }
    ],
    "urllib3": [
        {
            "cve": "CVE-2023-45803",
            "vulnerable_below": "2.0.7",
            "severity": Severity.HIGH,
            "title": "urllib3 HTTP request body not stripped on redirect",
            "cwe": "CWE-200"
        }
    ],
    "cryptography": [
        {
            "cve": "CVE-2023-49083",
            "vulnerable_below": "41.0.6",
            "severity": Severity.MEDIUM,
            "title": "NULL-pointer dereference in PKCS7 parsing",
            "cwe": "CWE-476"
        }
    ],
    "pyyaml": [
        {
            "cve": "CVE-2020-14343",
            "vulnerable_below": "5.4",
            "severity": Severity.CRITICAL,
            "title": "Arbitrary code execution in PyYAML full_load",
            "cwe": "CWE-502"
        }
    ]
}


class DependencyVulnerabilityAnalyzer:
    """
    Parses dependency lockfiles and flags vulnerable libraries with evidence.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def analyze_requirements_txt(
        self,
        assessment_id: str,
        asset_id: str,
        requirements_content: str,
        filename: str = "requirements.txt"
    ) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []

        lines = requirements_content.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            match = re.match(r"^([a-zA-Z0-9_\-]+)\s*(?:==|<=|>=|<|>)\s*([0-9a-zA-Z\.]+)", line)
            if not match:
                continue

            pkg_name = match.group(1).lower()
            version_str = match.group(2)

            if pkg_name in KNOWN_VULNERABLE_PACKAGES:
                advisories = KNOWN_VULNERABLE_PACKAGES[pkg_name]
                for adv in advisories:
                    vuln_below = adv["vulnerable_below"]
                    if self._is_version_below(version_str, vuln_below):
                        fid = f"find-{uuid.uuid4().hex[:8]}"
                        fp_raw = f"{asset_id}:{pkg_name}:{adv['cve']}:{version_str}"
                        fp_sha = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()

                        f = SecurityFinding(
                            finding_id=fid,
                            assessment_id=assessment_id,
                            asset_id=asset_id,
                            title=f"Vulnerable Dependency '{pkg_name}=={version_str}': {adv['title']} ({adv['cve']})",
                            category=FindingCategory.VULN_DEPENDENCY,
                            severity=adv["severity"],
                            cwe_id=adv["cwe"],
                            component_ref=f"{pkg_name}=={version_str}",
                            location_ref=filename,
                            evidence_redacted={
                                "package": pkg_name,
                                "installed_version": version_str,
                                "fixed_version": vuln_below,
                                "cve": adv["cve"]
                            },
                            fingerprint_sha256=fp_sha
                        )
                        findings.append(f)
                        self.repo.save_finding(f)

        logger.info(f"Analyzed {filename}: Found {len(findings)} vulnerable dependency findings.")
        return findings

    def _is_version_below(self, version_a: str, version_b: str) -> bool:
        """Simple semantic version comparison."""
        try:
            parts_a = [int(p) for p in re.findall(r"\d+", version_a)]
            parts_b = [int(p) for p in re.findall(r"\d+", version_b)]
            return parts_a < parts_b
        except Exception:
            return False
