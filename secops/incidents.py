"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Incident Management & Investigation Workbench - incidents.py
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from secops.models import (
    IncidentPriority,
    IncidentStatus,
    IncidentTimelineEntry,
    SecurityIncident,
    SecurityInvestigation,
    SecuritySeverity,
)
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.Incidents")


class IncidentManager:
    """
    Coordinates security incident lifecycles, investigation workbenches, and immutable chronological timelines.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def create_incident(
        self,
        title: str,
        description: str,
        severity: SecuritySeverity,
        priority: IncidentPriority,
        affected_assets: Optional[List[str]] = None,
        affected_identities: Optional[List[str]] = None,
        related_alert_ids: Optional[List[str]] = None,
        assigned_owner: Optional[str] = None,
    ) -> SecurityIncident:
        iid = f"inc-{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        incident = SecurityIncident(
            incident_id=iid,
            title=title,
            description=description,
            severity=severity,
            priority=priority,
            status=IncidentStatus.DETECTED,
            affected_assets=affected_assets or [],
            affected_identities=affected_identities or [],
            related_alert_ids=related_alert_ids or [],
            assigned_owner=assigned_owner,
            created_at=now_iso,
            updated_at=now_iso,
        )
        self.repo.save_incident(incident)

        # Record initial timeline entry
        self.add_timeline_entry(
            incident_id=iid,
            entry_type="INCIDENT_CREATED",
            description=f"Incident {iid} created: {title} ({severity.value}/{priority.value})",
            actor=assigned_owner or "SOC_AUTONOMOUS_ENGINE",
        )

        logger.warning(f"Created Security Incident {iid}: '{title}' ({priority.value})")
        return incident

    def add_timeline_entry(
        self,
        incident_id: str,
        entry_type: str,
        description: str,
        actor: str,
        evidence_reference: Optional[str] = None,
    ) -> IncidentTimelineEntry:
        eid = f"time-{uuid.uuid4().hex[:8]}"
        entry = IncidentTimelineEntry(
            timeline_entry_id=eid,
            incident_id=incident_id,
            entry_timestamp=datetime.now(timezone.utc).isoformat(),
            entry_type=entry_type,
            description=description,
            actor=actor,
            evidence_reference=evidence_reference,
        )
        self.repo.save_timeline_entry(entry)
        return entry

    def transition_incident(
        self,
        incident_id: str,
        new_status: IncidentStatus,
        actor: str,
        notes: str = "",
    ) -> SecurityIncident:
        inc = self.repo.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident {incident_id} not found.")

        old_status = inc.status
        inc.status = new_status
        inc.updated_at = datetime.now(timezone.utc).isoformat()
        if new_status == IncidentStatus.RESOLVED and notes:
            inc.resolution_summary = notes

        self.repo.save_incident(inc)
        self.add_timeline_entry(
            incident_id=incident_id,
            entry_type="STATUS_TRANSITION",
            description=f"Status changed {old_status.value} -> {new_status.value}. Notes: {notes}",
            actor=actor,
        )
        logger.info(f"Incident {incident_id} transitioned: {old_status.value} -> {new_status.value}")
        return inc

    def create_investigation(
        self,
        title: str,
        assigned_analyst: str,
        primary_hypothesis: str,
        supporting_event_ids: Optional[List[str]] = None,
        affected_assets: Optional[List[str]] = None,
        affected_identities: Optional[List[str]] = None,
    ) -> SecurityInvestigation:
        inv_id = f"inv-{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        inv = SecurityInvestigation(
            investigation_id=inv_id,
            title=title,
            assigned_analyst=assigned_analyst,
            primary_hypothesis=primary_hypothesis,
            status="OPEN",
            competing_hypotheses=[],
            supporting_event_ids=supporting_event_ids or [],
            contradictory_evidence=[],
            affected_assets=affected_assets or [],
            affected_identities=affected_identities or [],
            open_questions=["What was the initial ingress vector?", "Are lateral credentials compromised?"],
            confidence=0.5,
            created_at=now_iso,
            updated_at=now_iso,
        )

        with self.repo._get_connection() as conn:
            import json
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_investigations (
                    investigation_id, title, assigned_analyst, status,
                    primary_hypothesis, competing_hypotheses_json,
                    supporting_event_ids_json, contradictory_evidence_json,
                    affected_assets_json, affected_identities_json,
                    open_questions_json, findings_summary, confidence,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inv.investigation_id,
                    inv.title,
                    inv.assigned_analyst,
                    inv.status,
                    inv.primary_hypothesis,
                    json.dumps(inv.competing_hypotheses),
                    json.dumps(inv.supporting_event_ids),
                    json.dumps(inv.contradictory_evidence),
                    json.dumps(inv.affected_assets),
                    json.dumps(inv.affected_identities),
                    json.dumps(inv.open_questions),
                    inv.findings_summary,
                    inv.confidence,
                    inv.created_at,
                    inv.updated_at,
                ),
            )
        return inv
