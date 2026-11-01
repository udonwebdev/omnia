"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Central Security Operations Orchestrator - service.py
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from secops.alerts import AlertManager
from secops.baselines import BehavioralBaselineEngine
from secops.containment_gateway import ContainmentGateway
from secops.correlation import EventCorrelationEngine
from secops.detection_engine import ThreatDetectionEngine
from secops.evidence import DetectionEvaluationEngine, EvidencePreservationEngine
from secops.incidents import IncidentManager
from secops.models import (
    AlertStatus,
    BehavioralBaseline,
    ContainmentActionRecord,
    CorrelationGraph,
    DefensiveResponsePlan,
    DetectionRule,
    EvidencePackage,
    IncidentPriority,
    IncidentStatus,
    IndicatorType,
    OperationalRisk,
    ResponseActionType,
    RuleType,
    SecurityAlert,
    SecurityEvent,
    SecurityIncident,
    SecurityInvestigation,
    SecuritySeverity,
    TelemetrySource,
    ThreatIntelIndicator,
)
from secops.normalizer import SecurityEventNormalizer
from secops.persistence import SecOpsRepository
from secops.response_planner import DefensiveResponsePlanner
from secops.risk_scorer import SecurityRiskScorer
from secops.sources import TelemetrySourceRegistry
from secops.threat_hunting import ScopedThreatHunter
from secops.threat_intel import ThreatIntelEnricher

try:
    from events import event_fabric, EventFabric
except Exception:
    event_fabric = None
    EventFabric = Any

logger = logging.getLogger("Omnia.SecOps.Service")


class SecurityOperationsOrchestrator:
    """
    Unified SOC Intelligence Facade coordinating telemetry ingestion, behavioral baselining,
    hybrid detection, event correlation, threat hunting, governed containment, and evidence preservation.
    """

    def __init__(self, db_path: str = "omnia.db", event_fabric_instance: Optional[EventFabric] = None):
        self.repo = SecOpsRepository(db_path=db_path)
        self.event_fabric = event_fabric_instance or event_fabric

        self.source_registry = TelemetrySourceRegistry(self.repo)
        self.normalizer = SecurityEventNormalizer(self.repo)
        self.baselines = BehavioralBaselineEngine(self.repo)
        self.detection_engine = ThreatDetectionEngine(self.repo, self.baselines)
        self.correlation_engine = EventCorrelationEngine(self.repo)
        self.threat_intel = ThreatIntelEnricher(self.repo)
        self.risk_scorer = SecurityRiskScorer(self.repo)
        self.alert_manager = AlertManager(self.repo)
        self.hunter = ScopedThreatHunter(self.repo)
        self.incident_manager = IncidentManager(self.repo)
        self.response_planner = DefensiveResponsePlanner(self.repo)
        self.containment_gateway = ContainmentGateway(self.repo)
        self.evidence_engine = EvidencePreservationEngine(self.repo)
        self.evaluator = DetectionEvaluationEngine(self.repo)

        self._seed_default_rules()

    def _seed_default_rules(self) -> None:
        """Seeds standard defensive detection rules if not already present."""
        default_rules = [
            DetectionRule(
                rule_id="RULE-AUTH-001",
                name="Brute Force / Password Spray Attack Pattern",
                description="Repeated failed authentication attempts against accounts.",
                rule_type=RuleType.DETERMINISTIC,
                severity=SecuritySeverity.HIGH,
                confidence_score=0.9,
                threshold_params={"target_event_type": "USER_LOGIN_FAILED"},
                mitre_attack_technique="T1110",
            ),
            DetectionRule(
                rule_id="RULE-PRIV-001",
                name="Suspicious Administrator Privilege Escalation",
                description="Unauthorized assignment of privileged administrative roles.",
                rule_type=RuleType.DETERMINISTIC,
                severity=SecuritySeverity.CRITICAL,
                confidence_score=0.95,
                threshold_params={"target_event_type": "ROLE_ASSIGNMENT"},
                mitre_attack_technique="T1078.004",
            ),
            DetectionRule(
                rule_id="RULE-TAMPER-001",
                name="Security Audit Logging Tampering",
                description="Disabling or tampering with central security event collection.",
                rule_type=RuleType.DETERMINISTIC,
                severity=SecuritySeverity.CRITICAL,
                confidence_score=0.98,
                threshold_params={"target_event_type": "CONFIG_CHANGE"},
                mitre_attack_technique="T1562.001",
            ),
            DetectionRule(
                rule_id="RULE-ANOM-001",
                name="Abnormal API Traffic Volume Spikes",
                description="Statistical surge in API request volume exceeding baseline limits.",
                rule_type=RuleType.ANOMALY,
                severity=SecuritySeverity.MEDIUM,
                confidence_score=0.85,
                threshold_params={"metric_name": "api_request_rate", "z_threshold": 3.0},
                mitre_attack_technique="T1020",
            ),
            DetectionRule(
                rule_id="RULE-NET-001",
                name="Suspicious Outbound C2 Network Activity",
                description="Egress connection attempting communication with suspicious network ports.",
                rule_type=RuleType.DETERMINISTIC,
                severity=SecuritySeverity.HIGH,
                confidence_score=0.9,
                threshold_params={"target_event_type": "EGRESS_CONNECTION"},
                mitre_attack_technique="T1071",
            ),
        ]
        for r in default_rules:
            if not self.repo.get_rule(r.rule_id):
                self.repo.save_rule(r)

    # ------------------------------------------------------------------
    # High-Level Operational Workflows
    # ------------------------------------------------------------------
    def ingest_and_detect(
        self,
        source_id: str,
        provider: str,
        raw_payload: Dict[str, Any],
        environment: str = "PRODUCTION",
    ) -> List[SecurityAlert]:
        """
        Ingests a raw telemetry event, normalizes it, updates baseline statistics if applicable,
        and evaluates active detection rules.
        """
        event = self.normalizer.normalize_event(
            source_id=source_id,
            provider=provider,
            raw_payload=raw_payload,
            environment=environment,
        )
        self.source_registry.mark_successful_ingestion(source_id)

        # Baseline update if numerical metric is present
        if event.actor_id and "api_request_rate" in event.metadata:
            self.baselines.update_entity_metric(
                entity_id=event.actor_id,
                entity_type="USER",
                metric_name="api_request_rate",
                observed_value=float(event.metadata["api_request_rate"]),
            )

        # Evaluate detection rules
        alerts = self.detection_engine.evaluate_events([event])
        return alerts


# Global singleton instance
secops_service = SecurityOperationsOrchestrator()
