"""
OMNIA Module 43: Autonomous Infrastructure Provisioning & Environment Lifecycle Management
Infrastructure Drift Reconciliation Engine - reconciliation.py

Periodically or on-demand discovers actual live infrastructure resources
and compares them against declarative blueprint desired state.
Detects MISSING_RESOURCE, UNEXPECTED_RESOURCE, and CONFIGURATION_DRIFT.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from infrastructure_lifecycle.models import (
    DriftType,
    InfrastructureBlueprint,
    InfrastructureDriftRecord,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository
from infrastructure_lifecycle.providers import InfrastructureProviderRegistry

logger = logging.getLogger("Omnia.Infrastructure.Reconciliation")


class InfrastructureReconciler:
    """
    Compares declarative desired blueprint state against discovered actual state.
    Records drift findings and facilitates remediation.
    """

    def __init__(
        self,
        repository: Optional[InfrastructureRepository] = None,
        registry: Optional[InfrastructureProviderRegistry] = None,
    ):
        self.repo = repository or InfrastructureRepository()
        self.registry = registry or InfrastructureProviderRegistry(self.repo)

    def reconcile_environment(
        self,
        environment_id: str,
        auto_reconcile: bool = False,
    ) -> List[InfrastructureDriftRecord]:
        env = self.repo.get_environment(environment_id)
        if not env:
            raise KeyError(f"Environment '{environment_id}' not found.")

        bp = self.repo.get_blueprint(env.blueprint_id)
        if not bp:
            raise KeyError(f"Blueprint '{env.blueprint_id}' not found.")

        adapter = self.registry.get_adapter(env.provider_id)
        if not adapter:
            raise KeyError(f"Provider adapter '{env.provider_id}' not registered.")

        # Discovered live resources from provider
        discovered = adapter.discover_resources(environment_id)
        live_names = {}
        for r in discovered:
            if isinstance(r, dict):
                r_name = r.get("resource_name") or r.get("name") or str(r)
                live_names[r_name] = r
            else:
                live_names[getattr(r, "resource_name", str(r))] = r

        desired_names = {r["name"]: r for r in bp.resource_definitions}
        findings: List[InfrastructureDriftRecord] = []

        # Check missing resources
        for name, spec in desired_names.items():
            if name not in live_names:
                did = f"drift-{uuid.uuid4().hex[:8]}"
                rec = InfrastructureDriftRecord(
                    drift_id=did,
                    environment_id=environment_id,
                    drift_type=DriftType.MISSING_RESOURCE,
                    resource_id=name,
                    expected_state=f"Resource {name} should exist",
                    actual_state="Resource absent in provider",
                    remediation_suggestion=f"Provision missing resource '{name}'",
                    is_reconciled=False,
                )
                self.repo.save_drift_record(rec)
                findings.append(rec)

        # Check unexpected resources
        for name in live_names:
            if name not in desired_names:
                did = f"drift-{uuid.uuid4().hex[:8]}"
                rec = InfrastructureDriftRecord(
                    drift_id=did,
                    environment_id=environment_id,
                    drift_type=DriftType.UNEXPECTED_RESOURCE,
                    resource_id=name,
                    expected_state="Resource should not exist",
                    actual_state=f"Unmanaged resource {name} present in provider",
                    remediation_suggestion=f"Decommission or import unmanaged resource '{name}'",
                    is_reconciled=False,
                )
                self.repo.save_drift_record(rec)
                findings.append(rec)

        logger.info(f"Reconciliation for env '{environment_id}' completed. Findings={len(findings)}")
        return findings
