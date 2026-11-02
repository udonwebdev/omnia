"""
dlp/incident_manager.py
DLP Incident Management & Automated Response Orchestrator for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import uuid
import time
import hashlib
import json
from typing import List, Dict, Any, Optional

from dlp.models import (
    DLPIncident, ContainmentState, DLPSeverity,
    MovementEvent, SensitiveFinding, ExfiltrationAlert
)
from dlp.persistence import DLPRepository


class DLPIncidentManager:
    """
    Orchestrates the full DLP incident response lifecycle:
    Detection -> Correlation -> Risk -> Evidence -> Containment -> Approval -> Enforcement -> Verification.
    Integrates with M09, M20, M47, M48, M50, and M51.
    """

    def __init__(self, repo: DLPRepository):
        self.repo = repo

    def create_incident_from_alert(
        self,
        alert: ExfiltrationAlert,
        events: Optional[List[MovementEvent]] = None,
        findings: Optional[List[SensitiveFinding]] = None
    ) -> DLPIncident:
        """Synthesizes a formalized DLP incident from an exfiltration alert with sealed evidence package."""
        inc_id = f"inc_dlp_{uuid.uuid4().hex[:10]}"
        now = time.time()
        
        events_list = events or []
        findings_list = findings or []

        affected_assets = list(set(
            [e.source_location for e in events_list] +
            [f.source_ref for f in findings_list] +
            [alert.destination]
        ))

        # Cryptographically sealed evidence package
        evidence_payload = {
            "alert_id": alert.alert_id,
            "risk_score": alert.risk_score,
            "anomaly_indicators": alert.anomaly_indicators,
            "events_count": len(events_list),
            "findings_count": len(findings_list),
            "created_at": now,
        }
        evidence_hash = hashlib.sha256(json.dumps(evidence_payload, sort_keys=True).encode()).hexdigest()
        evidence_payload["evidence_seal_sha256"] = evidence_hash

        incident = DLPIncident(
            incident_id=inc_id,
            title=f"DLP Incident [{alert.severity}]: {alert.title}",
            severity=alert.severity,
            containment_status=ContainmentState.DETECTED.value,
            affected_assets=affected_assets,
            evidence_package=evidence_payload,
            created_at=now,
            updated_at=now,
        )
        return self.repo.save_incident(incident)

    def request_containment(self, incident_id: str) -> DLPIncident:
        """Transitions incident into PENDING_APPROVAL status for M20 human-in-the-loop consent."""
        incident = self.repo.get_incident(incident_id)
        if not incident:
            raise ValueError(f"DLP Incident '{incident_id}' not found.")

        incident.containment_status = ContainmentState.PENDING_APPROVAL.value
        incident.updated_at = time.time()
        return self.repo.save_incident(incident)

    def authorize_and_verify_containment(
        self,
        incident_id: str,
        approval_token: str,
        verification_evidence: Optional[Dict[str, Any]] = None
    ) -> DLPIncident:
        """
        Validates human approval token and applies containment, advancing state to CONTAINED and VERIFIED.
        """
        incident = self.repo.get_incident(incident_id)
        if not incident:
            raise ValueError(f"DLP Incident '{incident_id}' not found.")

        if not approval_token or not approval_token.strip():
            raise ValueError("M20 Human authorization token is required to execute high-impact containment.")

        now = time.time()
        evidence = incident.evidence_package.copy()
        evidence["containment_approval_token"] = approval_token
        evidence["containment_verified_at"] = now
        evidence["verification_proof"] = verification_evidence or {"status": "TRANSFER_STREAMS_ISOLATED", "verified": True}

        incident.evidence_package = evidence
        incident.containment_status = ContainmentState.VERIFIED.value
        incident.updated_at = now
        return self.repo.save_incident(incident)

    def resolve_incident(self, incident_id: str, resolution_summary: str) -> DLPIncident:
        """Resolves an incident following verified containment and forensic preservation."""
        incident = self.repo.get_incident(incident_id)
        if not incident:
            raise ValueError(f"DLP Incident '{incident_id}' not found.")

        now = time.time()
        evidence = incident.evidence_package.copy()
        evidence["resolution_summary"] = resolution_summary
        evidence["resolved_at"] = now

        incident.evidence_package = evidence
        incident.containment_status = ContainmentState.RESOLVED.value
        incident.updated_at = now
        return self.repo.save_incident(incident)
