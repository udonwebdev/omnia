"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Persistence Layer: SQLite Repository for Schema Version 24 Tables.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from process_intelligence.models import (
    BottleneckFinding,
    BottleneckType,
    DeviationType,
    ExecutionTraceRecord,
    ExperimentStatus,
    FailurePatternRecord,
    FindingSeverity,
    OptimizationCandidate,
    OptimizationExperimentRecord,
    OptimizationStatus,
    OptimizationType,
    ProcessDeviationRecord,
    ProcessEventRecord,
    ProcessEventType,
    ProcessGraphEdge,
    ProcessGraphNode,
    ProcessGraphRecord,
    TraceStatus,
    WorkflowChangeGovernanceRecord,
    WorkflowPerformanceSnapshot,
)


class ProcessIntelligenceRepository:
    """Manages persistent SQLite storage for all Module 39 process intelligence entities."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # Execution Traces & Events
    # -------------------------------------------------------------
    def save_trace(self, trace: ExecutionTraceRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_execution_traces (
                    trace_id, workflow_id, execution_id, status, started_at,
                    completed_at, total_duration_sec, total_waiting_sec, total_active_sec,
                    retry_count, failure_count, is_complete, events_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    status=excluded.status,
                    completed_at=excluded.completed_at,
                    total_duration_sec=excluded.total_duration_sec,
                    total_waiting_sec=excluded.total_waiting_sec,
                    total_active_sec=excluded.total_active_sec,
                    retry_count=excluded.retry_count,
                    failure_count=excluded.failure_count,
                    is_complete=excluded.is_complete,
                    events_count=excluded.events_count
                """,
                (
                    trace.trace_id,
                    trace.workflow_id,
                    trace.execution_id,
                    trace.status.value,
                    trace.started_at,
                    trace.completed_at,
                    trace.total_duration_sec,
                    trace.total_waiting_sec,
                    trace.total_active_sec,
                    trace.retry_count,
                    trace.failure_count,
                    1 if trace.is_complete else 0,
                    trace.events_count,
                ),
            )
            conn.commit()

    def get_trace(self, trace_id: str) -> Optional[ExecutionTraceRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM proc_execution_traces WHERE trace_id = ?", (trace_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ExecutionTraceRecord(
                trace_id=row["trace_id"],
                workflow_id=row["workflow_id"],
                execution_id=row["execution_id"],
                status=TraceStatus(row["status"]),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                total_duration_sec=row["total_duration_sec"],
                total_waiting_sec=row["total_waiting_sec"],
                total_active_sec=row["total_active_sec"],
                retry_count=row["retry_count"],
                failure_count=row["failure_count"],
                is_complete=bool(row["is_complete"]),
                events_count=row["events_count"],
            )

    def list_traces_for_workflow(self, workflow_id: str) -> List[ExecutionTraceRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM proc_execution_traces WHERE workflow_id = ? ORDER BY started_at ASC",
                (workflow_id,),
            )
            traces = []
            for row in cursor.fetchall():
                traces.append(
                    ExecutionTraceRecord(
                        trace_id=row["trace_id"],
                        workflow_id=row["workflow_id"],
                        execution_id=row["execution_id"],
                        status=TraceStatus(row["status"]),
                        started_at=row["started_at"],
                        completed_at=row["completed_at"],
                        total_duration_sec=row["total_duration_sec"],
                        total_waiting_sec=row["total_waiting_sec"],
                        total_active_sec=row["total_active_sec"],
                        retry_count=row["retry_count"],
                        failure_count=row["failure_count"],
                        is_complete=bool(row["is_complete"]),
                        events_count=row["events_count"],
                    )
                )
            return traces

    def save_event(self, event: ProcessEventRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_events (
                    event_id, trace_id, workflow_id, task_id, parent_task_id,
                    event_type, timestamp, duration_sec, waiting_time_sec,
                    error_category, resource_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO NOTHING
                """,
                (
                    event.event_id,
                    event.trace_id,
                    event.workflow_id,
                    event.task_id,
                    event.parent_task_id,
                    event.event_type.value,
                    event.timestamp,
                    event.duration_sec,
                    event.waiting_time_sec,
                    event.error_category,
                    event.resource_id,
                    json.dumps(event.metadata_payload),
                ),
            )
            conn.commit()

    def list_events_for_trace(self, trace_id: str) -> List[ProcessEventRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM proc_events WHERE trace_id = ? ORDER BY timestamp ASC",
                (trace_id,),
            )
            events = []
            for row in cursor.fetchall():
                events.append(
                    ProcessEventRecord(
                        event_id=row["event_id"],
                        trace_id=row["trace_id"],
                        workflow_id=row["workflow_id"],
                        task_id=row["task_id"],
                        parent_task_id=row["parent_task_id"],
                        event_type=ProcessEventType(row["event_type"]),
                        timestamp=row["timestamp"],
                        duration_sec=row["duration_sec"],
                        waiting_time_sec=row["waiting_time_sec"],
                        error_category=row["error_category"],
                        resource_id=row["resource_id"],
                        metadata_payload=json.loads(row["metadata_json"] or "{}"),
                    )
                )
            return events

    # -------------------------------------------------------------
    # Process Graphs
    # -------------------------------------------------------------
    def save_process_graph(self, graph: ProcessGraphRecord) -> None:
        nodes_dict = {
            k: {
                "node_id": v.node_id,
                "task_name": v.task_name,
                "node_type": v.node_type,
                "execution_count": v.execution_count,
                "total_active_duration_sec": v.total_active_duration_sec,
                "total_waiting_duration_sec": v.total_waiting_duration_sec,
                "failure_count": v.failure_count,
            }
            for k, v in graph.nodes.items()
        }
        edges_list = [
            {
                "source_node_id": e.source_node_id,
                "target_node_id": e.target_node_id,
                "transition_count": e.transition_count,
                "avg_transition_latency_sec": e.avg_transition_latency_sec,
            }
            for e in graph.edges
        ]
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_graphs (
                    graph_id, workflow_id, version, nodes_json, edges_json,
                    common_paths_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(graph_id) DO UPDATE SET
                    nodes_json=excluded.nodes_json,
                    edges_json=excluded.edges_json,
                    common_paths_json=excluded.common_paths_json
                """,
                (
                    graph.graph_id,
                    graph.workflow_id,
                    graph.version,
                    json.dumps(nodes_dict),
                    json.dumps(edges_list),
                    json.dumps(graph.common_paths),
                    graph.created_at,
                ),
            )
            conn.commit()

    def get_latest_graph_for_workflow(self, workflow_id: str) -> Optional[ProcessGraphRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM proc_graphs WHERE workflow_id = ? ORDER BY version DESC LIMIT 1",
                (workflow_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            nodes_data = json.loads(row["nodes_json"] or "{}")
            edges_data = json.loads(row["edges_json"] or "[]")
            nodes = {
                k: ProcessGraphNode(
                    node_id=v["node_id"],
                    task_name=v["task_name"],
                    node_type=v["node_type"],
                    execution_count=v["execution_count"],
                    total_active_duration_sec=v["total_active_duration_sec"],
                    total_waiting_duration_sec=v["total_waiting_duration_sec"],
                    failure_count=v["failure_count"],
                )
                for k, v in nodes_data.items()
            }
            edges = [
                ProcessGraphEdge(
                    source_node_id=e["source_node_id"],
                    target_node_id=e["target_node_id"],
                    transition_count=e["transition_count"],
                    avg_transition_latency_sec=e["avg_transition_latency_sec"],
                )
                for e in edges_data
            ]
            return ProcessGraphRecord(
                graph_id=row["graph_id"],
                workflow_id=row["workflow_id"],
                version=row["version"],
                nodes=nodes,
                edges=edges,
                common_paths=json.loads(row["common_paths_json"] or "[]"),
                created_at=row["created_at"],
            )

    # -------------------------------------------------------------
    # Performance & Bottlenecks
    # -------------------------------------------------------------
    def save_performance_snapshot(self, snapshot: WorkflowPerformanceSnapshot) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_performance_snapshots (
                    snapshot_id, workflow_id, trace_count, mean_duration_sec,
                    median_duration_sec, p90_duration_sec, p95_duration_sec,
                    p99_duration_sec, mean_waiting_time_sec, active_to_wait_ratio,
                    overall_failure_rate, retry_frequency_per_trace, assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.workflow_id,
                    snapshot.trace_count,
                    snapshot.mean_duration_sec,
                    snapshot.median_duration_sec,
                    snapshot.p90_duration_sec,
                    snapshot.p95_duration_sec,
                    snapshot.p99_duration_sec,
                    snapshot.mean_waiting_time_sec,
                    snapshot.active_to_wait_ratio,
                    snapshot.overall_failure_rate,
                    snapshot.retry_frequency_per_trace,
                    snapshot.assessed_at,
                ),
            )
            conn.commit()

    def get_latest_performance_snapshot(self, workflow_id: str) -> Optional[WorkflowPerformanceSnapshot]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM proc_performance_snapshots WHERE workflow_id = ? ORDER BY assessed_at DESC LIMIT 1",
                (workflow_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return WorkflowPerformanceSnapshot(
                snapshot_id=row["snapshot_id"],
                workflow_id=row["workflow_id"],
                trace_count=row["trace_count"],
                mean_duration_sec=row["mean_duration_sec"],
                median_duration_sec=row["median_duration_sec"],
                p90_duration_sec=row["p90_duration_sec"],
                p95_duration_sec=row["p95_duration_sec"],
                p99_duration_sec=row["p99_duration_sec"],
                mean_waiting_time_sec=row["mean_waiting_time_sec"],
                active_to_wait_ratio=row["active_to_wait_ratio"],
                overall_failure_rate=row["overall_failure_rate"],
                retry_frequency_per_trace=row["retry_frequency_per_trace"],
                assessed_at=row["assessed_at"],
            )

    def save_bottleneck(self, finding: BottleneckFinding) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_bottleneck_findings (
                    finding_id, workflow_id, component_id, bottleneck_type,
                    severity, estimated_delay_sec, frequency_ratio, confidence,
                    potential_causes_json, recommended_action, supporting_trace_ids_json,
                    detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(finding_id) DO UPDATE SET
                    estimated_delay_sec=excluded.estimated_delay_sec,
                    frequency_ratio=excluded.frequency_ratio,
                    confidence=excluded.confidence
                """,
                (
                    finding.finding_id,
                    finding.workflow_id,
                    finding.component_id,
                    finding.bottleneck_type.value,
                    finding.severity.value,
                    finding.estimated_delay_sec,
                    finding.frequency_ratio,
                    finding.confidence,
                    json.dumps(finding.potential_causes),
                    finding.recommended_action,
                    json.dumps(finding.supporting_trace_ids),
                    finding.detected_at,
                ),
            )
            conn.commit()

    def list_bottlenecks_for_workflow(self, workflow_id: str) -> List[BottleneckFinding]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM proc_bottleneck_findings WHERE workflow_id = ? ORDER BY estimated_delay_sec DESC",
                (workflow_id,),
            )
            findings = []
            for row in cursor.fetchall():
                findings.append(
                    BottleneckFinding(
                        finding_id=row["finding_id"],
                        workflow_id=row["workflow_id"],
                        component_id=row["component_id"],
                        bottleneck_type=BottleneckType(row["bottleneck_type"]),
                        severity=FindingSeverity(row["severity"]),
                        estimated_delay_sec=row["estimated_delay_sec"],
                        frequency_ratio=row["frequency_ratio"],
                        confidence=row["confidence"],
                        potential_causes=json.loads(row["potential_causes_json"] or "[]"),
                        recommended_action=row["recommended_action"],
                        supporting_trace_ids=json.loads(row["supporting_trace_ids_json"] or "[]"),
                        detected_at=row["detected_at"],
                    )
                )
            return findings

    # -------------------------------------------------------------
    # Process Deviations & Conformance
    # -------------------------------------------------------------
    def save_deviation(self, dev: ProcessDeviationRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_deviations (
                    deviation_id, trace_id, workflow_id, deviation_type,
                    severity, description, policy_rule_violated, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dev.deviation_id,
                    dev.trace_id,
                    dev.workflow_id,
                    dev.deviation_type.value,
                    dev.severity.value,
                    dev.description,
                    dev.policy_rule_violated,
                    dev.detected_at,
                ),
            )
            conn.commit()

    def list_deviations(self, workflow_id: str) -> List[ProcessDeviationRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM proc_deviations WHERE workflow_id = ? ORDER BY detected_at DESC",
                (workflow_id,),
            )
            records = []
            for row in cursor.fetchall():
                records.append(
                    ProcessDeviationRecord(
                        deviation_id=row["deviation_id"],
                        trace_id=row["trace_id"],
                        workflow_id=row["workflow_id"],
                        deviation_type=DeviationType(row["deviation_type"]),
                        severity=FindingSeverity(row["severity"]),
                        description=row["description"],
                        policy_rule_violated=row["policy_rule_violated"],
                        detected_at=row["detected_at"],
                    )
                )
            return records

    # -------------------------------------------------------------
    # Failure Patterns & Rework
    # -------------------------------------------------------------
    def save_failure_pattern(self, pattern: FailurePatternRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_failure_patterns (
                    pattern_id, workflow_id, error_type, affected_tasks_json,
                    occurrence_count, total_rework_duration_sec, estimated_rework_cost,
                    identified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pattern_id) DO UPDATE SET
                    occurrence_count=excluded.occurrence_count,
                    total_rework_duration_sec=excluded.total_rework_duration_sec,
                    estimated_rework_cost=excluded.estimated_rework_cost
                """,
                (
                    pattern.pattern_id,
                    pattern.workflow_id,
                    pattern.error_type,
                    json.dumps(pattern.affected_tasks),
                    pattern.occurrence_count,
                    pattern.total_rework_duration_sec,
                    pattern.estimated_rework_cost,
                    pattern.identified_at,
                ),
            )
            conn.commit()

    def list_failure_patterns(self, workflow_id: str) -> List[FailurePatternRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM proc_failure_patterns WHERE workflow_id = ? ORDER BY total_rework_duration_sec DESC",
                (workflow_id,),
            )
            patterns = []
            for row in cursor.fetchall():
                patterns.append(
                    FailurePatternRecord(
                        pattern_id=row["pattern_id"],
                        workflow_id=row["workflow_id"],
                        error_type=row["error_type"],
                        affected_tasks=json.loads(row["affected_tasks_json"] or "[]"),
                        occurrence_count=row["occurrence_count"],
                        total_rework_duration_sec=row["total_rework_duration_sec"],
                        estimated_rework_cost=row["estimated_rework_cost"],
                        identified_at=row["identified_at"],
                    )
                )
            return patterns

    # -------------------------------------------------------------
    # Optimization Candidates & Experiments
    # -------------------------------------------------------------
    def save_optimization_candidate(self, cand: OptimizationCandidate) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_optimization_candidates (
                    candidate_id, workflow_id, current_version, optimization_type,
                    title, description, current_behavior, proposed_behavior,
                    expected_time_reduction_pct, expected_cost_reduction_pct,
                    reversibility_score, validation_strategy, rollback_strategy,
                    supporting_evidence_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    status=excluded.status
                """,
                (
                    cand.candidate_id,
                    cand.workflow_id,
                    cand.current_version,
                    cand.optimization_type.value,
                    cand.title,
                    cand.description,
                    cand.current_behavior,
                    cand.proposed_behavior,
                    cand.expected_time_reduction_pct,
                    cand.expected_cost_reduction_pct,
                    cand.reversibility_score,
                    cand.validation_strategy,
                    cand.rollback_strategy,
                    json.dumps(cand.supporting_evidence),
                    cand.status.value,
                    cand.created_at,
                ),
            )
            conn.commit()

    def list_candidates_for_workflow(self, workflow_id: str) -> List[OptimizationCandidate]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM proc_optimization_candidates WHERE workflow_id = ? ORDER BY expected_time_reduction_pct DESC",
                (workflow_id,),
            )
            candidates = []
            for row in cursor.fetchall():
                candidates.append(
                    OptimizationCandidate(
                        candidate_id=row["candidate_id"],
                        workflow_id=row["workflow_id"],
                        current_version=row["current_version"],
                        optimization_type=OptimizationType(row["optimization_type"]),
                        title=row["title"],
                        description=row["description"],
                        current_behavior=row["current_behavior"],
                        proposed_behavior=row["proposed_behavior"],
                        expected_time_reduction_pct=row["expected_time_reduction_pct"],
                        expected_cost_reduction_pct=row["expected_cost_reduction_pct"],
                        reversibility_score=row["reversibility_score"],
                        validation_strategy=row["validation_strategy"],
                        rollback_strategy=row["rollback_strategy"],
                        supporting_evidence=json.loads(row["supporting_evidence_json"] or "[]"),
                        status=OptimizationStatus(row["status"]),
                        created_at=row["created_at"],
                    )
                )
            return candidates

    def save_experiment(self, exp: OptimizationExperimentRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_experiments (
                    experiment_id, candidate_id, workflow_id, baseline_trace_count,
                    target_trace_count, guardrail_metrics_json, observed_improvement_pct,
                    is_guardrail_breached, status, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(experiment_id) DO UPDATE SET
                    observed_improvement_pct=excluded.observed_improvement_pct,
                    is_guardrail_breached=excluded.is_guardrail_breached,
                    status=excluded.status,
                    completed_at=excluded.completed_at
                """,
                (
                    exp.experiment_id,
                    exp.candidate_id,
                    exp.workflow_id,
                    exp.baseline_trace_count,
                    exp.target_trace_count,
                    json.dumps(exp.guardrail_metrics),
                    exp.observed_improvement_pct,
                    1 if exp.is_guardrail_breached else 0,
                    exp.status.value,
                    exp.started_at,
                    exp.completed_at,
                ),
            )
            conn.commit()

    def get_experiment(self, experiment_id: str) -> Optional[OptimizationExperimentRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM proc_experiments WHERE experiment_id = ?", (experiment_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return OptimizationExperimentRecord(
                experiment_id=row["experiment_id"],
                candidate_id=row["candidate_id"],
                workflow_id=row["workflow_id"],
                baseline_trace_count=row["baseline_trace_count"],
                target_trace_count=row["target_trace_count"],
                guardrail_metrics=json.loads(row["guardrail_metrics_json"] or "{}"),
                observed_improvement_pct=row["observed_improvement_pct"],
                is_guardrail_breached=bool(row["is_guardrail_breached"]),
                status=ExperimentStatus(row["status"]),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
            )

    # -------------------------------------------------------------
    # Workflow Change Governance
    # -------------------------------------------------------------
    def save_governance_record(self, gov: WorkflowChangeGovernanceRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proc_change_governance (
                    governance_id, workflow_id, candidate_id, from_version,
                    to_version, approved_by, approval_token, change_status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(governance_id) DO UPDATE SET
                    approved_by=excluded.approved_by,
                    approval_token=excluded.approval_token,
                    change_status=excluded.change_status,
                    updated_at=excluded.updated_at
                """,
                (
                    gov.governance_id,
                    gov.workflow_id,
                    gov.candidate_id,
                    gov.from_version,
                    gov.to_version,
                    gov.approved_by,
                    gov.approval_token,
                    gov.change_status,
                    gov.created_at,
                    gov.updated_at,
                ),
            )
            conn.commit()

    def get_governance_record(self, governance_id: str) -> Optional[WorkflowChangeGovernanceRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM proc_change_governance WHERE governance_id = ?", (governance_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return WorkflowChangeGovernanceRecord(
                governance_id=row["governance_id"],
                workflow_id=row["workflow_id"],
                candidate_id=row["candidate_id"],
                from_version=row["from_version"],
                to_version=row["to_version"],
                approved_by=row["approved_by"],
                approval_token=row["approval_token"],
                change_status=row["change_status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
