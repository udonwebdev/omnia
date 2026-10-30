"""
OMNIA Module 37: Environment Management & Target Infrastructure Registry
Tracks target deployment environments, desired vs. actual releases, configuration revisions,
and maintenance states.
"""

import time
import logging
from typing import Dict, Any, List, Optional
from release.models import EnvironmentRecord, EnvironmentType
from release.persistence import ReleaseRepository

logger = logging.getLogger("Omnia.Release.Environments")


class EnvironmentManager:
    """Manages deployment target environments, desired states, and leases."""

    def __init__(self, repo: ReleaseRepository):
        self.repo = repo

    def register_environment(
        self,
        environment_id: str,
        environment_type: EnvironmentType,
        app_id: str,
        provider_type: str = "local_process",
        target_endpoint: str = "http://127.0.0.1:8080",
        requires_approval: bool = True,
        configuration_revision: str = "rev-1",
    ) -> EnvironmentRecord:
        """Registers a deployment target environment."""
        record = EnvironmentRecord(
            environment_id=environment_id,
            environment_type=environment_type,
            app_id=app_id,
            provider_type=provider_type,
            target_endpoint=target_endpoint,
            requires_approval=requires_approval,
            configuration_revision=configuration_revision,
            health_status="HEALTHY",
            last_verified_at=time.time(),
        )
        self.repo.save_environment(record)
        logger.info(f"Registered environment '{environment_id}' ({environment_type.value}) for app '{app_id}'")
        return record

    def acquire_environment_lease(self, environment_id: str, node_id: str, ttl_seconds: float = 60.0) -> bool:
        """Acquires a distributed deployment lock for an environment."""
        env = self.repo.get_environment(environment_id)
        if not env:
            return False

        now = time.time()
        if env.cluster_lease_node and env.lease_expires_at and env.lease_expires_at > now:
            if env.cluster_lease_node != node_id:
                logger.warning(f"Environment '{environment_id}' is leased to '{env.cluster_lease_node}' until {env.lease_expires_at}")
                return False

        env.cluster_lease_node = node_id
        env.lease_expires_at = now + ttl_seconds
        self.repo.save_environment(env)
        return True

    def release_environment_lease(self, environment_id: str, node_id: str) -> bool:
        """Releases the deployment lock."""
        env = self.repo.get_environment(environment_id)
        if not env:
            return False
        if env.cluster_lease_node == node_id:
            env.cluster_lease_node = None
            env.lease_expires_at = None
            self.repo.save_environment(env)
            return True
        return False
