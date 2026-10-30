"""
OMNIA Module 36: SQLite Persistence Repository for Observability & Diagnostics
Stores metrics, traces, component health contracts, checks, dependency graph edges,
hypotheses, and remediation verification records.
"""

import sqlite3
import json
import logging
from typing import Dict, Any, List, Optional
from observability.models import (
    OperationalMetric,
    TraceSpan,
    ComponentHealthRecord,
    HealthCheckDefinition,
    InfrastructureDependencyEdge,
    DiagnosticHypothesis,
    InfrastructureRemediationAction,
    ComponentHealthStatus,
    HealthCheckType,
    DependencyType,
    FailureCategory,
    RemediationAutonomyLevel,
    RecoveryVerificationStatus,
)

logger = logging.getLogger("Omnia.Observability.Persistence")


class ObservabilityRepository:
    """Manages SQLite persistence for operational observability, diagnostics, and recovery state."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Ensures Schema Version 18 tables are initialized."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS observability_metrics (
                metric_id TEXT PRIMARY KEY,
                component_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                timestamp REAL NOT NULL,
                labels TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS observability_traces (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                operation_name TEXT NOT NULL,
                component_id TEXT NOT NULL,
                parent_span_id TEXT,
                start_time REAL NOT NULL,
                end_time REAL,
                duration_ms REAL NOT NULL,
                status TEXT NOT NULL,
                tags TEXT NOT NULL,
                error_message TEXT
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS component_health_registry (
                component_id TEXT PRIMARY KEY,
                component_name TEXT NOT NULL,
                module_ownership TEXT NOT NULL,
                version TEXT NOT NULL,
                current_status TEXT NOT NULL,
                status_message TEXT NOT NULL,
                critical_dependencies TEXT NOT NULL,
                last_check_timestamp REAL,
                last_healthy_timestamp REAL,
                last_failure_timestamp REAL,
                consecutive_failures INTEGER NOT NULL,
                liveness_ok INTEGER NOT NULL,
                readiness_ok INTEGER NOT NULL,
                functional_ok INTEGER NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_check_definitions (
                check_id TEXT PRIMARY KEY,
                target_component_id TEXT NOT NULL,
                name TEXT NOT NULL,
                check_type TEXT NOT NULL,
                interval_seconds REAL NOT NULL,
                timeout_seconds REAL NOT NULL,
                is_active INTEGER NOT NULL,
                metadata TEXT NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS infrastructure_dependencies (
                edge_id TEXT PRIMARY KEY,
                source_component_id TEXT NOT NULL,
                target_component_id TEXT NOT NULL,
                dependency_type TEXT NOT NULL,
                criticality REAL NOT NULL,
                failure_propagation_probability REAL NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS diagnostic_hypotheses (
                hypothesis_id TEXT PRIMARY KEY,
                suspected_component_id TEXT NOT NULL,
                failure_category TEXT NOT NULL,
                confidence REAL NOT NULL,
                explanation TEXT NOT NULL,
                supporting_evidence TEXT NOT NULL,
                contradicting_evidence TEXT NOT NULL,
                cascading_impact_components TEXT NOT NULL,
                recommended_remediation_action TEXT,
                timestamp REAL NOT NULL
            );
            """)

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS infrastructure_remediations (
                action_id TEXT PRIMARY KEY,
                target_component_id TEXT NOT NULL,
                proposed_action TEXT NOT NULL,
                failure_category TEXT NOT NULL,
                reason TEXT NOT NULL,
                autonomy_level INTEGER NOT NULL,
                status TEXT NOT NULL,
                is_reversible INTEGER NOT NULL,
                approval_request_id TEXT,
                approval_token TEXT,
                retry_budget INTEGER NOT NULL,
                retry_count INTEGER NOT NULL,
                verification_window_seconds REAL NOT NULL,
                created_at REAL NOT NULL,
                executed_at REAL,
                verified_at REAL,
                verification_evidence TEXT,
                error_message TEXT
            );
            """)
            conn.commit()

    # --- Metrics ---
    def save_metric(self, metric: OperationalMetric) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO observability_metrics (
                metric_id, component_id, metric_name, value, unit, timestamp, labels
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.metric_id,
                metric.component_id,
                metric.metric_name,
                metric.value,
                metric.unit,
                metric.timestamp,
                json.dumps(metric.labels),
            ))
            conn.commit()

    def list_metrics(self, component_id: Optional[str] = None, limit: int = 50) -> List[OperationalMetric]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if component_id:
                cursor.execute("""
                SELECT * FROM observability_metrics 
                WHERE component_id = ? 
                ORDER BY timestamp DESC LIMIT ?
                """, (component_id, limit))
            else:
                cursor.execute("""
                SELECT * FROM observability_metrics 
                ORDER BY timestamp DESC LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            return [
                OperationalMetric(
                    metric_id=r["metric_id"],
                    component_id=r["component_id"],
                    metric_name=r["metric_name"],
                    value=r["value"],
                    unit=r["unit"],
                    timestamp=r["timestamp"],
                    labels=json.loads(r["labels"]),
                ) for r in rows
            ]

    # --- Traces ---
    def save_trace(self, span: TraceSpan) -> None:
        self.save_trace_span(span)

    def save_trace_span(self, span: TraceSpan) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO observability_traces (
                span_id, trace_id, operation_name, component_id, parent_span_id,
                start_time, end_time, duration_ms, status, tags, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                span.span_id,
                span.trace_id,
                span.operation_name,
                span.component_id,
                span.parent_span_id,
                span.start_time,
                span.end_time,
                span.duration_ms,
                span.status,
                json.dumps(span.tags),
                span.error_message,
            ))
            conn.commit()

    def list_traces(self, component_id: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> List[TraceSpan]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM observability_traces WHERE 1=1"
            params = []
            if component_id:
                query += " AND component_id = ?"
                params.append(component_id)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY start_time DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [
                TraceSpan(
                    span_id=r["span_id"],
                    trace_id=r["trace_id"],
                    operation_name=r["operation_name"],
                    component_id=r["component_id"],
                    parent_span_id=r["parent_span_id"],
                    start_time=r["start_time"],
                    end_time=r["end_time"],
                    duration_ms=r["duration_ms"],
                    status=r["status"],
                    tags=json.loads(r["tags"]),
                    error_message=r["error_message"],
                ) for r in rows
            ]

    # --- Component Health Registry ---
    def save_component_health(self, comp: ComponentHealthRecord) -> None:
        self.save_component(comp)

    def save_component(self, comp: ComponentHealthRecord) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO component_health_registry (
                component_id, component_name, module_ownership, version,
                current_status, status_message, critical_dependencies,
                last_check_timestamp, last_healthy_timestamp, last_failure_timestamp,
                consecutive_failures, liveness_ok, readiness_ok, functional_ok
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                comp.component_id,
                comp.component_name,
                comp.module_ownership,
                comp.version,
                comp.current_status.value if isinstance(comp.current_status, ComponentHealthStatus) else str(comp.current_status),
                comp.status_message,
                json.dumps(comp.critical_dependencies),
                comp.last_check_timestamp,
                comp.last_healthy_timestamp,
                comp.last_failure_timestamp,
                comp.consecutive_failures,
                1 if comp.liveness_ok else 0,
                1 if comp.readiness_ok else 0,
                1 if comp.functional_ok else 0,
            ))
            conn.commit()

    def get_component_health(self, component_id: str) -> Optional[ComponentHealthRecord]:
        return self.get_component(component_id)

    def get_component(self, component_id: str) -> Optional[ComponentHealthRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM component_health_registry WHERE component_id = ?", (component_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ComponentHealthRecord(
                component_id=row["component_id"],
                component_name=row["component_name"],
                module_ownership=row["module_ownership"],
                version=row["version"],
                current_status=ComponentHealthStatus(row["current_status"]),
                status_message=row["status_message"],
                critical_dependencies=json.loads(row["critical_dependencies"]),
                last_check_timestamp=row["last_check_timestamp"],
                last_healthy_timestamp=row["last_healthy_timestamp"],
                last_failure_timestamp=row["last_failure_timestamp"],
                consecutive_failures=row["consecutive_failures"],
                liveness_ok=bool(row["liveness_ok"]),
                readiness_ok=bool(row["readiness_ok"]),
                functional_ok=bool(row["functional_ok"]),
            )

    def list_component_health(self) -> List[ComponentHealthRecord]:
        return self.list_components()

    def list_components(self) -> List[ComponentHealthRecord]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM component_health_registry")
            rows = cursor.fetchall()
            return [
                ComponentHealthRecord(
                    component_id=r["component_id"],
                    component_name=r["component_name"],
                    module_ownership=r["module_ownership"],
                    version=r["version"],
                    current_status=ComponentHealthStatus(r["current_status"]),
                    status_message=r["status_message"],
                    critical_dependencies=json.loads(r["critical_dependencies"]),
                    last_check_timestamp=r["last_check_timestamp"],
                    last_healthy_timestamp=r["last_healthy_timestamp"],
                    last_failure_timestamp=r["last_failure_timestamp"],
                    consecutive_failures=r["consecutive_failures"],
                    liveness_ok=bool(r["liveness_ok"]),
                    readiness_ok=bool(r["readiness_ok"]),
                    functional_ok=bool(r["functional_ok"]),
                ) for r in rows
            ]

    # --- Health Check Definitions ---
    def save_health_check_definition(self, definition: HealthCheckDefinition) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO health_check_definitions (
                check_id, target_component_id, name, check_type, interval_seconds,
                timeout_seconds, is_active, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                definition.check_id,
                definition.target_component_id,
                definition.name,
                definition.check_type.value if isinstance(definition.check_type, HealthCheckType) else str(definition.check_type),
                definition.interval_seconds,
                definition.timeout_seconds,
                1 if definition.is_active else 0,
                json.dumps(definition.metadata),
            ))
            conn.commit()

    def get_health_check_definition(self, check_id: str) -> Optional[HealthCheckDefinition]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM health_check_definitions WHERE check_id = ?", (check_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return HealthCheckDefinition(
                check_id=row["check_id"],
                target_component_id=row["target_component_id"],
                name=row["name"],
                check_type=HealthCheckType(row["check_type"]),
                interval_seconds=row["interval_seconds"],
                timeout_seconds=row["timeout_seconds"],
                is_active=bool(row["is_active"]),
                metadata=json.loads(row["metadata"]),
            )

    def list_health_check_definitions(self, target_component_id: Optional[str] = None) -> List[HealthCheckDefinition]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if target_component_id:
                cursor.execute("SELECT * FROM health_check_definitions WHERE target_component_id = ?", (target_component_id,))
            else:
                cursor.execute("SELECT * FROM health_check_definitions")
            rows = cursor.fetchall()
            return [
                HealthCheckDefinition(
                    check_id=r["check_id"],
                    target_component_id=r["target_component_id"],
                    name=r["name"],
                    check_type=HealthCheckType(r["check_type"]),
                    interval_seconds=r["interval_seconds"],
                    timeout_seconds=r["timeout_seconds"],
                    is_active=bool(r["is_active"]),
                    metadata=json.loads(r["metadata"]),
                ) for r in rows
            ]

    # --- Dependency Edges ---
    def save_dependency_edge(self, edge: InfrastructureDependencyEdge) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO infrastructure_dependencies (
                edge_id, source_component_id, target_component_id, dependency_type,
                criticality, failure_propagation_probability
            ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                edge.edge_id,
                edge.source_component_id,
                edge.target_component_id,
                edge.dependency_type.value if isinstance(edge.dependency_type, DependencyType) else str(edge.dependency_type),
                edge.criticality,
                edge.failure_propagation_probability,
            ))
            conn.commit()

    def list_dependency_edges(self) -> List[InfrastructureDependencyEdge]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM infrastructure_dependencies")
            rows = cursor.fetchall()
            return [
                InfrastructureDependencyEdge(
                    edge_id=r["edge_id"],
                    source_component_id=r["source_component_id"],
                    target_component_id=r["target_component_id"],
                    dependency_type=DependencyType(r["dependency_type"]),
                    criticality=r["criticality"],
                    failure_propagation_probability=r["failure_propagation_probability"],
                ) for r in rows
            ]

    # --- Diagnostic Hypotheses ---
    def save_diagnostic_hypothesis(self, hyp: DiagnosticHypothesis) -> None:
        self.save_hypothesis(hyp)

    def save_hypothesis(self, hyp: DiagnosticHypothesis) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO diagnostic_hypotheses (
                hypothesis_id, suspected_component_id, failure_category, confidence,
                explanation, supporting_evidence, contradicting_evidence,
                cascading_impact_components, recommended_remediation_action, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                hyp.hypothesis_id,
                hyp.suspected_component_id,
                hyp.failure_category.value if isinstance(hyp.failure_category, FailureCategory) else str(hyp.failure_category),
                hyp.confidence,
                hyp.explanation,
                json.dumps(hyp.supporting_evidence),
                json.dumps(hyp.contradicting_evidence),
                json.dumps(hyp.cascading_impact_components),
                hyp.recommended_remediation_action,
                hyp.timestamp,
            ))
            conn.commit()

    def get_diagnostic_hypothesis(self, hypothesis_id: str) -> Optional[DiagnosticHypothesis]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM diagnostic_hypotheses WHERE hypothesis_id = ?", (hypothesis_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return DiagnosticHypothesis(
                hypothesis_id=row["hypothesis_id"],
                suspected_component_id=row["suspected_component_id"],
                failure_category=FailureCategory(row["failure_category"]),
                confidence=row["confidence"],
                explanation=row["explanation"],
                supporting_evidence=json.loads(row["supporting_evidence"]),
                contradicting_evidence=json.loads(row["contradicting_evidence"]),
                cascading_impact_components=json.loads(row["cascading_impact_components"]),
                recommended_remediation_action=row["recommended_remediation_action"],
                timestamp=row["timestamp"],
            )

    # --- Remediation Actions ---
    def save_remediation_action(self, act: InfrastructureRemediationAction) -> None:
        self.save_remediation(act)

    def save_remediation(self, act: InfrastructureRemediationAction) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO infrastructure_remediations (
                action_id, target_component_id, proposed_action, failure_category,
                reason, autonomy_level, status, is_reversible, approval_request_id,
                approval_token, retry_budget, retry_count, verification_window_seconds,
                created_at, executed_at, verified_at, verification_evidence, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                act.action_id,
                act.target_component_id,
                act.proposed_action,
                act.failure_category.value if isinstance(act.failure_category, FailureCategory) else str(act.failure_category),
                act.reason,
                int(act.autonomy_level),
                act.status.value if isinstance(act.status, RecoveryVerificationStatus) else str(act.status),
                1 if act.is_reversible else 0,
                act.approval_request_id,
                act.approval_token,
                act.retry_budget,
                act.retry_count,
                act.verification_window_seconds,
                act.created_at,
                act.executed_at,
                act.verified_at,
                act.verification_evidence,
                act.error_message,
            ))
            conn.commit()

    def get_remediation_action(self, action_id: str) -> Optional[InfrastructureRemediationAction]:
        return self.get_remediation(action_id)

    def get_remediation(self, action_id: str) -> Optional[InfrastructureRemediationAction]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM infrastructure_remediations WHERE action_id = ?", (action_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return InfrastructureRemediationAction(
                action_id=row["action_id"],
                target_component_id=row["target_component_id"],
                proposed_action=row["proposed_action"],
                failure_category=FailureCategory(row["failure_category"]),
                reason=row["reason"],
                autonomy_level=RemediationAutonomyLevel(row["autonomy_level"]),
                status=RecoveryVerificationStatus(row["status"]),
                is_reversible=bool(row["is_reversible"]),
                approval_request_id=row["approval_request_id"],
                approval_token=row["approval_token"],
                retry_budget=row["retry_budget"],
                retry_count=row["retry_count"],
                verification_window_seconds=row["verification_window_seconds"],
                created_at=row["created_at"],
                executed_at=row["executed_at"],
                verified_at=row["verified_at"],
                verification_evidence=row["verification_evidence"],
                error_message=row["error_message"],
            )
