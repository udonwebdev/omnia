"""
OMNIA Module 35: SQLite Persistence Repository for Cybersecurity & Runtime Defense
Stores security telemetry, threat intelligence indicators, rules, incidents,
containment actions, forensic evidence, and posture assessments.
"""

import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from defense.models import (
    SecurityTelemetryEvent,
    ThreatIndicator,
    SecurityDetectionRule,
    SecurityIncident,
    ContainmentAction,
    ForensicEvidenceRecord,
    SecurityPostureAssessment,
    SecuritySeverity,
    IndicatorType,
    IndicatorValidationStatus,
    ThreatClassification,
    SecurityPostureState,
    IncidentStatus,
    ResponseAutonomyLevel,
    ContainmentStatus,
)

logger = logging.getLogger("Omnia.Defense.Persistence")


class DefenseRepository:
    """Manages SQLite storage for all defense and security telemetry subsystem state."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Ensures Schema Version 17 tables are initialized if migrations haven't run yet."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_telemetry_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                source_component TEXT NOT NULL,
                action_category TEXT NOT NULL,
                outcome TEXT NOT NULL,
                severity TEXT NOT NULL,
                timestamp REAL NOT NULL,
                schema_version INTEGER NOT NULL,
                source_identity TEXT,
                node_identity TEXT,
                correlation_id TEXT,
                resource_reference TEXT,
                details TEXT NOT NULL,
                data_classification TEXT NOT NULL,
                signature TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS threat_intelligence_indicators (
                indicator_id TEXT PRIMARY KEY,
                indicator_type TEXT NOT NULL,
                indicator_value TEXT NOT NULL,
                source TEXT NOT NULL,
                source_reliability REAL NOT NULL,
                confidence REAL NOT NULL,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                expires_at REAL,
                context TEXT NOT NULL,
                threat_classification TEXT NOT NULL,
                validation_status TEXT NOT NULL,
                applicable_scope TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_detection_rules (
                rule_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                threat_classification TEXT NOT NULL,
                severity TEXT NOT NULL,
                required_telemetry_types TEXT NOT NULL,
                matching_criteria TEXT NOT NULL,
                confidence REAL NOT NULL,
                version INTEGER NOT NULL,
                is_active INTEGER NOT NULL,
                suppression_window_sec REAL NOT NULL,
                expected_response_level INTEGER NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_incidents (
                incident_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                threat_classification TEXT NOT NULL,
                severity TEXT NOT NULL,
                confidence REAL NOT NULL,
                detection_source TEXT NOT NULL,
                affected_assets TEXT NOT NULL,
                related_event_ids TEXT NOT NULL,
                evidence_ids TEXT NOT NULL,
                status TEXT NOT NULL,
                assigned_owner TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                containment_action_ids TEXT NOT NULL,
                resolution_summary TEXT,
                audit_history TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_containment_actions (
                action_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target_resource TEXT NOT NULL,
                scope TEXT NOT NULL,
                reason TEXT NOT NULL,
                response_level INTEGER NOT NULL,
                status TEXT NOT NULL,
                is_reversible INTEGER NOT NULL,
                approval_request_id TEXT,
                approval_token TEXT,
                requested_at REAL NOT NULL,
                executed_at REAL,
                verified_at REAL,
                verification_evidence TEXT,
                error_message TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS forensic_evidence_records (
                evidence_id TEXT PRIMARY KEY,
                incident_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                source_identifier TEXT NOT NULL,
                collector_identity TEXT NOT NULL,
                integrity_digest TEXT NOT NULL,
                raw_payload_redacted TEXT NOT NULL,
                collected_at REAL NOT NULL,
                data_classification TEXT NOT NULL,
                chain_of_custody TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_posture_assessments (
                assessment_id TEXT PRIMARY KEY,
                overall_state TEXT NOT NULL,
                score REAL NOT NULL,
                active_incidents_count INTEGER NOT NULL,
                critical_alerts_count INTEGER NOT NULL,
                monitored_sources_count INTEGER NOT NULL,
                missing_sources TEXT NOT NULL,
                component_posture TEXT NOT NULL,
                recommended_remediations TEXT NOT NULL,
                timestamp REAL NOT NULL
            );
            """)
            conn.commit()

    # --- Telemetry Events ---
    def save_telemetry_event(self, event: SecurityTelemetryEvent) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO security_telemetry_events (
                event_id, event_type, source_component, action_category, outcome,
                severity, timestamp, schema_version, source_identity, node_identity,
                correlation_id, resource_reference, details, data_classification, signature
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id,
                event.event_type,
                event.source_component,
                event.action_category,
                event.outcome,
                event.severity.value if isinstance(event.severity, SecuritySeverity) else str(event.severity),
                event.timestamp,
                event.schema_version,
                event.source_identity,
                event.node_identity,
                event.correlation_id,
                event.resource_reference,
                json.dumps(event.details),
                event.data_classification,
                event.signature,
            ))
            conn.commit()

    def get_telemetry_event(self, event_id: str) -> Optional[SecurityTelemetryEvent]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM security_telemetry_events WHERE event_id = ?", (event_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return SecurityTelemetryEvent(
                event_id=row["event_id"],
                event_type=row["event_type"],
                source_component=row["source_component"],
                action_category=row["action_category"],
                outcome=row["outcome"],
                severity=SecuritySeverity(row["severity"]),
                timestamp=row["timestamp"],
                schema_version=row["schema_version"],
                source_identity=row["source_identity"],
                node_identity=row["node_identity"],
                correlation_id=row["correlation_id"],
                resource_reference=row["resource_reference"],
                details=json.loads(row["details"]),
                data_classification=row["data_classification"],
                signature=row["signature"],
            )

    # --- Threat Intelligence Indicators ---
    def save_indicator(self, indicator: ThreatIndicator) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO threat_intelligence_indicators (
                indicator_id, indicator_type, indicator_value, source, source_reliability,
                confidence, first_seen, last_seen, expires_at, context,
                threat_classification, validation_status, applicable_scope
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                indicator.indicator_id,
                indicator.indicator_type.value if isinstance(indicator.indicator_type, IndicatorType) else str(indicator.indicator_type),
                indicator.indicator_value,
                indicator.source,
                indicator.source_reliability,
                indicator.confidence,
                indicator.first_seen,
                indicator.last_seen,
                indicator.expires_at,
                json.dumps(indicator.context),
                indicator.threat_classification.value if isinstance(indicator.threat_classification, ThreatClassification) else str(indicator.threat_classification),
                indicator.validation_status.value if isinstance(indicator.validation_status, IndicatorValidationStatus) else str(indicator.validation_status),
                indicator.applicable_scope,
            ))
            conn.commit()

    def get_indicator(self, indicator_id: str) -> Optional[ThreatIndicator]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM threat_intelligence_indicators WHERE indicator_id = ?", (indicator_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ThreatIndicator(
                indicator_id=row["indicator_id"],
                indicator_type=IndicatorType(row["indicator_type"]),
                indicator_value=row["indicator_value"],
                source=row["source"],
                source_reliability=row["source_reliability"],
                confidence=row["confidence"],
                first_seen=row["first_seen"],
                last_seen=row["last_seen"],
                expires_at=row["expires_at"],
                context=json.loads(row["context"]),
                threat_classification=ThreatClassification(row["threat_classification"]),
                validation_status=IndicatorValidationStatus(row["validation_status"]),
                applicable_scope=row["applicable_scope"],
            )

    def find_indicators_by_value(self, indicator_value: str) -> List[ThreatIndicator]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM threat_intelligence_indicators WHERE indicator_value = ?", (indicator_value,))
            rows = cursor.fetchall()
            return [
                ThreatIndicator(
                    indicator_id=r["indicator_id"],
                    indicator_type=IndicatorType(r["indicator_type"]),
                    indicator_value=r["indicator_value"],
                    source=r["source"],
                    source_reliability=r["source_reliability"],
                    confidence=r["confidence"],
                    first_seen=r["first_seen"],
                    last_seen=r["last_seen"],
                    expires_at=r["expires_at"],
                    context=json.loads(r["context"]),
                    threat_classification=ThreatClassification(r["threat_classification"]),
                    validation_status=IndicatorValidationStatus(r["validation_status"]),
                    applicable_scope=r["applicable_scope"],
                ) for r in rows
            ]

    # --- Detection Rules ---
    def save_detection_rule(self, rule: SecurityDetectionRule) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO security_detection_rules (
                rule_id, name, description, threat_classification, severity,
                required_telemetry_types, matching_criteria, confidence, version,
                is_active, suppression_window_sec, expected_response_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule.rule_id,
                rule.name,
                rule.description,
                rule.threat_classification.value if isinstance(rule.threat_classification, ThreatClassification) else str(rule.threat_classification),
                rule.severity.value if isinstance(rule.severity, SecuritySeverity) else str(rule.severity),
                json.dumps(rule.required_telemetry_types),
                json.dumps(rule.matching_criteria),
                rule.confidence,
                rule.version,
                1 if rule.is_active else 0,
                rule.suppression_window_sec,
                int(rule.expected_response_level),
            ))
            conn.commit()

    def list_active_rules(self) -> List[SecurityDetectionRule]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM security_detection_rules WHERE is_active = 1")
            rows = cursor.fetchall()
            return [
                SecurityDetectionRule(
                    rule_id=r["rule_id"],
                    name=r["name"],
                    description=r["description"],
                    threat_classification=ThreatClassification(r["threat_classification"]),
                    severity=SecuritySeverity(r["severity"]),
                    required_telemetry_types=json.loads(r["required_telemetry_types"]),
                    matching_criteria=json.loads(r["matching_criteria"]),
                    confidence=r["confidence"],
                    version=r["version"],
                    is_active=bool(r["is_active"]),
                    suppression_window_sec=r["suppression_window_sec"],
                    expected_response_level=ResponseAutonomyLevel(r["expected_response_level"]),
                ) for r in rows
            ]

    # --- Incidents ---
    def save_incident(self, incident: SecurityIncident) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO security_incidents (
                incident_id, title, threat_classification, severity, confidence,
                detection_source, affected_assets, related_event_ids, evidence_ids,
                status, assigned_owner, created_at, updated_at, containment_action_ids,
                resolution_summary, audit_history
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                incident.incident_id,
                incident.title,
                incident.threat_classification.value if isinstance(incident.threat_classification, ThreatClassification) else str(incident.threat_classification),
                incident.severity.value if isinstance(incident.severity, SecuritySeverity) else str(incident.severity),
                incident.confidence,
                incident.detection_source,
                json.dumps(incident.affected_assets),
                json.dumps(incident.related_event_ids),
                json.dumps(incident.evidence_ids),
                incident.status.value if isinstance(incident.status, IncidentStatus) else str(incident.status),
                incident.assigned_owner,
                incident.created_at,
                incident.updated_at,
                json.dumps(incident.containment_action_ids),
                incident.resolution_summary,
                json.dumps(incident.audit_history),
            ))
            conn.commit()

    def get_incident(self, incident_id: str) -> Optional[SecurityIncident]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM security_incidents WHERE incident_id = ?", (incident_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return SecurityIncident(
                incident_id=row["incident_id"],
                title=row["title"],
                threat_classification=ThreatClassification(row["threat_classification"]),
                severity=SecuritySeverity(row["severity"]),
                confidence=row["confidence"],
                detection_source=row["detection_source"],
                affected_assets=json.loads(row["affected_assets"]),
                related_event_ids=json.loads(row["related_event_ids"]),
                evidence_ids=json.loads(row["evidence_ids"]),
                status=IncidentStatus(row["status"]),
                assigned_owner=row["assigned_owner"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                containment_action_ids=json.loads(row["containment_action_ids"]),
                resolution_summary=row["resolution_summary"],
                audit_history=json.loads(row["audit_history"]),
            )

    def list_active_incidents(self) -> List[SecurityIncident]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM security_incidents 
            WHERE status NOT IN ('RESOLVED', 'CLOSED')
            ORDER BY created_at DESC
            """)
            rows = cursor.fetchall()
            return [
                SecurityIncident(
                    incident_id=r["incident_id"],
                    title=r["title"],
                    threat_classification=ThreatClassification(r["threat_classification"]),
                    severity=SecuritySeverity(r["severity"]),
                    confidence=r["confidence"],
                    detection_source=r["detection_source"],
                    affected_assets=json.loads(r["affected_assets"]),
                    related_event_ids=json.loads(r["related_event_ids"]),
                    evidence_ids=json.loads(r["evidence_ids"]),
                    status=IncidentStatus(r["status"]),
                    assigned_owner=r["assigned_owner"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    containment_action_ids=json.loads(r["containment_action_ids"]),
                    resolution_summary=r["resolution_summary"],
                    audit_history=json.loads(r["audit_history"]),
                ) for r in rows
            ]

    # --- Containment Actions ---
    def save_containment_action(self, action: ContainmentAction) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO security_containment_actions (
                action_id, incident_id, action_type, target_resource, scope,
                reason, response_level, status, is_reversible, approval_request_id,
                approval_token, requested_at, executed_at, verified_at,
                verification_evidence, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action.action_id,
                action.incident_id,
                action.action_type,
                action.target_resource,
                action.scope,
                action.reason,
                int(action.response_level),
                action.status.value if isinstance(action.status, ContainmentStatus) else str(action.status),
                1 if action.is_reversible else 0,
                action.approval_request_id,
                action.approval_token,
                action.requested_at,
                action.executed_at,
                action.verified_at,
                action.verification_evidence,
                action.error_message,
            ))
            conn.commit()

    def get_containment_action(self, action_id: str) -> Optional[ContainmentAction]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM security_containment_actions WHERE action_id = ?", (action_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ContainmentAction(
                action_id=row["action_id"],
                incident_id=row["incident_id"],
                action_type=row["action_type"],
                target_resource=row["target_resource"],
                scope=row["scope"],
                reason=row["reason"],
                response_level=ResponseAutonomyLevel(row["response_level"]),
                status=ContainmentStatus(row["status"]),
                is_reversible=bool(row["is_reversible"]),
                approval_request_id=row["approval_request_id"],
                approval_token=row["approval_token"],
                requested_at=row["requested_at"],
                executed_at=row["executed_at"],
                verified_at=row["verified_at"],
                verification_evidence=row["verification_evidence"],
                error_message=row["error_message"],
            )

    # --- Forensic Evidence Records ---
    def save_evidence_record(self, record: ForensicEvidenceRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO forensic_evidence_records (
                evidence_id, incident_id, artifact_type, source_identifier, collector_identity,
                integrity_digest, raw_payload_redacted, collected_at, data_classification, chain_of_custody
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.evidence_id,
                record.incident_id,
                record.artifact_type,
                record.source_identifier,
                record.collector_identity,
                record.integrity_digest,
                record.raw_payload_redacted,
                record.collected_at,
                record.data_classification,
                json.dumps(record.chain_of_custody),
            ))
            conn.commit()

    def get_evidence_record(self, evidence_id: str) -> Optional[ForensicEvidenceRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM forensic_evidence_records WHERE evidence_id = ?", (evidence_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ForensicEvidenceRecord(
                evidence_id=row["evidence_id"],
                incident_id=row["incident_id"],
                artifact_type=row["artifact_type"],
                source_identifier=row["source_identifier"],
                collector_identity=row["collector_identity"],
                integrity_digest=row["integrity_digest"],
                raw_payload_redacted=row["raw_payload_redacted"],
                collected_at=row["collected_at"],
                data_classification=row["data_classification"],
                chain_of_custody=json.loads(row["chain_of_custody"]),
            )

    # --- Posture Assessments ---
    def save_posture_assessment(self, assessment: SecurityPostureAssessment) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO security_posture_assessments (
                assessment_id, overall_state, score, active_incidents_count,
                critical_alerts_count, monitored_sources_count, missing_sources,
                component_posture, recommended_remediations, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                assessment.assessment_id,
                assessment.overall_state.value if isinstance(assessment.overall_state, SecurityPostureState) else str(assessment.overall_state),
                assessment.score,
                assessment.active_incidents_count,
                assessment.critical_alerts_count,
                assessment.monitored_sources_count,
                json.dumps(assessment.missing_sources),
                json.dumps({k: (v.value if isinstance(v, SecurityPostureState) else str(v)) for k, v in assessment.component_posture.items()}),
                json.dumps(assessment.recommended_remediations),
                assessment.timestamp,
            ))
            conn.commit()

    def get_latest_posture_assessment(self) -> Optional[SecurityPostureAssessment]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM security_posture_assessments ORDER BY timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            return SecurityPostureAssessment(
                assessment_id=row["assessment_id"],
                overall_state=SecurityPostureState(row["overall_state"]),
                score=row["score"],
                active_incidents_count=row["active_incidents_count"],
                critical_alerts_count=row["critical_alerts_count"],
                monitored_sources_count=row["monitored_sources_count"],
                missing_sources=json.loads(row["missing_sources"]),
                component_posture={k: SecurityPostureState(v) for k, v in json.loads(row["component_posture"]).items()},
                recommended_remediations=json.loads(row["recommended_remediations"]),
                timestamp=row["timestamp"],
            )
