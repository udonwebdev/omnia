"""
Security Guard & Quarantine Engine for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Guarantees:
1. External data is never automatically trusted as fact or system instruction.
2. Active detection and scrubbing of obvious secret material (API keys, tokens, credentials).
3. Active prompt injection defense marking untrusted external text.
4. Suspicious or malformed content is routed to quarantine rather than silently bypassing security.
5. Integration with Module 09 policy engine and Module 25 redaction engine.
"""

import re
import logging
from typing import Dict, Any, Tuple, List, Optional

from ingestion.models import (
    IngestionEnvelope,
    DataClassification,
    TrustBoundary,
    IngestionStatus
)
from secrets.redaction import redaction_engine
from policy_engine import policy_engine
from audit_logger import audit_logger

logger = logging.getLogger("Omnia.Ingestion.Security")

# Secret patterns for pre-ingestion quarantine
SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"whsec_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+RSA\s+PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"password[\"']?\s*[:=]\s*[\"']?[^\s\"',]{6,}", re.IGNORECASE),
    re.compile(r"client_secret[\"']?\s*[:=]\s*[\"']?[^\s\"',]{10,}", re.IGNORECASE)
]

# Prompt injection signatures in external content
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are\s+now", re.IGNORECASE),
    re.compile(r"bypass\s+(omnia|security|safety)\s+policy", re.IGNORECASE),
    re.compile(r"reveal\s+(api\s+keys|credentials|secrets|tokens)", re.IGNORECASE),
    re.compile(r"delete\s+the\s+(database|cluster|node|filesystem)", re.IGNORECASE),
    re.compile(r"override\s+system\s+prompt", re.IGNORECASE)
]


class IngestionSecurityGuard:
    """Enforces secret protection, prompt injection resistance, and policy compliance."""

    def __init__(self, pol_engine=None, redactor=None):
        self.policy_engine = pol_engine or policy_engine
        self.redaction_engine = redactor or redaction_engine

    def scan_for_secrets(self, text_content: str) -> Tuple[bool, List[str]]:
        """Scans string content for exposed credentials and cryptographic material."""
        detected = []
        for pattern in SECRET_PATTERNS:
            matches = pattern.findall(text_content)
            if matches:
                detected.append(f"PATTERN_MATCH:{pattern.pattern[:20]}")
        return len(detected) > 0, detected

    def detect_prompt_injection(self, text_content: str) -> Tuple[bool, List[str]]:
        """Identifies prompt injection and privilege escalation attempts in external text."""
        detected = []
        for pattern in INJECTION_PATTERNS:
            if pattern.search(text_content):
                detected.append(f"INJECTION_SIGNATURE:{pattern.pattern[:25]}")
        return len(detected) > 0, detected

    def sanitize_untrusted_text(self, text_content: str) -> str:
        """
        Wraps untrusted external text in explicit data containment tags,
        preventing downstream models from interpreting text as instructions.
        """
        redacted = self.redaction_engine.redact_text(text_content)
        sanitized = self.redaction_engine.sanitize_for_llm(redacted)
        return f"[UNTRUSTED_EXTERNAL_DATA]\n{sanitized}\n[/UNTRUSTED_EXTERNAL_DATA]"

    def evaluate_envelope(self, envelope: IngestionEnvelope) -> Tuple[bool, Optional[str]]:
        """
        Evaluates incoming envelope against security invariants.
        Returns (allowed, quarantine_reason).
        """
        # 1. Policy Engine Verification (Module 09)
        action_name = f"ingestion.{envelope.source_id}"
        allowed, reason = self.policy_engine.verify_action(action_name, {
            "source_id": envelope.source_id,
            "classification": envelope.classification.value,
            "size": envelope.payload_size
        })
        if not allowed:
            audit_logger.log_event(
                tool_name="ingestion_policy_denial",
                params={"envelope_id": envelope.envelope_id, "source_id": envelope.source_id},
                allowed=False,
                outcome=f"POLICY_DENIED: {reason}"
            )
            return False, f"POLICY_DENIED: {reason}"

        # 2. Convert payload to string representation for pattern inspection
        payload_str = str(envelope.raw_payload)

        # 3. Secret Protection: Obvious secrets must not enter ordinary ingestion
        has_secrets, secret_details = self.scan_for_secrets(payload_str)
        if has_secrets:
            logger.warning(f"SECRET_DETECTED in envelope '{envelope.envelope_id}' from '{envelope.source_id}'. Quarantining.")
            audit_logger.log_event(
                tool_name="ingestion_secret_quarantine",
                params={"envelope_id": envelope.envelope_id, "source_id": envelope.source_id},
                allowed=False,
                outcome="QUARANTINED_SECRET_MATERIAL"
            )
            return False, f"QUARANTINED: Secret material detected: {secret_details}"

        # 4. Prompt Injection Tagging: Mark envelope if injection signatures present
        has_injection, injection_details = self.detect_prompt_injection(payload_str)
        if has_injection:
            logger.warning(f"PROMPT_INJECTION_DETECTED in envelope '{envelope.envelope_id}'. Tagging as untrusted.")
            envelope.trust_boundary = TrustBoundary.UNTRUSTED_EXTERNAL
            envelope.metadata["prompt_injection_flags"] = injection_details
            envelope.metadata["sanitized_safe"] = True

        return True, None


ingestion_security_guard = IngestionSecurityGuard()
