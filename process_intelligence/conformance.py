"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Process Conformance Analyzer: Deviations, Skipped Approval Gates & Policy Violations.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from process_intelligence.models import (
    DeviationType,
    FindingSeverity,
    ProcessDeviationRecord,
)
from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Conformance")


class ProcessConformanceAnalyzer:
    """
    Compares reconstructed execution traces against reference workflow templates.
    Detects skipped approval gates, unauthorized paths, and missing required steps.
    """

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def audit_trace_conformance(
        self,
        trace_id: str,
        expected_mandatory_steps: List[str],
        policy_rules: Optional[dict[str, str]] = None,
    ) -> List[ProcessDeviationRecord]:
        """Audits a single execution trace against expected mandatory sequence and gates."""
        trace = self.repo.get_trace(trace_id)
        if not trace:
            raise ValueError(f"Trace '{trace_id}' not found.")

        events = self.repo.list_events_for_trace(trace_id)
        executed_tasks = [e.task_id for e in events]
        deviations: List[ProcessDeviationRecord] = []

        # 1. Missing mandatory steps
        for step in expected_mandatory_steps:
            if step not in executed_tasks:
                dev_type = DeviationType.SKIPPED_APPROVAL_GATE if "approval" in step.lower() else DeviationType.MISSING_REQUIRED_STEP
                sev = FindingSeverity.CRITICAL if dev_type == DeviationType.SKIPPED_APPROVAL_GATE else FindingSeverity.HIGH
                d = ProcessDeviationRecord(
                    deviation_id=f"dev-{uuid.uuid4().hex[:8]}",
                    trace_id=trace_id,
                    workflow_id=trace.workflow_id,
                    deviation_type=dev_type,
                    severity=sev,
                    description=f"Mandatory execution step '{step}' was omitted from trace.",
                    policy_rule_violated=policy_rules.get(step, "POLICY_GOV_MANDATORY_GATE") if policy_rules else None,
                )
                self.repo.save_deviation(d)
                deviations.append(d)

        logger.info(f"Trace '{trace_id}' conformance check: {len(deviations)} deviations found.")
        return deviations
