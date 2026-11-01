"""
OMNIA Module 44: Autonomous Software Delivery, CI/CD Intelligence & Release Engineering
Persistence Repository - persistence.py

Manages durable storage for Software Delivery records across SQLite tables.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from software_delivery.models import (
    ArtifactAttestation,
    BuildArtifactRecord,
    BuildExecutionRecord,
    BuildStatus,
    ChangeCategory,
    ChangeImpactReport,
    DependencyAssessment,
    DeploymentHandoffRecord,
    FindingSeverity,
    GateStatus,
    HandoffStatus,
    PipelineDefinition,
    PipelineExecution,
    PipelineStageExecution,
    PipelineStageType,
    PipelineStatus,
    QualityGateResult,
    RegressionFinding,
    ReleaseCandidateRecord,
    ReleaseStage,
    RepairAttemptRecord,
    RepositoryType,
    SecurityAssessment,
    SourceRepository,
    SourceRevision,
    TestExecutionRecord,
    TestStatus,
)

logger = logging.getLogger("Omnia.SoftwareDelivery.Persistence")


class SoftwareDeliveryRepository:
    """Repository managing persistence for Module 44 entities."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Source Repositories & Revisions
    # ------------------------------------------------------------------
    def save_repository(self, repo: SourceRepository) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_repositories (
                    repository_id, name, provider_type, clone_url, default_branch,
                    is_active, metadata_json, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repo.repository_id,
                    repo.name,
                    repo.provider_type.value,
                    repo.clone_url,
                    repo.default_branch,
                    1 if repo.is_active else 0,
                    json.dumps(repo.metadata),
                    repo.registered_at,
                ),
            )

    def get_repository(self, repository_id: str) -> Optional[SourceRepository]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_repositories WHERE repository_id = ?",
                (repository_id,),
            ).fetchone()
            if not row:
                return None
            return SourceRepository(
                repository_id=row["repository_id"],
                name=row["name"],
                provider_type=RepositoryType(row["provider_type"]),
                clone_url=row["clone_url"],
                default_branch=row["default_branch"],
                is_active=bool(row["is_active"]),
                metadata=json.loads(row["metadata_json"] or "{}"),
                registered_at=row["registered_at"],
            )

    def list_repositories(self) -> List[SourceRepository]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM delivery_repositories WHERE is_active = 1").fetchall()
            return [
                SourceRepository(
                    repository_id=r["repository_id"],
                    name=r["name"],
                    provider_type=RepositoryType(r["provider_type"]),
                    clone_url=r["clone_url"],
                    default_branch=r["default_branch"],
                    is_active=bool(r["is_active"]),
                    metadata=json.loads(r["metadata_json"] or "{}"),
                    registered_at=r["registered_at"],
                )
                for r in rows
            ]

    def save_revision(self, rev: SourceRevision) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_revisions (
                    revision_id, repository_id, commit_hash, branch, author,
                    commit_message, timestamp, parent_commits_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rev.revision_id,
                    rev.repository_id,
                    rev.commit_hash,
                    rev.branch,
                    rev.author,
                    rev.commit_message,
                    rev.timestamp,
                    json.dumps(rev.parent_commits),
                ),
            )

    def get_revision(self, revision_id: str) -> Optional[SourceRevision]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_revisions WHERE revision_id = ?",
                (revision_id,),
            ).fetchone()
            if not row:
                return None
            return SourceRevision(
                revision_id=row["revision_id"],
                repository_id=row["repository_id"],
                commit_hash=row["commit_hash"],
                branch=row["branch"],
                author=row["author"],
                commit_message=row["commit_message"],
                timestamp=row["timestamp"],
                parent_commits=json.loads(row["parent_commits_json"] or "[]"),
            )

    # ------------------------------------------------------------------
    # Change Impact Reports
    # ------------------------------------------------------------------
    def save_impact_report(self, r: ChangeImpactReport) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_impact_reports (
                    report_id, revision_id, repository_id, changed_files_json,
                    change_categories_json, impacted_modules_json, relevant_test_suites_json,
                    migration_detected, security_sensitive, confidence_score, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.report_id,
                    r.revision_id,
                    r.repository_id,
                    json.dumps(r.changed_files),
                    json.dumps([c.value for c in r.change_categories]),
                    json.dumps(r.impacted_modules),
                    json.dumps(r.relevant_test_suites),
                    1 if r.migration_detected else 0,
                    1 if r.security_sensitive else 0,
                    r.confidence_score,
                    json.dumps(r.evidence),
                    r.created_at,
                ),
            )

    def get_impact_report(self, report_id: str) -> Optional[ChangeImpactReport]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_impact_reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
            if not row:
                return None
            return ChangeImpactReport(
                report_id=row["report_id"],
                revision_id=row["revision_id"],
                repository_id=row["repository_id"],
                changed_files=json.loads(row["changed_files_json"] or "[]"),
                change_categories=[ChangeCategory(c) for c in json.loads(row["change_categories_json"] or "[]")],
                impacted_modules=json.loads(row["impacted_modules_json"] or "[]"),
                relevant_test_suites=json.loads(row["relevant_test_suites_json"] or "[]"),
                migration_detected=bool(row["migration_detected"]),
                security_sensitive=bool(row["security_sensitive"]),
                confidence_score=row["confidence_score"],
                evidence=json.loads(row["evidence_json"] or "{}"),
                created_at=row["created_at"],
            )

    # ------------------------------------------------------------------
    # Pipeline Definitions & Executions
    # ------------------------------------------------------------------
    def save_pipeline_definition(self, p: PipelineDefinition) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_pipeline_definitions (
                    pipeline_id, name, repository_id, stages_json, triggers_json,
                    env_vars_json, timeout_seconds, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.pipeline_id,
                    p.name,
                    p.repository_id,
                    json.dumps([s.value for s in p.stages]),
                    json.dumps(p.triggers),
                    json.dumps(p.environment_variables),
                    p.timeout_seconds,
                    1 if p.is_active else 0,
                    p.created_at,
                ),
            )

    def get_pipeline_definition(self, pipeline_id: str) -> Optional[PipelineDefinition]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_pipeline_definitions WHERE pipeline_id = ?",
                (pipeline_id,),
            ).fetchone()
            if not row:
                return None
            return PipelineDefinition(
                pipeline_id=row["pipeline_id"],
                name=row["name"],
                repository_id=row["repository_id"],
                stages=[PipelineStageType(s) for s in json.loads(row["stages_json"] or "[]")],
                triggers=json.loads(row["triggers_json"] or "[]"),
                environment_variables=json.loads(row["env_vars_json"] or "{}"),
                timeout_seconds=row["timeout_seconds"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
            )

    def save_pipeline_execution(self, pe: PipelineExecution) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_pipeline_executions (
                    execution_id, pipeline_id, revision_id, status, stages_executed_json,
                    started_at, completed_at, total_duration_seconds, error_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pe.execution_id,
                    pe.pipeline_id,
                    pe.revision_id,
                    pe.status.value,
                    json.dumps(pe.stages_executed),
                    pe.started_at,
                    pe.completed_at,
                    pe.total_duration_seconds,
                    pe.error_summary,
                ),
            )

    def get_pipeline_execution(self, execution_id: str) -> Optional[PipelineExecution]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_pipeline_executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if not row:
                return None
            return PipelineExecution(
                execution_id=row["execution_id"],
                pipeline_id=row["pipeline_id"],
                revision_id=row["revision_id"],
                status=PipelineStatus(row["status"]),
                stages_executed=json.loads(row["stages_executed_json"] or "[]"),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                total_duration_seconds=row["total_duration_seconds"],
                error_summary=row["error_summary"],
            )

    def save_stage_execution(self, se: PipelineStageExecution) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_stage_executions (
                    stage_id, pipeline_execution_id, stage_type, status,
                    started_at, completed_at, duration_seconds, exit_code, logs, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    se.stage_id,
                    se.pipeline_execution_id,
                    se.stage_type.value,
                    se.status.value,
                    se.started_at,
                    se.completed_at,
                    se.duration_seconds,
                    se.exit_code,
                    se.logs,
                    se.error_message,
                ),
            )

    def list_stage_executions(self, pipeline_execution_id: str) -> List[PipelineStageExecution]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM delivery_stage_executions WHERE pipeline_execution_id = ? ORDER BY started_at ASC",
                (pipeline_execution_id,),
            ).fetchall()
            return [
                PipelineStageExecution(
                    stage_id=r["stage_id"],
                    pipeline_execution_id=r["pipeline_execution_id"],
                    stage_type=PipelineStageType(r["stage_type"]),
                    status=PipelineStatus(r["status"]),
                    started_at=r["started_at"],
                    completed_at=r["completed_at"],
                    duration_seconds=r["duration_seconds"],
                    exit_code=r["exit_code"],
                    logs=r["logs"] or "",
                    error_message=r["error_message"],
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Build & Test Executions
    # ------------------------------------------------------------------
    def save_build_execution(self, b: BuildExecutionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_build_executions (
                    build_id, pipeline_execution_id, command, status,
                    artifact_paths_json, logs, duration_seconds, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    b.build_id,
                    b.pipeline_execution_id,
                    b.command,
                    b.status.value,
                    json.dumps(b.artifact_paths),
                    b.logs,
                    b.duration_seconds,
                    b.executed_at,
                ),
            )

    def get_build_execution(self, build_id: str) -> Optional[BuildExecutionRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_build_executions WHERE build_id = ?",
                (build_id,),
            ).fetchone()
            if not row:
                return None
            return BuildExecutionRecord(
                build_id=row["build_id"],
                pipeline_execution_id=row["pipeline_execution_id"],
                command=row["command"],
                status=BuildStatus(row["status"]),
                artifact_paths=json.loads(row["artifact_paths_json"] or "[]"),
                logs=row["logs"] or "",
                duration_seconds=row["duration_seconds"],
                executed_at=row["executed_at"],
            )

    def save_test_execution(self, t: TestExecutionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_test_executions (
                    test_run_id, pipeline_execution_id, suite_name, total_tests,
                    passed_tests, failed_tests, skipped_tests, duration_seconds,
                    coverage_pct, status, failure_details_json, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    t.test_run_id,
                    t.pipeline_execution_id,
                    t.suite_name,
                    t.total_tests,
                    t.passed_tests,
                    t.failed_tests,
                    t.skipped_tests,
                    t.duration_seconds,
                    t.coverage_pct,
                    t.status.value,
                    json.dumps(t.failure_details),
                    t.executed_at,
                ),
            )

    def get_test_execution(self, test_run_id: str) -> Optional[TestExecutionRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_test_executions WHERE test_run_id = ?",
                (test_run_id,),
            ).fetchone()
            if not row:
                return None
            return TestExecutionRecord(
                test_run_id=row["test_run_id"],
                pipeline_execution_id=row["pipeline_execution_id"],
                suite_name=row["suite_name"],
                total_tests=row["total_tests"],
                passed_tests=row["passed_tests"],
                failed_tests=row["failed_tests"],
                skipped_tests=row["skipped_tests"],
                duration_seconds=row["duration_seconds"],
                coverage_pct=row["coverage_pct"],
                status=TestStatus(row["status"]),
                failure_details=json.loads(row["failure_details_json"] or "[]"),
                executed_at=row["executed_at"],
            )

    # ------------------------------------------------------------------
    # Quality Gates & Security Assessments
    # ------------------------------------------------------------------
    def save_quality_gate(self, q: QualityGateResult) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_quality_gate_results (
                    gate_id, pipeline_execution_id, status, score, metrics_json,
                    violations_json, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q.gate_id,
                    q.pipeline_execution_id,
                    q.status.value,
                    q.score,
                    json.dumps(q.metrics),
                    json.dumps(q.violations),
                    q.evaluated_at,
                ),
            )

    def get_quality_gate(self, gate_id: str) -> Optional[QualityGateResult]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_quality_gate_results WHERE gate_id = ?",
                (gate_id,),
            ).fetchone()
            if not row:
                return None
            return QualityGateResult(
                gate_id=row["gate_id"],
                pipeline_execution_id=row["pipeline_execution_id"],
                status=GateStatus(row["status"]),
                score=row["score"],
                metrics=json.loads(row["metrics_json"] or "{}"),
                violations=json.loads(row["violations_json"] or "[]"),
                evaluated_at=row["evaluated_at"],
            )

    def save_dependency_assessment(self, d: DependencyAssessment) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_dependency_assessments (
                    assessment_id, revision_id, direct_dependency_count,
                    transitive_dependency_count, vulnerabilities_detected,
                    deprecated_dependencies_json, outdated_dependencies_json,
                    findings_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.assessment_id,
                    d.revision_id,
                    d.direct_dependency_count,
                    d.transitive_dependency_count,
                    d.vulnerabilities_detected,
                    json.dumps(d.deprecated_dependencies),
                    json.dumps(d.outdated_dependencies),
                    json.dumps(d.findings),
                    d.created_at,
                ),
            )

    def save_security_assessment(self, s: SecurityAssessment) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_security_assessments (
                    assessment_id, revision_id, secrets_found_count,
                    sast_violations_count, highest_severity, findings_json,
                    is_passing, scanned_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s.assessment_id,
                    s.revision_id,
                    s.secrets_found_count,
                    s.sast_violations_count,
                    s.highest_severity.value,
                    json.dumps(s.findings),
                    1 if s.is_passing else 0,
                    s.scanned_at,
                ),
            )

    # ------------------------------------------------------------------
    # Artifacts & Attestations
    # ------------------------------------------------------------------
    def save_artifact(self, a: BuildArtifactRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_artifacts (
                    artifact_id, pipeline_execution_id, name, artifact_type,
                    storage_uri, checksum_sha256, size_bytes, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    a.artifact_id,
                    a.pipeline_execution_id,
                    a.name,
                    a.artifact_type,
                    a.storage_uri,
                    a.checksum_sha256,
                    a.size_bytes,
                    json.dumps(a.metadata),
                    a.created_at,
                ),
            )

    def get_artifact(self, artifact_id: str) -> Optional[BuildArtifactRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            if not row:
                return None
            return BuildArtifactRecord(
                artifact_id=row["artifact_id"],
                pipeline_execution_id=row["pipeline_execution_id"],
                name=row["name"],
                artifact_type=row["artifact_type"],
                storage_uri=row["storage_uri"],
                checksum_sha256=row["checksum_sha256"],
                size_bytes=row["size_bytes"],
                metadata=json.loads(row["metadata_json"] or "{}"),
                created_at=row["created_at"],
            )

    def save_attestation(self, att: ArtifactAttestation) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_attestations (
                    attestation_id, artifact_id, predicate_type, builder_id,
                    source_repository, source_commit, build_config_json,
                    is_signed, signature_ref, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    att.attestation_id,
                    att.artifact_id,
                    att.predicate_type,
                    att.builder_id,
                    att.source_repository,
                    att.source_commit,
                    json.dumps(att.build_config),
                    1 if att.is_signed else 0,
                    att.signature_ref,
                    att.created_at,
                ),
            )

    # ------------------------------------------------------------------
    # Regressions & Autonomous Repairs
    # ------------------------------------------------------------------
    def save_regression(self, r: RegressionFinding) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_regression_findings (
                    regression_id, pipeline_execution_id, component_name,
                    metric_name, baseline_value, current_value, delta_pct,
                    severity, description, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.regression_id,
                    r.pipeline_execution_id,
                    r.component_name,
                    r.metric_name,
                    r.baseline_value,
                    r.current_value,
                    r.delta_pct,
                    r.severity.value,
                    r.description,
                    r.detected_at,
                ),
            )

    def save_repair_attempt(self, rep: RepairAttemptRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_repair_attempts (
                    repair_id, pipeline_execution_id, failure_type, proposed_patch,
                    applied, retest_success, retry_count, max_retries_allowed,
                    approval_token, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rep.repair_id,
                    rep.pipeline_execution_id,
                    rep.failure_type,
                    rep.proposed_patch,
                    1 if rep.applied else 0,
                    1 if rep.retest_success else 0,
                    rep.retry_count,
                    rep.max_retries_allowed,
                    rep.approval_token,
                    rep.created_at,
                ),
            )

    # ------------------------------------------------------------------
    # Release Candidates & Deployment Handoffs
    # ------------------------------------------------------------------
    def save_release_candidate(self, rc: ReleaseCandidateRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_release_candidates (
                    candidate_id, version, artifact_id, source_revision_id,
                    stage, release_notes, approval_token, approver, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rc.candidate_id,
                    rc.version,
                    rc.artifact_id,
                    rc.source_revision_id,
                    rc.stage.value,
                    rc.release_notes,
                    rc.approval_token,
                    rc.approver,
                    rc.created_at,
                ),
            )

    def get_release_candidate(self, candidate_id: str) -> Optional[ReleaseCandidateRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_release_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            if not row:
                return None
            return ReleaseCandidateRecord(
                candidate_id=row["candidate_id"],
                version=row["version"],
                artifact_id=row["artifact_id"],
                source_revision_id=row["source_revision_id"],
                stage=ReleaseStage(row["stage"]),
                release_notes=row["release_notes"] or "",
                approval_token=row["approval_token"],
                approver=row["approver"],
                created_at=row["created_at"],
            )

    def save_deployment_handoff(self, h: DeploymentHandoffRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO delivery_deployment_handoffs (
                    handoff_id, release_candidate_id, target_environment_id,
                    deployment_strategy, status, module43_deployment_id,
                    verification_evidence_json, requested_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    h.handoff_id,
                    h.release_candidate_id,
                    h.target_environment_id,
                    h.deployment_strategy,
                    h.status.value,
                    h.module43_deployment_id,
                    json.dumps(h.verification_evidence),
                    h.requested_at,
                    h.completed_at,
                ),
            )

    def get_deployment_handoff(self, handoff_id: str) -> Optional[DeploymentHandoffRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM delivery_deployment_handoffs WHERE handoff_id = ?",
                (handoff_id,),
            ).fetchone()
            if not row:
                return None
            return DeploymentHandoffRecord(
                handoff_id=row["handoff_id"],
                release_candidate_id=row["release_candidate_id"],
                target_environment_id=row["target_environment_id"],
                deployment_strategy=row["deployment_strategy"],
                status=HandoffStatus(row["status"]),
                module43_deployment_id=row["module43_deployment_id"],
                verification_evidence=json.loads(row["verification_evidence_json"] or "{}"),
                requested_at=row["requested_at"],
                completed_at=row["completed_at"],
            )
