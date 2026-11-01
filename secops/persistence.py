"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Persistence Repository - persistence.py
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from secops.models import (
    AlertStatus,
    BaselineStatus,
    BehavioralBaseline,
    ContainmentActionRecord,
    CorrelationGraph,
    DefensiveResponsePlan,
    DetectionEvaluation,
    DetectionRule,
    EventCategory,
    EventResult,
    EvidencePackage,
    IncidentPriority,
    IncidentStatus,
    IncidentTimelineEntry,
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

logger = logging.getLogger("Omnia.SecOps.Persistence")


class SecOpsRepository:
    """
    CRUD repository for all Module 47 SQLite tables.
    """

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ------------------------------------------------------------------
    # Telemetry Sources
    # ------------------------------------------------------------------
    def save_source(self, source: TelemetrySource) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_telemetry_sources (
                    source_id, provider, environment, asset_scope_json,
                    event_types_supported_json, collection_method, auth_method,
                    last_successful_ingestion, health_status, retention_days,
                    coverage_limitations_json, registered_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.source_id,
                    source.provider,
                    source.environment,
                    json.dumps(source.asset_scope),
                    json.dumps(source.event_types_supported),
                    source.collection_method,
                    source.auth_method,
                    source.last_successful_ingestion,
                    source.health_status,
                    source.retention_days,
                    json.dumps(source.coverage_limitations),
                    source.registered_at,
                    json.dumps(source.metadata),
                ),
            )

    def get_source(self, source_id: str) -> Optional[TelemetrySource]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM soc_telemetry_sources WHERE source_id = ?", (source_id,)
            ).fetchone()
            if not row:
                return None
            return TelemetrySource(
                source_id=row["source_id"],
                provider=row["provider"],
                environment=row["environment"],
                asset_scope=json.loads(row["asset_scope_json"] or "[]"),
                event_types_supported=json.loads(row["event_types_supported_json"] or "[]"),
                collection_method=row["collection_method"],
                auth_method=row["auth_method"],
                last_successful_ingestion=row["last_successful_ingestion"],
                health_status=row["health_status"],
                retention_days=row["retention_days"],
                coverage_limitations=json.loads(row["coverage_limitations_json"] or "[]"),
                registered_at=row["registered_at"],
                metadata=json.loads(row["metadata_json"] or "{}"),
            )

    def list_sources(self) -> List[TelemetrySource]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM soc_telemetry_sources").fetchall()
            return [
                TelemetrySource(
                    source_id=r["source_id"],
                    provider=r["provider"],
                    environment=r["environment"],
                    asset_scope=json.loads(r["asset_scope_json"] or "[]"),
                    event_types_supported=json.loads(r["event_types_supported_json"] or "[]"),
                    collection_method=r["collection_method"],
                    auth_method=r["auth_method"],
                    last_successful_ingestion=r["last_successful_ingestion"],
                    health_status=r["health_status"],
                    retention_days=r["retention_days"],
                    coverage_limitations=json.loads(r["coverage_limitations_json"] or "[]"),
                    registered_at=r["registered_at"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Security Events
    # ------------------------------------------------------------------
    def save_event(self, event: SecurityEvent) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_security_events (
                    event_id, source_id, provider, event_type, event_category,
                    event_timestamp, ingestion_timestamp, environment, asset_id,
                    actor_id, target_id, source_address, destination_address,
                    action, result, severity, confidence, metadata_json,
                    correlation_ids_json, raw_payload_hash, quarantine_reason,
                    is_quarantined
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.source_id,
                    event.provider,
                    event.event_type,
                    event.event_category.value,
                    event.event_timestamp,
                    event.ingestion_timestamp,
                    event.environment,
                    event.asset_id,
                    event.actor_id,
                    event.target_id,
                    event.source_address,
                    event.destination_address,
                    event.action,
                    event.result.value,
                    event.severity.value,
                    event.confidence,
                    json.dumps(event.metadata),
                    json.dumps(event.correlation_ids),
                    event.raw_payload_hash,
                    event.quarantine_reason,
                    1 if event.is_quarantined else 0,
                ),
            )

    def get_event(self, event_id: str) -> Optional[SecurityEvent]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM soc_security_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            if not row:
                return None
            return SecurityEvent(
                event_id=row["event_id"],
                source_id=row["source_id"],
                provider=row["provider"],
                event_type=row["event_type"],
                event_category=EventCategory(row["event_category"]),
                event_timestamp=row["event_timestamp"],
                ingestion_timestamp=row["ingestion_timestamp"],
                environment=row["environment"],
                asset_id=row["asset_id"],
                actor_id=row["actor_id"],
                target_id=row["target_id"],
                source_address=row["source_address"],
                destination_address=row["destination_address"],
                action=row["action"],
                result=EventResult(row["result"]),
                severity=SecuritySeverity(row["severity"]),
                confidence=row["confidence"],
                metadata=json.loads(row["metadata_json"] or "{}"),
                correlation_ids=json.loads(row["correlation_ids_json"] or "[]"),
                raw_payload_hash=row["raw_payload_hash"],
                quarantine_reason=row["quarantine_reason"],
                is_quarantined=bool(row["is_quarantined"]),
            )

    def query_events(
        self,
        event_type: Optional[str] = None,
        asset_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[SecurityEvent]:
        query = "SELECT * FROM soc_security_events WHERE 1=1"
        params: List[Any] = []
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if asset_id:
            query += " AND asset_id = ?"
            params.append(asset_id)
        if actor_id:
            query += " AND actor_id = ?"
            params.append(actor_id)
        query += " ORDER BY event_timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [
                SecurityEvent(
                    event_id=r["event_id"],
                    source_id=r["source_id"],
                    provider=r["provider"],
                    event_type=r["event_type"],
                    event_category=EventCategory(r["event_category"]),
                    event_timestamp=r["event_timestamp"],
                    ingestion_timestamp=r["ingestion_timestamp"],
                    environment=r["environment"],
                    asset_id=r["asset_id"],
                    actor_id=r["actor_id"],
                    target_id=r["target_id"],
                    source_address=r["source_address"],
                    destination_address=r["destination_address"],
                    action=r["action"],
                    result=EventResult(r["result"]),
                    severity=SecuritySeverity(r["severity"]),
                    confidence=r["confidence"],
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    correlation_ids=json.loads(r["correlation_ids_json"] or "[]"),
                    raw_payload_hash=r["raw_payload_hash"],
                    quarantine_reason=r["quarantine_reason"],
                    is_quarantined=bool(r["is_quarantined"]),
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Behavioral Baselines
    # ------------------------------------------------------------------
    def save_baseline(self, baseline: BehavioralBaseline) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_behavioral_baselines (
                    baseline_id, entity_id, entity_type, metric_name,
                    rolling_mean, rolling_stddev, sample_count, confidence_level,
                    status, seasonality_model_json, first_seen_at, last_updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    baseline.baseline_id,
                    baseline.entity_id,
                    baseline.entity_type,
                    baseline.metric_name,
                    baseline.rolling_mean,
                    baseline.rolling_stddev,
                    baseline.sample_count,
                    baseline.confidence_level,
                    baseline.status.value,
                    json.dumps(baseline.seasonality_model),
                    baseline.first_seen_at,
                    baseline.last_updated_at,
                ),
            )

    def get_baseline(self, entity_id: str, metric_name: str) -> Optional[BehavioralBaseline]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM soc_behavioral_baselines
                WHERE entity_id = ? AND metric_name = ?
                """,
                (entity_id, metric_name),
            ).fetchone()
            if not row:
                return None
            return BehavioralBaseline(
                baseline_id=row["baseline_id"],
                entity_id=row["entity_id"],
                entity_type=row["entity_type"],
                metric_name=row["metric_name"],
                rolling_mean=row["rolling_mean"],
                rolling_stddev=row["rolling_stddev"],
                sample_count=row["sample_count"],
                confidence_level=row["confidence_level"],
                status=BaselineStatus(row["status"]),
                seasonality_model=json.loads(row["seasonality_model_json"] or "{}"),
                first_seen_at=row["first_seen_at"],
                last_updated_at=row["last_updated_at"],
            )

    # ------------------------------------------------------------------
    # Detection Rules
    # ------------------------------------------------------------------
    def save_rule(self, rule: DetectionRule) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_detection_rules (
                    rule_id, name, description, rule_type, required_telemetry_sources_json,
                    severity, confidence_score, threshold_params_json, suppression_conditions_json,
                    mitre_attack_technique, version, is_enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.rule_id,
                    rule.name,
                    rule.description,
                    rule.rule_type.value,
                    json.dumps(rule.required_telemetry_sources),
                    rule.severity.value,
                    rule.confidence_score,
                    json.dumps(rule.threshold_params),
                    json.dumps(rule.suppression_conditions),
                    rule.mitre_attack_technique,
                    rule.version,
                    1 if rule.is_enabled else 0,
                    rule.created_at,
                    rule.updated_at,
                ),
            )

    def get_rule(self, rule_id: str) -> Optional[DetectionRule]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM soc_detection_rules WHERE rule_id = ?", (rule_id,)
            ).fetchone()
            if not row:
                return None
            return DetectionRule(
                rule_id=row["rule_id"],
                name=row["name"],
                description=row["description"],
                rule_type=RuleType(row["rule_type"]),
                required_telemetry_sources=json.loads(row["required_telemetry_sources_json"] or "[]"),
                severity=SecuritySeverity(row["severity"]),
                confidence_score=row["confidence_score"],
                threshold_params=json.loads(row["threshold_params_json"] or "{}"),
                suppression_conditions=json.loads(row["suppression_conditions_json"] or "[]"),
                mitre_attack_technique=row["mitre_attack_technique"],
                version=row["version"],
                is_enabled=bool(row["is_enabled"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_rules(self) -> List[DetectionRule]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM soc_detection_rules WHERE is_enabled = 1").fetchall()
            return [
                DetectionRule(
                    rule_id=r["rule_id"],
                    name=r["name"],
                    description=r["description"],
                    rule_type=RuleType(r["rule_type"]),
                    required_telemetry_sources=json.loads(r["required_telemetry_sources_json"] or "[]"),
                    severity=SecuritySeverity(r["severity"]),
                    confidence_score=r["confidence_score"],
                    threshold_params=json.loads(r["threshold_params_json"] or "{}"),
                    suppression_conditions=json.loads(r["suppression_conditions_json"] or "[]"),
                    mitre_attack_technique=r["mitre_attack_technique"],
                    version=r["version"],
                    is_enabled=bool(r["is_enabled"]),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    def save_alert(self, alert: SecurityAlert) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_alerts (
                    alert_id, rule_id, title, description, severity, confidence,
                    asset_id, actor_id, status, dedup_key, contributing_event_ids_json,
                    explanation_json, suppression_expires_at, assigned_to, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.alert_id,
                    alert.rule_id,
                    alert.title,
                    alert.description,
                    alert.severity.value,
                    alert.confidence,
                    alert.asset_id,
                    alert.actor_id,
                    alert.status.value,
                    alert.dedup_key,
                    json.dumps(alert.contributing_event_ids),
                    json.dumps(alert.explanation),
                    alert.suppression_expires_at,
                    alert.assigned_to,
                    alert.created_at,
                    alert.updated_at,
                ),
            )

    def get_alert(self, alert_id: str) -> Optional[SecurityAlert]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM soc_alerts WHERE alert_id = ?", (alert_id,)).fetchone()
            if not row:
                return None
            return SecurityAlert(
                alert_id=row["alert_id"],
                rule_id=row["rule_id"],
                title=row["title"],
                description=row["description"],
                severity=SecuritySeverity(row["severity"]),
                confidence=row["confidence"],
                asset_id=row["asset_id"],
                actor_id=row["actor_id"],
                status=AlertStatus(row["status"]),
                dedup_key=row["dedup_key"],
                contributing_event_ids=json.loads(row["contributing_event_ids_json"] or "[]"),
                explanation=json.loads(row["explanation_json"] or "{}"),
                suppression_expires_at=row["suppression_expires_at"],
                assigned_to=row["assigned_to"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def get_alert_by_dedup(self, dedup_key: str) -> Optional[SecurityAlert]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM soc_alerts WHERE dedup_key = ?", (dedup_key,)).fetchone()
            if not row:
                return None
            return SecurityAlert(
                alert_id=row["alert_id"],
                rule_id=row["rule_id"],
                title=row["title"],
                description=row["description"],
                severity=SecuritySeverity(row["severity"]),
                confidence=row["confidence"],
                asset_id=row["asset_id"],
                actor_id=row["actor_id"],
                status=AlertStatus(row["status"]),
                dedup_key=row["dedup_key"],
                contributing_event_ids=json.loads(row["contributing_event_ids_json"] or "[]"),
                explanation=json.loads(row["explanation_json"] or "{}"),
                suppression_expires_at=row["suppression_expires_at"],
                assigned_to=row["assigned_to"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    # ------------------------------------------------------------------
    # Correlation Graphs
    # ------------------------------------------------------------------
    def save_correlation_graph(self, graph: CorrelationGraph) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_correlation_graphs (
                    correlation_id, correlation_title, affected_entities_json,
                    participating_alert_ids_json, participating_event_ids_json,
                    attack_chain_sequence_json, correlation_confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    graph.correlation_id,
                    graph.correlation_title,
                    json.dumps(graph.affected_entities),
                    json.dumps(graph.participating_alert_ids),
                    json.dumps(graph.participating_event_ids),
                    json.dumps(graph.attack_chain_sequence),
                    graph.correlation_confidence,
                    graph.created_at,
                ),
            )

    def get_correlation_graph(self, correlation_id: str) -> Optional[CorrelationGraph]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM soc_correlation_graphs WHERE correlation_id = ?", (correlation_id,)
            ).fetchone()
            if not row:
                return None
            return CorrelationGraph(
                correlation_id=row["correlation_id"],
                correlation_title=row["correlation_title"],
                affected_entities=json.loads(row["affected_entities_json"] or "[]"),
                participating_alert_ids=json.loads(row["participating_alert_ids_json"] or "[]"),
                participating_event_ids=json.loads(row["participating_event_ids_json"] or "[]"),
                attack_chain_sequence=json.loads(row["attack_chain_sequence_json"] or "[]"),
                correlation_confidence=row["correlation_confidence"],
                created_at=row["created_at"],
            )

    # ------------------------------------------------------------------
    # Threat Intelligence Indicators
    # ------------------------------------------------------------------
    def save_indicator(self, indicator: ThreatIntelIndicator) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_threat_intel_indicators (
                    indicator_id, indicator_type, indicator_value, threat_actor,
                    campaign, confidence, mitre_techniques_json, source_provider,
                    published_at, expires_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    indicator.indicator_id,
                    indicator.indicator_type.value,
                    indicator.indicator_value,
                    indicator.threat_actor,
                    indicator.campaign,
                    indicator.confidence,
                    json.dumps(indicator.mitre_techniques),
                    indicator.source_provider,
                    indicator.published_at,
                    indicator.expires_at,
                    1 if indicator.is_active else 0,
                ),
            )

    def get_indicator(self, indicator_type: str, indicator_value: str) -> Optional[ThreatIntelIndicator]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM soc_threat_intel_indicators
                WHERE indicator_type = ? AND indicator_value = ? AND is_active = 1
                """,
                (indicator_type, indicator_value),
            ).fetchone()
            if not row:
                return None
            return ThreatIntelIndicator(
                indicator_id=row["indicator_id"],
                indicator_type=IndicatorType(row["indicator_type"]),
                indicator_value=row["indicator_value"],
                threat_actor=row["threat_actor"],
                campaign=row["campaign"],
                confidence=row["confidence"],
                mitre_techniques=json.loads(row["mitre_techniques_json"] or "[]"),
                source_provider=row["source_provider"],
                published_at=row["published_at"],
                expires_at=row["expires_at"],
                is_active=bool(row["is_active"]),
            )

    # ------------------------------------------------------------------
    # Incidents & Timelines
    # ------------------------------------------------------------------
    def save_incident(self, incident: SecurityIncident) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_incidents (
                    incident_id, title, description, severity, priority,
                    status, affected_assets_json, affected_identities_json,
                    related_alert_ids_json, investigation_id, assigned_owner,
                    resolution_summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident.incident_id,
                    incident.title,
                    incident.description,
                    incident.severity.value,
                    incident.priority.value,
                    incident.status.value,
                    json.dumps(incident.affected_assets),
                    json.dumps(incident.affected_identities),
                    json.dumps(incident.related_alert_ids),
                    incident.investigation_id,
                    incident.assigned_owner,
                    incident.resolution_summary,
                    incident.created_at,
                    incident.updated_at,
                ),
            )

    def get_incident(self, incident_id: str) -> Optional[SecurityIncident]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM soc_incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
            if not row:
                return None
            return SecurityIncident(
                incident_id=row["incident_id"],
                title=row["title"],
                description=row["description"],
                severity=SecuritySeverity(row["severity"]),
                priority=IncidentPriority(row["priority"]),
                status=IncidentStatus(row["status"]),
                affected_assets=json.loads(row["affected_assets_json"] or "[]"),
                affected_identities=json.loads(row["affected_identities_json"] or "[]"),
                related_alert_ids=json.loads(row["related_alert_ids_json"] or "[]"),
                investigation_id=row["investigation_id"],
                assigned_owner=row["assigned_owner"],
                resolution_summary=row["resolution_summary"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def save_timeline_entry(self, entry: IncidentTimelineEntry) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_incident_timelines (
                    timeline_entry_id, incident_id, entry_timestamp,
                    entry_type, description, evidence_reference, actor
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.timeline_entry_id,
                    entry.incident_id,
                    entry.entry_timestamp,
                    entry.entry_type,
                    entry.description,
                    entry.evidence_reference,
                    entry.actor,
                ),
            )

    def get_timeline_entries(self, incident_id: str) -> List[IncidentTimelineEntry]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM soc_incident_timelines WHERE incident_id = ? ORDER BY entry_timestamp ASC",
                (incident_id,),
            ).fetchall()
            return [
                IncidentTimelineEntry(
                    timeline_entry_id=r["timeline_entry_id"],
                    incident_id=r["incident_id"],
                    entry_timestamp=r["entry_timestamp"],
                    entry_type=r["entry_type"],
                    description=r["description"],
                    evidence_reference=r["evidence_reference"],
                    actor=r["actor"],
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Response Plans & Containment
    # ------------------------------------------------------------------
    def save_response_plan(self, plan: DefensiveResponsePlan) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_response_plans (
                    plan_id, incident_id, recommended_action, target_identifier,
                    justification, operational_risk, requires_approval,
                    approval_token_ref, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    plan.incident_id,
                    plan.recommended_action.value,
                    plan.target_identifier,
                    plan.justification,
                    plan.operational_risk.value,
                    1 if plan.requires_approval else 0,
                    plan.approval_token_ref,
                    plan.status,
                    plan.created_at,
                ),
            )

    def get_response_plan(self, plan_id: str) -> Optional[DefensiveResponsePlan]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM soc_response_plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
            if not row:
                return None
            return DefensiveResponsePlan(
                plan_id=row["plan_id"],
                incident_id=row["incident_id"],
                recommended_action=ResponseActionType(row["recommended_action"]),
                target_identifier=row["target_identifier"],
                justification=row["justification"],
                operational_risk=OperationalRisk(row["operational_risk"]),
                requires_approval=bool(row["requires_approval"]),
                approval_token_ref=row["approval_token_ref"],
                status=row["status"],
                created_at=row["created_at"],
            )

    def save_containment_action(self, action: ContainmentActionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_containment_actions (
                    action_id, plan_id, incident_id, action_type, target,
                    approval_token, status, execution_result_json,
                    executed_at, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.action_id,
                    action.plan_id,
                    action.incident_id,
                    action.action_type,
                    action.target,
                    action.approval_token,
                    action.status,
                    json.dumps(action.execution_result),
                    action.executed_at,
                    action.verified_at,
                ),
            )

    # ------------------------------------------------------------------
    # Evidence Packages
    # ------------------------------------------------------------------
    def save_evidence_package(self, pkg: EvidencePackage) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO soc_evidence_packages (
                    package_id, incident_id, investigation_id,
                    package_digest_sha256, evidence_manifest_json,
                    sealed_at, sealed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pkg.package_id,
                    pkg.incident_id,
                    pkg.investigation_id,
                    pkg.package_digest_sha256,
                    json.dumps(pkg.evidence_manifest),
                    pkg.sealed_at,
                    pkg.sealed_by,
                ),
            )

    def get_evidence_package(self, package_id: str) -> Optional[EvidencePackage]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM soc_evidence_packages WHERE package_id = ?", (package_id,)
            ).fetchone()
            if not row:
                return None
            return EvidencePackage(
                package_id=row["package_id"],
                incident_id=row["incident_id"],
                investigation_id=row["investigation_id"],
                package_digest_sha256=row["package_digest_sha256"],
                evidence_manifest=json.loads(row["evidence_manifest_json"] or "{}"),
                sealed_by=row["sealed_by"],
                sealed_at=row["sealed_at"],
            )
