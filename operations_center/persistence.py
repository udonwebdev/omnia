"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Persistence Layer: SQLite Repository for Schema Version 25 Tables.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from operations_center.models import (
    HealthObservationRecord,
    ImpactAssessmentRecord,
    IncidentAlertRecord,
    IncidentLifecycleState,
    IncidentRecord,
    IncidentSeverity,
    LogRecord,
    MetricRecord,
    PostIncidentReport,
    RecoveryActionStatus,
    RecoveryProposalRecord,
    RootCauseFinding,
    SLORecord,
    ServiceCriticality,
    ServiceRecord,
    SystemHealthState,
    TraceSpanRecord,
)


class OperationsCenterRepository:
    """Manages persistent SQLite storage for all Module 40 operations center records."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # Service Inventory & Dependencies
    # -------------------------------------------------------------
    def save_service(self, service: ServiceRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_service_inventory (
                    service_id, service_name, description, version, environment,
                    owner, criticality, health_endpoint, dependencies_json,
                    current_state, last_observed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_id) DO UPDATE SET
                    service_name=excluded.service_name,
                    description=excluded.description,
                    version=excluded.version,
                    environment=excluded.environment,
                    owner=excluded.owner,
                    criticality=excluded.criticality,
                    health_endpoint=excluded.health_endpoint,
                    dependencies_json=excluded.dependencies_json,
                    current_state=excluded.current_state,
                    last_observed_at=excluded.last_observed_at
                """,
                (
                    service.service_id,
                    service.service_name,
                    service.description,
                    service.version,
                    service.environment,
                    service.owner,
                    service.criticality.value,
                    service.health_endpoint,
                    json.dumps(service.dependencies),
                    service.current_state.value,
                    service.last_observed_at,
                    service.created_at,
                ),
            )
            conn.commit()

    def get_service(self, service_id: str) -> Optional[ServiceRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ops_service_inventory WHERE service_id = ?", (service_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ServiceRecord(
                service_id=row["service_id"],
                service_name=row["service_name"],
                description=row["description"],
                version=row["version"],
                environment=row["environment"],
                owner=row["owner"],
                criticality=ServiceCriticality(row["criticality"]),
                health_endpoint=row["health_endpoint"],
                dependencies=json.loads(row["dependencies_json"] or "[]"),
                current_state=SystemHealthState(row["current_state"]),
                last_observed_at=row["last_observed_at"],
                created_at=row["created_at"],
            )

    def list_services(self) -> List[ServiceRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ops_service_inventory ORDER BY criticality ASC, service_id ASC")
            services = []
            for row in cursor.fetchall():
                services.append(
                    ServiceRecord(
                        service_id=row["service_id"],
                        service_name=row["service_name"],
                        description=row["description"],
                        version=row["version"],
                        environment=row["environment"],
                        owner=row["owner"],
                        criticality=ServiceCriticality(row["criticality"]),
                        health_endpoint=row["health_endpoint"],
                        dependencies=json.loads(row["dependencies_json"] or "[]"),
                        current_state=SystemHealthState(row["current_state"]),
                        last_observed_at=row["last_observed_at"],
                        created_at=row["created_at"],
                    )
                )
            return services

    # -------------------------------------------------------------
    # Health Observations
    # -------------------------------------------------------------
    def save_health_observation(self, obs: HealthObservationRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_health_observations (
                    observation_id, service_id, health_state, latency_ms,
                    error_rate, status_message, observed_at, is_stale
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obs.observation_id,
                    obs.service_id,
                    obs.health_state.value,
                    obs.latency_ms,
                    obs.error_rate,
                    obs.status_message,
                    obs.observed_at,
                    1 if obs.is_stale else 0,
                ),
            )
            # Also update service inventory current_state
            conn.execute(
                "UPDATE ops_service_inventory SET current_state = ?, last_observed_at = ? WHERE service_id = ?",
                (obs.health_state.value, obs.observed_at, obs.service_id),
            )
            conn.commit()

    def get_latest_health_observation(self, service_id: str) -> Optional[HealthObservationRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ops_health_observations WHERE service_id = ? ORDER BY observed_at DESC LIMIT 1",
                (service_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return HealthObservationRecord(
                observation_id=row["observation_id"],
                service_id=row["service_id"],
                health_state=SystemHealthState(row["health_state"]),
                latency_ms=row["latency_ms"],
                error_rate=row["error_rate"],
                status_message=row["status_message"],
                observed_at=row["observed_at"],
                is_stale=bool(row["is_stale"]),
            )

    # -------------------------------------------------------------
    # Telemetry Ingestion (Metrics, Logs, Spans)
    # -------------------------------------------------------------
    def save_metric(self, metric: MetricRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_telemetry_metrics (
                    metric_id, service_id, metric_name, value, unit, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    metric.metric_id,
                    metric.service_id,
                    metric.metric_name,
                    metric.value,
                    metric.unit,
                    metric.timestamp,
                ),
            )
            conn.commit()

    def query_metrics(self, service_id: str, metric_name: str, limit: int = 50) -> List[MetricRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM ops_telemetry_metrics
                WHERE service_id = ? AND metric_name = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (service_id, metric_name, limit),
            )
            metrics = []
            for row in cursor.fetchall():
                metrics.append(
                    MetricRecord(
                        metric_id=row["metric_id"],
                        service_id=row["service_id"],
                        metric_name=row["metric_name"],
                        value=row["value"],
                        unit=row["unit"],
                        timestamp=row["timestamp"],
                    )
                )
            return metrics

    def save_log(self, log: LogRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_telemetry_logs (
                    log_id, service_id, level, message, error_category, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    log.log_id,
                    log.service_id,
                    log.level,
                    log.message,
                    log.error_category,
                    log.timestamp,
                ),
            )
            conn.commit()

    def save_span(self, span: TraceSpanRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_telemetry_spans (
                    span_id, trace_id, service_id, operation_name,
                    duration_ms, status_code, parent_span_id, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span.span_id,
                    span.trace_id,
                    span.service_id,
                    span.operation_name,
                    span.duration_ms,
                    span.status_code,
                    span.parent_span_id,
                    span.timestamp,
                ),
            )
            conn.commit()

    # -------------------------------------------------------------
    # SLOs
    # -------------------------------------------------------------
    def save_slo(self, slo: SLORecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_slo_definitions (
                    slo_id, service_id, name, target_pct, current_sli_pct,
                    error_budget_remaining_pct, burn_rate, assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(slo_id) DO UPDATE SET
                    current_sli_pct=excluded.current_sli_pct,
                    error_budget_remaining_pct=excluded.error_budget_remaining_pct,
                    burn_rate=excluded.burn_rate,
                    assessed_at=excluded.assessed_at
                """,
                (
                    slo.slo_id,
                    slo.service_id,
                    slo.name,
                    slo.target_pct,
                    slo.current_sli_pct,
                    slo.error_budget_remaining_pct,
                    slo.burn_rate,
                    slo.assessed_at,
                ),
            )
            conn.commit()

    def get_slos_for_service(self, service_id: str) -> List[SLORecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ops_slo_definitions WHERE service_id = ?", (service_id,))
            slos = []
            for row in cursor.fetchall():
                slos.append(
                    SLORecord(
                        slo_id=row["slo_id"],
                        service_id=row["service_id"],
                        name=row["name"],
                        target_pct=row["target_pct"],
                        current_sli_pct=row["current_sli_pct"],
                        error_budget_remaining_pct=row["error_budget_remaining_pct"],
                        burn_rate=row["burn_rate"],
                        assessed_at=row["assessed_at"],
                    )
                )
            return slos

    # -------------------------------------------------------------
    # Incident Alerts & Incidents
    # -------------------------------------------------------------
    def save_alert(self, alert: IncidentAlertRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_incident_alerts (
                    alert_id, service_id, alert_name, severity, symptom_description,
                    supporting_metric_value, correlated_incident_id, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alert_id) DO UPDATE SET
                    correlated_incident_id=excluded.correlated_incident_id
                """,
                (
                    alert.alert_id,
                    alert.service_id,
                    alert.alert_name,
                    alert.severity.value,
                    alert.symptom_description,
                    alert.supporting_metric_value,
                    alert.correlated_incident_id,
                    alert.detected_at,
                ),
            )
            conn.commit()

    def list_uncorrelated_alerts(self) -> List[IncidentAlertRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ops_incident_alerts WHERE correlated_incident_id IS NULL ORDER BY detected_at ASC"
            )
            alerts = []
            for row in cursor.fetchall():
                alerts.append(
                    IncidentAlertRecord(
                        alert_id=row["alert_id"],
                        service_id=row["service_id"],
                        alert_name=row["alert_name"],
                        severity=IncidentSeverity(row["severity"]),
                        symptom_description=row["symptom_description"],
                        supporting_metric_value=row["supporting_metric_value"],
                        correlated_incident_id=row["correlated_incident_id"],
                        detected_at=row["detected_at"],
                    )
                )
            return alerts

    def save_incident(self, incident: IncidentRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_incidents (
                    incident_id, title, severity, state, primary_service_id,
                    affected_services_json, correlated_alert_ids_json, assigned_to,
                    created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    severity=excluded.severity,
                    state=excluded.state,
                    affected_services_json=excluded.affected_services_json,
                    correlated_alert_ids_json=excluded.correlated_alert_ids_json,
                    assigned_to=excluded.assigned_to,
                    resolved_at=excluded.resolved_at
                """,
                (
                    incident.incident_id,
                    incident.title,
                    incident.severity.value,
                    incident.state.value,
                    incident.primary_service_id,
                    json.dumps(incident.affected_services),
                    json.dumps(incident.correlated_alert_ids),
                    incident.assigned_to,
                    incident.created_at,
                    incident.resolved_at,
                ),
            )
            conn.commit()

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ops_incidents WHERE incident_id = ?", (incident_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return IncidentRecord(
                incident_id=row["incident_id"],
                title=row["title"],
                severity=IncidentSeverity(row["severity"]),
                state=IncidentLifecycleState(row["state"]),
                primary_service_id=row["primary_service_id"],
                affected_services=json.loads(row["affected_services_json"] or "[]"),
                correlated_alert_ids=json.loads(row["correlated_alert_ids_json"] or "[]"),
                assigned_to=row["assigned_to"],
                created_at=row["created_at"],
                resolved_at=row["resolved_at"],
            )

    # -------------------------------------------------------------
    # Root Cause & Impact
    # -------------------------------------------------------------
    def save_root_cause(self, finding: RootCauseFinding) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_root_cause_findings (
                    finding_id, incident_id, candidate_cause, confidence,
                    supporting_evidence_json, contradictory_evidence_json, investigated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.finding_id,
                    finding.incident_id,
                    finding.candidate_cause,
                    finding.confidence,
                    json.dumps(finding.supporting_evidence),
                    json.dumps(finding.contradictory_evidence),
                    finding.investigated_at,
                ),
            )
            conn.commit()

    def save_impact_assessment(self, impact: ImpactAssessmentRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_impact_assessments (
                    assessment_id, incident_id, blast_radius_score, affected_workflows_json,
                    data_integrity_risk, operational_disruption, financial_exposure_estimate,
                    assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    impact.assessment_id,
                    impact.incident_id,
                    impact.blast_radius_score,
                    json.dumps(impact.affected_workflows),
                    impact.data_integrity_risk,
                    impact.operational_disruption,
                    impact.financial_exposure_estimate,
                    impact.assessed_at,
                ),
            )
            conn.commit()

    # -------------------------------------------------------------
    # Recovery Proposals & Postmortems
    # -------------------------------------------------------------
    def save_recovery_proposal(self, prop: RecoveryProposalRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_recovery_proposals (
                    proposal_id, incident_id, target_service_id, action_name,
                    rationale, expected_benefit, risk_level, requires_human_approval,
                    status, approval_token, approved_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    status=excluded.status,
                    approval_token=excluded.approval_token,
                    approved_by=excluded.approved_by
                """,
                (
                    prop.proposal_id,
                    prop.incident_id,
                    prop.target_service_id,
                    prop.action_name,
                    prop.rationale,
                    prop.expected_benefit,
                    prop.risk_level,
                    1 if prop.requires_human_approval else 0,
                    prop.status.value,
                    prop.approval_token,
                    prop.approved_by,
                    prop.created_at,
                ),
            )
            conn.commit()

    def get_recovery_proposal(self, proposal_id: str) -> Optional[RecoveryProposalRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ops_recovery_proposals WHERE proposal_id = ?", (proposal_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return RecoveryProposalRecord(
                proposal_id=row["proposal_id"],
                incident_id=row["incident_id"],
                target_service_id=row["target_service_id"],
                action_name=row["action_name"],
                rationale=row["rationale"],
                expected_benefit=row["expected_benefit"],
                risk_level=row["risk_level"],
                requires_human_approval=bool(row["requires_human_approval"]),
                status=RecoveryActionStatus(row["status"]),
                approval_token=row["approval_token"],
                approved_by=row["approved_by"],
                created_at=row["created_at"],
            )

    def save_postmortem(self, pm: PostIncidentReport) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO ops_postmortem_reports (
                    report_id, incident_id, title, summary, root_cause,
                    timeline_events_json, what_went_well_json, what_failed_json,
                    action_items_json, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id) DO UPDATE SET
                    title=excluded.title,
                    summary=excluded.summary,
                    root_cause=excluded.root_cause,
                    timeline_events_json=excluded.timeline_events_json,
                    what_went_well_json=excluded.what_went_well_json,
                    what_failed_json=excluded.what_failed_json,
                    action_items_json=excluded.action_items_json,
                    published_at=excluded.published_at
                """,
                (
                    pm.report_id,
                    pm.incident_id,
                    pm.title,
                    pm.summary,
                    pm.root_cause,
                    json.dumps(pm.timeline_events),
                    json.dumps(pm.what_went_well),
                    json.dumps(pm.what_failed),
                    json.dumps(pm.action_items),
                    pm.published_at,
                ),
            )
            conn.commit()

    def list_active_incidents(self) -> List[IncidentRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM ops_incidents
                WHERE state NOT IN ('RESOLVED', 'CLOSED')
                ORDER BY created_at DESC
                """
            )
            incidents = []
            for row in cursor.fetchall():
                incidents.append(
                    IncidentRecord(
                        incident_id=row["incident_id"],
                        title=row["title"],
                        severity=IncidentSeverity(row["severity"]),
                        state=IncidentLifecycleState(row["state"]),
                        primary_service_id=row["primary_service_id"],
                        affected_services=json.loads(row["affected_services_json"] or "[]"),
                        correlated_alert_ids=json.loads(row["correlated_alert_ids_json"] or "[]"),
                        assigned_to=row["assigned_to"],
                        created_at=row["created_at"],
                        resolved_at=row["resolved_at"],
                    )
                )
            return incidents

    def list_recovery_proposals_for_incident(self, incident_id: str) -> List[RecoveryProposalRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ops_recovery_proposals WHERE incident_id = ? ORDER BY created_at DESC",
                (incident_id,)
            )
            proposals = []
            for row in cursor.fetchall():
                proposals.append(
                    RecoveryProposalRecord(
                        proposal_id=row["proposal_id"],
                        incident_id=row["incident_id"],
                        target_service_id=row["target_service_id"],
                        action_name=row["action_name"],
                        rationale=row["rationale"],
                        expected_benefit=row["expected_benefit"],
                        risk_level=row["risk_level"],
                        requires_human_approval=bool(row["requires_human_approval"]),
                        status=RecoveryActionStatus(row["status"]),
                        approval_token=row["approval_token"],
                        approved_by=row["approved_by"],
                        created_at=row["created_at"],
                    )
                )
            return proposals

    def get_postmortem_for_incident(self, incident_id: str) -> Optional[PostIncidentReport]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM ops_postmortem_reports WHERE incident_id = ? ORDER BY published_at DESC LIMIT 1",
                (incident_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return PostIncidentReport(
                report_id=row["report_id"],
                incident_id=row["incident_id"],
                title=row["title"],
                summary=row["summary"],
                root_cause=row["root_cause"],
                timeline_events=json.loads(row["timeline_events_json"] or "[]"),
                what_went_well=json.loads(row["what_went_well_json"] or "[]"),
                what_failed=json.loads(row["what_failed_json"] or "[]"),
                action_items=json.loads(row["action_items_json"] or "[]"),
                published_at=row["published_at"],
            )
