"""
Freshness & Lifecycle Evaluator for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Guarantees:
1. Distinguishes observed_at, received_at, normalized_at, and expires_at.
2. Evaluates state: FRESH -> AGING -> STALE -> EXPIRED.
3. Prevents stale external data from masquerading as current ground truth.
"""

import time
import logging
from typing import Tuple

from ingestion.models import (
    NormalizedRecord,
    FreshnessStatus
)

logger = logging.getLogger("Omnia.Ingestion.Freshness")


class FreshnessEvaluator:
    """Evaluates temporal currency and expiration thresholds of normalized records."""

    @staticmethod
    def evaluate_freshness(
        record: NormalizedRecord,
        aging_threshold_sec: float = 3600.0,      # 1 hour
        stale_threshold_sec: float = 86400.0,     # 24 hours
        as_of_time: float = None
    ) -> FreshnessStatus:
        """Computes current freshness state of a record."""
        now = as_of_time or time.time()

        # Check explicit expiration first
        if record.expires_at and now > record.expires_at:
            return FreshnessStatus.EXPIRED

        age = now - record.observed_at
        if age < 0:
            # Future timestamp anomaly
            return FreshnessStatus.UNKNOWN

        if age <= aging_threshold_sec:
            return FreshnessStatus.FRESH
        elif age <= stale_threshold_sec:
            return FreshnessStatus.AGING
        else:
            return FreshnessStatus.STALE

    @staticmethod
    def is_usable_for_decision(record: NormalizedRecord) -> bool:
        """Determines if a record is sufficiently fresh for autonomous operational decisions."""
        status = FreshnessEvaluator.evaluate_freshness(record)
        return status in (FreshnessStatus.FRESH, FreshnessStatus.AGING)


freshness_evaluator = FreshnessEvaluator()
