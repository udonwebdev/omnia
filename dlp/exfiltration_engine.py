"""
dlp/exfiltration_engine.py
Exfiltration Detection Engine for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import uuid
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from dlp.models import (
    ExfiltrationAlert, DLPSeverity, MovementEvent, SensitiveFinding,
    DLPChannel, SensitivityTier
)
from dlp.persistence import DLPRepository


class ExfiltrationDetectionEngine:
    """
    Contextual exfiltration pattern analysis:
    - Multi-factor risk scoring (0-100)
    - Volume surge anomalies
    - Unusual / untrusted destinations
    - Off-hours transfer detection
    - Bulk staging and archive compression (.zip, .7z, .tar.gz)
    - Unapproved removable media transfers
    - Explainable risk attribution
    """

    SUSPICIOUS_DOMAINS = [
        "pastebin.com", "anonfiles.com", "mega.nz", "temp.sh",
        "transfer.sh", "filebin.net", "gofile.io", "discordapp.com/api/webhooks",
        "api.telegram.org", "wetransfer.com", "dropmefiles.com"
    ]

    ARCHIVE_EXTENSIONS = [
        ".zip", ".tar.gz", ".tgz", ".7z", ".rar", ".bz2", ".xz", ".iso", ".enc"
    ]

    def __init__(self, repo: DLPRepository):
        self.repo = repo

    def evaluate_movement_risk(
        self,
        event: MovementEvent,
        findings: Optional[List[SensitiveFinding]] = None,
        custom_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, List[str], DLPSeverity, Optional[ExfiltrationAlert]]:
        """
        Analyzes a data movement event and any associated sensitive findings.
        Returns (risk_score, anomaly_indicators, severity, alert_or_none).
        """
        findings_list = findings or []
        context = custom_context or {}
        indicators: List[str] = []
        score = 0.0

        # 1. Volume Surge Factor
        vol = event.volume_bytes
        if vol >= 100 * 1024 * 1024:  # >= 100 MB
            score += 35.0
            indicators.append(f"CRITICAL_VOLUME_ANOMALY: Transfer size of {vol / (1024*1024):.1f}MB exceeds 100MB threshold (+35)")
        elif vol >= 25 * 1024 * 1024:  # >= 25 MB
            score += 25.0
            indicators.append(f"HIGH_VOLUME_ANOMALY: Transfer size of {vol / (1024*1024):.1f}MB exceeds 25MB baseline (+25)")
        elif vol >= 5 * 1024 * 1024:   # >= 5 MB
            score += 15.0
            indicators.append(f"ELEVATED_VOLUME: Transfer size of {vol / (1024*1024):.1f}MB exceeds normal profile (+15)")

        # 2. Destination Anomaly Factor
        dest = event.destination_location.lower()
        if any(susp in dest for susp in self.SUSPICIOUS_DOMAINS):
            score += 35.0
            indicators.append(f"UNAPPROVED_DESTINATION: Destination '{event.destination_location}' matches high-risk exfiltration endpoint (+35)")
        elif dest.startswith("http://") or (dest.replace(".", "").isdigit()):
            score += 20.0
            indicators.append(f"UNENCRYPTED_OR_DIRECT_IP_DESTINATION: Raw IP or plaintext destination '{dest}' (+20)")

        # 3. Off-Hours Temporal Anomaly Factor
        event_time = datetime.fromtimestamp(event.timestamp, tz=timezone.utc)
        hour = event_time.hour
        weekday = event_time.weekday()  # 5 = Saturday, 6 = Sunday
        is_weekend = weekday >= 5
        is_night = hour < 6 or hour >= 21

        if is_weekend or is_night:
            score += 20.0
            timing_desc = "Weekend" if is_weekend else "Off-hours (21:00-06:00 UTC)"
            indicators.append(f"TEMPORAL_ANOMALY: Movement occurred during {timing_desc} [Hour: {hour:02d}:00 UTC] (+20)")

        # 4. Compression / Staging Factor
        src = event.source_location.lower()
        if any(src.endswith(ext) or dest.endswith(ext) for ext in self.ARCHIVE_EXTENSIONS):
            score += 25.0
            indicators.append("STAGING_COMPRESSION: Transfer payload contains compressed archive file (.zip/.7z/.tar.gz) (+25)")
        if "temp" in src or "tmp" in src or "appdata" in src:
            score += 15.0
            indicators.append("TEMPORARY_STAGING_PATH: Source location indicates staging in temporary directory (+15)")

        # 5. Removable Media (USB) Factor
        if event.channel == DLPChannel.REMOVABLE_MEDIA.value:
            if not event.is_authorized:
                score += 30.0
                indicators.append("UNAUTHORIZED_REMOVABLE_MEDIA: Transfer to unapproved USB/external storage device (+30)")
            else:
                score += 10.0
                indicators.append("REMOVABLE_MEDIA_USAGE: Transfer to approved external storage media (+10)")

        # 6. Sensitive Finding Severity Density Factor
        if findings_list:
            high_sev_count = sum(
                1 for f in findings_list
                if f.sensitivity_tier in (SensitivityTier.HIGHLY_RESTRICTED.value, SensitivityTier.RESTRICTED.value)
            )
            if high_sev_count > 0:
                score += 30.0
                indicators.append(f"RESTRICTED_DATA_EXPOSURE: Payload contains {high_sev_count} highly restricted/restricted data findings (+30)")
            else:
                score += 15.0
                indicators.append(f"SENSITIVE_FINDINGS_PRESENT: Payload contains {len(findings_list)} confidential data findings (+15)")

        # 7. Recent Rapid Movement Burst Factor
        recent_events = self.repo.list_movement_events(actor_id=event.actor_id, limit=10)
        burst_count = sum(1 for e in recent_events if abs(event.timestamp - e.timestamp) <= 300)
        if burst_count >= 5:
            score += 20.0
            indicators.append(f"RAPID_TRANSFER_BURST: {burst_count} movement events recorded within 5-minute window (+20)")

        # Clamp score to [0.0, 100.0]
        risk_score = min(100.0, max(0.0, score))

        # Severity mapping
        if risk_score >= 80.0:
            severity = DLPSeverity.CRITICAL
        elif risk_score >= 60.0:
            severity = DLPSeverity.HIGH
        elif risk_score >= 40.0:
            severity = DLPSeverity.MEDIUM
        else:
            severity = DLPSeverity.LOW

        # Confidence calibrated by number of correlated signals
        confidence = min(0.99, 0.60 + 0.08 * len(indicators))

        alert = None
        if risk_score >= 40.0:
            alert = ExfiltrationAlert(
                alert_id=f"alt_{uuid.uuid4().hex[:12]}",
                title=f"Exfiltration Risk [{severity.value}]: {indicators[0] if indicators else 'Anomalous Transfer'}",
                severity=severity.value,
                risk_score=risk_score,
                confidence=confidence,
                anomaly_indicators=indicators,
                actor_id=event.actor_id,
                destination=event.destination_location,
                status="OPEN",
                timestamp=time.time(),
            )
            self.repo.save_exfiltration_alert(alert)

        return risk_score, indicators, severity, alert
