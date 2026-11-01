"""
OMNIA Module 45: Autonomous Quality Assurance, Software Verification & Continuous Testing Intelligence
Persistence Repository - persistence.py

Manages durable storage for QA & Software Verification records across SQLite tables.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from qa_verification.models import (
    AcceptanceCriterion,
    CoverageRecord,
    DefectCategory,
    DefectRecord,
    DefectSeverity,
    FlakyClassification,
    FlakyTestRecord,
    GeneratedTestCase,
    MutationTestResult,
    PerformanceAssessment,
    QualityAssessment,
    QualityTier,
    RegressionRecord,
    RepairVerification,
    RequirementType,
    TestCategory,
    TestEvidence,
    TestStrategy,
    VerificationExecution,
    VerificationMission,
    VerificationProject,
    VerificationRequirement,
    VerificationResult,
    VerificationStatus,
)

logger = logging.getLogger("Omnia.QAVerification.Persistence")


class QAVerificationRepository:
    """Repository managing persistence for Module 45 entities."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Projects & Requirements
    # ------------------------------------------------------------------
    def save_project(self, p: VerificationProject) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_projects (
                    project_id, name, repository_ref, framework, is_active,
                    metadata_json, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.project_id,
                    p.name,
                    p.repository_ref,
                    p.framework,
                    1 if p.is_active else 0,
                    json.dumps(p.metadata),
                    p.registered_at,
                ),
            )

    def get_project(self, project_id: str) -> Optional[VerificationProject]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM qa_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if not row:
                return None
            return VerificationProject(
                project_id=row["project_id"],
                name=row["name"],
                repository_ref=row["repository_ref"],
                framework=row["framework"],
                is_active=bool(row["is_active"]),
                metadata=json.loads(row["metadata_json"] or "{}"),
                registered_at=row["registered_at"],
            )

    def save_requirement(self, req: VerificationRequirement) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_requirements (
                    requirement_id, project_id, title, description, requirement_type,
                    source_reference, is_ambiguous, ambiguity_notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    req.requirement_id,
                    req.project_id,
                    req.title,
                    req.description,
                    req.requirement_type.value,
                    req.source_reference,
                    1 if req.is_ambiguous else 0,
                    req.ambiguity_notes,
                    req.created_at,
                ),
            )

    def get_requirement(self, requirement_id: str) -> Optional[VerificationRequirement]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM qa_requirements WHERE requirement_id = ?",
                (requirement_id,),
            ).fetchone()
            if not row:
                return None
            return VerificationRequirement(
                requirement_id=row["requirement_id"],
                project_id=row["project_id"],
                title=row["title"],
                description=row["description"],
                requirement_type=RequirementType(row["requirement_type"]),
                source_reference=row["source_reference"],
                is_ambiguous=bool(row["is_ambiguous"]),
                ambiguity_notes=row["ambiguity_notes"],
                created_at=row["created_at"],
            )

    def list_requirements(self, project_id: str) -> List[VerificationRequirement]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_requirements WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            return [
                VerificationRequirement(
                    requirement_id=r["requirement_id"],
                    project_id=r["project_id"],
                    title=r["title"],
                    description=r["description"],
                    requirement_type=RequirementType(r["requirement_type"]),
                    source_reference=r["source_reference"],
                    is_ambiguous=bool(r["is_ambiguous"]),
                    ambiguity_notes=r["ambiguity_notes"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Acceptance Criteria & Strategies
    # ------------------------------------------------------------------
    def save_acceptance_criterion(self, ac: AcceptanceCriterion) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_acceptance_criteria (
                    criterion_id, requirement_id, expected_behavior,
                    preconditions_json, inputs_json, expected_outputs_json,
                    failure_conditions_json, priority, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ac.criterion_id,
                    ac.requirement_id,
                    ac.expected_behavior,
                    json.dumps(ac.preconditions),
                    json.dumps(ac.inputs),
                    json.dumps(ac.expected_outputs),
                    json.dumps(ac.failure_conditions),
                    ac.priority,
                    ac.confidence,
                ),
            )

    def list_acceptance_criteria(self, requirement_id: str) -> List[AcceptanceCriterion]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_acceptance_criteria WHERE requirement_id = ?",
                (requirement_id,),
            ).fetchall()
            return [
                AcceptanceCriterion(
                    criterion_id=r["criterion_id"],
                    requirement_id=r["requirement_id"],
                    expected_behavior=r["expected_behavior"],
                    preconditions=json.loads(r["preconditions_json"] or "[]"),
                    inputs=json.loads(r["inputs_json"] or "{}"),
                    expected_outputs=json.loads(r["expected_outputs_json"] or "{}"),
                    failure_conditions=json.loads(r["failure_conditions_json"] or "[]"),
                    priority=r["priority"],
                    confidence=r["confidence"],
                )
                for r in rows
            ]

    def save_test_strategy(self, ts: TestStrategy) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_test_strategies (
                    strategy_id, project_id, name, target_categories_json,
                    risk_weighting_json, allocated_budget_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts.strategy_id,
                    ts.project_id,
                    ts.name,
                    json.dumps([c.value for c in ts.target_categories]),
                    json.dumps(ts.risk_weighting),
                    ts.allocated_budget_seconds,
                    ts.created_at,
                ),
            )

    def get_test_strategy(self, strategy_id: str) -> Optional[TestStrategy]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM qa_test_strategies WHERE strategy_id = ?",
                (strategy_id,),
            ).fetchone()
            if not row:
                return None
            return TestStrategy(
                strategy_id=row["strategy_id"],
                project_id=row["project_id"],
                name=row["name"],
                target_categories=[TestCategory(c) for c in json.loads(row["target_categories_json"] or "[]")],
                risk_weighting=json.loads(row["risk_weighting_json"] or "{}"),
                allocated_budget_seconds=row["allocated_budget_seconds"],
                created_at=row["created_at"],
            )

    # ------------------------------------------------------------------
    # Test Cases, Missions & Executions
    # ------------------------------------------------------------------
    def save_test_case(self, tc: GeneratedTestCase) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_test_cases (
                    test_case_id, criterion_id, name, category, objective,
                    inputs_json, assertions_json, is_edge_case, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tc.test_case_id,
                    tc.criterion_id,
                    tc.name,
                    tc.category.value,
                    tc.objective,
                    json.dumps(tc.inputs),
                    json.dumps(tc.assertions),
                    1 if tc.is_edge_case else 0,
                    tc.created_at,
                ),
            )

    def list_test_cases(self, criterion_id: str) -> List[GeneratedTestCase]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_test_cases WHERE criterion_id = ?",
                (criterion_id,),
            ).fetchall()
            return [
                GeneratedTestCase(
                    test_case_id=r["test_case_id"],
                    criterion_id=r["criterion_id"],
                    name=r["name"],
                    category=TestCategory(r["category"]),
                    objective=r["objective"],
                    inputs=json.loads(r["inputs_json"] or "{}"),
                    assertions=json.loads(r["assertions_json"] or "[]"),
                    is_edge_case=bool(r["is_edge_case"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def save_mission(self, m: VerificationMission) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_missions (
                    mission_id, project_id, strategy_id, status, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    m.mission_id,
                    m.project_id,
                    m.strategy_id,
                    m.status.value,
                    m.created_at,
                    m.completed_at,
                ),
            )

    def get_mission(self, mission_id: str) -> Optional[VerificationMission]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM qa_missions WHERE mission_id = ?",
                (mission_id,),
            ).fetchone()
            if not row:
                return None
            return VerificationMission(
                mission_id=row["mission_id"],
                project_id=row["project_id"],
                strategy_id=row["strategy_id"],
                status=VerificationStatus(row["status"]),
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )

    def save_execution(self, e: VerificationExecution) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_executions (
                    execution_id, mission_id, test_case_id, status,
                    duration_seconds, stdout, stderr, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    e.execution_id,
                    e.mission_id,
                    e.test_case_id,
                    e.status.value,
                    e.duration_seconds,
                    e.stdout,
                    e.stderr,
                    e.executed_at,
                ),
            )

    def save_result(self, res: VerificationResult) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_results (
                    result_id, execution_id, passed, observed_output_json,
                    discrepancies_json, evidence_ids_json, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    res.result_id,
                    res.execution_id,
                    1 if res.passed else 0,
                    json.dumps(res.observed_output),
                    json.dumps(res.discrepancies),
                    json.dumps(res.evidence_ids),
                    res.evaluated_at,
                ),
            )

    def save_evidence(self, ev: TestEvidence) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_evidence (
                    evidence_id, execution_id, evidence_type, payload,
                    checksum_sha256, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ev.evidence_id,
                    ev.execution_id,
                    ev.evidence_type,
                    ev.payload,
                    ev.checksum_sha256,
                    ev.captured_at,
                ),
            )

    # ------------------------------------------------------------------
    # Defects & Flaky Tests
    # ------------------------------------------------------------------
    def save_defect(self, d: DefectRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_defects (
                    defect_id, project_id, execution_id, title, category,
                    severity, reproduction_steps_json, stack_trace,
                    is_reproduced, is_resolved, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.defect_id,
                    d.project_id,
                    d.execution_id,
                    d.title,
                    d.category.value,
                    d.severity.value,
                    json.dumps(d.reproduction_steps),
                    d.stack_trace,
                    1 if d.is_reproduced else 0,
                    1 if d.is_resolved else 0,
                    d.detected_at,
                ),
            )

    def get_defect(self, defect_id: str) -> Optional[DefectRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM qa_defects WHERE defect_id = ?",
                (defect_id,),
            ).fetchone()
            if not row:
                return None
            return DefectRecord(
                defect_id=row["defect_id"],
                project_id=row["project_id"],
                execution_id=row["execution_id"],
                title=row["title"],
                category=DefectCategory(row["category"]),
                severity=DefectSeverity(row["severity"]),
                reproduction_steps=json.loads(row["reproduction_steps_json"] or "[]"),
                stack_trace=row["stack_trace"],
                is_reproduced=bool(row["is_reproduced"]),
                is_resolved=bool(row["is_resolved"]),
                detected_at=row["detected_at"],
            )

    def update_defect_resolution(self, defect_id: str, is_resolved: bool) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE qa_defects SET is_resolved = ? WHERE defect_id = ?",
                (1 if is_resolved else 0, defect_id),
            )

    def list_unresolved_defects(self, project_id: str) -> List[DefectRecord]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM qa_defects WHERE project_id = ? AND is_resolved = 0",
                (project_id,),
            ).fetchall()
            return [
                DefectRecord(
                    defect_id=r["defect_id"],
                    project_id=r["project_id"],
                    execution_id=r["execution_id"],
                    title=r["title"],
                    category=DefectCategory(r["category"]),
                    severity=DefectSeverity(r["severity"]),
                    reproduction_steps=json.loads(r["reproduction_steps_json"] or "[]"),
                    stack_trace=r["stack_trace"],
                    is_reproduced=bool(r["is_reproduced"]),
                    is_resolved=bool(r["is_resolved"]),
                    detected_at=r["detected_at"],
                )
                for r in rows
            ]

    def save_flaky_test(self, ft: FlakyTestRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_flaky_tests (
                    flaky_id, test_case_id, runs_evaluated, passes,
                    failures, variance_score, classification, assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ft.flaky_id,
                    ft.test_case_id,
                    ft.runs_evaluated,
                    ft.passes,
                    ft.failures,
                    ft.variance_score,
                    ft.classification.value,
                    ft.assessed_at,
                ),
            )

    def save_mutation(self, mut: MutationTestResult) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_mutations (
                    mutation_id, mission_id, mutant_type, killed,
                    surviving_details, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    mut.mutation_id,
                    mut.mission_id,
                    mut.mutant_type,
                    1 if mut.killed else 0,
                    mut.surviving_details,
                    mut.executed_at,
                ),
            )

    # ------------------------------------------------------------------
    # Quality Assessments & Repairs
    # ------------------------------------------------------------------
    def save_quality_assessment(self, qa: QualityAssessment) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_quality_assessments (
                    assessment_id, project_id, mission_id, tier, overall_score,
                    functional_pass_rate, coverage_score, unresolved_defects_count,
                    regressions_count, flaky_tests_count, dimension_scores_json,
                    summary_notes, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    qa.assessment_id,
                    qa.project_id,
                    qa.mission_id,
                    qa.tier.value,
                    qa.overall_score,
                    qa.functional_pass_rate,
                    qa.coverage_score,
                    qa.unresolved_defects_count,
                    qa.regressions_count,
                    qa.flaky_tests_count,
                    json.dumps(qa.dimension_scores),
                    qa.summary_notes,
                    qa.evaluated_at,
                ),
            )

    def save_repair_verification(self, rv: RepairVerification) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO qa_repair_verifications (
                    repair_verification_id, defect_id, patch_ref, retest_passed,
                    regressions_found, verification_evidence_json, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rv.repair_verification_id,
                    rv.defect_id,
                    rv.patch_ref,
                    1 if rv.retest_passed else 0,
                    rv.regressions_found,
                    json.dumps(rv.verification_evidence),
                    rv.verified_at,
                ),
            )
            # If retest passed, mark defect resolved
            if rv.retest_passed and rv.regressions_found == 0:
                conn.execute(
                    "UPDATE qa_defects SET is_resolved = 1 WHERE defect_id = ?",
                    (rv.defect_id,),
                )
