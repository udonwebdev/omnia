"""
OMNIA Module 35: Security Posture Analyzer & Attack Surface Monitor
Assesses system posture across active incidents, critical alerts, monitored sources,
and component health. Never marks UNKNOWN as HEALTHY.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional

from defense.models import (
    SecurityPostureAssessment,
    SecurityPostureState,
    SecurityIncident,
    ThreatAlert,
    SecuritySeverity,
)

logger = logging.getLogger("Omnia.Defense.Posture")


class SecurityPostureAnalyzer:
    """Evaluates real-time defensive posture based on ground-truth observations."""

    CORE_COMPONENTS = [
        "auth_gateway",
        "secrets_engine",
        "policy_enforcer",
        "mesh_coordinator",
        "connector_gateway",
        "runtime_supervisor",
    ]

    def assess_posture(
        self,
        active_incidents: List[SecurityIncident],
        recent_alerts: List[ThreatAlert],
        missing_sources: List[str],
        timestamp: Optional[float] = None
    ) -> SecurityPostureAssessment:
        """Computes comprehensive security posture and score."""
        now = timestamp or time.time()
        assessment_id = f"posture-{uuid.uuid4().hex[:8]}"
        component_posture: Dict[str, SecurityPostureState] = {}
        recommended_remediations: List[str] = []

        # 1. Base component health from missing telemetry sources
        for comp in self.CORE_COMPONENTS:
            if comp in missing_sources:
                component_posture[comp] = SecurityPostureState.UNKNOWN
                recommended_remediations.append(f"Restore missing telemetry collector heartbeat for '{comp}'.")
            else:
                component_posture[comp] = SecurityPostureState.HEALTHY

        # 2. Factor in active incidents
        critical_incidents = [i for i in active_incidents if i.severity == SecuritySeverity.CRITICAL]
        high_incidents = [i for i in active_incidents if i.severity == SecuritySeverity.HIGH]
        medium_incidents = [i for i in active_incidents if i.severity == SecuritySeverity.MEDIUM]

        # 3. Factor in recent critical alerts
        critical_alerts = [a for a in recent_alerts if a.severity == SecuritySeverity.CRITICAL]

        # 4. Map affected assets to components
        for inc in active_incidents:
            for asset in inc.affected_assets:
                for comp in self.CORE_COMPONENTS:
                    if comp in asset.lower() or asset.lower() in comp:
                        if inc.severity == SecuritySeverity.CRITICAL:
                            component_posture[comp] = SecurityPostureState.CRITICAL
                        elif inc.severity == SecuritySeverity.HIGH and component_posture[comp] != SecurityPostureState.CRITICAL:
                            component_posture[comp] = SecurityPostureState.AT_RISK
                        elif component_posture[comp] == SecurityPostureState.HEALTHY:
                            component_posture[comp] = SecurityPostureState.DEGRADED

        # 5. Determine overall posture state
        if critical_incidents or len(critical_alerts) >= 2:
            overall_state = SecurityPostureState.CRITICAL
            score = 25.0
            recommended_remediations.append("Execute containment actions for critical security incidents immediately.")
        elif high_incidents or len(missing_sources) >= 3:
            overall_state = SecurityPostureState.AT_RISK
            score = 50.0
            recommended_remediations.append("Investigate high-severity incidents and address telemetry blind spots.")
        elif medium_incidents or missing_sources:
            overall_state = SecurityPostureState.DEGRADED
            score = 75.0
            recommended_remediations.append("Triage active medium-severity warnings and restore telemetry feeds.")
        else:
            overall_state = SecurityPostureState.HEALTHY
            score = 95.0

        assessment = SecurityPostureAssessment(
            assessment_id=assessment_id,
            overall_state=overall_state,
            score=score,
            active_incidents_count=len(active_incidents),
            critical_alerts_count=len(critical_alerts),
            monitored_sources_count=len(self.CORE_COMPONENTS) - len(missing_sources),
            missing_sources=missing_sources,
            component_posture=component_posture,
            recommended_remediations=recommended_remediations,
            timestamp=now,
        )
        return assessment
