"""
privacy/persistence.py
SQLite repository implementing full CRUD and optimized queries for all priv_* tables for OMNIA Module 51.
"""

import sqlite3
import json
import logging
import time
from typing import List, Optional, Dict, Any

from privacy.models import (
    DataAsset, DataClassification, DiscoveryScan, LineageRecord,
    ProcessingActivity, ConsentRecord, RetentionPolicy, DeletionRequest,
    DSRRequest, PrivacyAssessment, AccessDisclosureLog, VendorProcessor,
    CrossBorderTransfer, PrivacyIncident, AIGovernanceConfig, PrivacyAuditLog,
    SensitivityTier, DataCategory, AssetType, DSRType, DSRStatus,
    DeletionStatus, ConsentStatus, PIAStatus, PIAType, LawfulBasis,
    TransferMechanism, IncidentSeverity, ContainmentStatus
)

logger = logging.getLogger("omnia.privacy.persistence")


class PrivacyRepository:
    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA synchronous = OFF")
        return conn

    # --- 1. priv_data_assets ---
    def save_asset(self, asset: DataAsset) -> DataAsset:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_data_assets (
                    asset_id, name, asset_type, storage_location, owner,
                    residency_country, sensitivity_tier, is_active,
                    created_at, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    name=excluded.name,
                    asset_type=excluded.asset_type,
                    storage_location=excluded.storage_location,
                    owner=excluded.owner,
                    residency_country=excluded.residency_country,
                    sensitivity_tier=excluded.sensitivity_tier,
                    is_active=excluded.is_active,
                    updated_at=excluded.updated_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    asset.asset_id,
                    asset.name,
                    asset.asset_type.value if hasattr(asset.asset_type, "value") else str(asset.asset_type),
                    asset.storage_location,
                    asset.owner,
                    asset.residency_country,
                    asset.sensitivity_tier.value if hasattr(asset.sensitivity_tier, "value") else str(asset.sensitivity_tier),
                    1 if asset.is_active else 0,
                    asset.created_at,
                    asset.updated_at,
                    json.dumps(asset.metadata or {})
                )
            )
            conn.commit()
        return asset

    def get_asset(self, asset_id: str) -> Optional[DataAsset]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_data_assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if not row:
                return None
            return self._row_to_asset(row)

    def list_assets(
        self,
        residency: Optional[str] = None,
        sensitivity_tier: Optional[str] = None,
        active_only: bool = True
    ) -> List[DataAsset]:
        query = "SELECT * FROM priv_data_assets WHERE 1=1"
        params: List[Any] = []
        if active_only:
            query += " AND is_active = 1"
        if residency:
            query += " AND residency_country = ?"
            params.append(residency)
        if sensitivity_tier:
            query += " AND sensitivity_tier = ?"
            params.append(sensitivity_tier)
        query += " ORDER BY created_at DESC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_asset(r) for r in rows]

    def _row_to_asset(self, r: sqlite3.Row) -> DataAsset:
        return DataAsset(
            asset_id=r["asset_id"],
            name=r["name"],
            asset_type=AssetType(r["asset_type"]) if r["asset_type"] in AssetType._value2member_map_ else AssetType.DATABASE,
            storage_location=r["storage_location"],
            owner=r["owner"],
            residency_country=r["residency_country"],
            sensitivity_tier=SensitivityTier(r["sensitivity_tier"]) if r["sensitivity_tier"] in SensitivityTier._value2member_map_ else SensitivityTier.INTERNAL,
            is_active=bool(r["is_active"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            metadata=json.loads(r["metadata_json"] or "{}")
        )

    # --- 2. priv_data_classifications ---
    def save_classification(self, classification: DataClassification) -> DataClassification:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_data_classifications (
                    class_id, asset_id, field_name, category, sensitivity_tier,
                    confidence, rule_matched, classified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(class_id) DO UPDATE SET
                    category=excluded.category,
                    sensitivity_tier=excluded.sensitivity_tier,
                    confidence=excluded.confidence,
                    rule_matched=excluded.rule_matched,
                    classified_at=excluded.classified_at
                """,
                (
                    classification.class_id,
                    classification.asset_id,
                    classification.field_name,
                    classification.category.value if hasattr(classification.category, "value") else str(classification.category),
                    classification.sensitivity_tier.value if hasattr(classification.sensitivity_tier, "value") else str(classification.sensitivity_tier),
                    classification.confidence,
                    classification.rule_matched,
                    classification.classified_at
                )
            )
            conn.commit()
        return classification

    def get_classifications_by_asset(self, asset_id: str) -> List[DataClassification]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM priv_data_classifications WHERE asset_id = ? ORDER BY classified_at DESC",
                (asset_id,)
            ).fetchall()
            return [self._row_to_classification(r) for r in rows]

    def list_classifications(self, category: Optional[str] = None) -> List[DataClassification]:
        query = "SELECT * FROM priv_data_classifications"
        params: List[Any] = []
        if category:
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY classified_at DESC"
        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_classification(r) for r in rows]

    def _row_to_classification(self, r: sqlite3.Row) -> DataClassification:
        return DataClassification(
            class_id=r["class_id"],
            asset_id=r["asset_id"],
            field_name=r["field_name"],
            category=DataCategory(r["category"]) if r["category"] in DataCategory._value2member_map_ else DataCategory.PII,
            sensitivity_tier=SensitivityTier(r["sensitivity_tier"]) if r["sensitivity_tier"] in SensitivityTier._value2member_map_ else SensitivityTier.CONFIDENTIAL,
            confidence=r["confidence"],
            rule_matched=r["rule_matched"],
            classified_at=r["classified_at"]
        )

    # --- 3. priv_discovery_scans ---
    def save_scan(self, scan: DiscoveryScan) -> DiscoveryScan:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_discovery_scans (
                    scan_id, target_scope, scanner_identity, findings_count,
                    sensitive_fields_json, started_at, completed_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scan_id) DO UPDATE SET
                    findings_count=excluded.findings_count,
                    sensitive_fields_json=excluded.sensitive_fields_json,
                    completed_at=excluded.completed_at,
                    status=excluded.status
                """,
                (
                    scan.scan_id,
                    scan.target_scope,
                    scan.scanner_identity,
                    scan.findings_count,
                    json.dumps(scan.sensitive_fields or []),
                    scan.started_at,
                    scan.completed_at,
                    scan.status
                )
            )
            conn.commit()
        return scan

    def get_scan(self, scan_id: str) -> Optional[DiscoveryScan]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_discovery_scans WHERE scan_id = ?", (scan_id,)).fetchone()
            if not row:
                return None
            return self._row_to_scan(row)

    def list_scans(self) -> List[DiscoveryScan]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_discovery_scans ORDER BY started_at DESC").fetchall()
            return [self._row_to_scan(r) for r in rows]

    def _row_to_scan(self, r: sqlite3.Row) -> DiscoveryScan:
        return DiscoveryScan(
            scan_id=r["scan_id"],
            target_scope=r["target_scope"],
            scanner_identity=r["scanner_identity"],
            findings_count=r["findings_count"],
            sensitive_fields=json.loads(r["sensitive_fields_json"] or "[]"),
            started_at=r["started_at"],
            completed_at=r["completed_at"],
            status=r["status"]
        )

    # --- 4. priv_lineage_records ---
    def save_lineage(self, record: LineageRecord) -> LineageRecord:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_lineage_records (
                    lineage_id, source_asset_id, dest_asset_id, operation_type,
                    purpose, transformation_type, actor, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lineage_id) DO UPDATE SET
                    operation_type=excluded.operation_type,
                    purpose=excluded.purpose,
                    transformation_type=excluded.transformation_type,
                    actor=excluded.actor,
                    timestamp=excluded.timestamp
                """,
                (
                    record.lineage_id,
                    record.source_asset_id,
                    record.dest_asset_id,
                    record.operation_type,
                    record.purpose,
                    record.transformation_type,
                    record.actor,
                    record.timestamp
                )
            )
            conn.commit()
        return record

    def get_lineage_by_source(self, source_id: str) -> List[LineageRecord]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_lineage_records WHERE source_asset_id = ?", (source_id,)).fetchall()
            return [self._row_to_lineage(r) for r in rows]

    def get_lineage_by_dest(self, dest_id: str) -> List[LineageRecord]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_lineage_records WHERE dest_asset_id = ?", (dest_id,)).fetchall()
            return [self._row_to_lineage(r) for r in rows]

    def list_lineage(self) -> List[LineageRecord]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_lineage_records ORDER BY timestamp DESC").fetchall()
            return [self._row_to_lineage(r) for r in rows]

    def _row_to_lineage(self, r: sqlite3.Row) -> LineageRecord:
        return LineageRecord(
            lineage_id=r["lineage_id"],
            source_asset_id=r["source_asset_id"],
            dest_asset_id=r["dest_asset_id"],
            operation_type=r["operation_type"],
            purpose=r["purpose"],
            transformation_type=r["transformation_type"],
            actor=r["actor"],
            timestamp=r["timestamp"]
        )

    # --- 5. priv_processing_activities ---
    def save_processing_activity(self, activity: ProcessingActivity) -> ProcessingActivity:
        with self._get_conn() as conn:
            cat_list = [c.value if hasattr(c, "value") else str(c) for c in activity.data_categories]
            conn.execute(
                """
                INSERT INTO priv_processing_activities (
                    activity_id, name, purpose, lawful_basis, owner,
                    data_categories_json, retention_schedule, is_approved, review_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id) DO UPDATE SET
                    name=excluded.name,
                    purpose=excluded.purpose,
                    lawful_basis=excluded.lawful_basis,
                    owner=excluded.owner,
                    data_categories_json=excluded.data_categories_json,
                    retention_schedule=excluded.retention_schedule,
                    is_approved=excluded.is_approved,
                    review_date=excluded.review_date
                """,
                (
                    activity.activity_id,
                    activity.name,
                    activity.purpose,
                    activity.lawful_basis.value if hasattr(activity.lawful_basis, "value") else str(activity.lawful_basis),
                    activity.owner,
                    json.dumps(cat_list),
                    activity.retention_schedule,
                    1 if activity.is_approved else 0,
                    activity.review_date
                )
            )
            conn.commit()
        return activity

    def get_processing_activity(self, activity_id: str) -> Optional[ProcessingActivity]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_processing_activities WHERE activity_id = ?", (activity_id,)).fetchone()
            if not row:
                return None
            return self._row_to_activity(row)

    def get_processing_activity_by_purpose(self, purpose: str) -> Optional[ProcessingActivity]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_processing_activities WHERE purpose = ?", (purpose,)).fetchone()
            if not row:
                return None
            return self._row_to_activity(row)

    def list_processing_activities(self) -> List[ProcessingActivity]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_processing_activities ORDER BY activity_id").fetchall()
            return [self._row_to_activity(r) for r in rows]

    def _row_to_activity(self, r: sqlite3.Row) -> ProcessingActivity:
        raw_cats = json.loads(r["data_categories_json"] or "[]")
        categories = [DataCategory(c) for c in raw_cats if c in DataCategory._value2member_map_]
        return ProcessingActivity(
            activity_id=r["activity_id"],
            name=r["name"],
            purpose=r["purpose"],
            lawful_basis=LawfulBasis(r["lawful_basis"]) if r["lawful_basis"] in LawfulBasis._value2member_map_ else LawfulBasis.LEGITIMATE_INTERESTS,
            owner=r["owner"],
            data_categories=categories,
            retention_schedule=r["retention_schedule"],
            is_approved=bool(r["is_approved"]),
            review_date=r["review_date"]
        )

    # --- 6. priv_consent_records ---
    def save_consent(self, consent: ConsentRecord) -> ConsentRecord:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_consent_records (
                    consent_id, subject_id, purpose, status, granted_at, withdrawn_at, policy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(consent_id) DO UPDATE SET
                    status=excluded.status,
                    withdrawn_at=excluded.withdrawn_at,
                    policy_version=excluded.policy_version
                """,
                (
                    consent.consent_id,
                    consent.subject_id,
                    consent.purpose,
                    consent.status.value if hasattr(consent.status, "value") else str(consent.status),
                    consent.granted_at,
                    consent.withdrawn_at,
                    consent.policy_version
                )
            )
            conn.commit()
        return consent

    def get_consent(self, consent_id: str) -> Optional[ConsentRecord]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_consent_records WHERE consent_id = ?", (consent_id,)).fetchone()
            if not row:
                return None
            return self._row_to_consent(row)

    def get_latest_consent(self, subject_id: str, purpose: str) -> Optional[ConsentRecord]:
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM priv_consent_records
                WHERE subject_id = ? AND purpose = ?
                ORDER BY granted_at DESC LIMIT 1
                """,
                (subject_id, purpose)
            ).fetchone()
            if not row:
                return None
            return self._row_to_consent(row)

    def list_consents_for_subject(self, subject_id: str) -> List[ConsentRecord]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM priv_consent_records WHERE subject_id = ? ORDER BY granted_at DESC",
                (subject_id,)
            ).fetchall()
            return [self._row_to_consent(r) for r in rows]

    def _row_to_consent(self, r: sqlite3.Row) -> ConsentRecord:
        return ConsentRecord(
            consent_id=r["consent_id"],
            subject_id=r["subject_id"],
            purpose=r["purpose"],
            status=ConsentStatus(r["status"]) if r["status"] in ConsentStatus._value2member_map_ else ConsentStatus.GRANTED,
            granted_at=r["granted_at"],
            withdrawn_at=r["withdrawn_at"],
            policy_version=r["policy_version"]
        )

    # --- 7. priv_retention_policies ---
    def save_retention_policy(self, policy: RetentionPolicy) -> RetentionPolicy:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_retention_policies (
                    policy_id, purpose, max_retention_days, legal_basis, legal_hold_exempt, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_id) DO UPDATE SET
                    purpose=excluded.purpose,
                    max_retention_days=excluded.max_retention_days,
                    legal_basis=excluded.legal_basis,
                    legal_hold_exempt=excluded.legal_hold_exempt
                """,
                (
                    policy.policy_id,
                    policy.purpose,
                    policy.max_retention_days,
                    policy.legal_basis,
                    1 if policy.legal_hold_exempt else 0,
                    policy.created_at
                )
            )
            conn.commit()
        return policy

    def get_retention_policy_by_purpose(self, purpose: str) -> Optional[RetentionPolicy]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_retention_policies WHERE purpose = ?", (purpose,)).fetchone()
            if not row:
                return None
            return self._row_to_retention(row)

    def list_retention_policies(self) -> List[RetentionPolicy]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_retention_policies ORDER BY purpose").fetchall()
            return [self._row_to_retention(r) for r in rows]

    def _row_to_retention(self, r: sqlite3.Row) -> RetentionPolicy:
        return RetentionPolicy(
            policy_id=r["policy_id"],
            purpose=r["purpose"],
            max_retention_days=r["max_retention_days"],
            legal_basis=r["legal_basis"],
            legal_hold_exempt=bool(r["legal_hold_exempt"]),
            created_at=r["created_at"]
        )

    # --- 8. priv_deletion_requests ---
    def save_deletion_request(self, request: DeletionRequest) -> DeletionRequest:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_deletion_requests (
                    request_id, asset_id, target_selector, reason, requested_by,
                    approval_token, status, verified, requested_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    approval_token=excluded.approval_token,
                    status=excluded.status,
                    verified=excluded.verified,
                    completed_at=excluded.completed_at
                """,
                (
                    request.request_id,
                    request.asset_id,
                    request.target_selector,
                    request.reason,
                    request.requested_by,
                    request.approval_token,
                    request.status.value if hasattr(request.status, "value") else str(request.status),
                    1 if request.verified else 0,
                    request.requested_at,
                    request.completed_at
                )
            )
            conn.commit()
        return request

    def get_deletion_request(self, request_id: str) -> Optional[DeletionRequest]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_deletion_requests WHERE request_id = ?", (request_id,)).fetchone()
            if not row:
                return None
            return self._row_to_deletion(row)

    def list_deletion_requests(
        self,
        asset_id: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[DeletionRequest]:
        query = "SELECT * FROM priv_deletion_requests WHERE 1=1"
        params: List[Any] = []
        if asset_id:
            query += " AND asset_id = ?"
            params.append(asset_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY requested_at DESC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_deletion(r) for r in rows]

    def _row_to_deletion(self, r: sqlite3.Row) -> DeletionRequest:
        return DeletionRequest(
            request_id=r["request_id"],
            asset_id=r["asset_id"],
            target_selector=r["target_selector"],
            reason=r["reason"],
            requested_by=r["requested_by"],
            approval_token=r["approval_token"],
            status=DeletionStatus(r["status"]) if r["status"] in DeletionStatus._value2member_map_ else DeletionStatus.REQUESTED,
            verified=bool(r["verified"]),
            requested_at=r["requested_at"],
            completed_at=r["completed_at"]
        )

    # --- 9. priv_dsr_requests ---
    def save_dsr(self, dsr: DSRRequest) -> DSRRequest:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_dsr_requests (
                    dsr_id, subject_id, request_type, status, verification_token,
                    requester_email, deadline, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dsr_id) DO UPDATE SET
                    status=excluded.status,
                    verification_token=excluded.verification_token,
                    resolved_at=excluded.resolved_at
                """,
                (
                    dsr.dsr_id,
                    dsr.subject_id,
                    dsr.request_type.value if hasattr(dsr.request_type, "value") else str(dsr.request_type),
                    dsr.status.value if hasattr(dsr.status, "value") else str(dsr.status),
                    dsr.verification_token,
                    dsr.requester_email,
                    dsr.deadline,
                    dsr.created_at,
                    dsr.resolved_at
                )
            )
            conn.commit()
        return dsr

    def get_dsr(self, dsr_id: str) -> Optional[DSRRequest]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_dsr_requests WHERE dsr_id = ?", (dsr_id,)).fetchone()
            if not row:
                return None
            return self._row_to_dsr(row)

    def list_dsrs(self, status: Optional[str] = None, subject_id: Optional[str] = None) -> List[DSRRequest]:
        query = "SELECT * FROM priv_dsr_requests WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if subject_id:
            query += " AND subject_id = ?"
            params.append(subject_id)
        query += " ORDER BY created_at DESC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dsr(r) for r in rows]

    def _row_to_dsr(self, r: sqlite3.Row) -> DSRRequest:
        return DSRRequest(
            dsr_id=r["dsr_id"],
            subject_id=r["subject_id"],
            request_type=DSRType(r["request_type"]) if r["request_type"] in DSRType._value2member_map_ else DSRType.ACCESS,
            status=DSRStatus(r["status"]) if r["status"] in DSRStatus._value2member_map_ else DSRStatus.RECEIVED,
            verification_token=r["verification_token"],
            requester_email=r["requester_email"],
            deadline=r["deadline"],
            created_at=r["created_at"],
            resolved_at=r["resolved_at"]
        )

    # --- 10. priv_assessments ---
    def save_assessment(self, assessment: PrivacyAssessment) -> PrivacyAssessment:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_assessments (
                    assessment_id, activity_id, assessment_type, risk_score,
                    findings_json, safeguards_json, approval_status, assessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(assessment_id) DO UPDATE SET
                    risk_score=excluded.risk_score,
                    findings_json=excluded.findings_json,
                    safeguards_json=excluded.safeguards_json,
                    approval_status=excluded.approval_status,
                    assessed_at=excluded.assessed_at
                """,
                (
                    assessment.assessment_id,
                    assessment.activity_id,
                    assessment.assessment_type.value if hasattr(assessment.assessment_type, "value") else str(assessment.assessment_type),
                    assessment.risk_score,
                    json.dumps(assessment.findings or []),
                    json.dumps(assessment.safeguards or []),
                    assessment.approval_status.value if hasattr(assessment.approval_status, "value") else str(assessment.approval_status),
                    assessment.assessed_at
                )
            )
            conn.commit()
        return assessment

    def get_assessment(self, assessment_id: str) -> Optional[PrivacyAssessment]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_assessments WHERE assessment_id = ?", (assessment_id,)).fetchone()
            if not row:
                return None
            return self._row_to_assessment(row)

    def list_assessments_by_activity(self, activity_id: str) -> List[PrivacyAssessment]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM priv_assessments WHERE activity_id = ? ORDER BY assessed_at DESC",
                (activity_id,)
            ).fetchall()
            return [self._row_to_assessment(r) for r in rows]

    def _row_to_assessment(self, r: sqlite3.Row) -> PrivacyAssessment:
        return PrivacyAssessment(
            assessment_id=r["assessment_id"],
            activity_id=r["activity_id"],
            assessment_type=PIAType(r["assessment_type"]) if r["assessment_type"] in PIAType._value2member_map_ else PIAType.PIA,
            risk_score=r["risk_score"],
            findings=json.loads(r["findings_json"] or "[]"),
            safeguards=json.loads(r["safeguards_json"] or "[]"),
            approval_status=PIAStatus(r["approval_status"]) if r["approval_status"] in PIAStatus._value2member_map_ else PIAStatus.DRAFT,
            assessed_at=r["assessed_at"]
        )

    # --- 11. priv_access_disclosures ---
    def save_access_log(self, log: AccessDisclosureLog) -> AccessDisclosureLog:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_access_disclosures (
                    log_id, actor_id, asset_id, purpose, action, authorized, justification, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.log_id,
                    log.actor_id,
                    log.asset_id,
                    log.purpose,
                    log.action,
                    1 if log.authorized else 0,
                    log.justification,
                    log.timestamp
                )
            )
            conn.commit()
        return log

    def list_access_logs(
        self,
        asset_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        limit: int = 100
    ) -> List[AccessDisclosureLog]:
        query = "SELECT * FROM priv_access_disclosures WHERE 1=1"
        params: List[Any] = []
        if asset_id:
            query += " AND asset_id = ?"
            params.append(asset_id)
        if actor_id:
            query += " AND actor_id = ?"
            params.append(actor_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                AccessDisclosureLog(
                    log_id=r["log_id"],
                    actor_id=r["actor_id"],
                    asset_id=r["asset_id"],
                    purpose=r["purpose"],
                    action=r["action"],
                    authorized=bool(r["authorized"]),
                    justification=r["justification"],
                    timestamp=r["timestamp"]
                )
                for r in rows
            ]

    # --- 12. priv_vendor_processors ---
    def save_vendor(self, vendor: VendorProcessor) -> VendorProcessor:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_vendor_processors (
                    vendor_id, name, service_type, dpa_status, residency,
                    subprocessors_json, assessment_status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vendor_id) DO UPDATE SET
                    name=excluded.name,
                    service_type=excluded.service_type,
                    dpa_status=excluded.dpa_status,
                    residency=excluded.residency,
                    subprocessors_json=excluded.subprocessors_json,
                    assessment_status=excluded.assessment_status,
                    updated_at=excluded.updated_at
                """,
                (
                    vendor.vendor_id,
                    vendor.name,
                    vendor.service_type,
                    vendor.dpa_status,
                    vendor.residency,
                    json.dumps(vendor.subprocessors or []),
                    vendor.assessment_status,
                    vendor.updated_at
                )
            )
            conn.commit()
        return vendor

    def get_vendor(self, vendor_id: str) -> Optional[VendorProcessor]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_vendor_processors WHERE vendor_id = ?", (vendor_id,)).fetchone()
            if not row:
                return None
            return self._row_to_vendor(row)

    def list_vendors(self) -> List[VendorProcessor]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_vendor_processors ORDER BY name").fetchall()
            return [self._row_to_vendor(r) for r in rows]

    def _row_to_vendor(self, r: sqlite3.Row) -> VendorProcessor:
        return VendorProcessor(
            vendor_id=r["vendor_id"],
            name=r["name"],
            service_type=r["service_type"],
            dpa_status=r["dpa_status"],
            residency=r["residency"],
            subprocessors=json.loads(r["subprocessors_json"] or "[]"),
            assessment_status=r["assessment_status"],
            updated_at=r["updated_at"]
        )

    # --- 13. priv_cross_border_transfers ---
    def save_cross_border_transfer(self, transfer: CrossBorderTransfer) -> CrossBorderTransfer:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_cross_border_transfers (
                    transfer_id, source_country, dest_country, recipient,
                    purpose, transfer_mechanism, is_approved, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(transfer_id) DO UPDATE SET
                    transfer_mechanism=excluded.transfer_mechanism,
                    is_approved=excluded.is_approved,
                    reviewed_at=excluded.reviewed_at
                """,
                (
                    transfer.transfer_id,
                    transfer.source_country,
                    transfer.dest_country,
                    transfer.recipient,
                    transfer.purpose,
                    transfer.transfer_mechanism.value if hasattr(transfer.transfer_mechanism, "value") else str(transfer.transfer_mechanism),
                    1 if transfer.is_approved else 0,
                    transfer.reviewed_at
                )
            )
            conn.commit()
        return transfer

    def list_cross_border_transfers(self, approved_only: Optional[bool] = None) -> List[CrossBorderTransfer]:
        query = "SELECT * FROM priv_cross_border_transfers WHERE 1=1"
        params: List[Any] = []
        if approved_only is not None:
            query += " AND is_approved = ?"
            params.append(1 if approved_only else 0)
        query += " ORDER BY reviewed_at DESC"

        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                CrossBorderTransfer(
                    transfer_id=r["transfer_id"],
                    source_country=r["source_country"],
                    dest_country=r["dest_country"],
                    recipient=r["recipient"],
                    purpose=r["purpose"],
                    transfer_mechanism=TransferMechanism(r["transfer_mechanism"]) if r["transfer_mechanism"] in TransferMechanism._value2member_map_ else TransferMechanism.STANDARD_CONTRACTUAL_CLAUSES,
                    is_approved=bool(r["is_approved"]),
                    reviewed_at=r["reviewed_at"]
                )
                for r in rows
            ]

    # --- 14. priv_incidents ---
    def save_incident(self, incident: PrivacyIncident) -> PrivacyIncident:
        with self._get_conn() as conn:
            cats = [c.value if hasattr(c, "value") else str(c) for c in incident.affected_categories]
            conn.execute(
                """
                INSERT INTO priv_incidents (
                    incident_id, incident_type, affected_assets_json, affected_categories_json,
                    severity, containment_status, reportable, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(incident_id) DO UPDATE SET
                    containment_status=excluded.containment_status,
                    reportable=excluded.reportable
                """,
                (
                    incident.incident_id,
                    incident.incident_type,
                    json.dumps(incident.affected_assets or []),
                    json.dumps(cats),
                    incident.severity.value if hasattr(incident.severity, "value") else str(incident.severity),
                    incident.containment_status.value if hasattr(incident.containment_status, "value") else str(incident.containment_status),
                    1 if incident.reportable else 0,
                    incident.created_at
                )
            )
            conn.commit()
        return incident

    def get_incident(self, incident_id: str) -> Optional[PrivacyIncident]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_incidents WHERE incident_id = ?", (incident_id,)).fetchone()
            if not row:
                return None
            return self._row_to_incident(row)

    def list_incidents(self) -> List[PrivacyIncident]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_incidents ORDER BY created_at DESC").fetchall()
            return [self._row_to_incident(r) for r in rows]

    def _row_to_incident(self, r: sqlite3.Row) -> PrivacyIncident:
        raw_cats = json.loads(r["affected_categories_json"] or "[]")
        categories = [DataCategory(c) for c in raw_cats if c in DataCategory._value2member_map_]
        return PrivacyIncident(
            incident_id=r["incident_id"],
            incident_type=r["incident_type"],
            affected_assets=json.loads(r["affected_assets_json"] or "[]"),
            affected_categories=categories,
            severity=IncidentSeverity(r["severity"]) if r["severity"] in IncidentSeverity._value2member_map_ else IncidentSeverity.MEDIUM,
            containment_status=ContainmentStatus(r["containment_status"]) if r["containment_status"] in ContainmentStatus._value2member_map_ else ContainmentStatus.DETECTED,
            reportable=bool(r["reportable"]),
            created_at=r["created_at"]
        )

    # --- 15. priv_ai_governance ---
    def save_ai_governance(self, config: AIGovernanceConfig) -> AIGovernanceConfig:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_ai_governance (
                    ai_gov_id, model_id, provider, inference_logging_allowed,
                    training_permitted, prompt_redaction_enabled, retention_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ai_gov_id) DO UPDATE SET
                    inference_logging_allowed=excluded.inference_logging_allowed,
                    training_permitted=excluded.training_permitted,
                    prompt_redaction_enabled=excluded.prompt_redaction_enabled,
                    retention_policy=excluded.retention_policy
                """,
                (
                    config.ai_gov_id,
                    config.model_id,
                    config.provider,
                    1 if config.inference_logging_allowed else 0,
                    1 if config.training_permitted else 0,
                    1 if config.prompt_redaction_enabled else 0,
                    config.retention_policy
                )
            )
            conn.commit()
        return config

    def get_ai_governance(self, model_id: str) -> Optional[AIGovernanceConfig]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM priv_ai_governance WHERE model_id = ?", (model_id,)).fetchone()
            if not row:
                return None
            return AIGovernanceConfig(
                ai_gov_id=row["ai_gov_id"],
                model_id=row["model_id"],
                provider=row["provider"],
                inference_logging_allowed=bool(row["inference_logging_allowed"]),
                training_permitted=bool(row["training_permitted"]),
                prompt_redaction_enabled=bool(row["prompt_redaction_enabled"]),
                retention_policy=row["retention_policy"]
            )

    def list_ai_governance(self) -> List[AIGovernanceConfig]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_ai_governance ORDER BY model_id").fetchall()
            return [
                AIGovernanceConfig(
                    ai_gov_id=r["ai_gov_id"],
                    model_id=r["model_id"],
                    provider=r["provider"],
                    inference_logging_allowed=bool(r["inference_logging_allowed"]),
                    training_permitted=bool(r["training_permitted"]),
                    prompt_redaction_enabled=bool(r["prompt_redaction_enabled"]),
                    retention_policy=r["retention_policy"]
                )
                for r in rows
            ]

    # --- 16. priv_audit_logs ---
    def log_audit(self, event_type: str, actor: str, details: Dict[str, Any]) -> PrivacyAuditLog:
        import uuid
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO priv_audit_logs (audit_id, event_type, actor, details_json, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (audit_id, event_type, actor, json.dumps(details or {}), now)
            )
            conn.commit()
        return PrivacyAuditLog(
            audit_id=audit_id,
            event_type=event_type,
            actor=actor,
            details=details,
            timestamp=now
        )

    def list_audit_logs(self, limit: int = 100) -> List[PrivacyAuditLog]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM priv_audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
            return [
                PrivacyAuditLog(
                    audit_id=r["audit_id"],
                    event_type=r["event_type"],
                    actor=r["actor"],
                    details=json.loads(r["details_json"] or "{}"),
                    timestamp=r["timestamp"]
                )
                for r in rows
            ]
