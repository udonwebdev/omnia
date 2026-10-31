"""
Omnia Module 40: Autonomous Operations Center, System Observability & Incident Intelligence.
Service-Level Objective Manager: SLIs, Targets, Error Budgets & Burn Rates.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from operations_center.models import SLORecord
from operations_center.persistence import OperationsCenterRepository

logger = logging.getLogger("Omnia.Ops.SLO")


class ServiceLevelObjectiveManager:
    """Manages SLI measurements, SLO thresholds, error budget depletion, and burn rate calculations."""

    def __init__(self, repository: Optional[OperationsCenterRepository] = None):
        self.repo = repository or OperationsCenterRepository()

    def define_slo(
        self,
        service_id: str,
        name: str,
        target_pct: float = 99.9,
        slo_id: Optional[str] = None,
    ) -> SLORecord:
        """Configures a target Service-Level Objective for a service."""
        sid = slo_id or f"slo-{uuid.uuid4().hex[:8]}"
        slo = SLORecord(
            slo_id=sid,
            service_id=service_id,
            name=name,
            target_pct=target_pct,
            current_sli_pct=100.0,
            error_budget_remaining_pct=100.0,
            burn_rate=0.0,
        )
        self.repo.save_slo(slo)
        logger.info(f"Configured SLO '{sid}' for service '{service_id}': {name} Target={target_pct}%")
        return slo

    def evaluate_slo(
        self,
        slo_id: str,
        total_requests: int,
        good_requests: int,
        time_window_hours: float = 24.0,
    ) -> SLORecord:
        """
        Calculates:
        1. Current SLI: (good_requests / total_requests) * 100
        2. Error Budget Remaining: ((SLI - Target) / (100 - Target)) * 100
        3. Burn Rate: depletion velocity relative to 30-day budget
        """
        # Look up existing slo
        with self.repo._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ops_slo_definitions WHERE slo_id = ?", (slo_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"SLO '{slo_id}' not found.")

        target = row["target_pct"]
        if total_requests > 0:
            sli = (good_requests / total_requests) * 100.0
        else:
            sli = 100.0

        allowable_error = 100.0 - target
        observed_error = max(0.0, 100.0 - sli)

        if allowable_error > 0:
            error_budget_remaining = max(0.0, ((allowable_error - observed_error) / allowable_error) * 100.0)
            # Burn rate = 1.0 means consuming budget at exact 30-day rate
            burn_rate = (observed_error / allowable_error) * (720.0 / max(1.0, time_window_hours))
        else:
            error_budget_remaining = 100.0 if sli >= 100.0 else 0.0
            burn_rate = 0.0

        updated_slo = SLORecord(
            slo_id=row["slo_id"],
            service_id=row["service_id"],
            name=row["name"],
            target_pct=target,
            current_sli_pct=round(sli, 3),
            error_budget_remaining_pct=round(error_budget_remaining, 2),
            burn_rate=round(burn_rate, 2),
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.repo.save_slo(updated_slo)
        logger.info(
            f"Evaluated SLO '{slo_id}': SLI={sli:.2f}%, BudgetLeft={error_budget_remaining:.1f}%, BurnRate={burn_rate:.2f}x"
        )
        return updated_slo
