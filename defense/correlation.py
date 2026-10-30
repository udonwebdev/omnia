"""
OMNIA Module 35: Threat Correlation & Attack Chain Synthesis Engine
Connects related security alerts across identity, session, node, and temporal windows.
Distinguishes directly observed behavior from correlated hypotheses.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict

from defense.models import (
    ThreatAlert,
    SecurityIncident,
    ThreatClassification,
    SecuritySeverity,
    IncidentStatus,
)

logger = logging.getLogger("Omnia.Defense.Correlation")


class ThreatCorrelationEngine:
    """Correlates multiple security alerts across temporal windows and creates incidents."""

    def __init__(self, correlation_window_sec: float = 300.0):
        self.correlation_window_sec = correlation_window_sec
        # Maps correlation key (e.g. source_identity or node_identity) to active alert history
        self._alert_buckets: Dict[str, List[ThreatAlert]] = defaultdict(list)

    def _get_correlation_key(self, alert: ThreatAlert) -> str:
        """Determines the primary grouping key for multi-stage correlation."""
        if alert.source_identity:
            return f"ident:{alert.source_identity}"
        elif alert.node_identity:
            return f"node:{alert.node_identity}"
        elif alert.affected_resources:
            return f"res:{alert.affected_resources[0]}"
        return f"alert:{alert.alert_id}"

    def correlate_alerts(self, new_alerts: List[ThreatAlert], current_time: Optional[float] = None) -> List[SecurityIncident]:
        """Correlates new alerts into attack chains and synthesizes SecurityIncidents."""
        now = current_time or time.time()
        created_incidents: List[SecurityIncident] = []

        for alert in new_alerts:
            key = self._get_correlation_key(alert)
            bucket = self._alert_buckets[key]

            # Prune stale alerts outside correlation window
            cutoff = now - self.correlation_window_sec
            self._alert_buckets[key] = [a for a in bucket if a.timestamp >= cutoff]
            self._alert_buckets[key].append(alert)

            active_chain = self._alert_buckets[key]
            # Multi-stage attack chain detection (2 or more correlated alerts in window)
            if len(active_chain) >= 2:
                # Deduce highest severity
                severities = [a.severity for a in active_chain]
                top_severity = SecuritySeverity.INFO
                for s in [SecuritySeverity.CRITICAL, SecuritySeverity.HIGH, SecuritySeverity.MEDIUM, SecuritySeverity.LOW]:
                    if s in severities:
                        top_severity = s
                        break

                # Combine trigger events and assets
                event_ids: Set[str] = set()
                assets: Set[str] = set()
                titles: List[str] = []
                for a in active_chain:
                    event_ids.update(a.trigger_event_ids)
                    assets.update(a.affected_resources)
                    titles.append(a.title)

                incident_id = f"inc-{uuid.uuid4().hex[:8]}"
                chain_title = f"Correlated Attack Chain: {' -> '.join(titles[:3])}"
                avg_confidence = sum(a.confidence for a in active_chain) / len(active_chain)

                incident = SecurityIncident(
                    incident_id=incident_id,
                    title=chain_title,
                    threat_classification=alert.threat_classification,
                    severity=top_severity,
                    confidence=round(avg_confidence, 2),
                    detection_source="ThreatCorrelationEngine",
                    affected_assets=sorted(list(assets)),
                    related_event_ids=sorted(list(event_ids)),
                    evidence_ids=[],
                    status=IncidentStatus.DETECTED,
                    created_at=now,
                    updated_at=now,
                    audit_history=[{
                        "action": "CORRELATION_CHAIN_CREATED",
                        "correlated_alert_count": len(active_chain),
                        "timestamp": now,
                    }],
                )
                created_incidents.append(incident)
                # Clear bucket once promoted to incident
                self._alert_buckets[key].clear()
            elif alert.severity == SecuritySeverity.CRITICAL:
                # Standalone critical alert immediately spawns an incident
                incident_id = f"inc-{uuid.uuid4().hex[:8]}"
                incident = SecurityIncident(
                    incident_id=incident_id,
                    title=f"Critical Alert: {alert.title}",
                    threat_classification=alert.threat_classification,
                    severity=SecuritySeverity.CRITICAL,
                    confidence=alert.confidence,
                    detection_source=f"DetectionRule:{alert.rule_id}",
                    affected_assets=alert.affected_resources,
                    related_event_ids=alert.trigger_event_ids,
                    evidence_ids=[],
                    status=IncidentStatus.DETECTED,
                    created_at=now,
                    updated_at=now,
                    audit_history=[{
                        "action": "CRITICAL_ALERT_INCIDENT_CREATED",
                        "alert_id": alert.alert_id,
                        "timestamp": now,
                    }],
                )
                created_incidents.append(incident)

        return created_incidents
