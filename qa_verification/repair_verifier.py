"""
Autonomous Quality Assurance — Repair Verifier
Validates candidate fixes and defect repairs against original failing tests and regression suites.
Ensures zero regressions before marking defects resolved.
"""
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime, timezone

from .models import DefectRecord, RepairVerification, DefectSeverity
from .persistence import QAVerificationRepository


class RepairVerifier:
    def __init__(self, repository: Optional[QAVerificationRepository] = None):
        self.repo = repository or QAVerificationRepository()

    def verify_defect_repair(
        self,
        defect_id: str,
        patch_summary: str,
        failing_test_recheck_passed: bool,
        regression_test_results: Dict[str, bool],
        environment_id: str = "sandbox-repair"
    ) -> RepairVerification:
        defect = self.repo.get_defect(defect_id)
        if not defect:
            raise ValueError(f"Defect {defect_id} not found.")

        regressions_detected = [test_id for test_id, passed in regression_test_results.items() if not passed]
        is_verified = failing_test_recheck_passed and len(regressions_detected) == 0

        verification = RepairVerification(
            repair_verification_id=f"rep-{uuid.uuid4().hex[:10]}",
            defect_id=defect_id,
            patch_ref=patch_summary,
            retest_passed=failing_test_recheck_passed,
            regressions_found=len(regressions_detected),
            verification_evidence={
                "environment_id": environment_id,
                "regressions_detected": regressions_detected,
                "tested_count": len(regression_test_results),
                "is_verified": is_verified
            },
            verified_at=datetime.now(timezone.utc).isoformat()
        )

        self.repo.save_repair_verification(verification)

        if is_verified:
            self.repo.update_defect_resolution(defect_id, is_resolved=True)
        else:
            self.repo.update_defect_resolution(defect_id, is_resolved=False)

        return verification
