"""
Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.

Provides production-grade centralized operations observability, multi-tier telemetry ingestion,
hierarchical service registry, automated anomaly detection, incident correlation, root-cause
investigation, impact blast-radius analysis, human-in-the-loop recovery proposals, and postmortems.
"""

from operations_center.models import (
    ServiceCriticality,
    SystemHealthState,
    IncidentSeverity,
    IncidentLifecycleState,
    RecoveryActionStatus,
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
from operations_center.service import OperationsCenterOrchestrator, operations_center_service

__all__ = [
    # Enums
    "ServiceCriticality",
    "SystemHealthState",
    "IncidentSeverity",
    "IncidentLifecycleState",
    "RecoveryActionStatus",
    # Dataclasses
    "ServiceRecord",
    "HealthObservationRecord",
    "MetricRecord",
    "LogRecord",
    "TraceSpanRecord",
    "SLORecord",
    "IncidentAlertRecord",
    "IncidentRecord",
    "RootCauseFinding",
    "ImpactAssessmentRecord",
    "RecoveryProposalRecord",
    "PostIncidentReport",
    # Components
    "OperationsCenterRepository",
    "ServiceInventoryRegistry",
    "SystemHealthAggregator",
    "TelemetryIngestionGateway",
    "ServiceLevelObjectiveManager",
    "AnomalyAndIncidentDetector",
    "IncidentCorrelationEngine",
    "IncidentLifecycleManager",
    "RootCauseInvestigationEngine",
    "ImpactAssessmentEngine",
    "RecoveryRecommendationEngine",
    "RecoveryCoordinatorAdapter",
    "PostIncidentAnalysisEngine",
    "OperationsCenterReporter",
    "OperationsCenterOrchestrator",
    "operations_center_service",
]
