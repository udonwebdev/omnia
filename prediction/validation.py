"""
Omnia Module 32: Data Quality & Input Validation
Assesses historical sample count, timestamps, missing values, freshness,
and ensures strict prevention of temporal data leakage (future records).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
import time

from prediction.models import ForecastInput


@dataclass
class DataQualityReport:
    is_valid: bool
    sample_count: int
    missing_value_count: int
    duplicate_timestamp_count: int
    has_future_leakage: bool
    is_chronological: bool
    staleness_sec: float
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "sample_count": self.sample_count,
            "missing_value_count": self.missing_value_count,
            "duplicate_timestamp_count": self.duplicate_timestamp_count,
            "has_future_leakage": self.has_future_leakage,
            "is_chronological": self.is_chronological,
            "staleness_sec": self.staleness_sec,
            "issues": self.issues,
            "warnings": self.warnings,
        }


def validate_input_dataset(
    inputs: List[ForecastInput],
    as_of_time: Optional[float] = None,
    min_samples: int = 3,
    max_staleness_sec: float = 604800.0,  # 7 days max default
) -> Tuple[bool, DataQualityReport]:
    """
    Validates input dataset for forecasting, ensuring no temporal leakage
    and assessing sample size, timestamp consistency, and freshness.
    """
    as_of = as_of_time if as_of_time is not None else time.time()
    issues: List[str] = []
    warnings: List[str] = []

    if not inputs:
        report = DataQualityReport(
            is_valid=False,
            sample_count=0,
            missing_value_count=0,
            duplicate_timestamp_count=0,
            has_future_leakage=False,
            is_chronological=True,
            staleness_sec=0.0,
            issues=["No input observations provided."],
        )
        return False, report

    sample_count = len(inputs)
    if sample_count < min_samples:
        issues.append(f"Insufficient samples: {sample_count} provided, minimum {min_samples} required.")

    # Check temporal leakage: inputs MUST be <= as_of
    future_records = [inp for inp in inputs if inp.timestamp > as_of + 0.001]
    has_leakage = len(future_records) > 0
    if has_leakage:
        issues.append(f"Temporal data leakage detected: {len(future_records)} observations exist after as_of_time {as_of}.")

    # Check missing values
    missing_count = sum(1 for inp in inputs if inp.value is None)
    if missing_count > 0:
        issues.append(f"Missing values found: {missing_count} observations have None value.")

    # Check timestamps and chronological order
    timestamps = [inp.timestamp for inp in inputs]
    is_chronological = all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))
    if not is_chronological:
        warnings.append("Observations are not chronologically sorted; sorting will be applied.")

    # Check duplicates
    unique_timestamps = set(timestamps)
    duplicate_count = len(timestamps) - len(unique_timestamps)
    if duplicate_count > 0:
        warnings.append(f"Duplicate observation timestamps detected: {duplicate_count} collisions.")

    # Freshness
    latest_ts = max(timestamps) if timestamps else 0.0
    staleness_sec = max(0.0, as_of - latest_ts)
    if staleness_sec > max_staleness_sec:
        warnings.append(f"Dataset is stale: most recent observation is {staleness_sec:.1f}s older than as_of_time.")

    is_valid = len(issues) == 0
    report = DataQualityReport(
        is_valid=is_valid,
        sample_count=sample_count,
        missing_value_count=missing_count,
        duplicate_timestamp_count=duplicate_count,
        has_future_leakage=has_leakage,
        is_chronological=is_chronological,
        staleness_sec=staleness_sec,
        issues=issues,
        warnings=warnings,
    )
    return is_valid, report
