"""
Omnia Module 30: Knowledge Graph & Entity Resolution Persistence
Handles durable storage and retrieval of entities, relationships, identities,
and resolution candidates within SQLite.
"""

import sqlite3
import json
import time
import logging
from typing import List, Optional, Dict, Any, Tuple

from knowledge.models import (
    GraphEntity,
    GraphRelationship,
    EntityIdentity,
    ResolutionCandidate,
    EntityType,
    EntityStatus,
    RelationshipStatus,
    IdentifierType,
    ResolutionStatus,
)
from retrieval.models import DataClassification, TrustBoundary
from persistence.migrations import apply_migrations

logger = logging.getLogger("Omnia.Knowledge.Persistence")


class KnowledgePersistence:
    def __init__(self, db_path: str = "omnia_knowledge.db"):
        self.db_path = db_path
        apply_migrations(self.db_path)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- ENTITIES ---

    def upsert_entity(self, entity: GraphEntity) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO knowledge_entities (
                        entity_id, canonical_name, entity_type, aliases_json, attributes_json,
                        classification, trust_boundary, confidence, provenance_ids_json,
                        status, merged_into_id, owner_node, version, valid_from, valid_until,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(entity_id) DO UPDATE SET
                        canonical_name = excluded.canonical_name,
                        entity_type = excluded.entity_type,
                        aliases_json = excluded.aliases_json,
                        attributes_json = excluded.attributes_json,
                        classification = excluded.classification,
                        trust_boundary = excluded.trust_boundary,
                        confidence = excluded.confidence,
                        provenance_ids_json = excluded.provenance_ids_json,
                        status = excluded.status,
                        merged_into_id = excluded.merged_into_id,
                        owner_node = excluded.owner_node,
                        version = knowledge_entities.version + 1,
                        valid_from = excluded.valid_from,
                        valid_until = excluded.valid_until,
                        updated_at = excluded.updated_at
                    """,
                    (
                        entity.entity_id,
                        entity.canonical_name,
                        entity.entity_type.value if isinstance(entity.entity_type, EntityType) else str(entity.entity_type),
                        json.dumps(entity.aliases),
                        json.dumps(entity.attributes),
                        entity.classification.value if isinstance(entity.classification, DataClassification) else str(entity.classification),
                        entity.trust_boundary.value if isinstance(entity.trust_boundary, TrustBoundary) else str(entity.trust_boundary),
                        entity.confidence,
                        json.dumps(entity.provenance_ids),
                        entity.status.value if isinstance(entity.status, EntityStatus) else str(entity.status),
                        entity.merged_into_id,
                        entity.owner_node,
                        entity.version,
                        entity.valid_from,
                        entity.valid_until,
                        entity.created_at,
                        entity.updated_at,
                    ),
                )
        finally:
            conn.close()

    def get_entity(self, entity_id: str) -> Optional[GraphEntity]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM knowledge_entities WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_entity(row)
        finally:
            conn.close()

    def find_entities_by_type(self, entity_type: EntityType, limit: int = 100) -> List[GraphEntity]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            t_val = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
            cur.execute("SELECT * FROM knowledge_entities WHERE entity_type = ? LIMIT ?", (t_val, limit))
            return [self._row_to_entity(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def find_entities_by_name(self, name: str, limit: int = 20) -> List[GraphEntity]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM knowledge_entities WHERE canonical_name LIKE ? OR aliases_json LIKE ? LIMIT ?",
                (f"%{name}%", f"%{name}%", limit),
            )
            return [self._row_to_entity(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def list_all_entities(self, status: Optional[EntityStatus] = None, limit: int = 500) -> List[GraphEntity]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if status:
                s_val = status.value if isinstance(status, EntityStatus) else str(status)
                cur.execute("SELECT * FROM knowledge_entities WHERE status = ? LIMIT ?", (s_val, limit))
            else:
                cur.execute("SELECT * FROM knowledge_entities LIMIT ?", (limit,))
            return [self._row_to_entity(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # --- RELATIONSHIPS ---

    def upsert_relationship(self, rel: GraphRelationship) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO knowledge_relationships (
                        relationship_id, source_id, predicate, target_id, properties_json,
                        confidence, weight, directed, provenance_ids_json, status,
                        valid_from, valid_until, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(relationship_id) DO UPDATE SET
                        predicate = excluded.predicate,
                        properties_json = excluded.properties_json,
                        confidence = excluded.confidence,
                        weight = excluded.weight,
                        directed = excluded.directed,
                        provenance_ids_json = excluded.provenance_ids_json,
                        status = excluded.status,
                        valid_from = excluded.valid_from,
                        valid_until = excluded.valid_until,
                        updated_at = excluded.updated_at
                    """,
                    (
                        rel.relationship_id,
                        rel.source_id,
                        rel.predicate,
                        rel.target_id,
                        json.dumps(rel.properties),
                        rel.confidence,
                        rel.weight,
                        1 if rel.directed else 0,
                        json.dumps(rel.provenance_ids),
                        rel.status.value if isinstance(rel.status, RelationshipStatus) else str(rel.status),
                        rel.valid_from,
                        rel.valid_until,
                        rel.created_at,
                        rel.updated_at,
                    ),
                )
        finally:
            conn.close()

    def get_relationship(self, rel_id: str) -> Optional[GraphRelationship]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM knowledge_relationships WHERE relationship_id = ?", (rel_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_relationship(row)
        finally:
            conn.close()

    def find_relationships_from(self, source_id: str, predicate: Optional[str] = None) -> List[GraphRelationship]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if predicate:
                cur.execute(
                    "SELECT * FROM knowledge_relationships WHERE source_id = ? AND predicate = ? AND status = 'ACTIVE'",
                    (source_id, predicate),
                )
            else:
                cur.execute(
                    "SELECT * FROM knowledge_relationships WHERE source_id = ? AND status = 'ACTIVE'",
                    (source_id,),
                )
            return [self._row_to_relationship(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def find_relationships_to(self, target_id: str, predicate: Optional[str] = None) -> List[GraphRelationship]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if predicate:
                cur.execute(
                    "SELECT * FROM knowledge_relationships WHERE target_id = ? AND predicate = ? AND status = 'ACTIVE'",
                    (target_id, predicate),
                )
            else:
                cur.execute(
                    "SELECT * FROM knowledge_relationships WHERE target_id = ? AND status = 'ACTIVE'",
                    (target_id,),
                )
            return [self._row_to_relationship(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def find_adjacent_relationships(self, entity_id: str) -> List[GraphRelationship]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT * FROM knowledge_relationships 
                WHERE (source_id = ? OR target_id = ?) AND status = 'ACTIVE'
                """,
                (entity_id, entity_id),
            )
            return [self._row_to_relationship(r) for r in cur.fetchall()]
        finally:
            conn.close()

    # --- IDENTITIES ---

    def add_identity(self, identity: EntityIdentity) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO entity_identities (
                        identity_id, entity_id, identifier_type, identifier_value,
                        confidence, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(identifier_type, identifier_value) DO UPDATE SET
                        entity_id = excluded.entity_id,
                        confidence = excluded.confidence
                    """,
                    (
                        identity.identity_id,
                        identity.entity_id,
                        identity.identifier_type.value if isinstance(identity.identifier_type, IdentifierType) else str(identity.identifier_type),
                        identity.identifier_value,
                        identity.confidence,
                        identity.created_at,
                    ),
                )
        finally:
            conn.close()

    def get_identities_for_entity(self, entity_id: str) -> List[EntityIdentity]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM entity_identities WHERE entity_id = ?", (entity_id,))
            return [self._row_to_identity(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def find_entity_by_identity(self, id_type: IdentifierType, id_value: str) -> Optional[GraphEntity]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            t_val = id_type.value if isinstance(id_type, IdentifierType) else str(id_type)
            cur.execute(
                """
                SELECT e.* FROM knowledge_entities e
                JOIN entity_identities i ON e.entity_id = i.entity_id
                WHERE i.identifier_type = ? AND i.identifier_value = ?
                """,
                (t_val, id_value),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_entity(row)
        finally:
            conn.close()

    # --- RESOLUTION CANDIDATES ---

    def record_resolution_candidate(self, cand: ResolutionCandidate) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO entity_resolution_candidates (
                        candidate_id, source_entity_id, target_entity_id,
                        similarity_score, match_reasons_json, status, evaluated_at, resolution_notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(candidate_id) DO UPDATE SET
                        similarity_score = excluded.similarity_score,
                        match_reasons_json = excluded.match_reasons_json,
                        status = excluded.status,
                        resolution_notes = excluded.resolution_notes
                    """,
                    (
                        cand.candidate_id,
                        cand.source_entity_id,
                        cand.target_entity_id,
                        cand.similarity_score,
                        json.dumps(cand.match_reasons),
                        cand.status.value if isinstance(cand.status, ResolutionStatus) else str(cand.status),
                        cand.evaluated_at,
                        cand.resolution_notes,
                    ),
                )
        finally:
            conn.close()

    def get_pending_candidates(self, min_similarity: float = 0.0) -> List[ResolutionCandidate]:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM entity_resolution_candidates WHERE status = 'PENDING' AND similarity_score >= ?",
                (min_similarity,),
            )
            return [self._row_to_candidate(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def update_candidate_status(self, candidate_id: str, status: ResolutionStatus, notes: Optional[str] = None) -> None:
        conn = self._get_connection()
        try:
            with conn:
                s_val = status.value if isinstance(status, ResolutionStatus) else str(status)
                conn.execute(
                    """
                    UPDATE entity_resolution_candidates 
                    SET status = ?, resolution_notes = ?
                    WHERE candidate_id = ?
                    """,
                    (s_val, notes, candidate_id),
                )
        finally:
            conn.close()

    # --- NON-DESTRUCTIVE ENTITY MERGING & SPLITTING ---

    def merge_entities(self, primary_id: str, secondary_id: str, reason: str = "") -> bool:
        """
        Non-destructive resolution merge:
        Marks secondary entity as MERGED and points its merged_into_id to primary.
        Adds secondary canonical name and aliases to primary's aliases list.
        Re-points secondary's identities to primary.
        Does NOT silently delete any record.
        """
        conn = self._get_connection()
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM knowledge_entities WHERE entity_id = ?", (primary_id,))
                p_row = cur.fetchone()
                cur.execute("SELECT * FROM knowledge_entities WHERE entity_id = ?", (secondary_id,))
                s_row = cur.fetchone()

                if not p_row or not s_row:
                    return False

                primary = self._row_to_entity(p_row)
                secondary = self._row_to_entity(s_row)

                # Merge aliases
                new_aliases = set(primary.aliases)
                new_aliases.add(secondary.canonical_name)
                for a in secondary.aliases:
                    new_aliases.add(a)
                primary.aliases = list(new_aliases)

                # Merge attributes conservatively
                for k, v in secondary.attributes.items():
                    if k not in primary.attributes:
                        primary.attributes[k] = v

                # Merge provenance
                p_prov = set(primary.provenance_ids)
                p_prov.update(secondary.provenance_ids)
                primary.provenance_ids = list(p_prov)
                primary.updated_at = time.time()

                # Update primary
                conn.execute(
                    """
                    UPDATE knowledge_entities 
                    SET aliases_json = ?, attributes_json = ?, provenance_ids_json = ?, updated_at = ?
                    WHERE entity_id = ?
                    """,
                    (
                        json.dumps(primary.aliases),
                        json.dumps(primary.attributes),
                        json.dumps(primary.provenance_ids),
                        primary.updated_at,
                        primary.entity_id,
                    ),
                )

                # Mark secondary as MERGED
                conn.execute(
                    """
                    UPDATE knowledge_entities
                    SET status = 'MERGED', merged_into_id = ?, updated_at = ?
                    WHERE entity_id = ?
                    """,
                    (primary.entity_id, time.time(), secondary.entity_id),
                )

                # Update identities referencing secondary
                conn.execute(
                    """
                    UPDATE entity_identities
                    SET entity_id = ?
                    WHERE entity_id = ?
                    """,
                    (primary.entity_id, secondary.entity_id),
                )

                # Mark any candidate between them as RESOLVED_SAME
                conn.execute(
                    """
                    UPDATE entity_resolution_candidates
                    SET status = 'RESOLVED_SAME', resolution_notes = ?
                    WHERE (source_entity_id = ? AND target_entity_id = ?)
                       OR (source_entity_id = ? AND target_entity_id = ?)
                    """,
                    (f"Merged: {reason}", primary_id, secondary_id, secondary_id, primary_id),
                )
                return True
        finally:
            conn.close()

    def split_entity(self, merged_id: str, reason: str = "") -> bool:
        """
        Reverses a merge for an entity that was marked MERGED.
        Restores it to ACTIVE status and clears merged_into_id.
        """
        conn = self._get_connection()
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM knowledge_entities WHERE entity_id = ?", (merged_id,))
                row = cur.fetchone()
                if not row:
                    return False
                if row["status"] != "MERGED":
                    return False

                conn.execute(
                    """
                    UPDATE knowledge_entities
                    SET status = 'ACTIVE', merged_into_id = NULL, updated_at = ?
                    WHERE entity_id = ?
                    """,
                    (time.time(), merged_id),
                )
                return True
        finally:
            conn.close()

    # --- SERIALIZATION HELPERS ---

    def _row_to_entity(self, r: sqlite3.Row) -> GraphEntity:
        return GraphEntity(
            entity_id=r["entity_id"],
            canonical_name=r["canonical_name"],
            entity_type=EntityType(r["entity_type"]) if r["entity_type"] in EntityType.__members__ else EntityType.CUSTOM,
            aliases=json.loads(r["aliases_json"] or "[]"),
            attributes=json.loads(r["attributes_json"] or "{}"),
            classification=DataClassification(r["classification"]) if r["classification"] in DataClassification.__members__ else DataClassification.INTERNAL,
            trust_boundary=TrustBoundary(r["trust_boundary"]) if r["trust_boundary"] in TrustBoundary.__members__ else TrustBoundary.TRUSTED_INTERNAL,
            confidence=float(r["confidence"]),
            provenance_ids=json.loads(r["provenance_ids_json"] or "[]"),
            status=EntityStatus(r["status"]) if r["status"] in EntityStatus.__members__ else EntityStatus.ACTIVE,
            merged_into_id=r["merged_into_id"],
            owner_node=r["owner_node"],
            version=int(r["version"]),
            valid_from=float(r["valid_from"]),
            valid_until=float(r["valid_until"]) if r["valid_until"] is not None else None,
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
        )

    def _row_to_relationship(self, r: sqlite3.Row) -> GraphRelationship:
        return GraphRelationship(
            relationship_id=r["relationship_id"],
            source_id=r["source_id"],
            predicate=r["predicate"],
            target_id=r["target_id"],
            properties=json.loads(r["properties_json"] or "{}"),
            confidence=float(r["confidence"]),
            weight=float(r["weight"]),
            directed=bool(r["directed"]),
            provenance_ids=json.loads(r["provenance_ids_json"] or "[]"),
            status=RelationshipStatus(r["status"]) if r["status"] in RelationshipStatus.__members__ else RelationshipStatus.ACTIVE,
            valid_from=float(r["valid_from"]),
            valid_until=float(r["valid_until"]) if r["valid_until"] is not None else None,
            created_at=float(r["created_at"]),
            updated_at=float(r["updated_at"]),
        )

    def _row_to_identity(self, r: sqlite3.Row) -> EntityIdentity:
        return EntityIdentity(
            identity_id=r["identity_id"],
            entity_id=r["entity_id"],
            identifier_type=IdentifierType(r["identifier_type"]) if r["identifier_type"] in IdentifierType.__members__ else IdentifierType.CUSTOM,
            identifier_value=r["identifier_value"],
            confidence=float(r["confidence"]),
            created_at=float(r["created_at"]),
        )

    def _row_to_candidate(self, r: sqlite3.Row) -> ResolutionCandidate:
        return ResolutionCandidate(
            candidate_id=r["candidate_id"],
            source_entity_id=r["source_entity_id"],
            target_entity_id=r["target_entity_id"],
            similarity_score=float(r["similarity_score"]),
            match_reasons=json.loads(r["match_reasons_json"] or "[]"),
            status=ResolutionStatus(r["status"]) if r["status"] in ResolutionStatus.__members__ else ResolutionStatus.PENDING,
            evaluated_at=float(r["evaluated_at"]),
            resolution_notes=r["resolution_notes"],
        )
