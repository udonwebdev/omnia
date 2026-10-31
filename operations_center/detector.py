"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Anomaly & Incident Detector: Rule-Based & Metric Threshold Alerting.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from operations_center.models import (
    IncidentAlertRecord,
    IncidentSeverity,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.Detector")


class AnomalyAndIncidentDetector:
    """
    Monitors streaming metrics, error rates, and queue depths against defined thresholds.
    Generates actionable IncidentAlertRecords without creating alert storms.
    """

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def check_metric_threshold(
        self,
        service_id: str,
        metric_name: str,
        current_value: float,
        critical_threshold: float,
        warning_threshold: float,
        is_higher_worse: bool = True,
    ) -> Optional[IncidentAlertRecord]:
        """Evaluates a single metric reading against warning/critical thresholds."""
        is_critical = (current_value >= critical_threshold) if is_higher_worse else (current_value <= critical_threshold)
        is_warning = (current_value >= warning_threshold) if is_higher_worse else (current_value <= warning_threshold)

        if not is_warning and not is_critical:
            return None

        severity = IncidentSeverity.SEV_1_CRITICAL if is_critical else IncidentSeverity.SEV_3_MODERATE
        alert_name = f"{metric_name}_{'BREACH' if is_critical else 'WARNING'}"
        desc = (
            f"Metric '{metric_name}' value {current_value} violated "
            f"{'critical' if is_critical else 'warning'} threshold ({critical_threshold if is_critical else warning_threshold})."
        )

        aid = f"alt-{uuid.uuid4().hex[:8]}"
        alert = IncidentAlertRecord(
            alert_id=aid,
            service_id=service_id,
            alert_name=alert_name,
            severity=severity,
            symptom_description=desc,
            supporting_metric_value=current_value,
            correlated_incident_id=None,
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_alert(alert)
        logger.warning(f"Raised alert '{aid}' on '{service_id}': {alert_name} [{severity.value}]")
        return alert
