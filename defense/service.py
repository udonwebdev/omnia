"""
OMNIA Module 35: Autonomous Cybersecurity & Runtime Defense Service Facade
Provides the unified CyberDefenseService interface for telemetry ingestion, threat detection,
correlation, incident management, containment, evidence preservation, and event publication.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from defense.models import (
    SecurityTelemetryEvent,
    ThreatIndicator,
    SecurityDetectionRule,
    ThreatAlert,
    SecurityIncident,
    ContainmentAction,
    ForensicEvidenceRecord,
    SecurityPostureAssessment,
    SecuritySeverity,
    IndicatorType,
    ThreatClassification,
    SecurityPostureState,
    IncidentStatus,
    ResponseAutonomyLevel,
    ContainmentStatus,
)
from defense.persistence import DefenseRepository
from defense.telemetry import SecurityTelemetryCollector, SecurityEventNormalizer
from defense.intelligence import ThreatIntelligenceManager, IndicatorValidator
from defense.detector import ThreatDetectionEngine
from defense.correlation import ThreatCorrelationEngine
from defense.posture import SecurityPostureAnalyzer
from defense.containment import ContainmentCoordinator
from defense.forensics import ForensicEvidenceManager
from defense.recovery import RecoveryCoordinator
from events import event_fabric, Event, EventEnvelope, EventPriority, EventSeverity

logger = logging.getLogger("Omnia.Defense.Service")


class CyberDefenseService:
    """Master facade for OMNIA Module 35 Autonomous Cybersecurity & Runtime Defense."""

    def __init__(self, db_path: str = "omnia.db"):
        self.repo = DefenseRepository(db_path=db_path)
        self.normalizer = SecurityEventNormalizer()
        self.collector = SecurityTelemetryCollector(normalizer=self.normalizer)
        self.intel_manager = ThreatIntelligenceManager(validator=IndicatorValidator())
        self.detector = ThreatDetectionEngine(intel_mgr=self.intel_manager)
        self.correlation_engine = ThreatCorrelationEngine()
        self.posture_analyzer = SecurityPostureAnalyzer()
        self.containment_coord = ContainmentCoordinator()
        self.forensics_manager = ForensicEvidenceManager(normalizer=self.normalizer)
        self.recovery_coord = RecoveryCoordinator()
        self.event_bus = event_fabric

    # --- Telemetry Ingestion & Processing ---
    def ingest_security_event(
        self,
        raw_event: Dict[str, Any],
        source_component: str,
        action_category: str,
        outcome: str,
        severity: SecuritySeverity = SecuritySeverity.INFO,
        source_identity: Optional[str] = None,
        node_identity: Optional[str] = None,
        correlation_id: Optional[str] = None,
        resource_reference: Optional[str] = None,
    ) -> Tuple[SecurityTelemetryEvent, List[ThreatAlert], List[SecurityIncident]]:
        """Normalizes raw security telemetry, runs threat detection & correlation, and persists records."""
        event = self.normalizer.normalize(
            raw_event=raw_event,
            source_component=source_component,
            action_category=action_category,
            outcome=outcome,
            severity=severity,
            source_identity=source_identity,
            node_identity=node_identity,
            correlation_id=correlation_id,
            resource_reference=resource_reference,
        )

        # 1. Ingest into collector (tracks heartbeat & buffer)
        self.collector.ingest_event(event)
        self.repo.save_telemetry_event(event)

        # 2. Evaluate against detection rules
        alerts = self.detector.evaluate_event(event)

        # 3. Correlate alerts into incidents
        new_incidents = []
        if alerts:
            new_incidents = self.correlation_engine.correlate_alerts(alerts, event.timestamp)
            for inc in new_incidents:
                self.repo.save_incident(inc)
                # Auto-preserve event as forensic evidence
                evid = self.forensics_manager.preserve_evidence(
                    incident_id=inc.incident_id,
                    artifact_type="telemetry_event",
                    source_identifier=event.event_id,
                    raw_payload=event.to_dict(),
                )
                self.repo.save_evidence_record(evid)
                inc.evidence_ids.append(evid.evidence_id)
                self.repo.save_incident(inc)

                # Emit event fabric notification
                self._emit_event(
                    event_type="security.incident.created",
                    payload={"incident_id": inc.incident_id, "title": inc.title, "severity": inc.severity.value},
                    severity=EventSeverity.CRITICAL if inc.severity == SecuritySeverity.CRITICAL else EventSeverity.WARNING,
                )

        return event, alerts, new_incidents

    # --- Threat Intelligence ---
    def register_threat_indicator(
        self,
        indicator_id: str,
        indicator_type: IndicatorType,
        indicator_value: str,
        source: str,
        confidence: float = 0.5,
        threat_classification: ThreatClassification = ThreatClassification.ANOMALOUS_BEHAVIOR,
    ) -> ThreatIndicator:
        """Ingests and validates a defensive threat intelligence indicator."""
        ind = self.intel_manager.ingest_indicator(
            indicator_id=indicator_id,
            indicator_type=indicator_type,
            indicator_value=indicator_value,
            source=source,
            confidence=confidence,
            threat_classification=threat_classification,
        )
        self.repo.save_indicator(ind)
        return ind

    # --- Posture Assessment ---
    def assess_security_posture(self) -> SecurityPostureAssessment:
        """Evaluates overall system defensive posture, active incidents, and telemetry coverage."""
        active_incidents = self.repo.list_active_incidents()
        missing = self.collector.get_missing_sources()
        assessment = self.posture_analyzer.assess_posture(
            active_incidents=active_incidents,
            recent_alerts=[],
            missing_sources=missing,
        )
        self.repo.save_posture_assessment(assessment)
        return assessment

    # --- Containment & Response ---
    def request_containment(
        self,
        incident_id: str,
        action_type: str,
        target_resource: str,
        scope: str,
        reason: str,
        is_reversible: bool = True,
    ) -> ContainmentAction:
        """Plans a containment response according to active autonomy levels."""
        incident = self.repo.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident '{incident_id}' not found.")

        action = self.containment_coord.plan_containment(
            incident=incident,
            action_type=action_type,
            target_resource=target_resource,
            scope=scope,
            reason=reason,
            is_reversible=is_reversible,
        )
        self.repo.save_containment_action(action)
        incident.containment_action_ids.append(action.action_id)
        if action.status == ContainmentStatus.APPROVAL_PENDING:
            incident.transition_to(IncidentStatus.CONTAINMENT_PENDING, "CyberDefenseService", f"Awaiting approval for {action.action_type}")
        self.repo.save_incident(incident)
        return action

    def authorize_and_execute_containment(
        self,
        action_id: str,
        approval_token: str,
    ) -> Tuple[bool, str]:
        """Applies approval token and executes containment within isolated bounds."""
        action = self.repo.get_containment_action(action_id)
        if not action:
            return False, f"Action '{action_id}' not found."

        self.containment_coord._actions[action_id] = action
        ok = self.containment_coord.record_approval(action_id, approval_token)
        if not ok:
            return False, "Failed to record approval token."

        exec_ok, evidence_text = self.containment_coord.execute_containment(action_id)
        self.repo.save_containment_action(action)

        incident = self.repo.get_incident(action.incident_id)
        if incident and exec_ok:
            if incident.status == IncidentStatus.CONTAINMENT_PENDING:
                incident.transition_to(IncidentStatus.CONTAINED, "CyberDefenseService", f"Containment executed: {evidence_text}")
                self.repo.save_incident(incident)

            # Preserve containment record as evidence
            evid = self.forensics_manager.preserve_evidence(
                incident_id=incident.incident_id,
                artifact_type="containment_verification",
                source_identifier=action_id,
                raw_payload=action.to_dict(),
            )
            self.repo.save_evidence_record(evid)

        return exec_ok, evidence_text

    # --- Recovery ---
    def resolve_incident(
        self,
        incident_id: str,
        actor: str,
        resolution_summary: str,
    ) -> bool:
        """Transitions an incident safely to RESOLVED."""
        incident = self.repo.get_incident(incident_id)
        if not incident:
            return False
        ok = self.recovery_coord.execute_recovery(incident, actor, resolution_summary)
        if ok:
            self.repo.save_incident(incident)
            self._emit_event(
                event_type="security.incident.resolved",
                payload={"incident_id": incident.incident_id, "resolution": resolution_summary},
                severity=EventSeverity.INFO,
            )
        return ok

    def _emit_event(self, event_type: str, payload: Dict[str, Any], severity: EventSeverity = EventSeverity.INFO) -> None:
        try:
            event = Event(
                envelope=EventEnvelope(
                    event_type=event_type,
                    source="defense.service",
                    severity=severity,
                    priority=EventPriority.HIGH if severity in (EventSeverity.CRITICAL, EventSeverity.WARNING) else EventPriority.NORMAL,
                ),
                payload=payload,
            )
            # In sync context, fire-and-forget or task creation
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    asyncio.create_task(self.event_bus.publish(event))
                else:
                    loop.run_until_complete(self.event_bus.publish(event))
            except RuntimeError:
                pass
        except Exception as e:
            logger.warning(f"Benign event fabric notification failure: {e}")


# Singleton instance
cyber_defense_service = CyberDefenseService()
