"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Scoped Threat Hunting Engine - threat_hunting.py
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from secops.models import SecurityEvent
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.ThreatHunting")


class ScopedThreatHunter:
    """
    Read-only, parameterized hunting interface over authorized telemetry.
    Strictly forbids command injection, active network probing, and out-of-scope targets.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def hunt_telemetry(
        self,
        analyst_operator: str,
        asset_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[SecurityEvent]:
        # Enforce maximum safety limit
        safe_limit = max(1, min(limit, 500))

        events = self.repo.query_events(
            event_type=event_type,
            asset_id=asset_id,
            actor_id=actor_id,
            limit=safe_limit,
        )

        logger.info(
            f"Analyst {analyst_operator} executed threat hunt (Asset: {asset_id}, Actor: {actor_id}, "
            f"Type: {event_type}) - Retrieved {len(events)} events."
        )
        return events
