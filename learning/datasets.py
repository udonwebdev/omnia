"""
Omnia Module 33: Learning Dataset Builder & Versioning
Creates immutable, reproducible datasets with cryptographic manifests,
temporal boundary enforcement, and anti-leakage train/validation splits.
"""

from __future__ import annotations

import json
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

from learning.models import LearningDataset, LearningSignal, DatasetPurpose, SignalQualityStatus


class DatasetBuilder:
    """
    Constructs deterministic learning datasets from verified learning signals.
    """

    def __init__(self) -> None:
        pass

    def build_dataset(
        self,
        dataset_id: str,
        version: str,
        purpose: DatasetPurpose,
        signals: List[LearningSignal],
        train_val_split_ratio: float = 0.8,
        temporal_cutoff: Optional[float] = None,
    ) -> LearningDataset:
        """
        Filters, validates, temporally orders, and splits signals into an immutable dataset.
        """
        # 1. Filter out invalid, tampered, or rejected signals
        valid_signals = [
            s for s in signals
            if s.quality_status == SignalQualityStatus.ACCEPTED and s.is_eligible_for_training
        ]

        # 2. Enforce temporal boundary if provided
        if temporal_cutoff is not None:
            valid_signals = [s for s in valid_signals if s.observation_time <= temporal_cutoff]

        # 3. Sort chronologically
        valid_signals.sort(key=lambda s: (s.observation_time, s.signal_id))

        signal_ids = [s.signal_id for s in valid_signals]
        sample_count = len(signal_ids)

        # 4. Strict chronological split (train earlier, val later)
        split_index = int(sample_count * train_val_split_ratio)
        train_signal_ids = signal_ids[:split_index]
        val_signal_ids = signal_ids[split_index:]

        # 5. Extract schemas and feature definitions
        feature_schema = self._extract_feature_schema(valid_signals)

        # 6. Compute cryptographic manifest & checksums
        manifest = {
            "dataset_id": dataset_id,
            "version": version,
            "purpose": purpose.value if isinstance(purpose, DatasetPurpose) else str(purpose),
            "sample_count": sample_count,
            "train_count": len(train_signal_ids),
            "val_count": len(val_signal_ids),
            "train_signal_ids": train_signal_ids,
            "validation_signal_ids": val_signal_ids,
            "split_strategy": "chronological_boundary",
        }

        # Content digest of all signal provenances
        content_buffer = "".join(f"{s.signal_id}:{s.provenance_hash}" for s in valid_signals)
        content_digest = hashlib.sha256(content_buffer.encode("utf-8")).hexdigest()

        start_time = valid_signals[0].event_time if valid_signals else time.time()
        end_time = valid_signals[-1].observation_time if valid_signals else start_time

        return LearningDataset(
            dataset_id=dataset_id,
            version=version,
            purpose=purpose,
            time_window_start=start_time,
            time_window_end=end_time,
            sample_count=sample_count,
            content_digest=content_digest,
            manifest=manifest,
            inclusion_rules=["quality_status == ACCEPTED", "is_eligible_for_training == True"],
            features_schema=feature_schema,
            created_at=time.time(),
        )

    def _extract_feature_schema(self, signals: List[LearningSignal]) -> Dict[str, Any]:
        schema: Dict[str, Any] = {}
        for s in signals:
            for k, v in s.metrics.items():
                if k not in schema:
                    schema[k] = type(v).__name__
        return schema
