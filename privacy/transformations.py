"""
privacy/transformations.py
Privacy Transformation Engine:
Implements cryptographic tokenization, masking, regex redaction, pseudonymization,
and k-anonymity aggregation using standard Python libraries (hashlib, hmac, secrets).
"""

import re
import hmac
import hashlib
import secrets
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("omnia.privacy.transformations")


class PrivacyTransformationEngine:
    DEFAULT_KEY = "omnia_default_crypto_salt_v35"

    def tokenize(self, value: str, secret_key: Optional[str] = None) -> str:
        """Deterministically tokenizes a sensitive value using HMAC-SHA256."""
        if not value:
            return ""
        key = (secret_key or self.DEFAULT_KEY).encode("utf-8")
        h = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"tok_{h[:16]}"

    def pseudonymize(self, value: str, secret_key: Optional[str] = None) -> str:
        """Generates a pseudonymous identifier using HMAC-SHA256."""
        if not value:
            return ""
        key = (secret_key or self.DEFAULT_KEY).encode("utf-8")
        h = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"psn_{h[:24]}"

    def mask(
        self,
        value: str,
        mask_char: str = "*",
        unmasked_prefix: int = 1,
        unmasked_suffix: int = 2
    ) -> str:
        """Masks a sensitive string preserving contextual format."""
        if not value:
            return ""

        # Special handling for email addresses
        if "@" in value and "." in value:
            parts = value.split("@", 1)
            local = parts[0]
            domain = parts[1]
            if len(local) <= 2:
                masked_local = local[0] + mask_char
            else:
                masked_local = local[0] + (mask_char * (len(local) - 2)) + local[-1]
            return f"{masked_local}@{domain}"

        # Special handling for SSN
        clean_digits = re.sub(r"\D", "", value)
        if len(clean_digits) == 9:
            return f"***-**-{clean_digits[-4:]}"

        # Special handling for credit card (16 digits)
        if len(clean_digits) == 16:
            return f"{mask_char * 12}{clean_digits[-4:]}"

        # Generic string masking
        vlen = len(value)
        if vlen <= unmasked_prefix + unmasked_suffix:
            return mask_char * vlen

        prefix = value[:unmasked_prefix]
        suffix = value[-unmasked_suffix:]
        middle_len = vlen - unmasked_prefix - unmasked_suffix
        return f"{prefix}{mask_char * middle_len}{suffix}"

    def redact(self, text: str, patterns: Optional[List[str]] = None) -> str:
        """Redacts sensitive patterns (SSN, credit card, emails, auth tokens) from text."""
        if not text:
            return ""

        default_patterns = [
            (r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED:SSN]"),
            (r"\b(?:\d{4}[ -]?){3}\d{4}\b", "[REDACTED:CREDIT_CARD]"),
            (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED:EMAIL]"),
            (r"(?i)(?:bearer\s+[A-Za-z0-9\-_]{16,}|api[_-]?key[:=]\s*['\"]?[A-Za-z0-9]{16,}['\"]?)", "[REDACTED:TOKEN]"),
            (r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED:PHONE]"),
        ]

        result = text
        for pat, repl in default_patterns:
            result = re.sub(pat, repl, result)

        if patterns:
            for p in patterns:
                result = re.sub(p, "[REDACTED]", result)

        return result

    def aggregate_k_anonymity(
        self,
        records: List[Dict[str, Any]],
        quasi_identifiers: List[str],
        k: int = 3
    ) -> List[Dict[str, Any]]:
        """Suppresses or generalizes records that do not meet the k-anonymity threshold."""
        if not records or not quasi_identifiers:
            return records

        # Group records by quasi-identifier signature
        groups: Dict[tuple, List[Dict[str, Any]]] = {}
        for r in records:
            sig = tuple(str(r.get(qi, "")) for qi in quasi_identifiers)
            groups.setdefault(sig, []).append(r)

        anonymized: List[Dict[str, Any]] = []
        for sig, grouped_recs in groups.items():
            if len(grouped_recs) >= k:
                anonymized.extend(grouped_recs)
            else:
                # Suppress quasi-identifiers for groups smaller than k
                for r in grouped_recs:
                    suppressed = dict(r)
                    for qi in quasi_identifiers:
                        suppressed[qi] = "*SUPPRESSED*"
                    anonymized.append(suppressed)

        return anonymized
