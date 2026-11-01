"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Telemetry Source Registry - sources.py
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from secops.models import TelemetrySource
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.Sources")


class TelemetrySourceRegistry:
    """
    Maintains inventory of authorized telemetry feeds across Identity, Cloud, API, and Workloads.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def register_source(
        self,
        provider: str,
        environment: str,
        collection_method: str,
        auth_method: str,
        asset_scope: Optional[List[str]] = None,
        event_types_supported: Optional[List[str]] = None,
        retention_days: int = 90,
        coverage_limitations: Optional[List[str]] = None,
        source_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TelemetrySource:
        sid = source_id or f"src-{uuid.uuid4().hex[:8]}"
        src = TelemetrySource(
            source_id=sid,
            provider=provider,
            environment=environment,
            collection_method=collection_method,
            auth_method=auth_method,
            asset_scope=asset_scope or [],
            event_types_supported=event_types_supported or [],
            health_status="HEALTHY",
            retention_days=retention_days,
            coverage_limitations=coverage_limitations or [],
            registered_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )
        self.repo.save_source(src)
        logger.info(f"Registered telemetry source {sid} ({provider} - {environment})")
        return src

    def update_source_health(self, source_id: str, is_healthy: bool, note: Optional[str] = None) -> None:
        src = self.repo.get_source(source_id)
        if not src:
            raise ValueError(f"Telemetry source {source_id} not found.")
        src.health_status = "HEALTHY" if is_healthy else "UNAVAILABLE"
        if note:
            src.metadata["health_note"] = note
        self.repo.save_source(src)

    def mark_successful_ingestion(self, source_id: str) -> None:
        src = self.repo.get_source(source_id)
        if src:
            src.last_successful_ingestion = datetime.now(timezone.utc).isoformat()
            self.repo.save_source(src)
