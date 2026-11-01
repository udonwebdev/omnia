"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Secret & Credential Exposure Detector - secret_detector.py

Detects exposed API keys, private keys, database connection strings, and tokens.
Immediately redacts all raw secrets, preserving only cryptographic hashes or masked substrings.
Never stores or authenticates with discovered credentials.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from app_security.models import FindingCategory, SecurityFinding, Severity
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.SecretDetector")


# Common high-confidence credential regexes
SECRET_PATTERNS = [
    (r"(?i)(?:api_key|apikey|secret_key|secret|password|token)\s*[:=]\s*['\"]([a-zA-Z0-9_\-]{16,})['\"]", "Generic API Key/Secret"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"-----BEGIN\s+(?:RSA|OPENSSH|PRIVATE)\s+KEY-----", "Private Key Header"),
    (r"(?i)postgres(?:ql)?://[a-zA-Z0-9_\-]+:[^@]+@[a-zA-Z0-9_\-\.]+:[0-9]+/[a-zA-Z0-9_\-]+", "PostgreSQL Connection String with Password"),
    (r"(?i)mongodb(?:\+srv)?://[a-zA-Z0-9_\-]+:[^@]+@[a-zA-Z0-9_\-\.]+", "MongoDB Connection String with Password")
]


class SecretExposureDetector:
    """
    Scans files and configuration strings for exposed secrets with mandatory redaction.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def scan_content_for_secrets(
        self,
        assessment_id: str,
        asset_id: str,
        filename: str,
        content: str
    ) -> List[SecurityFinding]:
        findings: List[SecurityFinding] = []

        lines = content.splitlines()
        for lineno, line in enumerate(lines, start=1):
            matched_spans = []
            for pattern, desc in SECRET_PATTERNS:
                matches = re.finditer(pattern, line)
                for m in matches:
                    span = m.span()
                    # Avoid overlapping matches on the same span in the same line
                    if any(s[0] <= span[0] and s[1] >= span[1] for s in matched_spans):
                        continue
                    matched_spans.append(span)

                    raw_secret = m.group(0)
                    # Mask secret: keep first 3 chars, mask rest with asterisk
                    masked = raw_secret[:4] + "*" * (min(20, max(4, len(raw_secret) - 4)))
                    secret_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()

                    fid = f"find-{uuid.uuid4().hex[:8]}"
                    fp_raw = f"{asset_id}:{filename}:{lineno}:{desc}"
                    fp_sha = hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()

                    f = SecurityFinding(
                        finding_id=fid,
                        assessment_id=assessment_id,
                        asset_id=asset_id,
                        title=f"Exposed Credential / Secret Detected: {desc}",
                        category=FindingCategory.SECRET_LEAK,
                        severity=Severity.CRITICAL,
                        cwe_id="CWE-798",
                        component_ref=filename,
                        location_ref=f"Line {lineno}",
                        evidence_redacted={
                            "secret_type": desc,
                            "masked_sample": masked,
                            "secret_sha256": secret_hash,
                            "line_number": lineno
                        },
                        fingerprint_sha256=fp_sha
                    )
                    findings.append(f)
                    self.repo.save_finding(f)

        logger.info(f"Scanned {filename} for secrets: Isolated {len(findings)} exposures.")
        return findings
