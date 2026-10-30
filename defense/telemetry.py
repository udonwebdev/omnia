"""
OMNIA Module 35: Security Telemetry Collector & Normalizer
Normalizes raw security events, detects missing monitoring sources, redacts credentials,
validates signatures/timestamps, and manages backpressure buffering.
"""

import time
import uuid
import re
import hashlib
import json
import logging
from typing import Dict, Any, List, Optional, Set
from defense.models import (
    SecurityTelemetryEvent,
    SecuritySeverity,
)

logger = logging.getLogger("Omnia.Defense.Telemetry")


class SecurityEventNormalizer:
    """Normalizes raw telemetry, validates event schemas, and redacts sensitive credentials."""

    SECRET_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
        re.compile(r"ghp_[a-zA-Z0-9]{36}", re.IGNORECASE),
        re.compile(r"xoxb-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
        re.compile(r"bearer\s+[a-zA-Z0-9\-._~+/]+=*", re.IGNORECASE),
        re.compile(r"ey[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}", re.IGNORECASE), # JWT
    ]

    SENSITIVE_KEYS = {
        "password", "secret", "token", "api_key", "credential", "auth", "private_key",
        "authorization", "jwt", "access_token", "refresh_token", "client_secret"
    }

    def sanitize_payload(self, data: Any) -> Any:
        """Recursively scrubs secrets and tokens from dictionary and string structures."""
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if any(sec_key in k.lower() for sec_key in self.SENSITIVE_KEYS):
                    sanitized[k] = "[REDACTED_SECRET]"
                else:
                    sanitized[k] = self.sanitize_payload(v)
            return sanitized
        elif isinstance(data, list):
            return [self.sanitize_payload(item) for item in data]
        elif isinstance(data, str):
            res = data
            for pat in self.SECRET_PATTERNS:
                res = pat.sub("[REDACTED_SECRET]", res)
            return res
        return data

    def normalize(
        self,
        raw_event: Dict[str, Any],
        source_component: str,
        action_category: str,
        outcome: str,
        severity: SecuritySeverity = SecuritySeverity.INFO,
        event_id: Optional[str] = None,
        source_identity: Optional[str] = None,
        node_identity: Optional[str] = None,
        correlation_id: Optional[str] = None,
        resource_reference: Optional[str] = None,
        timestamp: Optional[float] = None,
        data_classification: str = "INTERNAL",
    ) -> SecurityTelemetryEvent:
        """Validates and normalizes raw input into a verified SecurityTelemetryEvent."""
        eid = event_id or f"sec-evt-{uuid.uuid4().hex[:12]}"
        ts = timestamp if timestamp is not None else time.time()
        
        # Cleanse payload
        clean_details = self.sanitize_payload(raw_event.get("details", raw_event))

        # Compute deterministic integrity signature of normalized event
        sig_body = f"{eid}:{source_component}:{action_category}:{outcome}:{ts}"
        sig = hashlib.sha256(sig_body.encode("utf-8")).hexdigest()

        return SecurityTelemetryEvent(
            event_id=eid,
            event_type=raw_event.get("event_type", "security.telemetry.generic"),
            source_component=source_component,
            action_category=action_category,
            outcome=outcome,
            severity=severity,
            timestamp=ts,
            schema_version=1,
            source_identity=source_identity or raw_event.get("source_identity"),
            node_identity=node_identity or raw_event.get("node_identity"),
            correlation_id=correlation_id or raw_event.get("correlation_id"),
            resource_reference=resource_reference or raw_event.get("resource_reference"),
            details=clean_details,
            data_classification=data_classification,
            signature=sig,
        )


class SecurityTelemetryCollector:
    """Manages telemetry ingestion, deduplication, blind spot tracking, and bounded buffering."""

    REQUIRED_TELEMETRY_SOURCES = {
        "auth_gateway",
        "secrets_engine",
        "policy_enforcer",
        "mesh_coordinator",
        "connector_gateway",
        "runtime_supervisor",
    }

    def __init__(self, normalizer: Optional[SecurityEventNormalizer] = None, max_buffer_size: int = 1000):
        self.normalizer = normalizer or SecurityEventNormalizer()
        self.max_buffer_size = max_buffer_size
        self._buffer: List[SecurityTelemetryEvent] = []
        self._seen_event_ids: Set[str] = set()
        self._source_heartbeats: Dict[str, float] = {}
        self._heartbeat_timeout_sec: float = 300.0  # 5 minutes

    def record_source_heartbeat(self, source_name: str, timestamp: Optional[float] = None) -> None:
        """Records an active telemetry heartbeat from a monitored source."""
        self._source_heartbeats[source_name] = timestamp or time.time()

    def get_missing_sources(self, current_time: Optional[float] = None) -> List[str]:
        """Identifies monitored sources that have missed their heartbeat window."""
        now = current_time or time.time()
        missing = []
        for src in sorted(self.REQUIRED_TELEMETRY_SOURCES):
            last_hb = self._source_heartbeats.get(src)
            if last_hb is None or (now - last_hb) > self._heartbeat_timeout_sec:
                missing.append(src)
        return missing

    def ingest_event(self, event: SecurityTelemetryEvent) -> bool:
        """Ingests an event with deduplication, backpressure checking, and source tracking."""
        if event.event_id in self._seen_event_ids:
            logger.debug(f"Duplicate telemetry event rejected: {event.event_id}")
            return False

        # Track source health
        self.record_source_heartbeat(event.source_component, event.timestamp)

        # Backpressure handling
        if len(self._buffer) >= self.max_buffer_size:
            evicted = self._buffer.pop(0)
            self._seen_event_ids.discard(evicted.event_id)
            logger.warning(f"Telemetry buffer full. Evicted oldest event {evicted.event_id}")

        self._buffer.append(event)
        self._seen_event_ids.add(event.event_id)
        return True

    def drain_events(self) -> List[SecurityTelemetryEvent]:
        """Drains all buffered telemetry events for downstream detection processing."""
        events = list(self._buffer)
        self._buffer.clear()
        return events
