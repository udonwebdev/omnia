"""
privacy/incident_manager.py
Privacy Incident & Data Breach Management:
Assesses unauthorized disclosures, categorizes breach severity, evaluates regulatory
reportability (GDPR Art 33 72-hour notice, state breach notification statutes),
and tracks containment across M47/M48/M49/M50.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional

from privacy.models import PrivacyIncident, IncidentSeverity, ContainmentStatus, DataCategory
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.incident_manager")


class PrivacyIncidentManager:
    # High-risk categories triggering statutory breach notification
    REPORTABLE_CATEGORIES = {
        DataCategory.CREDENTIALS,
        DataCategory.HEALTH,
        DataCategory.FINANCIAL,
        DataCategory.GOV_ID,
        DataCategory.BIOMETRIC,
    }

    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def record_incident(
        self,
        incident_type: str,
        affected_assets: List[str],
        affected_categories: List[str],
        severity: str = "MEDIUM",
        containment_status: str = "DETECTED",
        incident_id: Optional[str] = None
    ) -> PrivacyIncident:
        """Registers a privacy incident or potential data disclosure."""
        iid = incident_id or f"inc_{uuid.uuid4().hex[:12]}"
        now = time.time()

        sev = IncidentSeverity(severity.upper()) if severity.upper() in IncidentSeverity._value2member_map_ else IncidentSeverity.MEDIUM
        c_status = ContainmentStatus(containment_status.upper()) if containment_status.upper() in ContainmentStatus._value2member_map_ else ContainmentStatus.DETECTED

        cats: List[DataCategory] = []
        for c in affected_categories:
            if c.upper() in DataCategory._value2member_map_:
                cats.append(DataCategory(c.upper()))

        # Determine statutory reportability
        is_reportable = any(c in self.REPORTABLE_CATEGORIES for c in cats) or sev in (IncidentSeverity.HIGH, IncidentSeverity.CRITICAL)

        incident = PrivacyIncident(
            incident_id=iid,
            incident_type=incident_type,
            affected_assets=affected_assets,
            affected_categories=cats,
            severity=sev,
            containment_status=c_status,
            reportable=is_reportable,
            created_at=now
        )
        saved = self.repo.save_incident(incident)
        self.repo.log_audit("PRIVACY_INCIDENT_RECORDED", "secops", {
            "incident_id": iid,
            "type": incident_type,
            "severity": sev.value,
            "reportable": is_reportable
        })
        logger.warning(f"Privacy incident recorded: {iid} ({incident_type}, reportable={is_reportable})")
        return saved

    def update_containment(self, incident_id: str, new_status: str, actor: str = "secops_lead") -> Optional[PrivacyIncident]:
        """Updates containment progression (DETECTED -> CONTAINING -> CONTAINED -> REMEDIATED -> CLOSED)."""
        inc = self.repo.get_incident(incident_id)
        if not inc:
            return None

        status = ContainmentStatus(new_status.upper()) if new_status.upper() in ContainmentStatus._value2member_map_ else inc.containment_status
        inc.containment_status = status
        saved = self.repo.save_incident(inc)
        self.repo.log_audit("INCIDENT_CONTAINMENT_UPDATED", actor, {
            "incident_id": incident_id,
            "status": status.value
        })
        return saved

    def assess_reportability(self, incident_id: str) -> Dict[str, Any]:
        """Assesses regulatory notification timelines and requirements."""
        inc = self.repo.get_incident(incident_id)
        if not inc:
            return {"error": "INCIDENT_NOT_FOUND"}

        hours_remaining = max(0.0, 72.0 - ((time.time() - inc.created_at) / 3600.0))
        requires_dpa_notice = inc.reportable
        requires_subject_notice = inc.severity == IncidentSeverity.CRITICAL

        return {
            "incident_id": inc.incident_id,
            "severity": inc.severity.value,
            "reportable": inc.reportable,
            "regulatory_notice_deadline_hours": round(hours_remaining, 1),
            "requires_supervisory_authority_notice": requires_dpa_notice,
            "requires_data_subject_communication": requires_subject_notice,
            "affected_assets_count": len(inc.affected_assets),
            "containment_status": inc.containment_status.value
        }
