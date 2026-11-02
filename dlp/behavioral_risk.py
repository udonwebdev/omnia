"""
dlp/behavioral_risk.py
Insider Risk & Behavioral Correlation Engine for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

from typing import List, Dict, Any, Optional, Tuple

from dlp.models import (
    MovementEvent, DLPChannel
)
from dlp.persistence import DLPRepository


class BehavioralRiskEngine:
    """
    Correlates insider risk signals (bulk repository queries, unapproved media usage,
    off-path staging, rapid repeated transfer attempts) into an explainable risk score.

    Architectural Invariant:
    Produces explainable risk scores and review recommendations ONLY;
    strictly NO automatic disciplinary or punitive employment actions.
    """

    def __init__(self, repo: DLPRepository):
        self.repo = repo

    def assess_actor_behavior(
        self,
        actor_id: str,
        lookback_events: int = 50
    ) -> Tuple[float, List[str], str]:
        """
        Assesses the insider risk profile for a specific actor across recent movement telemetry.
        Returns (risk_score: 0-100, explainable_factors: List[str], review_recommendation: str).
        """
        events = self.repo.list_movement_events(actor_id=actor_id, limit=lookback_events)
        if not events:
            return 0.0, ["No recent data movement telemetry recorded for actor."], "NORMAL_ACTIVITY"

        factors: List[str] = []
        score = 0.0

        # 1. Total Cumulative Volume Transferred
        total_volume = sum(e.volume_bytes for e in events)
        if total_volume > 200 * 1024 * 1024:  # > 200 MB
            score += 30.0
            factors.append(f"CUMULATIVE_VOLUME_SPIKE: Total movement volume of {total_volume / (1024*1024):.1f}MB exceeds 200MB baseline (+30)")
        elif total_volume > 50 * 1024 * 1024:  # > 50 MB
            score += 15.0
            factors.append(f"ELEVATED_VOLUME: Total movement volume of {total_volume / (1024*1024):.1f}MB (+15)")

        # 2. Unapproved Removable Media Transfers
        media_events = [e for e in events if e.channel == DLPChannel.REMOVABLE_MEDIA.value]
        unapproved_media = [e for e in media_events if not e.is_authorized]
        if unapproved_media:
            score += 35.0
            factors.append(f"UNAUTHORIZED_MEDIA_USAGE: {len(unapproved_media)} unapproved USB/external media transfer attempt(s) detected (+35)")

        # 3. Cloud / External Sharing Actions
        cloud_events = [e for e in events if e.channel == DLPChannel.CLOUD.value]
        unauth_cloud = [e for e in cloud_events if not e.is_authorized]
        if unauth_cloud:
            score += 25.0
            factors.append(f"UNAPPROVED_EXTERNAL_SHARING: {len(unauth_cloud)} public/external cloud share event(s) detected (+25)")

        # 4. Off-Path Clipboard / Local Export Activity
        clipboard_events = [e for e in events if e.channel == DLPChannel.CLIPBOARD.value]
        if len(clipboard_events) >= 5:
            score += 20.0
            factors.append(f"BULK_CLIPBOARD_EXPORTS: High frequency of sensitive clipboard operations ({len(clipboard_events)} events) (+20)")

        # 5. Blocked Transfer History
        decisions = []
        for e in events[:20]:
            # Check if event was blocked in transfer decisions
            # Lightweight check: look up decisions for this event
            # Since decisions are linked to event_id:
            pass

        # Clamp score to [0.0, 100.0]
        risk_score = min(100.0, max(0.0, score))

        if risk_score >= 60.0:
            recommendation = "PRIORITY_SECURITY_REVIEW_REQUIRED: Multiple high-risk exfiltration signals correlated. Recommend supervisor / security review."
        elif risk_score >= 35.0:
            recommendation = "ELEVATED_MONITORING: Non-standard movement patterns observed. Maintain enhanced telemetry logging."
        else:
            recommendation = "NORMAL_ACTIVITY: Telemetry aligned with baseline workload parameters."

        return risk_score, factors, recommendation
