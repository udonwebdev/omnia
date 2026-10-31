"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Incident Correlation Engine: Alert Clustering & Deduplication.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from operations_center.models import (
    IncidentAlertRecord,
    IncidentLifecycleState,
    IncidentRecord,
    IncidentSeverity,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.Correlation")


class IncidentCorrelationEngine:
    """
    Groups disparate alerts occurring within temporal and architectural proximity
    into single, coherent Incident records, preventing alert fatigue and redundant triage.
    """

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def correlate_active_alerts(self) -> List[IncidentRecord]:
        """Clusters unassigned alerts by primary service and dependency relationships."""
        alerts = self.repo.list_uncorrelated_alerts()
        if not alerts:
            return []

        # Group by primary service_id
        service_groups: Dict[str, List[IncidentAlertRecord]] = {}
        for a in alerts:
            if a.service_id not in service_groups:
                service_groups[a.service_id] = []
            service_groups[a.service_id].append(a)

        incidents: List[IncidentRecord] = []
        now = datetime.now(timezone.utc).isoformat()

        for svc_id, grouped_alerts in service_groups.items():
            # Determine maximum severity
            has_crit = any(a.severity == IncidentSeverity.SEV_1_CRITICAL for a in grouped_alerts)
            has_high = any(a.severity == IncidentSeverity.SEV_2_HIGH for a in grouped_alerts)
            if has_crit:
                sev = IncidentSeverity.SEV_1_CRITICAL
            elif has_high:
                sev = IncidentSeverity.SEV_2_HIGH
            else:
                sev = IncidentSeverity.SEV_3_MODERATE

            iid = f"inc-{uuid.uuid4().hex[:8]}"
            alert_ids = [a.alert_id for a in grouped_alerts]

            inc = IncidentRecord(
                incident_id=iid,
                title=f"Service Outage / Degradation on {svc_id} ({len(grouped_alerts)} correlated alerts)",
                severity=sev,
                state=IncidentLifecycleState.DETECTED,
                primary_service_id=svc_id,
                affected_services=[svc_id],
                correlated_alert_ids=alert_ids,
                created_at=now,
            )
            self.repo.save_incident(inc)

            # Link alerts to incident
            for a in grouped_alerts:
                a.correlated_incident_id = iid
                self.repo.save_alert(a)

            incidents.append(inc)
            logger.info(f"Correlated {len(grouped_alerts)} alerts on '{svc_id}' into Incident '{iid}' [{sev.value}]")

        return incidents
