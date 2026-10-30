"""
OMNIA Module 36: Anomaly Detection & Failure Classifier
Detects operational anomalies across metric streams (error rate spikes, queue backlogs,
latency degradation, memory growth) and maps signals to the unified Failure Taxonomy.
"""

import logging
from typing import Dict, Any, List, Optional
from observability.models import (
    OperationalMetric,
    FailureCategory,
    ComponentHealthStatus,
)
from observability.persistence import ObservabilityRepository

logger = logging.getLogger("Omnia.Observability.Detector")


class OperationalAnomalyDetector:
    """Detects metric anomalies and maps patterns into Failure Categories."""

    def __init__(self, repo: ObservabilityRepository):
        self.repo = repo
        # Thresholds
        self.error_rate_threshold = 0.05       # > 5% error rate is an anomaly
        self.queue_backlog_threshold = 100     # > 100 messages queued
        self.latency_p99_ms_threshold = 1000.0 # > 1000ms latency
        self.memory_mb_threshold = 2048.0      # > 2GB heap/RSS

    def analyze_metrics_for_component(self, component_id: str) -> List[Dict[str, Any]]:
        """Scans recent operational metrics for a component and detects anomalies."""
        metrics = self.repo.list_metrics(component_id=component_id, limit=50)
        anomalies = []

        for m in metrics:
            anomaly = None
            if "error_rate" in m.metric_name.lower() and m.value > self.error_rate_threshold:
                anomaly = {
                    "type": "HIGH_ERROR_RATE",
                    "metric_id": m.metric_id,
                    "value": m.value,
                    "threshold": self.error_rate_threshold,
                    "failure_category": FailureCategory.PERFORMANCE_DEGRADATION.value,
                    "message": f"Error rate {m.value * 100:.1f}% exceeds threshold {self.error_rate_threshold * 100:.1f}%",
                }
            elif "queue" in m.metric_name.lower() and m.value > self.queue_backlog_threshold:
                anomaly = {
                    "type": "QUEUE_BACKLOG",
                    "metric_id": m.metric_id,
                    "value": m.value,
                    "threshold": self.queue_backlog_threshold,
                    "failure_category": FailureCategory.EVENT_PIPELINE_FAILURE.value,
                    "message": f"Queue backlog {m.value} exceeds limit {self.queue_backlog_threshold}",
                }
            elif "latency" in m.metric_name.lower() and m.value > self.latency_p99_ms_threshold:
                anomaly = {
                    "type": "HIGH_LATENCY",
                    "metric_id": m.metric_id,
                    "value": m.value,
                    "threshold": self.latency_p99_ms_threshold,
                    "failure_category": FailureCategory.PERFORMANCE_DEGRADATION.value,
                    "message": f"Latency {m.value}ms exceeds p99 threshold {self.latency_p99_ms_threshold}ms",
                }
            elif "memory" in m.metric_name.lower() and m.value > self.memory_mb_threshold:
                anomaly = {
                    "type": "RESOURCE_EXHAUSTION",
                    "metric_id": m.metric_id,
                    "value": m.value,
                    "threshold": self.memory_mb_threshold,
                    "failure_category": FailureCategory.RESOURCE_EXHAUSTION.value,
                    "message": f"Memory usage {m.value}MB exceeds limit {self.memory_mb_threshold}MB",
                }

            if anomaly:
                anomalies.append(anomaly)

        return anomalies

    def classify_failure_signal(self, error_text: str, context: Optional[Dict[str, Any]] = None) -> FailureCategory:
        """Classifies raw errors into standard FailureCategory enum."""
        err = (error_text or "").lower()
        if "timeout" in err or "connection refused" in err or "econnrefused" in err:
            return FailureCategory.NETWORK_FAILURE
        elif "sqlite" in err or "database locked" in err or "db" in err or "integrityerror" in err:
            return FailureCategory.DATABASE_FAILURE
        elif "out of memory" in err or "oom" in err or "disk full" in err or "memory" in err:
            return FailureCategory.RESOURCE_EXHAUSTION
        elif "unauthorized" in err or "401" in err or "invalid token" in err or "expired" in err:
            return FailureCategory.AUTHENTICATION_FAILURE
        elif "forbidden" in err or "403" in err or "permission denied" in err:
            return FailureCategory.AUTHORIZATION_FAILURE
        elif "queue" in err or "event" in err or "broker" in err:
            return FailureCategory.EVENT_PIPELINE_FAILURE
        elif "crash" in err or "exit code" in err or "terminated" in err:
            return FailureCategory.PROCESS_FAILURE
        elif "dependency" in err or "upstream" in err:
            return FailureCategory.DEPENDENCY_FAILURE
        return FailureCategory.UNKNOWN_FAILURE
