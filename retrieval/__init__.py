"""
Omnia Module 28: Unified Search & Retrieval Engine.
"""

from retrieval.models import (
    SearchMode,
    CorpusType,
    SearchFilter,
    SearchQuery,
    EvidenceItem,
    SearchResult,
    SearchTelemetry
)
from retrieval.persistence import RetrievalPersistence
from retrieval.sources import (
    CorpusProvider,
    IngestedRecordsProvider,
    VectorMemoryProvider,
    TaskJournalProvider,
    ConfigStoreProvider
)
from retrieval.fusion import RankFusionEngine, rank_fusion_engine
from retrieval.service import UnifiedSearchService, unified_search_service

__all__ = [
    "SearchMode",
    "CorpusType",
    "SearchFilter",
    "SearchQuery",
    "EvidenceItem",
    "SearchResult",
    "SearchTelemetry",
    "RetrievalPersistence",
    "CorpusProvider",
    "IngestedRecordsProvider",
    "VectorMemoryProvider",
    "TaskJournalProvider",
    "ConfigStoreProvider",
    "RankFusionEngine",
    "rank_fusion_engine",
    "UnifiedSearchService",
    "unified_search_service"
]
