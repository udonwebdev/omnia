"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Regression Intelligence - regression.py

Detects behavioural, test suite, and performance regressions against historical baselines.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from software_delivery.models import (
    FindingSeverity,
    RegressionFinding,
    TestExecutionRecord,
)
from software_delivery.persistence import SoftwareDeliveryRepository

logger = logging.getLogger("Omnia.SoftwareDelivery.Regression")


class RegressionDetector:
    """
    Compares current test execution metrics against baseline values.
    """

    def __init__(self, repository: Optional[SoftwareDeliveryRepository] = None):
        self.repo = repository or SoftwareDeliveryRepository()

    def detect_regressions(
        self,
        pipeline_execution_id: str,
        current_tests: List[TestExecutionRecord],
        baseline_failure_rate: float = 0.0,
        baseline_duration_seconds: float = 1.0,
    ) -> List[RegressionFinding]:
        findings: List[RegressionFinding] = []

        for t in current_tests:
            # Check newly introduced test failures
            if t.failed_tests > 0 and baseline_failure_rate == 0.0:
                fid = f"regr-{uuid.uuid4().hex[:8]}"
                rf = RegressionFinding(
                    regression_id=fid,
                    pipeline_execution_id=pipeline_execution_id,
                    component_name=t.suite_name,
                    metric_name="failed_tests",
                    baseline_value=0.0,
                    current_value=float(t.failed_tests),
                    delta_pct=100.0,
                    severity=FindingSeverity.HIGH,
                    description=f"New test failures detected in {t.suite_name} (Failed={t.failed_tests})",
                )
                self.repo.save_regression(rf)
                findings.append(rf)

            # Check execution duration spikes (> 100% regression)
            if t.duration_seconds > (baseline_duration_seconds * 2.0):
                fid = f"regr-{uuid.uuid4().hex[:8]}"
                pct = ((t.duration_seconds - baseline_duration_seconds) / baseline_duration_seconds) * 100.0
                rf = RegressionFinding(
                    regression_id=fid,
                    pipeline_execution_id=pipeline_execution_id,
                    component_name=t.suite_name,
                    metric_name="duration_seconds",
                    baseline_value=baseline_duration_seconds,
                    current_value=t.duration_seconds,
                    delta_pct=round(pct, 1),
                    severity=FindingSeverity.MEDIUM,
                    description=f"Test runtime regression in {t.suite_name}: {t.duration_seconds}s vs baseline {baseline_duration_seconds}s",
                )
                self.repo.save_regression(rf)
                findings.append(rf)

        logger.info(f"Regression detector evaluated {len(current_tests)} suites: {len(findings)} regression(s) found.")
        return findings
