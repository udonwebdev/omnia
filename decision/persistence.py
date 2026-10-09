"""
Durable SQLite persistence for Module 29 Evidence & Decision Engine.
Backed by Migration Schema Version 11.
"""

import sqlite3
import json
import time
import logging
from typing import Dict, Any, List, Optional

from decision.models import (
    DecisionRecord,
    DecisionState,
    Claim,
    ClaimStatus,
    EvidenceLink,
    EvidenceStance,
    DecisionConflict,
    ConflictSeverity
)

logger = logging.getLogger("Omnia.Decision.Persistence")


class DecisionPersistence:
    """Manages durable persistence and queries for decisions, claims, links, and conflicts."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Decision Records ---

    def save_decision(self, decision: DecisionRecord) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO decision_records (
                    decision_id, subject_id, decision_type, state,
                    confidence_score, uncertainty_score, primary_claim_id,
                    summary, evaluated_at, expires_at, actor_id,
                    policy_version, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                decision.decision_id, decision.subject_id, decision.decision_type,
                decision.state.value, decision.confidence_score, decision.uncertainty_score,
                decision.primary_claim_id, decision.summary, decision.evaluated_at,
                decision.expires_at, decision.actor_id, decision.policy_version,
                json.dumps(decision.metadata, default=str)
            ))

            # Persist claims
            for claim in decision.claims:
                conn.execute("""
                    INSERT OR REPLACE INTO decision_claims (
                        claim_id, decision_id, statement, status, confidence_score,
                        supporting_evidence_count, contradicting_evidence_count,
                        evaluated_at, rationale, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    claim.claim_id, claim.decision_id, claim.statement,
                    claim.status.value, claim.confidence_score,
                    claim.supporting_evidence_count, claim.contradicting_evidence_count,
                    claim.evaluated_at, claim.rationale,
                    json.dumps(claim.metadata, default=str)
                ))

            # Persist evidence links
            for link in decision.evidence_links:
                conn.execute("""
                    INSERT OR REPLACE INTO decision_evidence_links (
                        link_id, decision_id, claim_id, evidence_id,
                        stance, weight, provenance_hash, linked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    link.link_id, link.decision_id, link.claim_id,
                    link.evidence_id, link.stance.value, link.weight,
                    link.provenance_hash, link.linked_at
                ))

            # Persist conflicts
            for cf in decision.conflicts:
                conn.execute("""
                    INSERT OR REPLACE INTO decision_conflicts (
                        conflict_id, decision_id, claim_id, conflict_type,
                        severity, resolution_state, resolved_by, resolution_rationale,
                        detected_at, resolved_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cf.conflict_id, cf.decision_id, cf.claim_id,
                    cf.conflict_type, cf.severity.value, cf.resolution_state,
                    cf.resolved_by, cf.resolution_rationale,
                    cf.detected_at, cf.resolved_at,
                    json.dumps(cf.metadata, default=str)
                ))

    def get_decision(self, decision_id: str) -> Optional[DecisionRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM decision_records WHERE decision_id = ?",
                (decision_id,)
            ).fetchone()
            if not row:
                return None

            claims = self._get_claims_for_decision(conn, decision_id)
            links = self._get_links_for_decision(conn, decision_id)
            conflicts = self._get_conflicts_for_decision(conn, decision_id)

            return DecisionRecord(
                decision_id=row["decision_id"],
                subject_id=row["subject_id"],
                decision_type=row["decision_type"],
                state=DecisionState(row["state"]),
                confidence_score=row["confidence_score"],
                uncertainty_score=row["uncertainty_score"],
                primary_claim_id=row["primary_claim_id"],
                summary=row["summary"],
                evaluated_at=row["evaluated_at"],
                expires_at=row["expires_at"],
                actor_id=row["actor_id"],
                policy_version=row["policy_version"],
                metadata=json.loads(row["metadata_json"]),
                claims=claims,
                evidence_links=links,
                conflicts=conflicts
            )

    def get_latest_decision_for_subject(self, subject_id: str) -> Optional[DecisionRecord]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT decision_id FROM decision_records WHERE subject_id = ? ORDER BY evaluated_at DESC LIMIT 1",
                (subject_id,)
            ).fetchone()
            if not row:
                return None
            return self.get_decision(row["decision_id"])

    def _get_claims_for_decision(self, conn: sqlite3.Connection, decision_id: str) -> List[Claim]:
        rows = conn.execute(
            "SELECT * FROM decision_claims WHERE decision_id = ?",
            (decision_id,)
        ).fetchall()
        return [
            Claim(
                claim_id=r["claim_id"],
                decision_id=r["decision_id"],
                statement=r["statement"],
                status=ClaimStatus(r["status"]),
                confidence_score=r["confidence_score"],
                supporting_evidence_count=r["supporting_evidence_count"],
                contradicting_evidence_count=r["contradicting_evidence_count"],
                evaluated_at=r["evaluated_at"],
                rationale=r["rationale"],
                metadata=json.loads(r["metadata_json"])
            )
            for r in rows
        ]

    def _get_links_for_decision(self, conn: sqlite3.Connection, decision_id: str) -> List[EvidenceLink]:
        rows = conn.execute(
            "SELECT * FROM decision_evidence_links WHERE decision_id = ?",
            (decision_id,)
        ).fetchall()
        return [
            EvidenceLink(
                link_id=r["link_id"],
                decision_id=r["decision_id"],
                claim_id=r["claim_id"],
                evidence_id=r["evidence_id"],
                stance=EvidenceStance(r["stance"]),
                weight=r["weight"],
                provenance_hash=r["provenance_hash"],
                linked_at=r["linked_at"]
            )
            for r in rows
        ]

    def _get_conflicts_for_decision(self, conn: sqlite3.Connection, decision_id: str) -> List[DecisionConflict]:
        rows = conn.execute(
            "SELECT * FROM decision_conflicts WHERE decision_id = ?",
            (decision_id,)
        ).fetchall()
        return [
            DecisionConflict(
                conflict_id=r["conflict_id"],
                decision_id=r["decision_id"],
                claim_id=r["claim_id"],
                conflict_type=r["conflict_type"],
                severity=ConflictSeverity(r["severity"]),
                resolution_state=r["resolution_state"],
                resolved_by=r["resolved_by"],
                resolution_rationale=r["resolution_rationale"],
                detected_at=r["detected_at"],
                resolved_at=r["resolved_at"],
                metadata=json.loads(r["metadata_json"])
            )
            for r in rows
        ]
