"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Alert Management Subsystem - alerts.py
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from secops.models import AlertStatus, SecurityAlert
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.Alerts")


class AlertManager:
    """
    Manages the alert lifecycle: NEW -> TRIAGED -> INVESTIGATING -> CONFIRMED / FALSE_POSITIVE -> RESOLVED.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def transition_alert_status(
        self,
        alert_id: str,
        new_status: AlertStatus,
        assigned_to: Optional[str] = None,
        resolution_notes: Optional[str] = None,
    ) -> SecurityAlert:
        alert = self.repo.get_alert(alert_id)
        if not alert:
            raise ValueError(f"Alert {alert_id} not found.")

        alert.status = new_status
        if assigned_to:
            alert.assigned_to = assigned_to
        if resolution_notes:
            alert.explanation["resolution_notes"] = resolution_notes

        alert.updated_at = datetime.now(timezone.utc).isoformat()
        self.repo.save_alert(alert)
        logger.info(f"Transitioned alert {alert_id} to status {new_status.value}")
        return alert

    def suppress_alert(self, alert_id: str, expires_at: str, reason: str) -> SecurityAlert:
        alert = self.repo.get_alert(alert_id)
        if not alert:
            raise ValueError(f"Alert {alert_id} not found.")

        alert.suppression_expires_at = expires_at
        alert.explanation["suppression_reason"] = reason
        alert.updated_at = datetime.now(timezone.utc).isoformat()
        self.repo.save_alert(alert)
        logger.info(f"Suppressed alert {alert_id} until {expires_at}")
        return alert
