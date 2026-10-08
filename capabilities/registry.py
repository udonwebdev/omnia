import time
import re
import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple, Set

from capabilities.models import (
    Capability,
    CapabilityProvider,
    CapabilityCategory,
    CapabilityHealth,
    CapabilityLifecycle,
    RiskLevel,
    SideEffectType,
    IdempotencyType,
    ReversibilityType,
    VerificationContract,
    CapabilityMatchQuery,
    CapabilityLease
)
from audit_logger import audit_logger

logger = logging.getLogger("Omnia.Capabilities.Registry")

class CapabilityRegistry:
    """Authoritative, centralized capability discovery and metadata registry."""

    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._leases: Dict[str, CapabilityLease] = {}
        self._listeners: List[Any] = []
        self._trusted_keys: Set[str] = {"core", "omnia_internal", "verified_plugin"}

    def register_capability(self, capability: Capability, auth_key: str = "core") -> Tuple[bool, str]:
        """Registers a new capability after strict security, schema, and version validation."""
        # Security: check authorization
        if auth_key not in self._trusted_keys:
            msg = f"SECURITY_REJECTION: Untrusted authorization key '{auth_key}' cannot register capability '{capability.id}'."
            logger.warning(msg)
            audit_logger.log_event("capability_registration", {"id": capability.id, "auth_key": auth_key}, allowed=False, outcome=msg)
            return False, msg

        # Validate Identity format (e.g. "namespace.action" or "namespace.sub.action")
        if not re.match(r"^[a-z0-9_\-]+(\.[a-z0-9_\-]+)+$", capability.id):
            msg = f"SCHEMA_REJECTION: Invalid capability ID format '{capability.id}'. Expected dot notation (e.g., 'browser.navigate')."
            logger.error(msg)
            return False, msg

        # Validate Version format
        if not re.match(r"^\d+\.\d+\.\d+$", capability.version):
            msg = f"SCHEMA_REJECTION: Invalid semantic version '{capability.version}' for capability '{capability.id}'."
            logger.error(msg)
            return False, msg

        # Validate schema presence
        if not isinstance(capability.input_schema, dict) or not isinstance(capability.output_schema, dict):
            msg = f"SCHEMA_REJECTION: Input and output schemas must be dictionaries for capability '{capability.id}'."
            logger.error(msg)
            return False, msg

        # Duplicate ID check: cannot overwrite with lower or incompatible version without explicit update
        if capability.id in self._capabilities:
            existing = self._capabilities[capability.id]
            if existing.version == capability.version:
                msg = f"CONFLICT_REJECTION: Duplicate capability registration for ID '{capability.id}' version '{capability.version}'."
                logger.warning(msg)
                audit_logger.log_event("capability_registration_conflict", {"id": capability.id}, allowed=False, outcome=msg)
                return False, msg

        # Set lifecycle
        capability.lifecycle = CapabilityLifecycle.REGISTERED
        capability.updated_at = time.time()
        self._capabilities[capability.id] = capability

        audit_logger.log_event("capability_registered", {
            "id": capability.id,
            "version": capability.version,
            "category": capability.category.value,
            "risk": capability.risk_level.value
        }, allowed=True, outcome="REGISTERED")

        logger.info(f"Capability registered: {capability.id} v{capability.version} [{capability.category.value}]")
        return True, "REGISTERED"

    def unregister_capability(self, capability_id: str, auth_key: str = "core") -> bool:
        """Safely removes a capability from the registry."""
        if auth_key not in self._trusted_keys:
            logger.warning(f"SECURITY_REJECTION: Unauthorized attempt to unregister '{capability_id}'.")
            return False

        if capability_id in self._capabilities:
            cap = self._capabilities[capability_id]
            cap.lifecycle = CapabilityLifecycle.REMOVED
            del self._capabilities[capability_id]
            audit_logger.log_event("capability_unregistered", {"id": capability_id}, allowed=True, outcome="REMOVED")
            logger.info(f"Capability unregistered: {capability_id}")
            return True
        return False

    def get_capability(self, capability_id: str) -> Optional[Capability]:
        """Retrieves a capability by stable ID."""
        return self._capabilities.get(capability_id)

    def list_capabilities(self, category: Optional[CapabilityCategory] = None) -> List[Capability]:
        """Lists all registered capabilities, optionally filtered by category."""
        caps = list(self._capabilities.values())
        if category:
            caps = [c for c in caps if c.category == category]
        return caps

    def register_provider(self, provider: CapabilityProvider, auth_key: str = "core") -> Tuple[bool, str]:
        """Registers or attaches an execution provider for a specific capability."""
        if auth_key not in self._trusted_keys:
            msg = f"SECURITY_REJECTION: Untrusted key '{auth_key}' cannot register provider '{provider.provider_id}'."
            return False, msg

        cap = self.get_capability(provider.capability_id)
        if not cap:
            msg = f"NOT_FOUND: Cannot register provider '{provider.provider_id}' for missing capability '{provider.capability_id}'."
            return False, msg

        cap.providers[provider.provider_id] = provider
        cap.updated_at = time.time()
        audit_logger.log_event("provider_registered", {
            "provider_id": provider.provider_id,
            "capability_id": provider.capability_id,
            "environment": provider.environment
        }, allowed=True, outcome="REGISTERED")
        return True, "PROVIDER_REGISTERED"

    def remove_provider(self, capability_id: str, provider_id: str) -> bool:
        """Removes a provider from a capability."""
        cap = self.get_capability(capability_id)
        if cap and provider_id in cap.providers:
            del cap.providers[provider_id]
            cap.updated_at = time.time()
            return True
        return False

    def resolve_provider(self, capability_id: str, environment: Optional[str] = None) -> Optional[CapabilityProvider]:
        """Selects the best available, healthy provider for a given capability with fallback negotiation."""
        cap = self.get_capability(capability_id)
        if not cap or not cap.providers:
            return None

        candidates = list(cap.providers.values())
        if environment:
            env_candidates = [p for p in candidates if p.environment == environment or p.environment == "local"]
            if env_candidates:
                candidates = env_candidates

        # Filter candidates by usable health
        healthy_candidates = [
            p for p in candidates
            if p.health in [CapabilityHealth.HEALTHY, CapabilityHealth.DEGRADED, CapabilityHealth.UNKNOWN]
        ]

        if not healthy_candidates:
            return None

        # Sort: priority ascending, latency ascending, cost ascending
        healthy_candidates.sort(key=lambda p: (
            0 if p.health == CapabilityHealth.HEALTHY else 1,
            p.priority,
            p.latency_ms,
            p.cost
        ))

        return healthy_candidates[0]

    def acquire_lease(self, capability_id: str, provider_id: str, task_id: str, duration_sec: float = 30.0) -> Optional[CapabilityLease]:
        """Acquires a temporary execution lease for a specific capability provider."""
        cap = self.get_capability(capability_id)
        if not cap or provider_id not in cap.providers:
            return None

        # Check existing active leases for this provider
        now = time.time()
        for l in list(self._leases.values()):
            if l.capability_id == capability_id and l.provider_id == provider_id and l.status == "ACTIVE":
                if now < l.expires_at and l.task_id != task_id:
                    # Resource is leased exclusively
                    return None
                elif now >= l.expires_at:
                    l.status = "EXPIRED"

        lease = CapabilityLease(
            capability_id=capability_id,
            provider_id=provider_id,
            task_id=task_id,
            acquired_at=now,
            expires_at=now + duration_sec,
            status="ACTIVE"
        )
        self._leases[lease.lease_id] = lease
        return lease

    def release_lease(self, lease_id: str) -> bool:
        """Releases an active capability lease."""
        if lease_id in self._leases:
            self._leases[lease_id].status = "RELEASED"
            del self._leases[lease_id]
            return True
        return False

    def get_dependencies(self, capability_id: str) -> List[str]:
        """Returns direct dependencies declared by the capability."""
        cap = self.get_capability(capability_id)
        return list(cap.dependencies) if cap else []

    def get_dependents(self, capability_id: str) -> List[str]:
        """Returns capabilities that depend on the given capability ID."""
        dependents = []
        for cid, cap in self._capabilities.items():
            if capability_id in cap.dependencies:
                dependents.append(cid)
        return dependents

    def update_health(self, capability_id: str, health: CapabilityHealth, message: Optional[str] = None):
        """Updates the health status of a capability and ripples status to dependent capabilities if failed."""
        cap = self.get_capability(capability_id)
        if not cap:
            return

        old_health = cap.health
        cap.health = health
        cap.updated_at = time.time()
        if message:
            cap.metadata["last_health_message"] = message

        if old_health != health:
            audit_logger.log_event("capability_health_changed", {
                "id": capability_id,
                "old": old_health.value,
                "new": health.value,
                "message": message or ""
            }, allowed=True, outcome=f"HEALTH_{health.value}")
            logger.info(f"Capability health updated: {capability_id} -> {health.value}")

        # If capability became UNAVAILABLE or FAILED, mark dependent capabilities DEGRADED or UNAVAILABLE
        if health in [CapabilityHealth.UNAVAILABLE, CapabilityHealth.FAILED, CapabilityHealth.DISABLED]:
            for dep_id in self.get_dependents(capability_id):
                dep_cap = self.get_capability(dep_id)
                if dep_cap and dep_cap.health == CapabilityHealth.HEALTHY:
                    dep_cap.health = CapabilityHealth.DEGRADED
                    dep_cap.metadata["dependency_failure"] = f"Dependency '{capability_id}' is {health.value}"
                    logger.warning(f"Rippling degraded health to dependent capability: {dep_id}")

    def verify_version_compatibility(self, capability_id: str, expected_version: str) -> bool:
        """Checks if installed version is compatible with expected version (major version match)."""
        cap = self.get_capability(capability_id)
        if not cap:
            return False
        exp_major = expected_version.split(".")[0]
        cur_major = cap.version.split(".")[0]
        return exp_major == cur_major

capability_registry = CapabilityRegistry()
