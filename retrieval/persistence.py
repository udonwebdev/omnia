"""
SQLite Persistence Repository for Omnia Module 28:
Unified Search & Retrieval Engine (Migration Version 10 Tables).
"""

import sqlite3
import json
import time
import logging
from typing import List, Dict, Any, Optional

from retrieval.models import EvidenceItem, SearchQuery, CorpusType
from ingestion.models import DataClassification, TrustBoundary, FreshnessStatus

logger = logging.getLogger("Omnia.Retrieval.Persistence")


class RetrievalPersistence:
    """Manages SQLite queries, evidence item archiving, and query caching."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # --- Evidence Records ---

    def save_evidence_items(self, items: List[EvidenceItem]) -> None:
        if not items:
            return
        with self._get_connection() as conn:
            for item in items:
                conn.execute("""
                    INSERT OR REPLACE INTO retrieval_evidence (
                        evidence_id, query_id, corpus_type, item_id, source_record_id,
                        title, content_snippet, retrieval_score, normalized_score,
                        confidence_score, source_id, canonical_id, provenance_hash,
                        observed_at, retrieved_at, classification, trust_boundary,
                        freshness_status, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.evidence_id, item.query_id, item.corpus_type.value, item.item_id,
                    item.source_record_id, item.title, item.content_snippet, item.retrieval_score,
                    item.normalized_score, item.confidence_score, item.source_id, item.canonical_id,
                    item.provenance_hash, item.observed_at, item.retrieved_at, item.classification.value,
                    item.trust_boundary.value, item.freshness.value, json.dumps(item.metadata, default=str)
                ))

    def get_evidence_by_query(self, query_id: str) -> List[EvidenceItem]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM retrieval_evidence WHERE query_id = ? ORDER BY confidence_score DESC",
                (query_id,)
            ).fetchall()
            return [self._row_to_evidence(r) for r in rows]

    def _row_to_evidence(self, row: sqlite3.Row) -> EvidenceItem:
        return EvidenceItem(
            evidence_id=row["evidence_id"],
            query_id=row["query_id"],
            corpus_type=CorpusType(row["corpus_type"]),
            item_id=row["item_id"],
            source_record_id=row["source_record_id"],
            title=row["title"],
            content_snippet=row["content_snippet"],
            retrieval_score=row["retrieval_score"],
            normalized_score=row["normalized_score"],
            confidence_score=row["confidence_score"],
            source_id=row["source_id"],
            canonical_id=row["canonical_id"],
            provenance_hash=row["provenance_hash"],
            observed_at=row["observed_at"],
            retrieved_at=row["retrieved_at"],
            classification=DataClassification(row["classification"]),
            trust_boundary=TrustBoundary(row["trust_boundary"]),
            freshness=FreshnessStatus(row["freshness_status"]),
            metadata=json.loads(row["metadata_json"])
        )

    # --- Query Audit Log ---

    def log_query(
        self,
        query: SearchQuery,
        total_hits: int,
        latency_ms: float
    ) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO retrieval_queries (
                    query_id, query_text, filters_json, mode, total_hits,
                    latency_ms, executed_at, actor_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                query.query_id, query.query_text,
                json.dumps(query.filters.__dict__, default=str),
                query.mode.value, total_hits, latency_ms,
                query.executed_at, query.actor_id,
                json.dumps(query.context_metadata, default=str)
            ))

    def get_logged_query(self, query_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM retrieval_queries WHERE query_id = ?",
                (query_id,)
            ).fetchone()
            if row:
                return dict(row)
            return None

    # --- Query Caching ---

    def get_cached_result(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        now = time.time()
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT results_json, expires_at FROM retrieval_cache WHERE cache_key = ?",
                (cache_key,)
            ).fetchone()
            if row and row["expires_at"] > now:
                conn.execute(
                    "UPDATE retrieval_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                    (cache_key,)
                )
                return json.loads(row["results_json"])
            return None

    def store_cache_result(
        self,
        cache_key: str,
        query_hash: str,
        filters_hash: str,
        results: List[Dict[str, Any]],
        ttl_seconds: float = 300.0
    ) -> None:
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO retrieval_cache (
                    cache_key, query_hash, filters_hash, results_json,
                    cached_at, expires_at, hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (cache_key, query_hash, filters_hash, json.dumps(results, default=str), now, now + ttl_seconds))
