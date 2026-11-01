"""
OMNIA Module 46: Autonomous Application Security Testing, Vulnerability Intelligence & Defensive Validation
Persistence Repository - persistence.py
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from app_security.models import (
    AssetType, Criticality, EnvironmentTier, ExposureTier, FindingCategory,
    FindingStatus, PriorityLevel, Severity, ValidationOutcome,
    SecurityAsset, SecurityAuthorization, AssessmentScope, SecurityAssessment,
    SecurityFinding, VulnerabilitySource, VulnerabilityRecord, ValidationExecution,
    ValidationEvidence, AttackPath, SecurityRiskAssessment, RemediationPlan,
    RemediationExecution, SecurityFixVerification, SecurityException,
    SecurityPostureSnapshot, SecurityAuditRecord
)

logger = logging.getLogger("Omnia.AppSecurity.Persistence")


class AppSecurityRepository:
    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------
    def save_asset(self, a: SecurityAsset) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_assets (
                    asset_id, name, asset_type, owner, environment, discovery_source,
                    authorization_id, technology_stack_json, exposure_tier, criticality,
                    security_posture_score, last_assessed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    a.asset_id, a.name, a.asset_type.value, a.owner, a.environment.value,
                    a.discovery_source, a.authorization_id, json.dumps(a.technology_stack),
                    a.exposure_tier.value, a.criticality.value, a.security_posture_score,
                    a.last_assessed_at, a.created_at
                )
            )

    def get_asset(self, asset_id: str) -> Optional[SecurityAsset]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sec_assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if not row:
                return None
            return SecurityAsset(
                asset_id=row["asset_id"],
                name=row["name"],
                asset_type=AssetType(row["asset_type"]),
                owner=row["owner"],
                environment=EnvironmentTier(row["environment"]),
                discovery_source=row["discovery_source"],
                authorization_id=row["authorization_id"],
                technology_stack=json.loads(row["technology_stack_json"] or "[]"),
                exposure_tier=ExposureTier(row["exposure_tier"]),
                criticality=Criticality(row["criticality"]),
                security_posture_score=row["security_posture_score"],
                last_assessed_at=row["last_assessed_at"],
                created_at=row["created_at"]
            )

    def list_assets(self) -> List[SecurityAsset]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM sec_assets").fetchall()
            return [
                SecurityAsset(
                    asset_id=r["asset_id"],
                    name=r["name"],
                    asset_type=AssetType(r["asset_type"]),
                    owner=r["owner"],
                    environment=EnvironmentTier(r["environment"]),
                    discovery_source=r["discovery_source"],
                    authorization_id=r["authorization_id"],
                    technology_stack=json.loads(r["technology_stack_json"] or "[]"),
                    exposure_tier=ExposureTier(r["exposure_tier"]),
                    criticality=Criticality(r["criticality"]),
                    security_posture_score=r["security_posture_score"],
                    last_assessed_at=r["last_assessed_at"],
                    created_at=r["created_at"]
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Authorizations & Scopes
    # ------------------------------------------------------------------
    def save_authorization(self, auth: SecurityAuthorization) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_authorizations (
                    authorization_id, name, operator, owner_approval_ref, assessment_purpose,
                    environment_tier, permitted_techniques_json, allow_destructive,
                    rate_limit_rps, valid_from, valid_until, is_revoked, revoked_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    auth.authorization_id, auth.name, auth.operator, auth.owner_approval_ref,
                    auth.assessment_purpose, auth.environment_tier.value,
                    json.dumps(auth.permitted_techniques), 1 if auth.allow_destructive else 0,
                    auth.rate_limit_rps, auth.valid_from, auth.valid_until,
                    1 if auth.is_revoked else 0, auth.revoked_reason, auth.created_at
                )
            )

    def get_authorization(self, authorization_id: str) -> Optional[SecurityAuthorization]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sec_authorizations WHERE authorization_id = ?", (authorization_id,)).fetchone()
            if not row:
                return None
            return SecurityAuthorization(
                authorization_id=row["authorization_id"],
                name=row["name"],
                operator=row["operator"],
                owner_approval_ref=row["owner_approval_ref"],
                assessment_purpose=row["assessment_purpose"],
                environment_tier=EnvironmentTier(row["environment_tier"]),
                permitted_techniques=json.loads(row["permitted_techniques_json"] or "[]"),
                allow_destructive=bool(row["allow_destructive"]),
                rate_limit_rps=row["rate_limit_rps"],
                valid_from=row["valid_from"],
                valid_until=row["valid_until"],
                is_revoked=bool(row["is_revoked"]),
                revoked_reason=row["revoked_reason"],
                created_at=row["created_at"]
            )

    def save_scope(self, s: AssessmentScope) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_scopes (
                    scope_id, authorization_id, asset_id, permitted_endpoints_json,
                    excluded_endpoints_json, permitted_components_json, excluded_components_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    s.scope_id, s.authorization_id, s.asset_id,
                    json.dumps(s.permitted_endpoints), json.dumps(s.excluded_endpoints),
                    json.dumps(s.permitted_components), json.dumps(s.excluded_components),
                    s.created_at
                )
            )

    def get_scopes_for_authorization(self, authorization_id: str) -> List[AssessmentScope]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM sec_scopes WHERE authorization_id = ?", (authorization_id,)).fetchall()
            return [
                AssessmentScope(
                    scope_id=r["scope_id"],
                    authorization_id=r["authorization_id"],
                    asset_id=r["asset_id"],
                    permitted_endpoints=json.loads(r["permitted_endpoints_json"] or "[]"),
                    excluded_endpoints=json.loads(r["excluded_endpoints_json"] or "[]"),
                    permitted_components=json.loads(r["permitted_components_json"] or "[]"),
                    excluded_components=json.loads(r["excluded_components_json"] or "[]"),
                    created_at=r["created_at"]
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Assessments & Findings
    # ------------------------------------------------------------------
    def save_assessment(self, a: SecurityAssessment) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_assessments (
                    assessment_id, authorization_id, asset_id, assessment_type,
                    status, started_at, completed_at, findings_count,
                    critical_findings_count, high_findings_count, raw_telemetry_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    a.assessment_id, a.authorization_id, a.asset_id, a.assessment_type,
                    a.status, a.started_at, a.completed_at, a.findings_count,
                    a.critical_findings_count, a.high_findings_count, json.dumps(a.raw_telemetry)
                )
            )

    def get_assessment(self, assessment_id: str) -> Optional[SecurityAssessment]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sec_assessments WHERE assessment_id = ?", (assessment_id,)).fetchone()
            if not row:
                return None
            return SecurityAssessment(
                assessment_id=row["assessment_id"],
                authorization_id=row["authorization_id"],
                asset_id=row["asset_id"],
                assessment_type=row["assessment_type"],
                status=row["status"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                findings_count=row["findings_count"],
                critical_findings_count=row["critical_findings_count"],
                high_findings_count=row["high_findings_count"],
                raw_telemetry=json.loads(row["raw_telemetry_json"] or "{}")
            )

    def save_finding(self, f: SecurityFinding) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_findings (
                    finding_id, assessment_id, asset_id, title, category,
                    severity, cwe_id, component_ref, location_ref,
                    evidence_redacted_json, fingerprint_sha256, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f.finding_id, f.assessment_id, f.asset_id, f.title, f.category.value,
                    f.severity.value, f.cwe_id, f.component_ref, f.location_ref,
                    json.dumps(f.evidence_redacted), f.fingerprint_sha256, f.status.value, f.created_at
                )
            )

    def get_finding(self, finding_id: str) -> Optional[SecurityFinding]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sec_findings WHERE finding_id = ?", (finding_id,)).fetchone()
            if not row:
                return None
            return SecurityFinding(
                finding_id=row["finding_id"],
                assessment_id=row["assessment_id"],
                asset_id=row["asset_id"],
                title=row["title"],
                category=FindingCategory(row["category"]),
                severity=Severity(row["severity"]),
                cwe_id=row["cwe_id"],
                component_ref=row["component_ref"],
                location_ref=row["location_ref"],
                evidence_redacted=json.loads(row["evidence_redacted_json"] or "{}"),
                fingerprint_sha256=row["fingerprint_sha256"],
                status=FindingStatus(row["status"]),
                created_at=row["created_at"]
            )

    def list_findings_for_asset(self, asset_id: str) -> List[SecurityFinding]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM sec_findings WHERE asset_id = ?", (asset_id,)).fetchall()
            return [
                SecurityFinding(
                    finding_id=r["finding_id"],
                    assessment_id=r["assessment_id"],
                    asset_id=r["asset_id"],
                    title=r["title"],
                    category=FindingCategory(r["category"]),
                    severity=Severity(r["severity"]),
                    cwe_id=r["cwe_id"],
                    component_ref=r["component_ref"],
                    location_ref=r["location_ref"],
                    evidence_redacted=json.loads(r["evidence_redacted_json"] or "{}"),
                    fingerprint_sha256=r["fingerprint_sha256"],
                    status=FindingStatus(r["status"]),
                    created_at=r["created_at"]
                )
                for r in rows
            ]

    def update_finding_status(self, finding_id: str, status: FindingStatus) -> None:
        with self._get_connection() as conn:
            conn.execute("UPDATE sec_findings SET status = ? WHERE finding_id = ?", (status.value, finding_id))

    # ------------------------------------------------------------------
    # Validations & Evidence
    # ------------------------------------------------------------------
    def save_validation(self, v: ValidationExecution) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_validations (
                    validation_id, finding_id, method, outcome, is_destructive, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    v.validation_id, v.finding_id, v.method, v.outcome.value,
                    1 if v.is_destructive else 0, v.executed_at
                )
            )

    def save_validation_evidence(self, ev: ValidationEvidence) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_validation_evidence (
                    evidence_id, validation_id, evidence_type, redacted_content, checksum_sha256, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ev.evidence_id, ev.validation_id, ev.evidence_type, ev.redacted_content, ev.checksum_sha256, ev.captured_at)
            )

    # ------------------------------------------------------------------
    # Risk, Attack Paths, Remediation & Fix Verifications
    # ------------------------------------------------------------------
    def save_risk_assessment(self, r: SecurityRiskAssessment) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_risk_assessments (
                    risk_assessment_id, finding_id, asset_id, technical_severity,
                    exploitability_score, asset_criticality_weight, exposure_multiplier,
                    contextual_risk_score, priority_level, urgency_recommendation, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.risk_assessment_id, r.finding_id, r.asset_id, r.technical_severity.value,
                    r.exploitability_score, r.asset_criticality_weight, r.exposure_multiplier,
                    r.contextual_risk_score, r.priority_level.value, r.urgency_recommendation, r.calculated_at
                )
            )

    def save_remediation_plan(self, p: RemediationPlan) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_remediation_plans (
                    plan_id, finding_id, recommended_action, action_details_json,
                    breaking_change_risk, estimated_complexity, patch_diff, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.plan_id, p.finding_id, p.recommended_action, json.dumps(p.action_details),
                    p.breaking_change_risk, p.estimated_complexity, p.patch_diff, p.status, p.created_at
                )
            )

    def save_fix_verification(self, v: SecurityFixVerification) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sec_fix_verifications (
                    verification_id, finding_id, plan_id, module45_mission_id,
                    original_probe_passed, regressions_found, is_fully_resolved, verified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    v.verification_id, v.finding_id, v.plan_id, v.module45_mission_id,
                    1 if v.original_probe_passed else 0, v.regressions_found,
                    1 if v.is_fully_resolved else 0, v.verified_at
                )
            )
            if v.is_fully_resolved:
                conn.execute("UPDATE sec_findings SET status = 'RESOLVED' WHERE finding_id = ?", (v.finding_id,))

    def save_audit_record(self, a: SecurityAuditRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sec_audit_records (
                    audit_id, authorization_id, asset_id, action_type, actor, details_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (a.audit_id, a.authorization_id, a.asset_id, a.action_type, a.actor, json.dumps(a.details), a.timestamp)
            )
