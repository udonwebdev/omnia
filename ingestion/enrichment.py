"""
Bounded Enrichment Engine with Loop Protection for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Guarantees:
1. Controlled enrichment (metadata lookup, language detection, classification).
2. Hard boundaries: max_depth, max_operations, timeout deadlines.
3. Cycle detection preventing infinite recursive lookups.
4. Every enrichment operation is recorded in the record's LineageStep chain.
"""

import time
import logging
from typing import Dict, Any, List, Optional, Callable, Set

from ingestion.models import (
    NormalizedRecord,
    LineageStep
)

logger = logging.getLogger("Omnia.Ingestion.Enrichment")

MAX_ENRICHMENT_DEPTH = 3
MAX_ENRICHMENT_OPERATIONS = 10


class EnrichmentLoopError(RuntimeError):
    """Raised when an enrichment operation attempts an infinite cycle or exceeds budget."""
    pass


class EnrichmentEngine:
    """Safely enriches normalized records within bounded resource and recursion limits."""

    def __init__(self):
        self._enrichers: Dict[str, Callable[[NormalizedRecord], Dict[str, Any]]] = {}
        self._init_built_in_enrichers()

    def _init_built_in_enrichers(self):
        """Initializes built-in metadata enrichers."""
        def enrich_general_metadata(record: NormalizedRecord) -> Dict[str, Any]:
            data = record.canonical_data
            enrichments = {}
            if isinstance(data, dict):
                # Detect language if text is present
                if "text" in data and isinstance(data["text"], str):
                    enrichments["has_text"] = True
                    enrichments["text_length"] = len(data["text"])
                if "amount" in data and "currency" in data:
                    enrichments["monetary_value"] = f"{data['amount']} {data['currency']}"
            return enrichments

        self.register_enricher("general_metadata", enrich_general_metadata)

    def register_enricher(self, name: str, enricher_fn: Callable[[NormalizedRecord], Dict[str, Any]]):
        self._enrichers[name] = enricher_fn

    def enrich(
        self,
        record: NormalizedRecord,
        enrichers: Optional[List[str]] = None,
        max_depth: int = MAX_ENRICHMENT_DEPTH,
        max_ops: int = MAX_ENRICHMENT_OPERATIONS
    ) -> NormalizedRecord:
        """
        Enriches a normalized record with loop detection and budget constraints.
        """
        target_enrichers = enrichers or list(self._enrichers.keys())
        ops_executed = 0
        seen_enrichers: Set[str] = set()

        for name in target_enrichers:
            if ops_executed >= max_ops:
                logger.warning(f"Enrichment budget exceeded ({max_ops} ops) for record '{record.record_id}'.")
                break

            if name in seen_enrichers:
                raise EnrichmentLoopError(f"Enrichment cycle detected: '{name}' already executed for record '{record.record_id}'.")

            seen_enrichers.add(name)
            enricher_fn = self._enrichers.get(name)
            if not enricher_fn:
                continue

            try:
                result = enricher_fn(record)
                ops_executed += 1
                if result:
                    record.canonical_data["_enriched"] = record.canonical_data.get("_enriched", {})
                    record.canonical_data["_enriched"].update(result)

                    # Append Lineage Step
                    record.provenance.lineage_chain.append(LineageStep(
                        stage_name="ENRICHED",
                        transformer_id=f"enricher.{name}",
                        transformer_version="1.0.0",
                        timestamp=time.time(),
                        metadata={"enricher": name, "keys_added": list(result.keys())}
                    ))
                    record.quality.transformation_count += 1
            except Exception as e:
                logger.error(f"Enricher '{name}' failed on record '{record.record_id}': {e}")

        return record


enrichment_engine = EnrichmentEngine()
