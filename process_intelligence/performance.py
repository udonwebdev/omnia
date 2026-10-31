"""
Omnia Module 39: Autonomous Workflow Optimization & Process Intelligence Engine.
Workflow Performance Analyzer: Statistical Latencies, Percentiles & Waiting Ratios.
"""

from __future__ import annotations

import logging
import statistics
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from process_intelligence.models import WorkflowPerformanceSnapshot
from process_intelligence.persistence import ProcessIntelligenceRepository

logger = logging.getLogger("Omnia.Process.Performance")


class WorkflowPerformanceAnalyzer:
    """
    Computes rigorous statistical latency distributions (mean, median, p90, p95, p99)
    and distinguishes active working duration from passive waiting queues.
    """

    def __init__(self, repository: Optional[ProcessIntelligenceRepository] = None):
        self.repo = repository or ProcessIntelligenceRepository()

    def analyze_workflow_performance(self, workflow_id: str) -> WorkflowPerformanceSnapshot:
        """Computes statistical performance metrics over all recorded traces for a workflow."""
        traces = self.repo.list_traces_for_workflow(workflow_id)
        if not traces:
            raise ValueError(f"No execution traces available for workflow '{workflow_id}'")

        durations = [t.total_duration_sec for t in traces]
        waiting_times = [t.total_waiting_sec for t in traces]
        active_times = [t.total_active_sec for t in traces]

        durations.sort()
        n = len(durations)

        def _percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * p
            f = int(k)
            c = min(f + 1, len(data) - 1)
            d0 = data[f] * (c - k)
            d1 = data[c] * (k - f)
            return d0 + d1

        mean_dur = statistics.mean(durations) if durations else 0.0
        median_dur = statistics.median(durations) if durations else 0.0
        p90 = _percentile(durations, 0.90)
        p95 = _percentile(durations, 0.95)
        p99 = _percentile(durations, 0.99)

        mean_waiting = statistics.mean(waiting_times) if waiting_times else 0.0
        total_active = sum(active_times)
        total_waiting = sum(waiting_times)
        active_to_wait_ratio = (total_active / total_waiting) if total_waiting > 0 else 1.0

        failures = sum(t.failure_count for t in traces)
        retries = sum(t.retry_count for t in traces)
        failure_rate = (failures / n) if n > 0 else 0.0
        retry_freq = (retries / n) if n > 0 else 0.0

        snapshot = WorkflowPerformanceSnapshot(
            snapshot_id=f"perf-{uuid.uuid4().hex[:8]}",
            workflow_id=workflow_id,
            trace_count=n,
            mean_duration_sec=round(mean_dur, 3),
            median_duration_sec=round(median_dur, 3),
            p90_duration_sec=round(p90, 3),
            p95_duration_sec=round(p95, 3),
            p99_duration_sec=round(p99, 3),
            mean_waiting_time_sec=round(mean_waiting, 3),
            active_to_wait_ratio=round(active_to_wait_ratio, 3),
            overall_failure_rate=round(failure_rate, 4),
            retry_frequency_per_trace=round(retry_freq, 3),
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_performance_snapshot(snapshot)
        logger.info(
            f"Performance for '{workflow_id}' ({n} traces): Mean={mean_dur:.2f}s, P95={p95:.2f}s, Wait={mean_waiting:.2f}s"
        )
        return snapshot
