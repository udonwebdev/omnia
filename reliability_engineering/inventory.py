"""
Omnia Module 41: Autonomous Reliability Engineering, Resilience Testing & Disaster Recovery.
Reliability Inventory Registry: Component Catalog, Dependencies & Failure Domains.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from reliability_engineering.models import (
    BackupType,
    ComponentReliabilityCriticality,
    FailoverReadinessState,
    FailureDomain,
    ReliabilityComponent,
)
from reliability_engineering.persistence import ReliabilityRepository

logger = logging.getLogger("Omnia.Reliability.Inventory")


class ReliabilityInventoryRegistry:
    """Manages the catalog of critical components and their reliability attributes."""

    def __init__(self, repository: Optional[ReliabilityRepository] = None):
        self.repo = repository or ReliabilityRepository()

    def register_component(
        self,
        component_id: str,
        component_name: str,
        criticality: ComponentReliabilityCriticality = ComponentReliabilityCriticality.HIGH,
        owner: str = "omnia-core",
        failure_domain: FailureDomain = FailureDomain.PROCESS,
        data_ownership: str = "STATELESS",
        dependencies: Optional[List[str]] = None,
        recovery_procedure: str = "DEFAULT_RESTART",
        backup_strategy: BackupType = BackupType.SNAPSHOT,
        redundancy_config: str = "N+1",
        failover_readiness: FailoverReadinessState = FailoverReadinessState.READY,
    ) -> ReliabilityComponent:
        """Registers or updates a critical subsystem component in the reliability inventory."""
        comp = ReliabilityComponent(
            component_id=component_id,
            component_name=component_name,
            criticality=criticality,
            owner=owner,
            failure_domain=failure_domain,
            data_ownership=data_ownership,
            dependencies=dependencies or [],
            recovery_procedure=recovery_procedure,
            backup_strategy=backup_strategy,
            redundancy_config=redundancy_config,
            failover_readiness=failover_readiness,
        )
        self.repo.save_component(comp)
        logger.info(f"Registered reliability component '{component_id}': {component_name} [{criticality.value}]")
        return comp

    def list_components(self) -> List[ReliabilityComponent]:
        return self.repo.list_components()

    def get_component(self, component_id: str) -> Optional[ReliabilityComponent]:
        return self.repo.get_component(component_id)

    def get_downstream_dependents(self, component_id: str) -> List[str]:
        """Identifies all components that directly depend on the specified component."""
        dependents = []
        for c in self.repo.list_components():
            if component_id in c.dependencies:
                dependents.append(c.component_id)
        return dependents
