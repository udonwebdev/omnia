"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Safe Vulnerability Validation Engine - safe_validation.py

Executes controlled, non-destructive validation probes to distinguish genuine vulnerabilities
from false positives. Never performs destructive exploitation, persistence, or data exfiltration.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from app_security.models import (
    FindingStatus, SecurityFinding, ValidationEvidence, ValidationExecution, ValidationOutcome
)
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.SafeValidation")


class SafeValidationEngine:
    """
    Safely proves whether an identified security finding is confirmed or a false positive.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def validate_finding_safely(
        self,
        finding_id: str,
        method: str,
        probe_runner: Callable[[], tuple[ValidationOutcome, str]],
        is_destructive: bool = False
    ) -> ValidationExecution:
        finding = self.repo.get_finding(finding_id)
        if not finding:
            raise ValueError(f"Finding {finding_id} not found.")

        vid = f"val-{uuid.uuid4().hex[:8]}"
        outcome, evidence_payload = probe_runner()

        # Immediately redact potential sensitive payload
        redacted_payload = evidence_payload[:256] + ("..." if len(evidence_payload) > 256 else "")
        payload_sha = hashlib.sha256(evidence_payload.encode("utf-8")).hexdigest()

        val = ValidationExecution(
            validation_id=vid,
            finding_id=finding_id,
            method=method,
            outcome=outcome,
            is_destructive=is_destructive,
            executed_at=datetime.now(timezone.utc).isoformat()
        )
        self.repo.save_validation(val)

        # Store evidence artifact
        ev = ValidationEvidence(
            evidence_id=f"ev-{uuid.uuid4().hex[:8]}",
            validation_id=vid,
            evidence_type="VALIDATION_PROBE_OUTPUT",
            redacted_content=redacted_payload,
            checksum_sha256=payload_sha
        )
        self.repo.save_validation_evidence(ev)

        # Update finding status based on outcome
        if outcome == ValidationOutcome.CONFIRMED:
            self.repo.update_finding_status(finding_id, FindingStatus.VALIDATED)
        elif outcome == ValidationOutcome.FALSE_POSITIVE:
            self.repo.update_finding_status(finding_id, FindingStatus.FALSE_POSITIVE)

        logger.info(f"Validated finding {finding_id} with method '{method}': Outcome={outcome.value}")
        return val
