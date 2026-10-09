"""
Corpus Providers & Unified Search Adapters for Omnia Module 28:
Unified Search & Retrieval Engine.

Queries real underlying subsystems:
1. Ingested Records (Module 27 SQLite tables: ingestion_normalized_records, ingestion_provenance)
2. Vector Memory (Module 05 ChromaDB PersistentClient via memory_engine)
3. Task Journal & Checkpoints (Module 15 task state tables)
4. Runtime Configuration Store (Module 24 config tables)
5. Capability Registry (Module 17 registry)
"""

import sqlite3
import json
import time
import logging
from typing import List, Dict, Any, Optional

from retrieval.models import CorpusType, SearchQuery, EvidenceItem
from ingestion.models import DataClassification, TrustBoundary, FreshnessStatus
from memory_engine import memory

logger = logging.getLogger("Omnia.Retrieval.Sources")


class CorpusProvider:
    """Base class for corpus-specific retrieval adapters."""

    def __init__(self, db_path: str = "omnia.db"):
        self.db_path = db_path

    def search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        raise NotImplementedError


class IngestedRecordsProvider(CorpusProvider):
    """Searches normalized records from Module 27 with full provenance lineage."""

    def search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        results = []
        q_tokens = [t.lower() for t in query.query_text.split() if len(t) > 2]
        if not q_tokens:
            q_tokens = [query.query_text.lower()]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Simple keyword matching on canonical data and entity IDs
            sql = """
                SELECT r.*, p.provenance_id, p.source_id, p.lineage_chain_json
                FROM ingestion_normalized_records r
                LEFT JOIN ingestion_provenance p ON r.record_id = p.record_id
                ORDER BY r.observed_at DESC
                LIMIT 50
            """
            try:
                rows = cursor.execute(sql).fetchall()
            except Exception as e:
                logger.debug(f"Ingested records search failed: {e}")
                return []

            for r in rows:
                data_str = r["canonical_data_json"].lower()
                can_id = r["canonical_id"].lower()
                type_str = r["canonical_entity_type"].lower()

                # Calculate match score
                match_count = sum(1 for t in q_tokens if t in data_str or t in can_id or t in type_str)
                if match_count > 0 or not query.query_text.strip():
                    score = float(match_count) / max(len(q_tokens), 1)
                    results.append({
                        "corpus_type": CorpusType.INGESTED_RECORDS,
                        "item_id": r["record_id"],
                        "source_record_id": r["record_id"],
                        "title": f"[{r['canonical_entity_type']}] {r['canonical_id']}",
                        "content_snippet": r["canonical_data_json"][:400],
                        "retrieval_score": score,
                        "source_id": r["source_id"] or "ingestion.service",
                        "canonical_id": r["canonical_id"],
                        "provenance_hash": r["provenance_id"] or "prov_hash_0",
                        "observed_at": r["observed_at"],
                        "classification": DataClassification.INTERNAL,
                        "trust_boundary": TrustBoundary.TRUSTED_INTERNAL,
                        "freshness": FreshnessStatus(r["freshness_status"]),
                        "metadata": {"quality_score": r["quality_score"]}
                    })
        return results


class VectorMemoryProvider(CorpusProvider):
    """Searches long-term semantic browser and activity embeddings from Module 05 ChromaDB."""

    def search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        results = []
        try:
            hits = memory.search_context(query=query.query_text, limit=query.limit)
            for idx, h in enumerate(hits):
                # Distance score approximated from rank
                sim_score = max(0.1, 1.0 - (idx * 0.15))
                results.append({
                    "corpus_type": CorpusType.WEB_CONTEXT,
                    "item_id": f"web_{idx}_{int(h.get('timestamp', time.time()))}",
                    "source_record_id": None,
                    "title": h.get("title") or "Browser Tab Session",
                    "content_snippet": h.get("snippet", ""),
                    "retrieval_score": sim_score,
                    "source_id": h.get("url") or "memory.engine",
                    "canonical_id": h.get("url"),
                    "provenance_hash": f"chroma_{hash(h.get('url', ''))}",
                    "observed_at": h.get("timestamp", time.time()),
                    "classification": DataClassification.INTERNAL,
                    "trust_boundary": TrustBoundary.TRUSTED_INTERNAL,
                    "freshness": FreshnessStatus.FRESH,
                    "metadata": {"url": h.get("url")}
                })
        except Exception as e:
            logger.debug(f"ChromaDB search bypassed: {e}")
        return results


class TaskJournalProvider(CorpusProvider):
    """Searches task journals, checkpoints, and execution graph history from Module 15."""

    def search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        results = []
        q_lower = query.query_text.lower()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                rows = cursor.execute("""
                    SELECT task_id, goal, status, created_at, updated_at, metadata_json
                    FROM tasks
                    ORDER BY updated_at DESC
                    LIMIT 20
                """).fetchall()
            except Exception as e:
                logger.debug(f"Tasks search failed: {e}")
                return []

            for r in rows:
                goal_str = (r["goal"] or "").lower()
                tid = r["task_id"].lower()
                if q_lower in goal_str or q_lower in tid or not q_lower.strip():
                    results.append({
                        "corpus_type": CorpusType.TASK_JOURNAL,
                        "item_id": r["task_id"],
                        "source_record_id": r["task_id"],
                        "title": f"Task: {r['goal'][:60]}",
                        "content_snippet": f"Status: {r['status']}\nMetadata: {r['metadata_json'][:200]}",
                        "retrieval_score": 0.85 if q_lower in goal_str else 0.5,
                        "source_id": "persistence.tasks",
                        "canonical_id": r["task_id"],
                        "provenance_hash": f"task_{r['task_id'][:8]}",
                        "observed_at": r["updated_at"],
                        "classification": DataClassification.INTERNAL,
                        "trust_boundary": TrustBoundary.TRUSTED_INTERNAL,
                        "freshness": FreshnessStatus.FRESH,
                        "metadata": {"status": r["status"]}
                    })
        return results


class ConfigStoreProvider(CorpusProvider):
    """Searches runtime configuration keys and values from Module 24."""

    def search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        results = []
        q_lower = query.query_text.lower()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                rows = cursor.execute("""
                    SELECT key, domain, data_type, default_value_json, scope
                    FROM config_schemas
                    LIMIT 30
                """).fetchall()
            except Exception as e:
                logger.debug(f"Config store search failed: {e}")
                return []

            for r in rows:
                k = r["key"].lower()
                dom = r["domain"].lower()
                if q_lower in k or q_lower in dom or not q_lower.strip():
                    results.append({
                        "corpus_type": CorpusType.CONFIG_STORE,
                        "item_id": r["key"],
                        "source_record_id": r["key"],
                        "title": f"Config [{r['domain']}]: {r['key']}",
                        "content_snippet": f"Scope: {r['scope']}\nType: {r['data_type']}\nDefault: {r['default_value_json']}",
                        "retrieval_score": 0.9 if q_lower in k else 0.6,
                        "source_id": "config.control_plane",
                        "canonical_id": r["key"],
                        "provenance_hash": f"cfg_{hash(r['key'])}",
                        "observed_at": time.time(),
                        "classification": DataClassification.INTERNAL,
                        "trust_boundary": TrustBoundary.TRUSTED_INTERNAL,
                        "freshness": FreshnessStatus.FRESH,
                        "metadata": {"domain": r["domain"], "scope": r["scope"]}
                    })
        return results
