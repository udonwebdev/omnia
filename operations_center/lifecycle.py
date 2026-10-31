"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Incident Lifecycle Manager: 8-State Deterministic State Machine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from operations_center.models import (
    IncidentLifecycleState,
    IncidentRecord,
    IncidentSeverity,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.Lifecycle")

VALID_INCIDENT_TRANSITIONS = {
    IncidentLifecycleState.DETECTED: [IncidentLifecycleState.TRIAGED, IncidentLifecycleState.CLOSED],
    IncidentLifecycleState.TRIAGED: [IncidentLifecycleState.INVESTIGATING, IncidentLifecycleState.MITIGATING],
    IncidentLifecycleState.INVESTIGATING: [IncidentLifecycleState.MITIGATING, IncidentLifecycleState.RECOVERING],
    IncidentLifecycleState.MITIGATING: [IncidentLifecycleState.RECOVERING, IncidentLifecycleState.RESOLVED],
    IncidentLifecycleState.RECOVERING: [IncidentLifecycleState.RESOLVED, IncidentLifecycleState.INVESTIGATING],
    IncidentLifecycleState.RESOLVED: [IncidentLifecycleState.REVIEWED, IncidentLifecycleState.INVESTIGATING],
    IncidentLifecycleState.REVIEWED: [IncidentLifecycleState.CLOSED],
    IncidentLifecycleState.CLOSED: [],
}


class IncidentLifecycleManager:
    """Orchestrates deterministic lifecycle transitions for active incidents."""

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def transition_state(
        self,
        incident_id: str,
        new_state: IncidentLifecycleState,
        operator_id: Optional[str] = None,
    ) -> IncidentRecord:
        """Transitions an incident forward in its lifecycle following valid state paths."""
        inc = self.repo.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident '{incident_id}' not found.")

        current = inc.state
        allowed = VALID_INCIDENT_TRANSITIONS.get(current, [])
        if new_state not in allowed and new_state != current:
            raise ValueError(f"Invalid incident transition from {current.value} to {new_state.value}")

        inc.state = new_state
        if new_state in (IncidentLifecycleState.RESOLVED, IncidentLifecycleState.CLOSED) and not inc.resolved_at:
            inc.resolved_at = datetime.now(timezone.utc).isoformat()
        if operator_id:
            inc.assigned_to = operator_id

        self.repo.save_incident(inc)
        logger.info(f"Transitioned Incident '{incident_id}' from {current.value} to {new_state.value}")
        return inc

    def update_severity(
        self,
        incident_id: str,
        new_severity: IncidentSeverity,
        rationale: str,
    ) -> IncidentRecord:
        """Updates the severity of an active incident with documented rationale."""
        inc = self.repo.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident '{incident_id}' not found.")
        old_sev = inc.severity
        inc.severity = new_severity
        self.repo.save_incident(inc)
        logger.info(f"Updated severity of Incident '{incident_id}' from {old_sev.value} to {new_severity.value}: {rationale}")
        return inc
