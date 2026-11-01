"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Temporal Event Correlation Engine - correlation.py
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from secops.models import CorrelationGraph, SecurityAlert, SecurityEvent
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.Correlation")


class EventCorrelationEngine:
    """
    Correlates security events and alerts across sliding time windows and shared entities.
    Identifies multi-stage attack patterns (e.g. Brute Force -> Admin Escalation -> Mass Data Exfiltration).
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def correlate_alerts_by_entity(
        self,
        alerts: List[SecurityAlert],
        entity_id: str,
        correlation_title: str = "Correlated Suspicious Activity",
    ) -> Optional[CorrelationGraph]:
        # Filter alerts involving this entity (actor or asset)
        relevant_alerts = [
            a for a in alerts if a.actor_id == entity_id or a.asset_id == entity_id
        ]
        if len(relevant_alerts) < 2:
            return None

        cid = f"corr-{uuid.uuid4().hex[:8]}"
        all_event_ids: List[str] = []
        sequence: List[Dict[str, Any]] = []

        for idx, a in enumerate(relevant_alerts, start=1):
            all_event_ids.extend(a.contributing_event_ids)
            sequence.append({
                "step": idx,
                "alert_id": a.alert_id,
                "title": a.title,
                "severity": a.severity.value,
                "timestamp": a.created_at,
            })

        # Multi-alert correlation boosts confidence
        confidence = min(0.99, 0.65 + (len(relevant_alerts) * 0.1))

        graph = CorrelationGraph(
            correlation_id=cid,
            correlation_title=f"{correlation_title} on {entity_id}",
            affected_entities=[entity_id],
            participating_alert_ids=[a.alert_id for a in relevant_alerts],
            participating_event_ids=list(set(all_event_ids)),
            attack_chain_sequence=sequence,
            correlation_confidence=confidence,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        self.repo.save_correlation_graph(graph)
        logger.info(
            f"Synthesized correlation graph {cid}: {len(relevant_alerts)} alerts chained on {entity_id}."
        )
        return graph
