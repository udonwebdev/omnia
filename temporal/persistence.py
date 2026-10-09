"""
Omnia Module 31: Temporal Knowledge & Causal State Persistence
Manages bi-temporal state tables, causal links, and evidence bindings in SQLite.
"""

import sqlite3
import json
import time
import logging
from typing import List, Optional, Dict, Any

from temporal.models import (
    TemporalStateRecord,
    CausalLink,
    CausalEvidenceBinding,
    CausalRelationType,
    CausalStatus,
    EvidenceSupportType,
)
from persistence.migrations import apply_migrations

logger = logging.getLogger("Omnia.Temporal.Persistence")


class TemporalPersistence:
    def __init__(self, db_path: str = "omnia_temporal.db"):
        self.db_path = db_path
        apply_migrations(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- TEMPORAL STATE RECORDS ---

    def record_state(self, state: TemporalStateRecord) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO temporal_entity_states (
                        state_id, entity_id, valid_from, valid_until, transaction_time,
                        recorded_by, state_payload_json, is_deleted, evidence_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(state_id) DO UPDATE SET
                        valid_until = excluded.valid_until,
                        state_payload_json = excluded.state_payload_json,
                        is_deleted = excluded.is_deleted,
                        evidence_id = excluded.evidence_id
                    """,
                    (
                        state.state_id,
                        state.entity_id,
                        state.valid_from,
                        state.valid_until,
                        state.transaction_time,
                        state.recorded_by,
                        json.dumps(state.state_payload),
                        1 if state.is_deleted else 0,
                        state.evidence_id,
                        state.created_at,
                    ),
                )
        finally:
            conn.close()

    def get_state(self, state_id: str) -> Optional[TemporalStateRecord]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM temporal_entity_states WHERE state_id = ?", (state_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_state(row)
        finally:
            conn.close()

    def get_states_for_entity(
        self,
        entity_id: str,
        as_of_transaction_time: Optional[float] = None
    ) -> List[TemporalStateRecord]:
        """
        Retrieves all states of an entity, optionally as known at a specific transaction time.
        Ordered by valid_from ascending.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if as_of_transaction_time is not None:
                cur.execute(
                    """
                    SELECT * FROM temporal_entity_states
                    WHERE entity_id = ? AND transaction_time <= ?
                    ORDER BY valid_from ASC, transaction_time ASC
                    """,
                    (entity_id, as_of_transaction_time),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM temporal_entity_states
                    WHERE entity_id = ?
                    ORDER BY valid_from ASC, transaction_time ASC
                    """,
                    (entity_id,),
                )
            return [self._row_to_state(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def close_previous_state(self, entity_id: str, until_time: float) -> None:
        """Closes currently open states (where valid_until IS NULL) by setting valid_until."""
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    UPDATE temporal_entity_states
                    SET valid_until = ?
                    WHERE entity_id = ? AND valid_until IS NULL
                    """,
                    (until_time, entity_id),
                )
        finally:
            conn.close()

    # --- CAUSAL LINKS ---

    def record_causal_link(self, link: CausalLink) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO causal_links (
                        causal_link_id, cause_entity_id, effect_entity_id, relation_type,
                        confidence, evidence_ids_json, mechanism_description, observed_lag_sec,
                        status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(causal_link_id) DO UPDATE SET
                        relation_type = excluded.relation_type,
                        confidence = excluded.confidence,
                        evidence_ids_json = excluded.evidence_ids_json,
                        mechanism_description = excluded.mechanism_description,
                        observed_lag_sec = excluded.observed_lag_sec,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        link.causal_link_id,
                        link.cause_entity_id,
                        link.effect_entity_id,
                        link.relation_type.value if isinstance(link.relation_type, CausalRelationType) else str(link.relation_type),
                        link.confidence,
                        json.dumps(link.evidence_ids),
                        link.mechanism_description,
                        link.observed_lag_sec,
                        link.status.value if isinstance(link.status, CausalStatus) else str(link.status),
                        link.created_at,
                        link.updated_at,
                    ),
                )
        finally:
            conn.close()

    def get_causal_link(self, link_id: str) -> Optional[CausalLink]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM causal_links WHERE causal_link_id = ?", (link_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_causal_link(row)
        finally:
            conn.close()

    def get_causes_for_effect(self, effect_id: str) -> List[CausalLink]:
        """Finds all causes pointing to effect_id."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM causal_links WHERE effect_entity_id = ? AND status != 'REFUTED'",
                (effect_id,),
            )
            return [self._row_to_causal_link(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_effects_for_cause(self, cause_id: str) -> List[CausalLink]:
        """Finds all effects emanating from cause_id."""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM causal_links WHERE cause_entity_id = ? AND status != 'REFUTED'",
                (cause_id,),
            )
            return [self._row_to_causal_link(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # --- CAUSAL EVIDENCE BINDINGS ---

    def bind_evidence(self, binding: CausalEvidenceBinding) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO causal_evidence_bindings (
                        binding_id, causal_link_id, evidence_id, support_type, strength, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(binding_id) DO UPDATE SET
                        support_type = excluded.support_type,
                        strength = excluded.strength
                    """,
                    (
                        binding.binding_id,
                        binding.causal_link_id,
                        binding.evidence_id,
                        binding.support_type.value if isinstance(binding.support_type, EvidenceSupportType) else str(binding.support_type),
                        binding.strength,
                        binding.created_at,
                    ),
                )
        finally:
            conn.close()

    def get_bindings_for_link(self, link_id: str) -> List[CausalEvidenceBinding]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM causal_evidence_bindings WHERE causal_link_id = ?", (link_id,))
            return [self._row_to_binding(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_evidence_bindings_for_link(self, link_id: str) -> List[CausalEvidenceBinding]:
        """Alias for get_bindings_for_link."""
        return self.get_bindings_for_link(link_id)

    # --- SERIALIZATION HELPERS ---

    def _row_to_state(self, r: sqlite3.Row) -> TemporalStateRecord:
        return TemporalStateRecord(
            state_id=r["state_id"],
            entity_id=r["entity_id"],
            valid_from=float(r["valid_from"]),
            valid_until=float(r["valid_until"]) if r["valid_until"] is not None else None,
            transaction_time=float(r["transaction_time"]),
            recorded_by=r["recorded_by"],
            state_payload=json.loads(r["state_payload_json"] or "{}"),
            is_deleted=bool(r["is_deleted"]),
            evidence_id=r["evidence_id"],
            created_at=float(r["created_at"]),
        )

    def _row_to_causal_link(self, r: sqlite3.Row) -> CausalLink:
        return CausalLink(
            causal_link_id=r["causal_link_id"],
            cause_entity_id=r["cause_entity_id"],
            effect_entity_id=r["effect_entity_id"],
            relation_type=CausalRelationType(r["relation_type"]) if r["relation_type"] in CausalRelationType.__members__ else CausalRelationType.RESULTED_IN,
            confidence=float(r["confidence"]),
            evidence_ids=json.loads(r["evidence_ids_json"] or "[]"),
            mechanism_description=r["mechanism_description"],
            observed_lag_sec=float(r["observed_lag_sec"]),
            status=CausalStatus(r["status"]) if r["status"] in CausalStatus.__members__ else CausalStatus.HYPOTHESIZED,
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
        )

    def _row_to_binding(self, r: sqlite3.Row) -> CausalEvidenceBinding:
        return CausalEvidenceBinding(
            binding_id=r["binding_id"],
            causal_link_id=r["causal_link_id"],
            evidence_id=r["evidence_id"],
            support_type=EvidenceSupportType(r["support_type"]) if r["support_type"] in EvidenceSupportType.__members__ else EvidenceSupportType.SUPPORTS,
            strength=float(r["strength"]),
            created_at=float(r["created_at"]),
        )
