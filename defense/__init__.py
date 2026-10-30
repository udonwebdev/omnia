"""
OMNIA Module 35: Autonomous Cybersecurity, Threat Intelligence & Runtime Defense Subsystem
Exports core models, services, and singleton instances.
"""

from defense.models import (
    SecuritySeverity,
    IndicatorType,
    IndicatorValidationStatus,
    ThreatClassification,
    SecurityPostureState,
    IncidentStatus,
    VALID_INCIDENT_TRANSITIONS,
    ResponseAutonomyLevel,
    ContainmentStatus,
    SecurityTelemetryEvent,
    ThreatIndicator,
    SecurityDetectionRule,
    ThreatAlert,
    SecurityIncident,
    ContainmentAction,
    ForensicEvidenceRecord,
    SecurityPostureAssessment,
)

from defense.telemetry import SecurityEventNormalizer, SecurityTelemetryCollector
from defense.intelligence import ThreatIntelligenceManager, IndicatorValidator
from defense.detector import ThreatDetectionEngine, BehavioralAnomalyDetector
from defense.correlation import ThreatCorrelationEngine
from defense.posture import SecurityPostureAnalyzer
from defense.containment import ContainmentCoordinator
from defense.forensics import ForensicEvidenceManager
from defense.recovery import RecoveryCoordinator
from defense.persistence import DefenseRepository
from defense.service import CyberDefenseService, cyber_defense_service

__all__ = [
    "SecuritySeverity",
    "IndicatorType",
    "IndicatorValidationStatus",
    "ThreatClassification",
    "SecurityPostureState",
    "IncidentStatus",
    "VALID_INCIDENT_TRANSITIONS",
    "ResponseAutonomyLevel",
    "ContainmentStatus",
    "SecurityTelemetryEvent",
    "ThreatIndicator",
    "SecurityDetectionRule",
    "ThreatAlert",
    "SecurityIncident",
    "ContainmentAction",
    "ForensicEvidenceRecord",
    "SecurityPostureAssessment",
    "SecurityEventNormalizer",
    "SecurityTelemetryCollector",
    "ThreatIntelligenceManager",
    "IndicatorValidator",
    "ThreatDetectionEngine",
    "BehavioralAnomalyDetector",
    "ThreatCorrelationEngine",
    "SecurityPostureAnalyzer",
    "ContainmentCoordinator",
    "ForensicEvidenceManager",
    "RecoveryCoordinator",
    "DefenseRepository",
    "CyberDefenseService",
    "cyber_defense_service",
]
