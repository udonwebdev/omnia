"""
Production Orchestrator & Gateway for Omnia Module 28:
Unified Search & Retrieval Engine (Hybrid, Ranking, Filtering, Provenance, Evidence Extraction).

Coordinates:
- Query normalization and filter validation
- Multi-corpus dispatch (Ingested, Vector Memory, Task Journal, Config Store)
- Reciprocal Rank Fusion & confidence calibration
- Evidence item persistence (Migration Version 10)
- Result caching & telemetry metrics
- Event Fabric publication into Module 18
"""

import time
import uuid
import hashlib
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

from retrieval.models import (
    SearchMode,
    CorpusType,
    SearchFilter,
    SearchQuery,
    EvidenceItem,
    SearchResult,
    SearchTelemetry
)
from retrieval.sources import (
    IngestedRecordsProvider,
    VectorMemoryProvider,
    TaskJournalProvider,
    ConfigStoreProvider
)
from retrieval.fusion import rank_fusion_engine, RankFusionEngine
from retrieval.persistence import RetrievalPersistence
from events.models import Event, EventEnvelope
from events.fabric import event_fabric
from policy_engine import policy_engine
from capabilities.registry import capability_registry
from capabilities.models import (
    Capability, CapabilityCategory, CapabilityProvider,
    CapabilityHealth, RiskLevel, SideEffectType, IdempotencyType
)

logger = logging.getLogger("Omnia.Retrieval.Service")


class UnifiedSearchService:
    """Authoritative service coordinating Omnia's hybrid multi-corpus retrieval and evidence extraction."""

    def __init__(
        self,
        persistence: Optional[RetrievalPersistence] = None,
        fusion_engine: Optional[RankFusionEngine] = None,
        node_id: str = "local_node"
    ):
        self.node_id = node_id
        self.persistence = persistence or RetrievalPersistence()
        self.fusion = fusion_engine or rank_fusion_engine
        self.telemetry = SearchTelemetry()

        # Initialize corpus providers
        self._providers: Dict[CorpusType, Any] = {
            CorpusType.INGESTED_RECORDS: IngestedRecordsProvider(self.persistence.db_path),
            CorpusType.WEB_CONTEXT: VectorMemoryProvider(self.persistence.db_path),
            CorpusType.TASK_JOURNAL: TaskJournalProvider(self.persistence.db_path),
            CorpusType.CONFIG_STORE: ConfigStoreProvider(self.persistence.db_path)
        }

        self._register_capabilities()

    def _register_capabilities(self):
        """Registers Module 28 search capabilities into Module 17 CapabilityRegistry."""
        try:
            cap = Capability(
                id="search.unified_query",
                name="Unified Hybrid Search & Evidence Retrieval",
                version="1.0.0",
                description="Performs fused hybrid retrieval across vector, structured, and knowledge corpora",
                category=CapabilityCategory.RETRIEVAL,
                provider=CapabilityProvider(provider_id="retrieval.service", name="Search Control Plane", version="1.0.0"),
                health=CapabilityHealth.HEALTHY,
                risk_level=RiskLevel.LOW,
                side_effect_type=SideEffectType.READ,
                idempotency=IdempotencyType.STRICTLY_IDEMPOTENT
            )
            capability_registry.register_capability(cap)
            logger.info("Registered search.unified_query capability into registry.")
        except Exception as e:
            logger.debug(f"Search capability registration bypassed: {e}")

    def search(
        self,
        query_text: Any,
        mode: SearchMode = SearchMode.HYBRID,
        filters: Optional[SearchFilter] = None,
        limit: int = 10,
        actor_id: str = "system",
        use_cache: bool = True
    ) -> SearchResult:
        """
        Executes unified search and evidence extraction across Omnia knowledge corpora.
        Accepts either a SearchQuery instance or raw query_text with individual parameters.
        """
        t0 = time.perf_counter()
        if isinstance(query_text, SearchQuery):
            query = query_text
            query_id = query.query_id
            query_text = query.query_text
            mode = query.mode
            search_filter = query.filters
            limit = query.limit
            actor_id = query.actor_id
        else:
            query_text = str(query_text)
            query_id = f"qry_{uuid.uuid4().hex[:12]}"
            search_filter = filters or SearchFilter()
            query = SearchQuery(
                query_id=query_id,
                query_text=query_text,
                mode=mode,
                filters=search_filter,
                limit=limit,
                actor_id=actor_id
            )

        self.telemetry.total_queries += 1
        if mode == SearchMode.HYBRID:
            self.telemetry.hybrid_queries += 1
        elif mode == SearchMode.SEMANTIC:
            self.telemetry.vector_queries += 1
        elif mode == SearchMode.STRUCTURED:
            self.telemetry.structured_queries += 1

        # 1. Policy Authorization (Module 09)
        allowed, reason = policy_engine.verify_action("retrieval.search", {
            "actor_id": actor_id,
            "mode": mode.value,
            "max_classification": search_filter.max_classification.value
        })
        if not allowed:
            logger.warning(f"Search query rejected by policy: {reason}")
            return SearchResult(
                query_id=query_id,
                query_text=query_text,
                mode=mode,
                total_hits=0,
                evidence_items=[],
                latency_ms=(time.perf_counter() - t0) * 1000.0,
                degraded=True,
                degradation_reason=f"POLICY_DENIED: {reason}"
            )

        # 2. Cache Lookup
        cache_key = self._generate_cache_key(query)
        if use_cache:
            cached_evidence = self.persistence.get_cached_result(cache_key)
            if cached_evidence is not None:
                self.telemetry.cache_hits += 1
                latency_ms = (time.perf_counter() - t0) * 1000.0
                items = [self.persistence._row_to_evidence(row) if hasattr(row, 'keys') else EvidenceItem(**row) for row in cached_evidence]
                return SearchResult(
                    query_id=query_id,
                    query_text=query_text,
                    mode=mode,
                    total_hits=len(items),
                    evidence_items=items,
                    latency_ms=latency_ms
                )

        # 3. Federated Corpus Querying
        target_corpora = search_filter.corpus_types or list(self._providers.keys())
        if mode == SearchMode.SEMANTIC:
            target_corpora = [c for c in target_corpora if c == CorpusType.WEB_CONTEXT]
        elif mode == SearchMode.STRUCTURED:
            target_corpora = [c for c in target_corpora if c in (CorpusType.INGESTED_RECORDS, CorpusType.TASK_JOURNAL, CorpusType.CONFIG_STORE)]

        candidates_by_corpus: Dict[CorpusType, List[Dict[str, Any]]] = {}
        degraded = False
        degradation_reasons = []

        for corpus in target_corpora:
            provider = self._providers.get(corpus)
            if not provider:
                continue
            try:
                hits = provider.search(query)
                candidates_by_corpus[corpus] = hits
            except Exception as e:
                degraded = True
                degradation_reasons.append(f"{corpus.value}_ERROR: {e}")
                logger.warning(f"Corpus provider '{corpus.value}' search degraded: {e}")
                self._emit_event("search.degraded", {
                    "corpus_type": corpus.value,
                    "reason": str(e)
                })

        # 4. Rank Fusion & Confidence Calibration
        evidence_items = self.fusion.fuse_and_rank(query, candidates_by_corpus)
        self.telemetry.evidence_items_produced += len(evidence_items)

        # 5. Persistence & Cache Storage
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self.telemetry.total_latency_ms += latency_ms

        if evidence_items:
            self.persistence.save_evidence_items(evidence_items)
            self.persistence.store_cache_result(
                cache_key=cache_key,
                query_hash=hashlib.sha256(query_text.encode("utf-8")).hexdigest(),
                filters_hash=hashlib.sha256(json.dumps(search_filter.__dict__, default=str).encode("utf-8")).hexdigest(),
                results=[e.to_dict() for e in evidence_items]
            )

        self.persistence.log_query(query, total_hits=len(evidence_items), latency_ms=latency_ms)

        # 6. Event Fabric Publication
        self._emit_event("search.executed", {
            "query_id": query_id,
            "query_text": query_text,
            "total_hits": len(evidence_items),
            "latency_ms": latency_ms
        })

        for e in evidence_items[:3]:
            self._emit_event("search.evidence.extracted", {
                "evidence_id": e.evidence_id,
                "source_record_id": e.source_record_id or e.item_id,
                "confidence_score": e.confidence_score
            })

        return SearchResult(
            query_id=query_id,
            query_text=query_text,
            mode=mode,
            total_hits=len(evidence_items),
            evidence_items=evidence_items,
            latency_ms=latency_ms,
            degraded=degraded,
            degradation_reason="; ".join(degradation_reasons) if degradation_reasons else None
        )

    def get_evidence(self, query_id: str) -> List[EvidenceItem]:
        return self.persistence.get_evidence_by_query(query_id)

    def get_telemetry(self) -> SearchTelemetry:
        return self.telemetry

    def _generate_cache_key(self, query: SearchQuery) -> str:
        s = f"{query.query_text}:{query.mode.value}:{json.dumps(query.filters.__dict__, sort_keys=True, default=str)}"
        return f"cache_{hashlib.sha256(s.encode('utf-8')).hexdigest()[:24]}"

    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        try:
            import asyncio
            evt = Event(
                envelope=EventEnvelope(
                    event_type=event_type,
                    source=f"retrieval.service.{self.node_id}"
                ),
                payload=payload
            )
            async def _pub():
                await event_fabric.publish(evt)
                await event_fabric._dispatch_lanes()
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_pub())
                else:
                    loop.run_until_complete(_pub())
            except RuntimeError:
                asyncio.run(_pub())
        except Exception as e:
            logger.debug(f"Search event publish skipped: {e}")


unified_search_service = UnifiedSearchService()
