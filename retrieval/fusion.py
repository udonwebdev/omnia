"""
Score Fusion, Ranking & Evidence Calibration Engine for Omnia Module 28:
Unified Search & Retrieval Engine.

Implements:
1. Reciprocal Rank Fusion (RRF): Combines disparate rank lists without assuming score scale comparability.
2. Score Normalization: Min-max scaling across multi-corpus retrieval candidates.
3. Confidence Calibration: Penalizes stale, low-authority, or unverified sources.
4. Security Filtering: Enforces Module 09 policy and classification ceilings.
"""

import time
import uuid
import logging
from typing import List, Dict, Any, Tuple

from retrieval.models import EvidenceItem, SearchQuery, CorpusType
from ingestion.models import DataClassification, TrustBoundary, FreshnessStatus

logger = logging.getLogger("Omnia.Retrieval.Fusion")


class RankFusionEngine:
    """Combines candidate lists from multiple corpus engines and produces calibrated evidence items."""

    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k

    def fuse_and_rank(
        self,
        query: SearchQuery,
        candidate_lists: Dict[CorpusType, List[Dict[str, Any]]]
    ) -> List[EvidenceItem]:
        """
        Executes Reciprocal Rank Fusion, applies freshness and confidence weighting,
        and constructs authoritative EvidenceItem records.
        """
        now = time.time()
        # Item Key -> (RRF Score, best candidate record)
        fused_scores: Dict[str, float] = {}
        record_map: Dict[str, Dict[str, Any]] = {}

        # 1. Reciprocal Rank Fusion
        for corpus_type, ranked_items in candidate_lists.items():
            for rank_idx, item in enumerate(ranked_items, start=1):
                item_key = f"{corpus_type.value}:{item['item_id']}"
                # Standard RRF formula: 1 / (k + rank)
                rrf_contrib = 1.0 / (self.rrf_k + rank_idx)
                fused_scores[item_key] = fused_scores.get(item_key, 0.0) + rrf_contrib
                if item_key not in record_map:
                    record_map[item_key] = item

        if not fused_scores:
            return []

        # 2. Score Normalization: Relative to max RRF score
        max_score = max(fused_scores.values())

        evidence_items: List[EvidenceItem] = []

        for item_key, raw_rrf in fused_scores.items():
            item = record_map[item_key]
            norm_score = (raw_rrf / max_score) if max_score > 0 else 1.0

            # 3. Security Filter: Enforce max_classification ceiling
            item_class = item.get("classification", DataClassification.INTERNAL)
            if self._classification_level(item_class) > self._classification_level(query.filters.max_classification):
                continue

            # 4. Freshness & Confidence Calibration
            observed_at = item.get("observed_at", now)
            age_sec = max(0.0, now - observed_at)
            freshness_status = item.get("freshness", FreshnessStatus.FRESH)

            # Decay factor based on age and status
            freshness_penalty = 1.0
            if freshness_status == FreshnessStatus.AGING:
                freshness_penalty = 0.85
            elif freshness_status == FreshnessStatus.STALE:
                freshness_penalty = 0.50
                if query.filters.exclude_stale:
                    continue
            elif freshness_status == FreshnessStatus.EXPIRED:
                freshness_penalty = 0.10
                if query.filters.exclude_stale:
                    continue

            # Authority multiplier
            quality_score = item.get("metadata", {}).get("quality_score", 1.0)
            calibrated_confidence = round(norm_score * freshness_penalty * quality_score, 4)

            evidence_items.append(EvidenceItem(
                evidence_id=f"ev_{uuid.uuid4().hex[:12]}",
                query_id=query.query_id,
                corpus_type=item["corpus_type"],
                item_id=item["item_id"],
                source_record_id=item.get("source_record_id"),
                title=item.get("title", "Untitled Document"),
                content_snippet=item.get("content_snippet", ""),
                retrieval_score=round(item.get("retrieval_score", norm_score), 4),
                normalized_score=round(norm_score, 4),
                confidence_score=calibrated_confidence,
                source_id=item.get("source_id", "unknown_source"),
                canonical_id=item.get("canonical_id"),
                provenance_hash=item.get("provenance_hash", "prov_0"),
                observed_at=observed_at,
                retrieved_at=now,
                classification=item_class,
                trust_boundary=item.get("trust_boundary", TrustBoundary.TRUSTED_INTERNAL),
                freshness=freshness_status,
                metadata=item.get("metadata", {})
            ))

        # 5. Sort by calibrated confidence descending and truncate to query limit
        evidence_items.sort(key=lambda e: e.confidence_score, reverse=True)
        return evidence_items[:query.limit]

    def _classification_level(self, classification: DataClassification) -> int:
        order = {
            DataClassification.PUBLIC: 1,
            DataClassification.INTERNAL: 2,
            DataClassification.CONFIDENTIAL: 3,
            DataClassification.SECRET: 4
        }
        return order.get(classification, 2)


rank_fusion_engine = RankFusionEngine()
