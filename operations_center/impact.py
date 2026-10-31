"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Impact Assessment Engine: Blast Radius & Dependency Disruption Evaluation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from operations_center.models import (
    ImpactAssessmentRecord,
    IncidentSeverity,
)
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.Impact")


class ImpactAssessmentEngine:
    """
    Evaluates downstream dependency cascade, affected workflows, and blast radius for incidents.
    """

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def assess_incident_impact(self, incident_id: str) -> ImpactAssessmentRecord:
        """Computes blast radius score and downstream operational disruption."""
        inc = self.repo.get_incident(incident_id)
        if not inc:
            raise ValueError(f"Incident '{incident_id}' not found.")

        # Find downstream services that depend on inc.primary_service_id
        all_services = self.repo.list_services()
        downstream = []
        for s in all_services:
            if inc.primary_service_id in s.dependencies:
                downstream.append(s.service_id)

        affected = list(set([inc.primary_service_id] + downstream))
        total_services = max(1, len(all_services))
        blast_score = len(affected) / total_services

        if inc.severity == IncidentSeverity.SEV_1_CRITICAL:
            disruption = "HIGH"
            integrity = "ELEVATED"
            cost_est = 25000.0
        elif inc.severity == IncidentSeverity.SEV_2_HIGH:
            disruption = "MODERATE"
            integrity = "LOW"
            cost_est = 5000.0
        else:
            disruption = "LOW"
            integrity = "LOW"
            cost_est = 500.0

        rec = ImpactAssessmentRecord(
            assessment_id=f"imp-{uuid.uuid4().hex[:8]}",
            incident_id=incident_id,
            blast_radius_score=round(blast_score, 2),
            affected_workflows=affected,
            data_integrity_risk=integrity,
            operational_disruption=disruption,
            financial_exposure_estimate=cost_est,
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_impact_assessment(rec)
        logger.info(f"Assessed impact for '{incident_id}': BlastRadius={blast_score:.1%}, Disruption={disruption}")
        return rec
