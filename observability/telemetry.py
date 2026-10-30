"""
OMNIA Module 36: Operational Telemetry Aggregator
Aggregates metrics, scrubs credentials from structured logs, and tracks distributed trace spans.
"""

import time
import uuid
import re
import logging
from typing import Dict, Any, List, Optional
from observability.models import OperationalMetric, TraceSpan

logger = logging.getLogger("Omnia.Observability.Telemetry")


class OperationalTelemetryCollector:
    """Collects and normalizes operational signals across memory, queues, latency, and traces."""

    SECRET_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
        re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE),
        re.compile(r"xoxb-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
        re.compile(r"bearer\s+[a-zA-Z0-9\-._~+/]+=*", re.IGNORECASE),
        re.compile(r"ey[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}", re.IGNORECASE),
    ]

    def __init__(self):
        self._metrics_buffer: List[OperationalMetric] = []
        self._active_spans: Dict[str, TraceSpan] = {}
        self._completed_spans: List[TraceSpan] = []

    def sanitize_log_text(self, text: str) -> str:
        """Recursively scrubs secrets from diagnostic log entries."""
        scrubbed = text
        for pat in self.SECRET_PATTERNS:
            scrubbed = pat.sub("[REDACTED_SECRET]", scrubbed)
        return scrubbed

    def record_metric(
        self,
        component_id: str,
        metric_name: str,
        value: float,
        unit: str,
        labels: Optional[Dict[str, str]] = None,
        timestamp: Optional[float] = None
    ) -> OperationalMetric:
        """Records a single operational metric observation."""
        metric = OperationalMetric(
            metric_id=f"metric-{uuid.uuid4().hex[:8]}",
            component_id=component_id,
            metric_name=metric_name,
            value=float(value),
            unit=unit,
            timestamp=timestamp or time.time(),
            labels=labels or {},
        )
        self._metrics_buffer.append(metric)
        return metric

    def start_trace_span(
        self,
        operation_name: str,
        component_id: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> TraceSpan:
        """Starts a new distributed trace span."""
        tid = trace_id or f"trace-{uuid.uuid4().hex[:12]}"
        sid = f"span-{uuid.uuid4().hex[:8]}"
        span = TraceSpan(
            trace_id=tid,
            span_id=sid,
            operation_name=operation_name,
            component_id=component_id,
            parent_span_id=parent_span_id,
            start_time=time.time(),
            tags=tags or {},
        )
        self._active_spans[sid] = span
        return span

    def finish_trace_span(
        self,
        span_id: str,
        status: str = "OK",
        error: Optional[str] = None
    ) -> Optional[TraceSpan]:
        """Finishes an active trace span, calculating its duration."""
        span = self._active_spans.pop(span_id, None)
        if span:
            span.finish(status=status, error=self.sanitize_log_text(error) if error else None)
            self._completed_spans.append(span)
            return span
        return None
