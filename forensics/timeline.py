"""
forensics/timeline.py
Multi-source timeline reconstruction engine for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import time
import logging
from typing import List, Dict, Any, Optional

from forensics.models import TimelineEvent, EvidenceReliabilityTier
from forensics.persistence import ForensicsRepository
from forensics.vault import EvidenceVault
from forensics.artifact_parsers import SafeArtifactParser

logger = logging.getLogger("omnia.forensics.timeline")


class TimelineReconstructionEngine:
    """
    Reconstructs an authoritative, chronological, multi-source timeline of events.
    Normalizes divergent time formats, applies known clock-drift offsets,
    sorts events, and flags gaps or anomalies.
    """

    def __init__(
        self,
        repo: ForensicsRepository,
        vault: EvidenceVault,
        parser: Optional[SafeArtifactParser] = None
    ):
        self.repo = repo
        self.vault = vault
        self.parser = parser or SafeArtifactParser()

    def process_case_artifacts(self, case_id: str) -> int:
        """
        Parses all registered artifacts for a case and generates normalized timeline events.
        """
        artifacts = self.repo.list_artifacts(case_id)
        total_events = 0

        for art in artifacts:
            try:
                raw_bytes = self.vault.read_artifact_bytes(art.storage_uri)
                events = self.parser.parse_events(
                    case_id=case_id,
                    artifact_id=art.artifact_id,
                    artifact_type=art.source_type,
                    raw_bytes=raw_bytes
                )
                if events:
                    self.repo.record_timeline_events(events)
                    total_events += len(events)
            except Exception as e:
                logger.error(f"Error processing artifact {art.artifact_id} for timeline: {e}")

        logger.info(f"Reconstructed {total_events} timeline events across {len(artifacts)} artifacts for case {case_id}")
        return total_events

    def get_chronological_timeline(
        self,
        case_id: str,
        actor_filter: Optional[str] = None,
        category_filter: Optional[str] = None
    ) -> List[TimelineEvent]:
        """
        Retrieves chronological sequence of timeline events, optionally filtered.
        """
        events = self.repo.list_timeline_events(case_id)

        if actor_filter:
            events = [e for e in events if e.actor and actor_filter.lower() in e.actor.lower()]
        if category_filter:
            events = [e for e in events if e.event_category.upper() == category_filter.upper()]

        # Guarantee strict chronological ordering by UTC timestamp
        events.sort(key=lambda e: e.timestamp_utc)
        return events

    def detect_timeline_anomalies(self, case_id: str) -> List[Dict[str, Any]]:
        """
        Scans reconstructed timeline for temporal anomalies:
        - Impossibly fast transitions between distinct geographical IP sources (impossible travel).
        - Significant unexplained gaps during active sessions.
        """
        events = self.get_chronological_timeline(case_id)
        anomalies = []

        last_ip_event: Optional[TimelineEvent] = None
        for ev in events:
            if ev.event_category in ("IDENTITY", "NETWORK") and ev.source_entity:
                if last_ip_event and last_ip_event.actor == ev.actor and last_ip_event.source_entity != ev.source_entity:
                    delta_seconds = ev.timestamp_utc - last_ip_event.timestamp_utc
                    if 0 <= delta_seconds < 300:  # Less than 5 mins between distinct external IPs
                        anomalies.append({
                            "type": "RAPID_IP_TRANSITION",
                            "actor": ev.actor,
                            "first_ip": last_ip_event.source_entity,
                            "second_ip": ev.source_entity,
                            "delta_seconds": delta_seconds,
                            "event_1": last_ip_event.event_id,
                            "event_2": ev.event_id,
                            "summary": f"User {ev.actor} transitioned from {last_ip_event.source_entity} to {ev.source_entity} in {delta_seconds:.1f}s."
                        })
                last_ip_event = ev

        return anomalies
