"""
Omnia Module 38: Autonomous Goal Management, Outcome Tracking & Strategic Execution Intelligence.
Persistence Layer: SQLite Repository for Schema Version 23 Tables.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from goals.models import (
    CorrectiveActionProposal,
    CorrectiveActionType,
    GoalChangeAuditRecord,
    GoalDefinition,
    GoalHealthRecord,
    GoalHealthState,
    GoalLifecycleState,
    GoalPriority,
    GoalProgressAssessment,
    GoalType,
    GoalVersionSnapshot,
    InitiativeRecord,
    KeyResultDefinition,
    MetricType,
    MilestoneRecord,
    OutcomeEvidenceRecord,
    VerificationTier,
)


class GoalRepository:
    """Manages persistent SQLite storage for all Module 38 goal and outcome records."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # -------------------------------------------------------------
    # Goal Definitions & Versions
    # -------------------------------------------------------------
    def save_goal(self, goal: GoalDefinition) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_definitions (
                    goal_id, title, description, purpose, owner, goal_type, priority,
                    state, version, parent_goal_id, start_date, target_date,
                    success_criteria_json, constraints_json, dependencies_json,
                    resources_json, review_schedule, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(goal_id) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    purpose=excluded.purpose,
                    owner=excluded.owner,
                    goal_type=excluded.goal_type,
                    priority=excluded.priority,
                    state=excluded.state,
                    version=excluded.version,
                    parent_goal_id=excluded.parent_goal_id,
                    start_date=excluded.start_date,
                    target_date=excluded.target_date,
                    success_criteria_json=excluded.success_criteria_json,
                    constraints_json=excluded.constraints_json,
                    dependencies_json=excluded.dependencies_json,
                    resources_json=excluded.resources_json,
                    review_schedule=excluded.review_schedule,
                    updated_at=excluded.updated_at
                """,
                (
                    goal.goal_id,
                    goal.title,
                    goal.description,
                    goal.purpose,
                    goal.owner,
                    goal.goal_type.value,
                    goal.priority.value,
                    goal.state.value,
                    goal.version,
                    goal.parent_goal_id,
                    goal.start_date,
                    goal.target_date,
                    json.dumps(goal.success_criteria),
                    json.dumps(goal.constraints),
                    json.dumps(goal.dependencies),
                    json.dumps(goal.resource_requirements),
                    goal.review_schedule,
                    goal.created_at,
                    goal.updated_at,
                ),
            )
            conn.commit()

    def get_goal(self, goal_id: str) -> Optional[GoalDefinition]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM goal_definitions WHERE goal_id = ?", (goal_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return GoalDefinition(
                goal_id=row["goal_id"],
                title=row["title"],
                description=row["description"],
                purpose=row["purpose"],
                owner=row["owner"],
                goal_type=GoalType(row["goal_type"]),
                priority=GoalPriority(row["priority"]),
                state=GoalLifecycleState(row["state"]),
                version=row["version"],
                parent_goal_id=row["parent_goal_id"],
                start_date=row["start_date"],
                target_date=row["target_date"],
                success_criteria=json.loads(row["success_criteria_json"] or "[]"),
                constraints=json.loads(row["constraints_json"] or "[]"),
                dependencies=json.loads(row["dependencies_json"] or "[]"),
                resource_requirements=json.loads(row["resources_json"] or "{}"),
                review_schedule=row["review_schedule"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_goals(self, parent_goal_id: Optional[str] = None, state: Optional[GoalLifecycleState] = None) -> List[GoalDefinition]:
        query = "SELECT * FROM goal_definitions WHERE 1=1"
        params: List[Any] = []
        if parent_goal_id is not None:
            query += " AND parent_goal_id = ?"
            params.append(parent_goal_id)
        if state is not None:
            query += " AND state = ?"
            params.append(state.value)
        query += " ORDER BY created_at DESC"

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            goals = []
            for row in cursor.fetchall():
                goals.append(
                    GoalDefinition(
                        goal_id=row["goal_id"],
                        title=row["title"],
                        description=row["description"],
                        purpose=row["purpose"],
                        owner=row["owner"],
                        goal_type=GoalType(row["goal_type"]),
                        priority=GoalPriority(row["priority"]),
                        state=GoalLifecycleState(row["state"]),
                        version=row["version"],
                        parent_goal_id=row["parent_goal_id"],
                        start_date=row["start_date"],
                        target_date=row["target_date"],
                        success_criteria=json.loads(row["success_criteria_json"] or "[]"),
                        constraints=json.loads(row["constraints_json"] or "[]"),
                        dependencies=json.loads(row["dependencies_json"] or "[]"),
                        resource_requirements=json.loads(row["resources_json"] or "{}"),
                        review_schedule=row["review_schedule"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                )
            return goals

    def save_version_snapshot(self, snapshot: GoalVersionSnapshot) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_versions (
                    snapshot_id, goal_id, version, title, description,
                    state, target_date, success_criteria_json, constraints_json,
                    changed_by, change_reason, snapshot_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.goal_id,
                    snapshot.version,
                    snapshot.title,
                    snapshot.description,
                    snapshot.state,
                    snapshot.target_date,
                    json.dumps(snapshot.success_criteria),
                    json.dumps(snapshot.constraints),
                    snapshot.changed_by,
                    snapshot.change_reason,
                    snapshot.snapshot_at,
                ),
            )
            conn.commit()

    def get_goal_versions(self, goal_id: str) -> List[GoalVersionSnapshot]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_versions WHERE goal_id = ? ORDER BY version ASC", (goal_id,)
            )
            versions = []
            for row in cursor.fetchall():
                versions.append(
                    GoalVersionSnapshot(
                        snapshot_id=row["snapshot_id"],
                        goal_id=row["goal_id"],
                        version=row["version"],
                        title=row["title"],
                        description=row["description"],
                        state=row["state"],
                        target_date=row["target_date"],
                        success_criteria=json.loads(row["success_criteria_json"] or "[]"),
                        constraints=json.loads(row["constraints_json"] or "[]"),
                        changed_by=row["changed_by"],
                        change_reason=row["change_reason"],
                        snapshot_at=row["snapshot_at"],
                    )
                )
            return versions

    # -------------------------------------------------------------
    # Key Results
    # -------------------------------------------------------------
    def save_key_result(self, kr: KeyResultDefinition) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_key_results (
                    key_result_id, goal_id, metric_name, description, unit,
                    metric_type, baseline_value, target_value, current_reported_value,
                    current_verified_value, measurement_frequency, calculation_method,
                    required_verification_tier, confidence, is_satisfied, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_result_id) DO UPDATE SET
                    metric_name=excluded.metric_name,
                    description=excluded.description,
                    unit=excluded.unit,
                    metric_type=excluded.metric_type,
                    baseline_value=excluded.baseline_value,
                    target_value=excluded.target_value,
                    current_reported_value=excluded.current_reported_value,
                    current_verified_value=excluded.current_verified_value,
                    measurement_frequency=excluded.measurement_frequency,
                    calculation_method=excluded.calculation_method,
                    required_verification_tier=excluded.required_verification_tier,
                    confidence=excluded.confidence,
                    is_satisfied=excluded.is_satisfied,
                    last_updated=excluded.last_updated
                """,
                (
                    kr.key_result_id,
                    kr.goal_id,
                    kr.metric_name,
                    kr.description,
                    kr.unit,
                    kr.metric_type.value,
                    kr.baseline_value,
                    kr.target_value,
                    kr.current_reported_value,
                    kr.current_verified_value,
                    kr.measurement_frequency,
                    kr.calculation_method,
                    kr.required_verification_tier.value,
                    kr.confidence,
                    1 if kr.is_satisfied else 0,
                    kr.last_updated,
                ),
            )
            conn.commit()

    def get_key_result(self, key_result_id: str) -> Optional[KeyResultDefinition]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_key_results WHERE key_result_id = ?", (key_result_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return KeyResultDefinition(
                key_result_id=row["key_result_id"],
                goal_id=row["goal_id"],
                metric_name=row["metric_name"],
                description=row["description"],
                unit=row["unit"],
                metric_type=MetricType(row["metric_type"]),
                baseline_value=row["baseline_value"],
                target_value=row["target_value"],
                current_reported_value=row["current_reported_value"],
                current_verified_value=row["current_verified_value"],
                measurement_frequency=row["measurement_frequency"],
                calculation_method=row["calculation_method"],
                required_verification_tier=VerificationTier(row["required_verification_tier"]),
                confidence=row["confidence"],
                is_satisfied=bool(row["is_satisfied"]),
                last_updated=row["last_updated"],
            )

    def list_key_results(self, goal_id: str) -> List[KeyResultDefinition]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_key_results WHERE goal_id = ? ORDER BY key_result_id",
                (goal_id,),
            )
            krs = []
            for row in cursor.fetchall():
                krs.append(
                    KeyResultDefinition(
                        key_result_id=row["key_result_id"],
                        goal_id=row["goal_id"],
                        metric_name=row["metric_name"],
                        description=row["description"],
                        unit=row["unit"],
                        metric_type=MetricType(row["metric_type"]),
                        baseline_value=row["baseline_value"],
                        target_value=row["target_value"],
                        current_reported_value=row["current_reported_value"],
                        current_verified_value=row["current_verified_value"],
                        measurement_frequency=row["measurement_frequency"],
                        calculation_method=row["calculation_method"],
                        required_verification_tier=VerificationTier(row["required_verification_tier"]),
                        confidence=row["confidence"],
                        is_satisfied=bool(row["is_satisfied"]),
                        last_updated=row["last_updated"],
                    )
                )
            return krs

    # -------------------------------------------------------------
    # Evidence Records
    # -------------------------------------------------------------
    def save_evidence_record(self, evidence: OutcomeEvidenceRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_evidence_records (
                    evidence_id, key_result_id, goal_id, verification_tier,
                    data_source, observed_value, evidence_summary, evidence_payload_json,
                    evidence_hash, verified_by, approval_token, verified_at, is_valid
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    observed_value=excluded.observed_value,
                    evidence_summary=excluded.evidence_summary,
                    evidence_payload_json=excluded.evidence_payload_json,
                    evidence_hash=excluded.evidence_hash,
                    verified_by=excluded.verified_by,
                    approval_token=excluded.approval_token,
                    verified_at=excluded.verified_at,
                    is_valid=excluded.is_valid
                """,
                (
                    evidence.evidence_id,
                    evidence.key_result_id,
                    evidence.goal_id,
                    evidence.verification_tier.value,
                    evidence.data_source,
                    evidence.observed_value,
                    evidence.evidence_summary,
                    json.dumps(evidence.evidence_payload),
                    evidence.evidence_hash,
                    evidence.verified_by,
                    evidence.approval_token,
                    evidence.verified_at,
                    1 if evidence.is_valid else 0,
                ),
            )
            conn.commit()

    def list_evidence_for_kr(self, key_result_id: str) -> List[OutcomeEvidenceRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_evidence_records WHERE key_result_id = ? ORDER BY verified_at DESC",
                (key_result_id,),
            )
            records = []
            for row in cursor.fetchall():
                records.append(
                    OutcomeEvidenceRecord(
                        evidence_id=row["evidence_id"],
                        key_result_id=row["key_result_id"],
                        goal_id=row["goal_id"],
                        verification_tier=VerificationTier(row["verification_tier"]),
                        data_source=row["data_source"],
                        observed_value=row["observed_value"],
                        evidence_summary=row["evidence_summary"],
                        evidence_payload=json.loads(row["evidence_payload_json"] or "{}"),
                        evidence_hash=row["evidence_hash"],
                        verified_by=row["verified_by"],
                        approval_token=row["approval_token"],
                        verified_at=row["verified_at"],
                        is_valid=bool(row["is_valid"]),
                    )
                )
            return records

    # -------------------------------------------------------------
    # Initiatives & Milestones
    # -------------------------------------------------------------
    def save_initiative(self, initiative: InitiativeRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_initiatives (
                    initiative_id, goal_id, title, scope, expected_outcome,
                    owner, required_capabilities_json, dependencies_json,
                    resources_json, target_date, status, task_graph_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(initiative_id) DO UPDATE SET
                    title=excluded.title,
                    scope=excluded.scope,
                    expected_outcome=excluded.expected_outcome,
                    owner=excluded.owner,
                    required_capabilities_json=excluded.required_capabilities_json,
                    dependencies_json=excluded.dependencies_json,
                    resources_json=excluded.resources_json,
                    target_date=excluded.target_date,
                    status=excluded.status,
                    task_graph_id=excluded.task_graph_id
                """,
                (
                    initiative.initiative_id,
                    initiative.goal_id,
                    initiative.title,
                    initiative.scope,
                    initiative.expected_outcome,
                    initiative.owner,
                    json.dumps(initiative.required_capabilities),
                    json.dumps(initiative.dependencies),
                    json.dumps(initiative.estimated_resources),
                    initiative.target_date,
                    initiative.status,
                    initiative.task_graph_id,
                    initiative.created_at,
                ),
            )
            conn.commit()

    def list_initiatives(self, goal_id: str) -> List[InitiativeRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_initiatives WHERE goal_id = ? ORDER BY created_at ASC",
                (goal_id,),
            )
            inits = []
            for row in cursor.fetchall():
                inits.append(
                    InitiativeRecord(
                        initiative_id=row["initiative_id"],
                        goal_id=row["goal_id"],
                        title=row["title"],
                        scope=row["scope"],
                        expected_outcome=row["expected_outcome"],
                        owner=row["owner"],
                        required_capabilities=json.loads(row["required_capabilities_json"] or "[]"),
                        dependencies=json.loads(row["dependencies_json"] or "[]"),
                        estimated_resources=json.loads(row["resources_json"] or "{}"),
                        target_date=row["target_date"],
                        status=row["status"],
                        task_graph_id=row["task_graph_id"],
                        created_at=row["created_at"],
                    )
                )
            return inits

    def save_milestone(self, milestone: MilestoneRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_milestones (
                    milestone_id, initiative_id, goal_id, title, description,
                    target_date, status, completed_at, verification_evidence_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(milestone_id) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    target_date=excluded.target_date,
                    status=excluded.status,
                    completed_at=excluded.completed_at,
                    verification_evidence_id=excluded.verification_evidence_id
                """,
                (
                    milestone.milestone_id,
                    milestone.initiative_id,
                    milestone.goal_id,
                    milestone.title,
                    milestone.description,
                    milestone.target_date,
                    milestone.status,
                    milestone.completed_at,
                    milestone.verification_evidence_id,
                ),
            )
            conn.commit()

    def list_milestones(self, goal_id: str) -> List[MilestoneRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_milestones WHERE goal_id = ? ORDER BY target_date ASC",
                (goal_id,),
            )
            milestones = []
            for row in cursor.fetchall():
                milestones.append(
                    MilestoneRecord(
                        milestone_id=row["milestone_id"],
                        initiative_id=row["initiative_id"],
                        goal_id=row["goal_id"],
                        title=row["title"],
                        description=row["description"],
                        target_date=row["target_date"],
                        status=row["status"],
                        completed_at=row["completed_at"],
                        verification_evidence_id=row["verification_evidence_id"],
                    )
                )
            return milestones

    # -------------------------------------------------------------
    # Progress & Health Snapshots
    # -------------------------------------------------------------
    def save_progress_assessment(self, assessment: GoalProgressAssessment) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_progress_snapshots (
                    assessment_id, goal_id, reported_task_progress, verified_outcome_progress,
                    activity_to_outcome_variance, schedule_variance_days, budget_variance_ratio,
                    assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assessment.assessment_id,
                    assessment.goal_id,
                    assessment.reported_task_progress,
                    assessment.verified_outcome_progress,
                    assessment.activity_to_outcome_variance,
                    assessment.schedule_variance_days,
                    assessment.budget_variance_ratio,
                    assessment.assessed_at,
                ),
            )
            conn.commit()

    def get_latest_progress_assessment(self, goal_id: str) -> Optional[GoalProgressAssessment]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_progress_snapshots WHERE goal_id = ? ORDER BY assessed_at DESC LIMIT 1",
                (goal_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return GoalProgressAssessment(
                assessment_id=row["assessment_id"],
                goal_id=row["goal_id"],
                reported_task_progress=row["reported_task_progress"],
                verified_outcome_progress=row["verified_outcome_progress"],
                activity_to_outcome_variance=row["activity_to_outcome_variance"],
                schedule_variance_days=row["schedule_variance_days"],
                budget_variance_ratio=row["budget_variance_ratio"],
                assessed_at=row["assessed_at"],
            )

    def save_health_record(self, health: GoalHealthRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_health_assessments (
                    health_id, goal_id, health_state, primary_reason,
                    progress_trajectory, risk_factors_json, stale_metric_count,
                    blocked_dependency_count, confidence_score, assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    health.health_id,
                    health.goal_id,
                    health.health_state.value,
                    health.primary_reason,
                    health.progress_trajectory,
                    json.dumps(health.risk_factors),
                    health.stale_metric_count,
                    health.blocked_dependency_count,
                    health.confidence_score,
                    health.assessed_at,
                ),
            )
            conn.commit()

    def get_latest_health_record(self, goal_id: str) -> Optional[GoalHealthRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_health_assessments WHERE goal_id = ? ORDER BY assessed_at DESC LIMIT 1",
                (goal_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return GoalHealthRecord(
                health_id=row["health_id"],
                goal_id=row["goal_id"],
                health_state=GoalHealthState(row["health_state"]),
                primary_reason=row["primary_reason"],
                progress_trajectory=row["progress_trajectory"],
                risk_factors=json.loads(row["risk_factors_json"] or "[]"),
                stale_metric_count=row["stale_metric_count"],
                blocked_dependency_count=row["blocked_dependency_count"],
                confidence_score=row["confidence_score"],
                assessed_at=row["assessed_at"],
            )

    # -------------------------------------------------------------
    # Corrective Action Proposals
    # -------------------------------------------------------------
    def save_corrective_action(self, action: CorrectiveActionProposal) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_corrective_actions (
                    proposal_id, goal_id, action_type, title, rationale,
                    expected_benefit, potential_cost, risk_level, dependencies_json,
                    supporting_evidence_json, requires_human_approval, status,
                    approval_token, approved_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    status=excluded.status,
                    approval_token=excluded.approval_token,
                    approved_by=excluded.approved_by
                """,
                (
                    action.proposal_id,
                    action.goal_id,
                    action.action_type.value,
                    action.title,
                    action.rationale,
                    action.expected_benefit,
                    action.potential_cost,
                    action.risk_level,
                    json.dumps(action.dependencies),
                    json.dumps(action.supporting_evidence),
                    1 if action.requires_human_approval else 0,
                    action.status,
                    action.approval_token,
                    action.approved_by,
                    action.created_at,
                ),
            )
            conn.commit()

    def list_corrective_actions(self, goal_id: str) -> List[CorrectiveActionProposal]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_corrective_actions WHERE goal_id = ? ORDER BY created_at DESC",
                (goal_id,),
            )
            proposals = []
            for row in cursor.fetchall():
                proposals.append(
                    CorrectiveActionProposal(
                        proposal_id=row["proposal_id"],
                        goal_id=row["goal_id"],
                        action_type=CorrectiveActionType(row["action_type"]),
                        title=row["title"],
                        rationale=row["rationale"],
                        expected_benefit=row["expected_benefit"],
                        potential_cost=row["potential_cost"],
                        risk_level=row["risk_level"],
                        dependencies=json.loads(row["dependencies_json"] or "[]"),
                        supporting_evidence=json.loads(row["supporting_evidence_json"] or "[]"),
                        requires_human_approval=bool(row["requires_human_approval"]),
                        status=row["status"],
                        approval_token=row["approval_token"],
                        approved_by=row["approved_by"],
                        created_at=row["created_at"],
                    )
                )
            return proposals

    # -------------------------------------------------------------
    # Audit Trail
    # -------------------------------------------------------------
    def save_audit_record(self, record: GoalChangeAuditRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO goal_change_audit (
                    audit_id, goal_id, change_type, field_name, old_value_json,
                    new_value_json, author, rationale, approval_token, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.audit_id,
                    record.goal_id,
                    record.change_type,
                    record.field_name,
                    json.dumps(record.old_value),
                    json.dumps(record.new_value),
                    record.author,
                    record.rationale,
                    record.approval_token,
                    record.timestamp,
                ),
            )
            conn.commit()

    def get_audit_trail(self, goal_id: str) -> List[GoalChangeAuditRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM goal_change_audit WHERE goal_id = ? ORDER BY timestamp ASC",
                (goal_id,),
            )
            trail = []
            for row in cursor.fetchall():
                trail.append(
                    GoalChangeAuditRecord(
                        audit_id=row["audit_id"],
                        goal_id=row["goal_id"],
                        change_type=row["change_type"],
                        field_name=row["field_name"],
                        old_value=json.loads(row["old_value_json"] or "null"),
                        new_value=json.loads(row["new_value_json"] or "null"),
                        author=row["author"],
                        rationale=row["rationale"],
                        approval_token=row["approval_token"],
                        timestamp=row["timestamp"],
                    )
                )
            return trail
