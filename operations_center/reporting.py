"""
Operations Center Reporter - Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.

Generates structured operations summaries, HUD status briefings, active incident reviews,
SLO error budget rollups, and post-incident digests.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from operations_center.models import (
    SystemHealthState,
    IncidentSeverity,
    IncidentLifecycleState,
    ServiceRecord,
    IncidentRecord,
    SLORecord,
    PostIncidentReport,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("omnia.operations_center.reporting")


class OperationsCenterReporter:
    """
    Compiles executive and engineering operational intelligence briefings,
    SLO health scorecards, and incident digests.
    """

    def __init__(self, repository: OperationsCenterRepository):
        self.repo = repository

    def generate_operations_overview(self) -> Dict[str, Any]:
        """
        Builds a comprehensive real-time dashboard of system health, active incidents,
        and SLO statuses.
        """
        services = self.repo.list_services()
        total_services = len(services)

        health_counts: Dict[str, int] = {
            SystemHealthState.HEALTHY.value: 0,
            SystemHealthState.DEGRADED.value: 0,
            SystemHealthState.UNAVAILABLE.value: 0,
            SystemHealthState.RECOVERING.value: 0,
            SystemHealthState.UNKNOWN.value: 0,
            SystemHealthState.MAINTENANCE.value: 0,
        }

        degraded_services: List[Dict[str, Any]] = []
        for svc in services:
            obs = self.repo.get_latest_health_observation(svc.service_id)
            state = obs.health_state if obs else svc.current_state
            health_counts[state.value] = health_counts.get(state.value, 0) + 1
            if state in (SystemHealthState.DEGRADED, SystemHealthState.UNAVAILABLE):
                degraded_services.append({
                    "service_id": svc.service_id,
                    "service_name": svc.service_name,
                    "criticality": svc.criticality.value,
                    "health_state": state.value,
                    "observed_at": obs.observed_at if obs else None,
                    "status_message": obs.status_message if obs else "No recent telemetry",
                })

        # Active incidents (not CLOSED or RESOLVED)
        active_incidents = [
            inc for inc in self.repo.list_active_incidents()
            if inc.state not in (IncidentLifecycleState.RESOLVED, IncidentLifecycleState.CLOSED)
        ]
        sev_counts: Dict[str, int] = {
            IncidentSeverity.SEV_1_CRITICAL.value: 0,
            IncidentSeverity.SEV_2_HIGH.value: 0,
            IncidentSeverity.SEV_3_MODERATE.value: 0,
            IncidentSeverity.SEV_4_LOW.value: 0,
            IncidentSeverity.INFORMATIONAL.value: 0,
        }
        for inc in active_incidents:
            sev_counts[inc.severity.value] = sev_counts.get(inc.severity.value, 0) + 1

        # SLO rollups
        failing_slos: List[Dict[str, Any]] = []
        with self.repo._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ops_slo_definitions")
            for row in cursor.fetchall():
                if row["error_budget_remaining_pct"] <= 0.0 or row["current_sli_pct"] < row["target_pct"]:
                    failing_slos.append({
                        "slo_id": row["slo_id"],
                        "name": row["name"],
                        "service_id": row["service_id"],
                        "target_pct": row["target_pct"],
                        "current_sli_pct": round(row["current_sli_pct"], 2),
                        "error_budget_remaining_pct": round(row["error_budget_remaining_pct"], 2),
                        "burn_rate": round(row["burn_rate"], 2),
                    })

        # Operational posture evaluation
        if sev_counts[IncidentSeverity.SEV_1_CRITICAL.value] > 0:
            posture = "CRITICAL_OUTAGE"
        elif (
            sev_counts[IncidentSeverity.SEV_2_HIGH.value] > 0
            or health_counts[SystemHealthState.UNAVAILABLE.value] > 0
        ):
            posture = "MAJOR_DISRUPTION"
        elif health_counts[SystemHealthState.DEGRADED.value] > 0 or len(failing_slos) > 0:
            posture = "DEGRADED_OPERATION"
        else:
            posture = "NORMAL_OPERATION"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operational_posture": posture,
            "total_services": total_services,
            "health_distribution": health_counts,
            "active_incidents_count": len(active_incidents),
            "severity_distribution": sev_counts,
            "degraded_services": degraded_services,
            "failing_slos_count": len(failing_slos),
            "failing_slos": failing_slos,
        }

    def format_incident_digest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """
        Builds a comprehensive digest of an incident including alerts, root cause,
        impact, and recovery status.
        """
        inc = self.repo.get_incident(incident_id)
        if not inc:
            return None

        # Fetch findings
        rc = None
        with self.repo._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ops_root_cause_findings WHERE incident_id = ? ORDER BY investigated_at DESC LIMIT 1",
                (incident_id,),
            )
            row = cursor.fetchone()
            if row:
                rc = {
                    "candidate_cause": row["candidate_cause"],
                    "confidence": row["confidence"],
                }

        # Fetch impact
        impact = None
        with self.repo._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ops_impact_assessments WHERE incident_id = ? ORDER BY assessed_at DESC LIMIT 1",
                (incident_id,),
            )
            row = cursor.fetchone()
            if row:
                impact = {
                    "blast_radius_score": row["blast_radius_score"],
                    "data_integrity_risk": row["data_integrity_risk"],
                    "operational_disruption": row["operational_disruption"],
                }

        recovery_proposals = self.repo.list_recovery_proposals_for_incident(incident_id)
        postmortem = self.repo.get_postmortem_for_incident(incident_id)

        return {
            "incident_id": inc.incident_id,
            "title": inc.title,
            "severity": inc.severity.value,
            "state": inc.state.value,
            "primary_service_id": inc.primary_service_id,
            "affected_services": inc.affected_services,
            "correlated_alerts": inc.correlated_alert_ids,
            "created_at": inc.created_at,
            "resolved_at": inc.resolved_at,
            "root_cause": rc,
            "impact": impact,
            "recovery_proposals": [
                {
                    "proposal_id": p.proposal_id,
                    "action_name": p.action_name,
                    "status": p.status.value,
                    "target_service_id": p.target_service_id,
                    "requires_human_approval": p.requires_human_approval,
                }
                for p in recovery_proposals
            ],
            "has_postmortem": postmortem is not None,
        }
