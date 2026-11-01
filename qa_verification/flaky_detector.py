"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Flaky Test Intelligence - flaky_detector.py

Identifies intermittent, non-deterministic, and timing-dependent test failures.
Never automatically counts flaky tests as passed.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from qa_verification.models import (
    FlakyClassification,
    FlakyTestRecord,
)
from qa_verification.persistence import QAVerificationRepository

logger = logging.getLogger("Omnia.QAVerification.FlakyDetector")


class FlakyTestDetector:
    """
    Evaluates historical test executions to isolate flaky tests from genuine regressions.
    """

    def __init__(self, repository: Optional[QAVerificationRepository] = None):
        self.repo = repository or QAVerificationRepository()

    def evaluate_test_stability(
        self,
        test_case_id: str,
        execution_results: List[bool],  # True for pass, False for fail
        flaky_id: Optional[str] = None,
    ) -> FlakyTestRecord:
        runs = len(execution_results)
        passes = sum(1 for r in execution_results if r)
        failures = runs - passes

        if runs == 0:
            classification = FlakyClassification.STABLE_PASSING
            var = 0.0
        elif passes == runs:
            classification = FlakyClassification.STABLE_PASSING
            var = 0.0
        elif failures == runs:
            classification = FlakyClassification.STABLE_FAILING
            var = 0.0
        else:
            # Alternating pass/fail outcomes indicates intermittent flakiness
            classification = FlakyClassification.INTERMITTENT_FLAKY
            var = round((passes * failures) / (runs * runs), 2)

        fid = flaky_id or f"flaky-{uuid.uuid4().hex[:8]}"
        record = FlakyTestRecord(
            flaky_id=fid,
            test_case_id=test_case_id,
            runs_evaluated=runs,
            passes=passes,
            failures=failures,
            variance_score=var,
            classification=classification,
        )
        self.repo.save_flaky_test(record)
        logger.info(
            f"Flaky assessment for '{test_case_id}': {classification.value} (Passes={passes}/{runs}, Var={var})"
        )
        return record
