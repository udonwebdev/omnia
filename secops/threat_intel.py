"""
OMNIA Module 47: Autonomous Threat Detection, Behavioral Analytics & Real-Time Security Operations Intelligence
Threat Intelligence Enricher - threat_intel.py
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from secops.models import IndicatorType, ThreatIntelIndicator
from secops.persistence import SecOpsRepository

logger = logging.getLogger("Omnia.SecOps.ThreatIntel")


class ThreatIntelEnricher:
    """
    Manages provider-neutral threat intelligence indicators (IPs, Domains, File Hashes, CVEs)
    with strict provenance tracking and non-authoritative containment boundaries.
    """

    def __init__(self, repository: Optional[SecOpsRepository] = None):
        self.repo = repository or SecOpsRepository()

    def record_indicator(
        self,
        indicator_type: IndicatorType,
        indicator_value: str,
        source_provider: str,
        threat_actor: Optional[str] = None,
        campaign: Optional[str] = None,
        confidence: float = 0.85,
        mitre_techniques: Optional[List[str]] = None,
        expires_at: Optional[str] = None,
    ) -> ThreatIntelIndicator:
        iid = f"ind-{uuid.uuid4().hex[:8]}"
        ind = ThreatIntelIndicator(
            indicator_id=iid,
            indicator_type=indicator_type,
            indicator_value=indicator_value,
            source_provider=source_provider,
            published_at=datetime.now(timezone.utc).isoformat(),
            threat_actor=threat_actor,
            campaign=campaign,
            confidence=confidence,
            mitre_techniques=mitre_techniques or [],
            expires_at=expires_at,
            is_active=True,
        )
        self.repo.save_indicator(ind)
        logger.info(f"Recorded threat intelligence indicator {iid} ({indicator_type.value}: {indicator_value})")
        return ind

    def lookup_indicator(self, indicator_type: str, indicator_value: str) -> Optional[ThreatIntelIndicator]:
        return self.repo.get_indicator(indicator_type, indicator_value)
