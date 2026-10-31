"""
Operations Center Orchestrator - Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.

Main entry point and orchestrator for all Module 40 capabilities.
Integrates telemetry, health, SLOs, anomaly detection, incident correlation, root-cause investigation,
impact assessment, recovery proposals with Module 20 human approval gate, and postmortems.
"""

from typing import Dict, Any, List, Optional
import uuid
import logging
from datetime import datetime, timezone

from operations_center.models import (
    ServiceRecord,
    HealthObservationRecord,
    MetricRecord,
    LogRecord,
    TraceSpanRecord,
    SLORecord,
    IncidentAlertRecord,
    IncidentRecord,
    RootCauseFinding,
    ImpactAssessmentRecord,
    RecoveryProposalRecord,
    PostIncidentReport,
    ServiceCriticality,
    SystemHealthState,
    IncidentSeverity,
    IncidentLifecycleState,
    RecoveryActionStatus,
)
from operations_center.persistence import OperationsCenterRepository
from operations_center.inventory import ServiceInventoryRegistry
from operations_center.health import SystemHealthAggregator
from operations_center.telemetry import TelemetryIngestionGateway
from operations_center.slo import ServiceLevelObjectiveManager
from operations_center.detector import AnomalyAndIncidentDetector
from operations_center.correlation import IncidentCorrelationEngine
from operations_center.lifecycle import IncidentLifecycleManager
from operations_center.investigation import RootCauseInvestigationEngine
from operations_center.impact import ImpactAssessmentEngine
from operations_center.recovery import RecoveryRecommendationEngine
from operations_center.coordinator import RecoveryCoordinatorAdapter
from operations_center.postmortem import PostIncidentAnalysisEngine
from operations_center.reporting import OperationsCenterReporter

# Module 10 Event Fabric integration
try:
    from event_fabric.service import event_fabric_service
except ImportError:
    event_fabric_service = None

logger = logging.getLogger("omnia.operations_center.service")


class OperationsCenterOrchestrator:
    """
    Unified facade and controller for the Module 40 Autonomous Operations Center.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.repo = OperationsCenterRepository(db_path=db_path or "omnia.db")
        self.inventory = ServiceInventoryRegistry(self.repo)
        self.health = SystemHealthAggregator(self.repo)
        self.telemetry = TelemetryIngestionGateway(self.repo)
        self.slo = ServiceLevelObjectiveManager(self.repo)
        self.detector = AnomalyAndIncidentDetector(self.repo)
        self.correlation = IncidentCorrelationEngine(self.repo)
        self.lifecycle = IncidentLifecycleManager(self.repo)
        self.investigation = RootCauseInvestigationEngine(self.repo)
        self.impact = ImpactAssessmentEngine(self.repo)
        self.recovery = RecoveryRecommendationEngine(self.repo)
        self.coordinator = RecoveryCoordinatorAdapter(self.repo)
        self.postmortem = PostIncidentAnalysisEngine(self.repo)
        self.reporter = OperationsCenterReporter(self.repo)

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publishes an event to the Omnia Event Fabric if available."""
        if event_fabric_service:
            try:
                event_fabric_service.publish(
                    topic=f"operations.{event_type}",
                    payload=payload,
                    source="module_40_operations_center"
                )
            except Exception as e:
                logger.warning("Failed to publish event %s to event fabric: %s", event_type, e)

    # --- 1. Service Inventory ---
    def register_service(
        self,
        service_id: str,
        service_name: str,
        criticality: ServiceCriticality = ServiceCriticality.HIGH,
        description: str = "",
        version: str = "1.0.0",
        environment: str = "production",
        owner: str = "omnia-core",
        owner_subsystem: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        endpoints: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ServiceRecord:
        health_ep = endpoints[0] if endpoints else None
        record = self.inventory.register_service(
            service_id=service_id,
            service_name=service_name,
            description=description or f"Operational service {service_name}",
            version=version,
            environment=environment,
            owner=owner_subsystem or owner,
            criticality=criticality,
            health_endpoint=health_ep,
            dependencies=dependencies,
        )
        self._publish_event("service.registered", {"service_id": service_id, "name": service_name})
        return record

    def list_services(self) -> List[ServiceRecord]:
        return self.repo.list_services()

    # --- 2. Health Monitoring ---
    def record_health_observation(
        self,
        service_id: str,
        health_state: SystemHealthState = SystemHealthState.HEALTHY,
        latency_ms: float = 0.0,
        error_rate: float = 0.0,
        status_message: str = "Nominal",
        check_type: str = "SYNTHETIC",
        cpu_usage_pct: float = 0.0,
        memory_usage_pct: float = 0.0,
        issues: Optional[List[str]] = None,
    ) -> HealthObservationRecord:
        msg = "; ".join(issues) if issues else status_message
        obs = self.health.record_health_observation(
            service_id=service_id,
            health_state=health_state,
            latency_ms=latency_ms,
            error_rate=error_rate,
            status_message=msg,
        )
        if obs.health_state in (SystemHealthState.DEGRADED, SystemHealthState.UNAVAILABLE):
            self._publish_event("health.degraded", {
                "service_id": service_id,
                "state": obs.health_state.value,
                "status_message": obs.status_message,
            })
        return obs

    def get_service_health(self, service_id: str, max_freshness_seconds: float = 300.0) -> Optional[HealthObservationRecord]:
        try:
            return self.health.evaluate_service_health(service_id, max_freshness_seconds=max_freshness_seconds)
        except Exception:
            return None

    # --- 3. Telemetry Ingestion ---
    def ingest_metric(
        self,
        service_id: str,
        metric_name: str,
        metric_value: Optional[float] = None,
        value: Optional[float] = None,
        unit: str = "count",
        dimensions: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> MetricRecord:
        val = metric_value if metric_value is not None else (value if value is not None else 0.0)
        return self.telemetry.ingest_metric(
            service_id=service_id,
            metric_name=metric_name,
            value=val,
            unit=unit,
            timestamp=timestamp,
        )

    def ingest_log(
        self,
        service_id: str,
        level: str,
        message: str,
        error_category: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> LogRecord:
        return self.telemetry.ingest_log(
            service_id=service_id,
            level=level,
            message=message,
            error_category=error_category,
            timestamp=timestamp,
        )

    def ingest_trace_span(
        self,
        trace_id: str,
        span_id: str,
        service_id: str,
        operation_name: str,
        duration_ms: float,
        parent_span_id: Optional[str] = None,
        status_code: Any = 200,
        tags: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> TraceSpanRecord:
        sc = 200 if str(status_code).upper() == "OK" else (int(status_code) if str(status_code).isdigit() else 500)
        return self.telemetry.ingest_span(
            trace_id=trace_id,
            service_id=service_id,
            operation_name=operation_name,
            duration_ms=duration_ms,
            status_code=sc,
            parent_span_id=parent_span_id,
            span_id=span_id,
            timestamp=timestamp,
        )

    # --- 4. SLO Management ---
    def register_slo(
        self,
        slo_id: str,
        slo_name: str,
        service_id: str,
        target_sli_percent: float,
        sli_metric_name: str = "",
        window_days: int = 30,
    ) -> SLORecord:
        return self.slo.define_slo(
            service_id=service_id,
            name=slo_name,
            target_pct=target_sli_percent,
            slo_id=slo_id,
        )

    def update_slo_metrics(
        self,
        slo_id: str,
        sli_current_percent: float,
        budget_remaining_percent: float,
        burn_rate_30d: float,
    ) -> Optional[SLORecord]:
        slo = None
        with self.repo._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ops_slo_definitions WHERE slo_id = ?", (slo_id,))
            row = cursor.fetchone()
            if row:
                slo = SLORecord(
                    slo_id=row["slo_id"],
                    service_id=row["service_id"],
                    name=row["name"],
                    target_pct=row["target_pct"],
                    current_sli_pct=sli_current_percent,
                    error_budget_remaining_pct=budget_remaining_percent,
                    burn_rate=burn_rate_30d,
                    assessed_at=datetime.now(timezone.utc).isoformat(),
                )
                self.repo.save_slo(slo)
        return slo

    # --- 5. Anomaly Detection & Incident Correlation ---
    def raise_alert(
        self,
        alert_name: str,
        service_id: str,
        severity: IncidentSeverity = IncidentSeverity.SEV_2_HIGH,
        description: str = "",
        metric_name: Optional[str] = None,
        metric_value: Optional[float] = None,
        threshold_value: Optional[float] = None,
    ) -> IncidentAlertRecord:
        aid = f"alt-{uuid.uuid4().hex[:8]}"
        val = metric_value if metric_value is not None else 0.0
        alert = IncidentAlertRecord(
            alert_id=aid,
            service_id=service_id,
            alert_name=alert_name,
            severity=severity,
            symptom_description=description,
            supporting_metric_value=val,
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_alert(alert)
        self._publish_event("alert.raised", {
            "alert_id": alert.alert_id,
            "service_id": service_id,
            "severity": severity.value,
            "alert_name": alert_name,
        })
        return alert

    def correlate_active_alerts(self) -> List[IncidentRecord]:
        """
        Groups all unassigned alerts into correlated incidents.
        """
        incidents = self.correlation.correlate_active_alerts()
        for inc in incidents:
            self._publish_event("incident.created", {
                "incident_id": inc.incident_id,
                "title": inc.title,
                "severity": inc.severity.value,
                "primary_service_id": inc.primary_service_id,
            })
        return incidents

    # --- 6. Incident Lifecycle Management ---
    def transition_incident_state(
        self,
        incident_id: str,
        new_state: IncidentLifecycleState,
        reason: str = "",
        operator_id: Optional[str] = None,
    ) -> IncidentRecord:
        inc = self.lifecycle.transition_state(incident_id, new_state, operator_id=operator_id)
        self._publish_event("incident.transitioned", {
            "incident_id": inc.incident_id,
            "new_state": new_state.value,
            "reason": reason,
        })
        return inc

    # --- 7. Investigation, Impact, & Recovery ---
    def investigate_root_cause(self, incident_id: str) -> RootCauseFinding:
        finding = self.investigation.investigate_incident(incident_id)
        self._publish_event("incident.root_cause_identified", {
            "incident_id": incident_id,
            "cause": finding.candidate_cause,
            "confidence": finding.confidence,
        })
        return finding

    def assess_impact(self, incident_id: str) -> ImpactAssessmentRecord:
        assessment = self.impact.assess_incident_impact(incident_id)
        self._publish_event("incident.impact_assessed", {
            "incident_id": incident_id,
            "blast_score": assessment.blast_radius_score,
            "disruption": assessment.operational_disruption,
        })
        return assessment

    def generate_recovery_proposals(self, incident_id: str) -> List[RecoveryProposalRecord]:
        proposals = self.recovery.generate_recovery_proposals(incident_id)
        for p in proposals:
            self._publish_event("recovery.proposed", {
                "incident_id": incident_id,
                "proposal_id": p.proposal_id,
                "action_name": p.action_name,
            })
        return proposals

    def execute_recovery_action(
        self,
        proposal_id: str,
        approval_token: Optional[str] = None,
        operator_notes: str = "",
        approver_id: str = "operations_coordinator",
    ) -> Dict[str, Any]:
        """
        Executes a recovery proposal. Crucially enforces Module 20 human approval token gate.
        """
        try:
            prop = self.coordinator.authorize_and_dispatch_recovery(
                proposal_id=proposal_id,
                approver_id=approver_id,
                approval_token=approval_token or "",
            )
            self._publish_event("recovery.executed", {
                "proposal_id": proposal_id,
                "status": "SUCCESS",
            })
            return {
                "status": "SUCCESS",
                "proposal_id": proposal_id,
                "action_name": prop.action_name,
                "approval_token": prop.approval_token,
                "approved_by": prop.approved_by,
            }
        except PermissionError as pe:
            return {
                "status": "APPROVAL_REQUIRED",
                "proposal_id": proposal_id,
                "reason": str(pe),
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "proposal_id": proposal_id,
                "reason": str(e),
            }

    # --- 8. Post-Incident Review & Analysis ---
    def compile_postmortem(
        self,
        incident_id: str,
        action_items: Optional[List[str]] = None,
    ) -> PostIncidentReport:
        report = self.postmortem.generate_postmortem(incident_id=incident_id)
        if action_items:
            report.action_items.extend(action_items)
            self.repo.save_postmortem(report)
        self._publish_event("incident.postmortem_compiled", {
            "incident_id": incident_id,
            "report_id": report.report_id,
        })
        return report

    # --- 9. Reporting & HUD ---
    def get_operations_overview(self) -> Dict[str, Any]:
        return self.reporter.generate_operations_overview()

    def get_incident_digest(self, incident_id: str) -> Optional[Dict[str, Any]]:
        return self.reporter.format_incident_digest(incident_id)


# Global singleton instance
operations_center_service = OperationsCenterOrchestrator()
