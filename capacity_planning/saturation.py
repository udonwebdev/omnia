"""
Omnia Module 42: Autonomous Capacity Planning, Infrastructure Forecasting & Elastic Resource Intelligence.
Saturation and Bottleneck Detector: Proactive Threshold Detection & Time-to-Saturation (TTS) Risk Analysis.
"""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from capacity_planning.models import (
    SaturationRiskFinding,
    SaturationRiskSeverity,
)
from capacity_planning.persistence import CapacityRepository

logger = logging.getLogger("Omnia.Capacity.Saturation")


class SaturationDetector:
    """
    Identifies approaching bottlenecks across Compute, Storage, Networking, and Application Limits.
    Detects CPU saturation, Memory exhaustion, Queue accumulation, and Connection exhaustion.
    Deduplicates unresolved alerts.
    """

    def __init__(self, repository: Optional[CapacityRepository] = None):
        self.repo = repository or CapacityRepository()

    def detect_saturation_risks(
        self,
        warning_threshold_pct: float = 75.0,
        critical_threshold_pct: float = 90.0,
    ) -> List[SaturationRiskFinding]:
        """
        Inspects latest measurements and active forecasts to detect current and approaching saturation.
        """
        latest_meas = self.repo.get_latest_measurements()
        findings: List[SaturationRiskFinding] = []

        unresolved = {r.resource_id: r for r in self.repo.list_unresolved_risks()}

        for rid, m in latest_meas.items():
            if m.collection_status != "VALID":
                continue

            util = m.utilization_pct
            severity: Optional[SaturationRiskSeverity] = None

            if util >= critical_threshold_pct:
                severity = SaturationRiskSeverity.CRITICAL
            elif util >= warning_threshold_pct:
                severity = SaturationRiskSeverity.HIGH
            elif util >= 65.0:
                severity = SaturationRiskSeverity.MEDIUM

            if severity:
                # Deduplicate if already reported and unresolved with same severity
                if rid in unresolved and unresolved[rid].severity == severity:
                    continue

                res = self.repo.get_resource(rid)
                res_type = res.resource_type if res else "GENERIC_RESOURCE"

                tts = None
                # Check if forecast has estimated saturation hours
                fc = self.repo.get_latest_forecast(rid, horizon="24H")
                if fc and fc.estimated_saturation_hours is not None:
                    tts = fc.estimated_saturation_hours

                finding_id = f"risk-{uuid.uuid4().hex[:8]}"
                cause = f"High sustained workload consumption ({util:.1f}% of capacity)"
                impact = f"Degraded execution latency, possible task queue blocking or thread pool exhaustion on {rid}."
                mitigation = (
                    f"Perform horizontal scale-out or worker pool expansion for {rid} to restore headroom."
                    if severity in (SaturationRiskSeverity.CRITICAL, SaturationRiskSeverity.HIGH)
                    else f"Monitor {rid} consumption and review background batch workloads."
                )

                risk = SaturationRiskFinding(
                    risk_id=finding_id,
                    resource_id=rid,
                    severity=severity,
                    observed_utilization_pct=round(util, 2),
                    estimated_time_to_saturation_hours=tts,
                    likely_cause=cause,
                    expected_operational_impact=impact,
                    recommended_mitigation=mitigation,
                    confidence_level=m.data_confidence,
                    is_resolved=False,
                )
                self.repo.save_risk(risk)
                findings.append(risk)
                logger.warning(
                    f"Saturation risk detected on '{rid}': Severity={severity.value}, "
                    f"Util={util:.1f}%, TTS={tts}h"
                )

        return findings

    def resolve_risk(self, risk_id: str) -> None:
        risks = self.repo.list_unresolved_risks()
        for r in risks:
            if r.risk_id == risk_id:
                r.is_resolved = True
                self.repo.save_risk(r)
                logger.info(f"Resolved saturation risk: {risk_id}")
                return
        logger.warning(f"Risk '{risk_id}' not found for resolution.")
