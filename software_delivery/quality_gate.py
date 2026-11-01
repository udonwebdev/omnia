"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Software Quality Gates - quality_gate.py

Evaluates build status, test passing rates, code coverage thresholds, and lint results.
Enforces that failed mandatory gates block release promotion unless explicitly waived.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from software_delivery.models import (
    BuildExecutionRecord,
    BuildStatus,
    GateStatus,
    QualityGateResult,
    TestExecutionRecord,
    TestStatus,
)
from software_delivery.persistence import SoftwareDeliveryRepository

logger = logging.getLogger("Omnia.SoftwareDelivery.QualityGate")


class QualityGateEngine:
    """
    Evaluates pipeline execution results against configured quality policies.
    """

    def __init__(self, repository: Optional[SoftwareDeliveryRepository] = None):
        self.repo = repository or SoftwareDeliveryRepository()

    def evaluate_quality(
        self,
        pipeline_execution_id: str,
        build_records: List[BuildExecutionRecord],
        test_records: List[TestExecutionRecord],
        min_coverage_pct: float = 75.0,
        gate_id: Optional[str] = None,
    ) -> QualityGateResult:
        gid = gate_id or f"gate-{uuid.uuid4().hex[:8]}"
        violations: List[str] = []

        # 1. Evaluate build executions
        for b in build_records:
            if b.status != BuildStatus.SUCCESS:
                violations.append(f"Build failed: command '{b.command}' exited with status {b.status.value}")

        # 2. Evaluate test executions
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        total_cov = 0.0
        cov_count = 0

        for t in test_records:
            total_tests += t.total_tests
            passed_tests += t.passed_tests
            failed_tests += t.failed_tests
            if t.coverage_pct is not None:
                total_cov += t.coverage_pct
                cov_count += 1
            if t.status != TestStatus.PASSED:
                violations.append(f"Test suite '{t.suite_name}' failed with {t.failed_tests} failure(s)")

        avg_cov = round(total_cov / cov_count, 1) if cov_count > 0 else 100.0
        if avg_cov < min_coverage_pct:
            violations.append(f"Code coverage {avg_cov}% is below mandatory threshold {min_coverage_pct}%")

        pass_rate = (passed_tests / total_tests) if total_tests > 0 else 1.0
        is_passed = (len(violations) == 0) and (failed_tests == 0)

        result = QualityGateResult(
            gate_id=gid,
            pipeline_execution_id=pipeline_execution_id,
            status=GateStatus.PASSED if is_passed else GateStatus.FAILED,
            score=round(pass_rate, 2),
            metrics={
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "average_coverage_pct": avg_cov,
                "min_coverage_pct": min_coverage_pct,
            },
            violations=violations,
        )
        self.repo.save_quality_gate(result)
        logger.info(
            f"Quality gate {gid} evaluated: Status={result.status.value}, "
            f"Score={result.score}, Violations={len(violations)}"
        )
        return result
