"""
OMNIA Module 43: Autonomous Infrastructure Provisioning & Environment Lifecycle Management
Infrastructure Reporting & Posture HUD - reporting.py
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure_lifecycle.persistence import InfrastructureRepository

logger = logging.getLogger("Omnia.Infrastructure.Reporting")


class InfrastructureReporter:
    """
    Compiles executive and operational posture reports on managed infrastructure.
    """

    def __init__(self, repository: Optional[InfrastructureRepository] = None):
        self.repo = repository or InfrastructureRepository()

    def generate_posture_report(self) -> Dict[str, Any]:
        envs = self.repo.list_environments()
        state_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}

        for e in envs:
            s = e.current_state.value
            state_counts[s] = state_counts.get(s, 0) + 1
            t = e.environment_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        providers = self.repo.list_providers()
        drift_records = self.repo.list_drift_records(reconciled=False)

        return {
            "total_environments": len(envs),
            "environments_by_state": state_counts,
            "environments_by_type": type_counts,
            "registered_providers_count": len(providers),
            "active_unreconciled_drift_count": len(drift_records),
            "environments": [
                {
                    "environment_id": e.environment_id,
                    "name": e.name,
                    "type": e.environment_type.value,
                    "state": e.current_state.value,
                    "provider_id": e.provider_id,
                    "active_release": e.active_release_version,
                    "is_locked": e.is_locked,
                }
                for e in envs
            ],
        }
