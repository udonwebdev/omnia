"""
forensics/persistence.py
SQLite-backed persistence repository for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import sqlite3
import json
import logging
from typing import List, Optional, Dict, Any

from forensics.models import (
    ForensicCase, CaseStatus,
    EvidenceArtifact, ArtifactType,
    ChainOfCustodyRecord, CustodyOperation,
    AcquisitionJob,
    TimelineEvent, EvidenceReliabilityTier,
    EvidenceCorrelation,
    ForensicHypothesis, HypothesisStatus,
    StatementItem, StatementCategory, ForensicReport,
    LegalHold
)

logger = logging.getLogger("omnia.forensics.persistence")


class ForensicsRepository:
    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Forensic Cases ---
    def create_case(self, case: ForensicCase) -> ForensicCase:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO for_cases (
                    case_id, title, description, incident_id, scope_definition,
                    status, lead_investigator, retention_days, legal_hold_active,
                    created_at, updated_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case.case_id, case.title, case.description, case.incident_id,
                    json.dumps(case.scope_definition), case.status.value,
                    case.lead_investigator, case.retention_days,
                    1 if case.legal_hold_active else 0,
                    case.created_at, case.updated_at, case.closed_at
                )
            )
            conn.commit()
        return case

    def get_case(self, case_id: str) -> Optional[ForensicCase]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM for_cases WHERE case_id = ?", (case_id,)
            ).fetchone()
            if not row:
                return None
            return ForensicCase(
                case_id=row["case_id"],
                title=row["title"],
                description=row["description"],
                incident_id=row["incident_id"],
                scope_definition=json.loads(row["scope_definition"] or "{}"),
                status=CaseStatus(row["status"]),
                lead_investigator=row["lead_investigator"],
                retention_days=row["retention_days"],
                legal_hold_active=bool(row["legal_hold_active"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                closed_at=row["closed_at"]
            )

    def update_case_status(self, case_id: str, status: CaseStatus, updated_at: float, closed_at: Optional[float] = None) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                UPDATE for_cases
                SET status = ?, updated_at = ?, closed_at = coalesce(?, closed_at)
                WHERE case_id = ?
                """,
                (status.value, updated_at, closed_at, case_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def update_case_legal_hold(self, case_id: str, active: bool, updated_at: float) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                UPDATE for_cases
                SET legal_hold_active = ?, updated_at = ?
                WHERE case_id = ?
                """,
                (1 if active else 0, updated_at, case_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def list_cases(self, status: Optional[CaseStatus] = None) -> List[ForensicCase]:
        with self._get_conn() as conn:
            if status:
                rows = conn.execute("SELECT * FROM for_cases WHERE status = ? ORDER BY created_at DESC", (status.value,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM for_cases ORDER BY created_at DESC").fetchall()

            cases = []
            for row in rows:
                cases.append(ForensicCase(
                    case_id=row["case_id"],
                    title=row["title"],
                    description=row["description"],
                    incident_id=row["incident_id"],
                    scope_definition=json.loads(row["scope_definition"] or "{}"),
                    status=CaseStatus(row["status"]),
                    lead_investigator=row["lead_investigator"],
                    retention_days=row["retention_days"],
                    legal_hold_active=bool(row["legal_hold_active"]),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    closed_at=row["closed_at"]
                ))
            return cases

    # --- Evidence Artifacts ---
    def record_artifact(self, artifact: EvidenceArtifact) -> EvidenceArtifact:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO for_evidence_artifacts (
                    artifact_id, case_id, source_type, source_identifier,
                    artifact_name, classification, sha256_hash, size_bytes,
                    storage_uri, parser_type, metadata_json, acquired_at,
                    acquired_by, integrity_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id, artifact.case_id, artifact.source_type.value,
                    artifact.source_identifier, artifact.artifact_name, artifact.classification,
                    artifact.sha256_hash, artifact.size_bytes, artifact.storage_uri,
                    artifact.parser_type, json.dumps(artifact.metadata), artifact.acquired_at,
                    artifact.acquired_by, artifact.integrity_status
                )
            )
            conn.commit()
        return artifact

    def get_artifact(self, artifact_id: str) -> Optional[EvidenceArtifact]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM for_evidence_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
            if not row:
                return None
            return EvidenceArtifact(
                artifact_id=row["artifact_id"],
                case_id=row["case_id"],
                source_type=ArtifactType(row["source_type"]),
                source_identifier=row["source_identifier"],
                artifact_name=row["artifact_name"],
                classification=row["classification"],
                sha256_hash=row["sha256_hash"],
                size_bytes=row["size_bytes"],
                storage_uri=row["storage_uri"],
                parser_type=row["parser_type"],
                metadata=json.loads(row["metadata_json"] or "{}"),
                acquired_at=row["acquired_at"],
                acquired_by=row["acquired_by"],
                integrity_status=row["integrity_status"]
            )

    def list_artifacts(self, case_id: str) -> List[EvidenceArtifact]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM for_evidence_artifacts WHERE case_id = ? ORDER BY acquired_at ASC", (case_id,)
            ).fetchall()
            artifacts = []
            for row in rows:
                artifacts.append(EvidenceArtifact(
                    artifact_id=row["artifact_id"],
                    case_id=row["case_id"],
                    source_type=ArtifactType(row["source_type"]),
                    source_identifier=row["source_identifier"],
                    artifact_name=row["artifact_name"],
                    classification=row["classification"],
                    sha256_hash=row["sha256_hash"],
                    size_bytes=row["size_bytes"],
                    storage_uri=row["storage_uri"],
                    parser_type=row["parser_type"],
                    metadata=json.loads(row["metadata_json"] or "{}"),
                    acquired_at=row["acquired_at"],
                    acquired_by=row["acquired_by"],
                    integrity_status=row["integrity_status"]
                ))
            return artifacts

    def update_artifact_integrity(self, artifact_id: str, status: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                "UPDATE for_evidence_artifacts SET integrity_status = ? WHERE artifact_id = ?",
                (status, artifact_id)
            )
            conn.commit()
            return cur.rowcount > 0

    # --- Append-Only Chain of Custody ---
    def record_custody(self, record: ChainOfCustodyRecord) -> ChainOfCustodyRecord:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO for_chain_of_custody (
                    custody_id, artifact_id, case_id, operation, actor,
                    reason, sha256_verified, integrity_ok, approval_token, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.custody_id, record.artifact_id, record.case_id,
                    record.operation.value, record.actor, record.reason,
                    record.sha256_verified, 1 if record.integrity_ok else 0,
                    record.approval_token, record.recorded_at
                )
            )
            conn.commit()
        return record

    def list_custody_records(self, case_id: str, artifact_id: Optional[str] = None) -> List[ChainOfCustodyRecord]:
        with self._get_conn() as conn:
            if artifact_id:
                rows = conn.execute(
                    "SELECT * FROM for_chain_of_custody WHERE case_id = ? AND artifact_id = ? ORDER BY recorded_at ASC",
                    (case_id, artifact_id)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM for_chain_of_custody WHERE case_id = ? ORDER BY recorded_at ASC",
                    (case_id,)
                ).fetchall()

            records = []
            for row in rows:
                records.append(ChainOfCustodyRecord(
                    custody_id=row["custody_id"],
                    artifact_id=row["artifact_id"],
                    case_id=row["case_id"],
                    operation=CustodyOperation(row["operation"]),
                    actor=row["actor"],
                    reason=row["reason"],
                    sha256_verified=row["sha256_verified"],
                    integrity_ok=bool(row["integrity_ok"]),
                    approval_token=row["approval_token"],
                    recorded_at=row["recorded_at"]
                ))
            return records

    # --- Timeline Events ---
    def record_timeline_events(self, events: List[TimelineEvent]) -> int:
        with self._get_conn() as conn:
            data = [
                (
                    e.event_id, e.case_id, e.artifact_id, e.timestamp_utc,
                    e.raw_timestamp, e.clock_drift_seconds, e.event_category,
                    e.action, e.actor, e.source_entity, e.target_entity,
                    e.summary, json.dumps(e.details), e.reliability_tier.value
                )
                for e in events
            ]
            conn.executemany(
                """
                INSERT INTO for_timeline_events (
                    event_id, case_id, artifact_id, timestamp_utc, raw_timestamp,
                    clock_drift_seconds, event_category, action, actor,
                    source_entity, target_entity, summary, details_json, reliability_tier
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                data
            )
            conn.commit()
        return len(events)

    def list_timeline_events(self, case_id: str) -> List[TimelineEvent]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM for_timeline_events WHERE case_id = ? ORDER BY timestamp_utc ASC",
                (case_id,)
            ).fetchall()
            events = []
            for r in rows:
                events.append(TimelineEvent(
                    event_id=r["event_id"],
                    case_id=r["case_id"],
                    artifact_id=r["artifact_id"],
                    timestamp_utc=r["timestamp_utc"],
                    raw_timestamp=r["raw_timestamp"],
                    clock_drift_seconds=r["clock_drift_seconds"],
                    event_category=r["event_category"],
                    action=r["action"],
                    actor=r["actor"],
                    source_entity=r["source_entity"],
                    target_entity=r["target_entity"],
                    summary=r["summary"],
                    details=json.loads(r["details_json"] or "{}"),
                    reliability_tier=EvidenceReliabilityTier(r["reliability_tier"])
                ))
            return events

    # --- Evidence Correlations ---
    def record_correlation(self, correlation: EvidenceCorrelation) -> EvidenceCorrelation:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO for_evidence_correlations (
                    correlation_id, case_id, source_artifact_id, target_artifact_id,
                    correlation_type, correlation_key, confidence_score, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correlation.correlation_id, correlation.case_id,
                    correlation.source_artifact_id, correlation.target_artifact_id,
                    correlation.correlation_type, correlation.correlation_key,
                    correlation.confidence_score, correlation.notes, correlation.created_at
                )
            )
            conn.commit()
        return correlation

    def list_correlations(self, case_id: str) -> List[EvidenceCorrelation]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM for_evidence_correlations WHERE case_id = ? ORDER BY created_at ASC",
                (case_id,)
            ).fetchall()
            correlations = []
            for r in rows:
                correlations.append(EvidenceCorrelation(
                    correlation_id=r["correlation_id"],
                    case_id=r["case_id"],
                    source_artifact_id=r["source_artifact_id"],
                    target_artifact_id=r["target_artifact_id"],
                    correlation_type=r["correlation_type"],
                    correlation_key=r["correlation_key"],
                    confidence_score=r["confidence_score"],
                    notes=r["notes"],
                    created_at=r["created_at"]
                ))
            return correlations

    # --- Hypotheses ---
    def record_hypothesis(self, hypothesis: ForensicHypothesis) -> ForensicHypothesis:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO for_hypotheses (
                    hypothesis_id, case_id, title, theory_description,
                    competing_with_id, status, support_score, refutation_score,
                    supporting_evidence_json, contradictory_evidence_json,
                    verdict_rationale, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis.hypothesis_id, hypothesis.case_id, hypothesis.title,
                    hypothesis.theory_description, hypothesis.competing_with_id,
                    hypothesis.status.value, hypothesis.support_score, hypothesis.refutation_score,
                    json.dumps(hypothesis.supporting_evidence),
                    json.dumps(hypothesis.contradictory_evidence),
                    hypothesis.verdict_rationale, hypothesis.created_at, hypothesis.updated_at
                )
            )
            conn.commit()
        return hypothesis

    def get_hypothesis(self, hypothesis_id: str) -> Optional[ForensicHypothesis]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM for_hypotheses WHERE hypothesis_id = ?", (hypothesis_id,)
            ).fetchone()
            if not row:
                return None
            return ForensicHypothesis(
                hypothesis_id=row["hypothesis_id"],
                case_id=row["case_id"],
                title=row["title"],
                theory_description=row["theory_description"],
                competing_with_id=row["competing_with_id"],
                status=HypothesisStatus(row["status"]),
                support_score=row["support_score"],
                refutation_score=row["refutation_score"],
                supporting_evidence=json.loads(row["supporting_evidence_json"] or "[]"),
                contradictory_evidence=json.loads(row["contradictory_evidence_json"] or "[]"),
                verdict_rationale=row["verdict_rationale"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    def update_hypothesis(self, hypothesis: ForensicHypothesis) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                UPDATE for_hypotheses
                SET status = ?, support_score = ?, refutation_score = ?,
                    supporting_evidence_json = ?, contradictory_evidence_json = ?,
                    verdict_rationale = ?, updated_at = ?
                WHERE hypothesis_id = ?
                """,
                (
                    hypothesis.status.value, hypothesis.support_score, hypothesis.refutation_score,
                    json.dumps(hypothesis.supporting_evidence),
                    json.dumps(hypothesis.contradictory_evidence),
                    hypothesis.verdict_rationale, hypothesis.updated_at,
                    hypothesis.hypothesis_id
                )
            )
            conn.commit()
            return cur.rowcount > 0

    def list_hypotheses(self, case_id: Optional[str] = None) -> List[ForensicHypothesis]:
        with self._get_conn() as conn:
            if case_id:
                rows = conn.execute(
                    "SELECT * FROM for_hypotheses WHERE case_id = ? ORDER BY created_at ASC",
                    (case_id,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM for_hypotheses ORDER BY created_at ASC"
                ).fetchall()
            hypotheses = []
            for r in rows:
                hypotheses.append(ForensicHypothesis(
                    hypothesis_id=r["hypothesis_id"],
                    case_id=r["case_id"],
                    title=r["title"],
                    theory_description=r["theory_description"],
                    competing_with_id=r["competing_with_id"],
                    status=HypothesisStatus(r["status"]),
                    support_score=r["support_score"],
                    refutation_score=r["refutation_score"],
                    supporting_evidence=json.loads(r["supporting_evidence_json"] or "[]"),
                    contradictory_evidence=json.loads(r["contradictory_evidence_json"] or "[]"),
                    verdict_rationale=r["verdict_rationale"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"]
                ))
            return hypotheses

    # --- Reports ---
    def record_report(self, report: ForensicReport) -> ForensicReport:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO for_reports (
                    report_id, case_id, title, executive_summary,
                    facts_json, inferences_json, hypotheses_json, unknowns_json,
                    recommendations_json, sign_off_investigator, cryptographic_seal, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id, report.case_id, report.title, report.executive_summary,
                    json.dumps([{"statement": s.statement, "evidence_refs": s.evidence_refs, "confidence": s.confidence} for s in report.facts]),
                    json.dumps([{"statement": s.statement, "evidence_refs": s.evidence_refs, "confidence": s.confidence} for s in report.inferences]),
                    json.dumps([{"statement": s.statement, "evidence_refs": s.evidence_refs, "confidence": s.confidence} for s in report.hypotheses]),
                    json.dumps([{"statement": s.statement, "evidence_refs": s.evidence_refs, "confidence": s.confidence} for s in report.unknowns]),
                    json.dumps(report.recommendations),
                    report.sign_off_investigator, report.cryptographic_seal, report.created_at
                )
            )
            conn.commit()
        return report

    def get_report(self, report_id: str) -> Optional[ForensicReport]:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM for_reports WHERE report_id = ?", (report_id,)
            ).fetchone()
            if not row:
                return None

            def parse_items(cat: StatementCategory, raw_json: str) -> List[StatementItem]:
                parsed = json.loads(raw_json or "[]")
                return [
                    StatementItem(
                        category=cat,
                        statement=item["statement"],
                        evidence_refs=item.get("evidence_refs", []),
                        confidence=item.get("confidence", 1.0)
                    )
                    for item in parsed
                ]

            return ForensicReport(
                report_id=row["report_id"],
                case_id=row["case_id"],
                title=row["title"],
                executive_summary=row["executive_summary"],
                facts=parse_items(StatementCategory.FACT, row["facts_json"]),
                inferences=parse_items(StatementCategory.INFERENCE, row["inferences_json"]),
                hypotheses=parse_items(StatementCategory.HYPOTHESIS, row["hypotheses_json"]),
                unknowns=parse_items(StatementCategory.UNKNOWN, row["unknowns_json"]),
                recommendations=json.loads(row["recommendations_json"] or "[]"),
                sign_off_investigator=row["sign_off_investigator"],
                cryptographic_seal=row["cryptographic_seal"],
                created_at=row["created_at"]
            )

    # --- Legal Holds ---
    def record_legal_hold(self, hold: LegalHold) -> LegalHold:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO for_legal_holds (
                    hold_id, case_id, hold_reason, applied_by, approval_token,
                    is_active, applied_at, released_at, released_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hold.hold_id, hold.case_id, hold.hold_reason, hold.applied_by,
                    hold.approval_token, 1 if hold.is_active else 0,
                    hold.applied_at, hold.released_at, hold.released_by
                )
            )
            conn.commit()
        return hold

    def release_legal_hold(self, hold_id: str, released_by: str, released_at: float) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                UPDATE for_legal_holds
                SET is_active = 0, released_by = ?, released_at = ?
                WHERE hold_id = ? AND is_active = 1
                """,
                (released_by, released_at, hold_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def list_legal_holds(self, case_id: str) -> List[LegalHold]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM for_legal_holds WHERE case_id = ? ORDER BY applied_at ASC", (case_id,)
            ).fetchall()
            holds = []
            for r in rows:
                holds.append(LegalHold(
                    hold_id=r["hold_id"],
                    case_id=r["case_id"],
                    hold_reason=r["hold_reason"],
                    applied_by=r["applied_by"],
                    approval_token=r["approval_token"],
                    is_active=bool(r["is_active"]),
                    applied_at=r["applied_at"],
                    released_at=r["released_at"],
                    released_by=r["released_by"]
                ))
            return holds
