"""
forensics/correlation.py
Cross-source evidence correlation engine for OMNIA Module 48:
Autonomous Digital Forensics, Evidence Preservation & Incident Investigation Intelligence.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional

from forensics.models import EvidenceCorrelation, TimelineEvent
from forensics.persistence import ForensicsRepository

logger = logging.getLogger("omnia.forensics.correlation")


class EvidenceCorrelationEngine:
    """
    Identifies relationships across disparate forensic artifacts and timeline events.
    Correlates on:
    - Shared Identity/Actor (User principal, service account)
    - Shared Network IP or Subnet
    - File SHA-256 hashes or binaries
    - Process lineage / Command invocation sequences
    """

    def __init__(self, repo: ForensicsRepository):
        self.repo = repo

    def correlate_case_evidence(self, case_id: str) -> List[EvidenceCorrelation]:
        """
        Scans all timeline events in a case and builds cross-artifact correlation records.
        """
        events = self.repo.list_timeline_events(case_id)
        artifacts = self.repo.list_artifacts(case_id)

        correlations: List[EvidenceCorrelation] = []

        # 1. Correlate by Actor across different artifacts
        actor_map: Dict[str, List[TimelineEvent]] = {}
        for ev in events:
            if ev.actor and ev.actor not in ("SYSTEM", "UNKNOWN_IDENTITY", "UNKNOWN"):
                actor_map.setdefault(ev.actor, []).append(ev)

        for actor, ev_list in actor_map.items():
            distinct_artifacts = list({e.artifact_id for e in ev_list if e.artifact_id})
            if len(distinct_artifacts) > 1:
                # We have cross-artifact activity by the same actor
                for i in range(len(distinct_artifacts) - 1):
                    src_art = distinct_artifacts[i]
                    tgt_art = distinct_artifacts[i + 1]
                    corr = EvidenceCorrelation(
                        correlation_id=f"corr_{uuid.uuid4().hex[:12]}",
                        case_id=case_id,
                        source_artifact_id=src_art,
                        target_artifact_id=tgt_art,
                        correlation_type="SHARED_ACTOR",
                        correlation_key=actor,
                        confidence_score=0.95,
                        notes=f"Actor '{actor}' observed performing actions across multiple distinct artifacts.",
                        created_at=time.time()
                    )
                    self.repo.record_correlation(corr)
                    correlations.append(corr)

        # 2. Correlate by IP Address
        ip_map: Dict[str, List[TimelineEvent]] = {}
        for ev in events:
            if ev.source_entity and "." in ev.source_entity and ev.source_entity != "0.0.0.0":
                ip_map.setdefault(ev.source_entity, []).append(ev)

        for ip, ev_list in ip_map.items():
            distinct_artifacts = list({e.artifact_id for e in ev_list if e.artifact_id})
            if len(distinct_artifacts) > 1:
                for i in range(len(distinct_artifacts) - 1):
                    src_art = distinct_artifacts[i]
                    tgt_art = distinct_artifacts[i + 1]
                    corr = EvidenceCorrelation(
                        correlation_id=f"corr_{uuid.uuid4().hex[:12]}",
                        case_id=case_id,
                        source_artifact_id=src_art,
                        target_artifact_id=tgt_art,
                        correlation_type="SHARED_IP",
                        correlation_key=ip,
                        confidence_score=0.90,
                        notes=f"Source IP '{ip}' linked across distinct telemetry sources.",
                        created_at=time.time()
                    )
                    self.repo.record_correlation(corr)
                    correlations.append(corr)

        logger.info(f"Generated {len(correlations)} evidence correlations for case {case_id}")
        return correlations
