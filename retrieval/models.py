"""
Domain models and dataclasses for Omnia Module 28:
Unified Search & Retrieval Engine (Hybrid, Provenance-Aware, Rank Fusion).
"""

import time
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ingestion.models import DataClassification, TrustBoundary, FreshnessStatus


class SearchMode(str, Enum):
    HYBRID = "HYBRID"              # Vector + Keyword + Structured + Temporal
    SEMANTIC = "SEMANTIC"          # Dense vector search via Module 05 ChromaDB
    KEYWORD = "KEYWORD"            # BM25 / token inverted index
    STRUCTURED = "STRUCTURED"      # Exact field / SQL lookup
    TEMPORAL = "TEMPORAL"          # Interval and observation time matching
    EXACT = "EXACT"                # Cryptographic hash or primary ID match


class CorpusType(str, Enum):
    INGESTED_RECORDS = "INGESTED_RECORDS"     # Normalized records from Module 27
    WEB_CONTEXT = "WEB_CONTEXT"               # ChromaDB browser tabs from Module 05
    TASK_JOURNAL = "TASK_JOURNAL"             # Module 15 execution journals & checkpoints
    CONFIG_STORE = "CONFIG_STORE"             # Module 24 configuration definitions
    CAPABILITIES = "CAPABILITIES"             # Module 17 capability manifests
    EVENT_FABRIC = "EVENT_FABRIC"             # Module 18 published events


@dataclass
class SearchFilter:
    """Multi-dimensional filtering constraints."""
    corpus_types: Optional[List[CorpusType]] = None
    min_observed_at: Optional[float] = None
    max_observed_at: Optional[float] = None
    max_classification: DataClassification = DataClassification.INTERNAL
    required_entity_types: Optional[List[str]] = None
    source_ids: Optional[List[str]] = None
    require_verified: bool = False
    exclude_stale: bool = False


@dataclass
class SearchQuery:
    """Unified search query representation."""
    query_id: str
    query_text: str
    mode: SearchMode = SearchMode.HYBRID
    filters: SearchFilter = field(default_factory=SearchFilter)
    limit: int = 10
    actor_id: str = "system"
    include_evidence: bool = True
    context_metadata: Dict[str, Any] = field(default_factory=dict)
    executed_at: float = field(default_factory=time.time)


@dataclass
class EvidenceItem:
    """Atomic, provenance-backed evidence item extracted from retrieved records."""
    evidence_id: str
    query_id: str
    corpus_type: CorpusType
    item_id: str
    source_record_id: Optional[str]
    title: str
    content_snippet: str
    retrieval_score: float         # Raw retrieval score from corpus engine
    normalized_score: float        # Normalized [0.0, 1.0] score
    confidence_score: float        # Freshness & source reliability adjusted score
    source_id: str
    canonical_id: Optional[str]
    provenance_hash: str
    observed_at: float
    retrieved_at: float = field(default_factory=time.time)
    classification: DataClassification = DataClassification.INTERNAL
    trust_boundary: TrustBoundary = TrustBoundary.TRUSTED_INTERNAL
    freshness: FreshnessStatus = FreshnessStatus.FRESH
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "query_id": self.query_id,
            "corpus_type": self.corpus_type.value,
            "item_id": self.item_id,
            "source_record_id": self.source_record_id,
            "title": self.title,
            "content_snippet": self.content_snippet,
            "retrieval_score": self.retrieval_score,
            "normalized_score": self.normalized_score,
            "confidence_score": self.confidence_score,
            "source_id": self.source_id,
            "canonical_id": self.canonical_id,
            "provenance_hash": self.provenance_hash,
            "observed_at": self.observed_at,
            "retrieved_at": self.retrieved_at,
            "classification": self.classification.value,
            "trust_boundary": self.trust_boundary.value,
            "freshness": self.freshness.value,
            "metadata": self.metadata
        }


@dataclass
class SearchResult:
    """Unified result container returned by the Search & Retrieval Engine."""
    query_id: str
    query_text: str
    mode: SearchMode
    total_hits: int
    evidence_items: List[EvidenceItem]
    latency_ms: float
    degraded: bool = False
    degradation_reason: Optional[str] = None
    executed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "mode": self.mode.value,
            "total_hits": self.total_hits,
            "evidence_items": [e.to_dict() for e in self.evidence_items],
            "latency_ms": self.latency_ms,
            "degraded": self.degraded,
            "degradation_reason": self.degradation_reason,
            "executed_at": self.executed_at
        }


@dataclass
class SearchTelemetry:
    """Real-time observability metrics for retrieval performance."""
    total_queries: int = 0
    hybrid_queries: int = 0
    vector_queries: int = 0
    keyword_queries: int = 0
    structured_queries: int = 0
    cache_hits: int = 0
    degraded_queries: int = 0
    evidence_items_produced: int = 0
    average_latency_ms: float = 0.0
    total_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_queries": self.total_queries,
            "hybrid_queries": self.hybrid_queries,
            "vector_queries": self.vector_queries,
            "keyword_queries": self.keyword_queries,
            "structured_queries": self.structured_queries,
            "cache_hits": self.cache_hits,
            "degraded_queries": self.degraded_queries,
            "evidence_items_produced": self.evidence_items_produced,
            "average_latency_ms": (self.total_latency_ms / self.total_queries) if self.total_queries > 0 else 0.0
        }
