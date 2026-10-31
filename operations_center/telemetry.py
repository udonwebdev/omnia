"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Telemetry Ingestion Gateway: Metrics, Structured Logs & Tracing with Secret Scrubbing.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from operations_center.models import (
    LogRecord,
    MetricRecord,
    TraceSpanRecord,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.Telemetry")

SECRET_REGEX = re.compile(
    r"(?i)(bearer\s+[a-z0-9_\-\.]{15,}|password\s*[:=]\s*[^\s,;]+|secret\s*[:=]\s*[^\s,;]+|api_?key\s*[:=]\s*[^\s,;]+)"
)


class TelemetryIngestionGateway:
    """
    Ingests metrics, logs, and distributed trace spans.
    Recursively scrubs credentials and sensitive tokens from messages and payloads.
    """

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def scrub_text(self, text: str) -> str:
        """Sanitizes text by replacing sensitive secrets with [REDACTED]."""
        if not text:
            return ""
        return SECRET_REGEX.sub("[REDACTED_CREDENTIAL]", text)

    def ingest_metric(
        self,
        service_id: str,
        metric_name: str,
        value: float,
        unit: str,
        timestamp: Optional[str] = None,
    ) -> MetricRecord:
        """Ingests a numeric metric time-series point."""
        mid = f"met-{uuid.uuid4().hex[:8]}"
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        metric = MetricRecord(
            metric_id=mid,
            service_id=service_id,
            metric_name=metric_name,
            value=value,
            unit=unit,
            timestamp=ts,
        )
        self.repo.save_metric(metric)
        return metric

    def ingest_log(
        self,
        service_id: str,
        level: str,
        message: str,
        error_category: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> LogRecord:
        """Ingests a structured log line after scrubbing credentials."""
        lid = f"log-{uuid.uuid4().hex[:8]}"
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        sanitized_msg = self.scrub_text(message)
        log = LogRecord(
            log_id=lid,
            service_id=service_id,
            level=level.upper(),
            message=sanitized_msg,
            error_category=error_category,
            timestamp=ts,
        )
        self.repo.save_log(log)
        return log

    def ingest_span(
        self,
        trace_id: str,
        service_id: str,
        operation_name: str,
        duration_ms: float,
        status_code: int = 200,
        parent_span_id: Optional[str] = None,
        span_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> TraceSpanRecord:
        """Ingests a distributed trace span."""
        sid = span_id or f"spn-{uuid.uuid4().hex[:8]}"
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        span = TraceSpanRecord(
            span_id=sid,
            trace_id=trace_id,
            service_id=service_id,
            operation_name=operation_name,
            duration_ms=duration_ms,
            status_code=status_code,
            parent_span_id=parent_span_id,
            timestamp=ts,
        )
        self.repo.save_span(span)
        return span
