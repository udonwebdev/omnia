"""
Omnia Module 33: Signal Validation & Anti-Leakage
Validates raw learning signals, guards against temporal leakage,
sanitizes sensitive data, and performs deduplication.
"""

from __future__ import annotations

import re
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

from learning.models import LearningSignal, SignalType, SignalQualityStatus


SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[-_]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"authorization", re.IGNORECASE),
    re.compile(r"private[-_]?key", re.IGNORECASE),
]

JWT_PATTERN = re.compile(r"ey[A-Za-z0-9-_]+\.ey[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+")
API_KEY_PATTERN = re.compile(r"(?:Bearer\s+|key-|sk-)[a-zA-Z0-9_-]{16,}")


class SignalValidator:
    """
    Validates learning signals to ensure data integrity, anti-leakage compliance,
    and privacy/security constraints before dataset inclusion.
    """

    def __init__(self) -> None:
        pass

    def validate_signal(
        self,
        signal: LearningSignal,
        system_current_time: Optional[float] = None,
    ) -> Tuple[bool, SignalQualityStatus, str]:
        """
        Validates signal integrity, temporal consistency, and sanitization.
        Returns (is_valid, quality_status, rejection_reason).
        """
        now = system_current_time or time.time()

        # 1. Basic structural checks
        if not signal.signal_id or not signal.source_module:
            return False, SignalQualityStatus.REJECTED, "Missing signal_id or source_module"

        # 2. Temporal validity checks (Anti-leakage: observations cannot be from future)
        if signal.observation_time > (now + 1.0):  # 1 sec tolerance for clock drift
            return (
                False,
                SignalQualityStatus.REJECTED,
                f"Signal observation_time {signal.observation_time} is in the future compared to {now}",
            )

        if signal.event_time > (signal.observation_time + 1.0):
            return (
                False,
                SignalQualityStatus.REJECTED,
                "Signal event_time cannot be after observation_time (retrocausality leakage)",
            )

        # 3. Check for unmasked secrets / credentials in metrics or metadata
        leakage_reason = self._check_leakage(signal.metrics)
        if leakage_reason:
            return False, SignalQualityStatus.REJECTED, f"Prohibited sensitive data detected: {leakage_reason}"

        return True, SignalQualityStatus.ACCEPTED, ""

    def sanitize_payload(self, data: Any) -> Any:
        """
        Recursively redact secrets and token strings from dictionary or list payloads.
        """
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if any(p.search(k) for p in SENSITIVE_KEY_PATTERNS):
                    sanitized[k] = "[REDACTED]"
                else:
                    sanitized[k] = self.sanitize_payload(v)
            return sanitized
        elif isinstance(data, list):
            return [self.sanitize_payload(item) for item in data]
        elif isinstance(data, str):
            val = JWT_PATTERN.sub("[REDACTED_JWT]", data)
            val = API_KEY_PATTERN.sub("[REDACTED_KEY]", val)
            return val
        return data

    def compute_payload_hash(self, payload: Dict[str, Any]) -> str:
        """
        Computes deterministic SHA-256 hash of payload/metrics.
        """
        import json
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _check_leakage(self, data: Any) -> Optional[str]:
        """
        Inspects object for sensitive patterns or raw secrets.
        """
        if isinstance(data, dict):
            for k, v in data.items():
                if any(p.search(k) for p in SENSITIVE_KEY_PATTERNS):
                    return f"Key '{k}' matches sensitive credential pattern"
                reason = self._check_leakage(v)
                if reason:
                    return reason
        elif isinstance(data, list):
            for item in data:
                reason = self._check_leakage(item)
                if reason:
                    return reason
        elif isinstance(data, str):
            if JWT_PATTERN.search(data):
                return "Payload contains unredacted JWT token string"
            if API_KEY_PATTERN.search(data):
                return "Payload contains unredacted API key/bearer pattern"
        return None
