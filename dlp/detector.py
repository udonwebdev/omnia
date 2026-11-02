"""
dlp/detector.py
Sensitive Information Detector for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import re
import uuid
import time
from typing import List, Dict, Any, Tuple, Optional

from dlp.models import (
    SensitiveFinding, DataCategory, SensitivityTier
)


def luhn_checksum(card_number_str: str) -> bool:
    """Validates credit card numbers using the Luhn algorithm (mod 10 check)."""
    digits = [int(c) for c in card_number_str if c.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    
    checksum = 0
    reverse_digits = digits[::-1]
    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = digit * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += digit
    return checksum % 10 == 0


class SensitiveContentDetector:
    """
    Multi-layer sensitive information detection engine combining regex,
    checksum algorithms (Luhn), structured pattern matching, and context analysis.
    """

    PATTERNS = {
        # PII
        "SSN": {
            "regex": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            "category": DataCategory.PII,
            "tier": SensitivityTier.HIGHLY_RESTRICTED,
            "confidence": 0.95,
        },
        "EMAIL": {
            "regex": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
            "category": DataCategory.PII,
            "tier": SensitivityTier.CONFIDENTIAL,
            "confidence": 0.85,
        },
        "PHONE": {
            "regex": re.compile(r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b"),
            "category": DataCategory.PII,
            "tier": SensitivityTier.CONFIDENTIAL,
            "confidence": 0.80,
        },
        # Credentials & API Keys
        "AWS_KEY": {
            "regex": re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
            "category": DataCategory.CREDENTIALS,
            "tier": SensitivityTier.HIGHLY_RESTRICTED,
            "confidence": 0.98,
        },
        "GITHUB_TOKEN": {
            "regex": re.compile(r"\b(gh[pousr]_[0-9a-zA-Z]{36})\b"),
            "category": DataCategory.CREDENTIALS,
            "tier": SensitivityTier.HIGHLY_RESTRICTED,
            "confidence": 0.98,
        },
        "SLACK_TOKEN": {
            "regex": re.compile(r"\b(xox[baprs]-[0-9a-zA-Z-]{10,48})\b"),
            "category": DataCategory.CREDENTIALS,
            "tier": SensitivityTier.HIGHLY_RESTRICTED,
            "confidence": 0.95,
        },
        "PRIVATE_KEY": {
            "regex": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
            "category": DataCategory.CREDENTIALS,
            "tier": SensitivityTier.HIGHLY_RESTRICTED,
            "confidence": 1.0,
        },
        "GENERIC_API_KEY": {
            "regex": re.compile(r"""(?i)(?:api[_-]?key|secret[_-]?token|bearer\s+)["':=\s]+([a-zA-Z0-9_\-]{20,64})"""),
            "category": DataCategory.CREDENTIALS,
            "tier": SensitivityTier.HIGHLY_RESTRICTED,
            "confidence": 0.90,
        },
        # Intellectual Property & Confidentiality
        "IP_CONFIDENTIAL_MARKER": {
            "regex": re.compile(r"(?i)\b(?:TOP SECRET|STRICTLY CONFIDENTIAL|PROPRIETARY AND CONFIDENTIAL|TRADE SECRET|DO NOT DISTRIBUTE)\b"),
            "category": DataCategory.INTELLECTUAL_PROPERTY,
            "tier": SensitivityTier.RESTRICTED,
            "confidence": 0.90,
        },
        # Source Code & Infrastructure Secrets
        "SOURCE_CODE": {
            "regex": re.compile(r"(?m)(?:^(?:import\s+\w+|from\s+\w+\s+import|def\s+\w+\s*\(|class\s+\w+[\s:(]|public\s+class\s+\w+|#include\s+<[\w.]+>))"),
            "category": DataCategory.SOURCE_CODE,
            "tier": SensitivityTier.INTERNAL,
            "confidence": 0.85,
        },
        # Healthcare / Medical
        "HEALTHCARE_MRN": {
            "regex": re.compile(r"(?i)\b(?:MRN|Medical Record Number|Patient ID)[:\s]+[A-Z0-9]{6,12}\b"),
            "category": DataCategory.HEALTHCARE,
            "tier": SensitivityTier.HIGHLY_RESTRICTED,
            "confidence": 0.90,
        },
    }

    # Credit card regex: matches formatted (with hyphens or spaces) or contiguous digits
    CREDIT_CARD_REGEX = re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b|\b\d{13,19}\b")

    def __init__(self):
        pass

    def inspect_content(self, text: str, source_ref: str = "payload") -> List[SensitiveFinding]:
        """
        Scans given text for all known sensitive patterns, validating algorithmic checksums
        such as Luhn for financial payment card data.
        """
        if not text:
            return []

        findings: List[SensitiveFinding] = []

        # 1. Regex Pattern Matching
        for pattern_name, spec in self.PATTERNS.items():
            matches = spec["regex"].findall(text)
            if matches:
                count = len(matches)
                finding = SensitiveFinding(
                    finding_id=f"find_{uuid.uuid4().hex[:12]}",
                    source_ref=source_ref,
                    data_category=spec["category"].value,
                    sensitivity_tier=spec["tier"].value,
                    detection_method=f"REGEX_{pattern_name}",
                    confidence=spec["confidence"],
                    matched_tokens_count=count,
                    detected_at=time.time(),
                    metadata={
                        "pattern_name": pattern_name,
                        "sample_match_masked": self._mask_sample(matches[0] if isinstance(matches[0], str) else matches[0][0]),
                    }
                )
                findings.append(finding)

        # 2. Financial Credit Card Detection with Luhn validation
        cc_candidates = self.CREDIT_CARD_REGEX.findall(text)
        valid_cc_matches = []
        for candidate in cc_candidates:
            clean_num = re.sub(r"\D", "", candidate)
            if 13 <= len(clean_num) <= 19 and luhn_checksum(clean_num):
                valid_cc_matches.append(clean_num)

        if valid_cc_matches:
            finding = SensitiveFinding(
                finding_id=f"find_{uuid.uuid4().hex[:12]}",
                source_ref=source_ref,
                data_category=DataCategory.FINANCIAL.value,
                sensitivity_tier=SensitivityTier.HIGHLY_RESTRICTED.value,
                detection_method="LUHN_VALIDATED_CREDIT_CARD",
                confidence=0.99,
                matched_tokens_count=len(valid_cc_matches),
                detected_at=time.time(),
                metadata={
                    "card_count": len(valid_cc_matches),
                    "sample_masked": self._mask_credit_card(valid_cc_matches[0]),
                }
            )
            findings.append(finding)

        return findings

    def redact_content(self, text: str) -> str:
        """
        Redacts sensitive tokens in text, replacing them with type-specific placeholders.
        """
        if not text:
            return ""

        redacted = text

        # Redact Credit Cards
        def _replace_cc(m):
            clean = re.sub(r"\D", "", m.group(0))
            if 13 <= len(clean) <= 19 and luhn_checksum(clean):
                return f"[REDACTED_FINANCIAL_CARD_****{clean[-4:]}]"
            return m.group(0)

        redacted = self.CREDIT_CARD_REGEX.sub(_replace_cc, redacted)

        # Redact SSN
        redacted = self.PATTERNS["SSN"]["regex"].sub("[REDACTED_SSN]", redacted)

        # Redact AWS Key
        redacted = self.PATTERNS["AWS_KEY"]["regex"].sub("[REDACTED_AWS_KEY]", redacted)

        # Redact GitHub Token
        redacted = self.PATTERNS["GITHUB_TOKEN"]["regex"].sub("[REDACTED_GITHUB_TOKEN]", redacted)

        # Redact Slack Token
        redacted = self.PATTERNS["SLACK_TOKEN"]["regex"].sub("[REDACTED_SLACK_TOKEN]", redacted)

        # Redact Private Key blocks
        redacted = re.sub(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
            "[REDACTED_PRIVATE_KEY_BLOCK]",
            redacted
        )

        # Redact Generic API keys
        redacted = self.PATTERNS["GENERIC_API_KEY"]["regex"].sub(r"\g<0>".split(":")[0] + ": [REDACTED_API_KEY]", redacted)

        return redacted

    def _mask_sample(self, token: str) -> str:
        if not token:
            return ""
        if len(token) <= 4:
            return "****"
        return token[:2] + "*" * (len(token) - 4) + token[-2:]

    def _mask_credit_card(self, num: str) -> str:
        if len(num) >= 4:
            return f"****-****-****-{num[-4:]}"
        return "****"
