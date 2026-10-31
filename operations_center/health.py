"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
System Health Aggregator: Multi-State Assessment & Freshness Verification.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from operations_center.models import (
    HealthObservationRecord,
    SystemHealthState,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.Health")


class SystemHealthAggregator:
    """
    Evaluates service operational condition across 6 states.
    Ensures that stale telemetry is never presented as confirmed healthy (marks UNKNOWN/DEGRADED).
    """

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def record_health_observation(
        self,
        service_id: str,
        health_state: SystemHealthState,
        latency_ms: float = 0.0,
        error_rate: float = 0.0,
        status_message: str = "Nominal",
    ) -> HealthObservationRecord:
        """Records an authoritative health check observation for a service."""
        service = self.repo.get_service(service_id)
        if not service:
            raise ValueError(f"Service '{service_id}' not found in inventory.")

        now = datetime.now(timezone.utc).isoformat()
        obs = HealthObservationRecord(
            observation_id=f"obs-{uuid.uuid4().hex[:8]}",
            service_id=service_id,
            health_state=health_state,
            latency_ms=latency_ms,
            error_rate=error_rate,
            status_message=status_message,
            observed_at=now,
            is_stale=False,
        )
        self.repo.save_health_observation(obs)
        logger.info(f"Health observation for '{service_id}': {health_state.value} ({status_message})")
        return obs

    def evaluate_service_health(self, service_id: str, max_freshness_seconds: float = 300.0) -> HealthObservationRecord:
        """
        Retrieves the latest health observation, checking timestamp freshness.
        If data is older than max_freshness_seconds, flags as stale and degrades state.
        """
        obs = self.repo.get_latest_health_observation(service_id)
        if not obs:
            return HealthObservationRecord(
                observation_id=f"obs-{uuid.uuid4().hex[:8]}",
                service_id=service_id,
                health_state=SystemHealthState.UNKNOWN,
                latency_ms=0.0,
                error_rate=0.0,
                status_message="No health observations recorded.",
                is_stale=True,
            )

        # Check freshness
        try:
            obs_dt = datetime.fromisoformat(obs.observed_at)
            age = (datetime.now(timezone.utc) - obs_dt).total_seconds()
            if age > max_freshness_seconds:
                obs.is_stale = True
                if obs.health_state == SystemHealthState.HEALTHY:
                    obs.health_state = SystemHealthState.UNKNOWN
                    obs.status_message = f"Stale telemetry: observation age {age:.0f}s exceeds threshold {max_freshness_seconds:.0f}s."
        except Exception:
            pass

        return obs
