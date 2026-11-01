"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Security Fix Verification & Continuous Regression Monitor - regression_monitor.py

Verifies that security fixes actually neutralize the vulnerability via Module 45 test execution.
Monitors whether resolved vulnerabilities reappear during subsequent commits or releases.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from app_security.models import FindingStatus, SecurityFixVerification
from app_security.persistence import AppSecurityRepository

logger = logging.getLogger("Omnia.AppSecurity.RegressionMonitor")


class SecurityRegressionMonitor:
    """
    Verifies patches and continuously monitors repositories for vulnerability recurrence.
    """

    def __init__(self, repository: Optional[AppSecurityRepository] = None):
        self.repo = repository or AppSecurityRepository()

    def verify_fix_with_evidence(
        self,
        finding_id: str,
        plan_id: str,
        recheck_probe_fn: Callable[[], bool],
        module45_mission_id: Optional[str] = None,
        regressions_detected: int = 0
    ) -> SecurityFixVerification:
        finding = self.repo.get_finding(finding_id)
        if not finding:
            raise ValueError(f"Finding {finding_id} not found.")

        # Probe passes if the vulnerability is no longer exploitable / absent
        probe_passed = recheck_probe_fn()
        is_fully_resolved = probe_passed and (regressions_detected == 0)

        vid = f"verif-{uuid.uuid4().hex[:8]}"
        verification = SecurityFixVerification(
            verification_id=vid,
            finding_id=finding_id,
            plan_id=plan_id,
            module45_mission_id=module45_mission_id,
            original_probe_passed=probe_passed,
            regressions_found=regressions_detected,
            is_fully_resolved=is_fully_resolved,
            verified_at=datetime.now(timezone.utc).isoformat()
        )
        self.repo.save_fix_verification(verification)

        if is_fully_resolved:
            logger.info(f"Finding {finding_id} independently VERIFIED RESOLVED (Plan: {plan_id})")
        else:
            logger.warning(f"Finding {finding_id} fix FAILED verification (ProbePassed: {probe_passed}, Regressions: {regressions_detected})")

        return verification

    def detect_reintroduced_vulnerability(
        self,
        asset_id: str,
        fingerprint_sha256: str
    ) -> bool:
        """Checks if a previously resolved finding fingerprint has reappeared."""
        findings = self.repo.list_findings_for_asset(asset_id)
        resolved_fps = {f.fingerprint_sha256 for f in findings if f.status == FindingStatus.RESOLVED}
        is_reintroduced = fingerprint_sha256 in resolved_fps
        if is_reintroduced:
            logger.critical(f"SECURITY_REGRESSION: Finding fingerprint {fingerprint_sha256} re-detected on asset {asset_id}!")
        return is_reintroduced
