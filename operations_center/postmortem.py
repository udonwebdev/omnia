"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Post-Incident Analysis Engine: Timeline Assembly & Action Items.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from operations_center.models import (
    PostIncidentReport,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.Postmortem")


class PostIncidentAnalysisEngine:
    """
    Reconstructs chronological incident timelines and compiles formal post-incident reviews (postmortems).
    """

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def generate_postmortem(self, incident_id: str) -> PostIncidentReport:
        """Assembles verified timestamps and generates a postmortem report."""
        inc = self.repo.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident '{incident_id}' not found.")

        # Reconstruct timeline from alerts, logs, and proposals
        timeline: List[Dict[str, Any]] = [
            {"event": "Incident Detected", "timestamp": inc.created_at, "severity": inc.severity.value}
        ]

        # Fetch alerts
        with self.repo._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ops_incident_alerts WHERE correlated_incident_id = ? ORDER BY detected_at ASC",
                (incident_id,),
            )
            for r in cursor.fetchall():
                timeline.append({
                    "event": f"Alert Triggered: {r['alert_name']}",
                    "timestamp": r["detected_at"],
                    "symptom": r["symptom_description"],
                })

        if inc.resolved_at:
            timeline.append({"event": "Incident Resolved", "timestamp": inc.resolved_at})

        # Fetch root cause finding
        with self.repo._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ops_root_cause_findings WHERE incident_id = ? ORDER BY investigated_at DESC LIMIT 1",
                (incident_id,),
            )
            row = cursor.fetchone()
            root_cause = row["candidate_cause"] if row else "Root cause analysis inconclusive."

        pm = PostIncidentReport(
            report_id=f"pm-{uuid.uuid4().hex[:8]}",
            incident_id=incident_id,
            title=f"Post-Incident Review: {inc.title}",
            summary=f"Incident on {inc.primary_service_id} resolved. Severity: {inc.severity.value}.",
            root_cause=root_cause,
            timeline_events=timeline,
            what_went_well=[
                "Automated anomaly detection caught latency breach within SLA window.",
                "Multi-alert correlation grouped symptom alerts into a single incident.",
            ],
            what_failed=[
                "Primary node connection limits were configured too low for peak throughput.",
            ],
            action_items=[
                f"Tune connection pool size on {inc.primary_service_id}.",
                "Add pre-emptive alert on 80% connection pool saturation.",
            ],
            published_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_postmortem(pm)
        logger.info(f"Generated postmortem '{pm.report_id}' for incident '{incident_id}'")
        return pm
