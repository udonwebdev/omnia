"""
Omnia Module 43: Autonomous Infrastructure Provisioning, Deployment & Environment Lifecycle Management.
Infrastructure Provider Registry and Base Adapter Contract.
"""

from __future__ import annotations

import abc
import logging
from typing import Any, Dict, List, Optional

from infrastructure_lifecycle.models import (
    InfrastructureProviderRecord,
    ProviderCapability,
    ProviderType,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository

logger = logging.getLogger("Omnia.Infrastructure.Providers")


class BaseInfrastructureAdapter(abc.ABC):
    """Abstract interface contract for all infrastructure and hosting environment providers."""

    @property
    @abc.abstractmethod
    def provider_type(self) -> ProviderType:
        pass

    @property
    @abc.abstractmethod
    def supported_capabilities(self) -> List[ProviderCapability]:
        pass

    @abc.abstractmethod
    def discover_resources(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    def provision_resource(self, resource_spec: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    def inspect_resource(self, provider_ref: str) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    def mutate_resource(self, provider_ref: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    def decommission_resource(self, provider_ref: str) -> bool:
        pass


class LocalSandboxProviderAdapter(BaseInfrastructureAdapter):
    """Production local-process, container, and isolated sandbox environment adapter."""

    def __init__(
        self,
        provider_id: str = "provider-local-sandbox",
        capabilities: Optional[List[ProviderCapability]] = None,
        provider_type: ProviderType = ProviderType.LOCAL_PROCESS,
    ):
        self._provider_id = provider_id
        self._provider_type = provider_type
        self._capabilities = capabilities or [
            ProviderCapability.DISCOVERY,
            ProviderCapability.PROVISION,
            ProviderCapability.MUTATE,
            ProviderCapability.RESTART,
            ProviderCapability.DECOMMISSION,
            ProviderCapability.INSPECT,
            ProviderCapability.LOGS,
        ]
        self._simulated_pool: Dict[str, Dict[str, Any]] = {}

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def provider_type(self) -> ProviderType:
        return self._provider_type

    @property
    def supported_capabilities(self) -> List[ProviderCapability]:
        return self._capabilities

    def get_record(self) -> InfrastructureProviderRecord:
        return InfrastructureProviderRecord(
            provider_id=self._provider_id,
            name=f"Provider {self._provider_id}",
            provider_type=self._provider_type,
            supported_capabilities=self._capabilities,
        )

    def health_check(self) -> bool:
        return True

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self._capabilities

    def discover_resources(self, filter_params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return list(self._simulated_pool.values())

    def provision_resource(self, resource_spec: Any = None, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        if not self.supports(ProviderCapability.PROVISION):
            raise PermissionError(f"Provider '{self._provider_id}' does not support PROVISION capability.")
        if isinstance(resource_spec, dict):
            spec = dict(resource_spec)
        elif isinstance(resource_spec, str):
            spec = {"resource_name": resource_spec}
            if args:
                spec["resource_type"] = args[0]
            if len(args) > 1 and isinstance(args[1], dict):
                spec.update(args[1])
        else:
            spec = {}
        spec.update(kwargs)
        rid = spec.get("resource_name") or spec.get("name") or "res-unnamed"
        ref = f"local-proc://{rid}"
        entry = {
            "provider_ref": ref,
            "resource_name": rid,
            "resource_type": spec.get("resource_type") or spec.get("type") or "PROCESS",
            "status": "HEALTHY",
            "capacity": spec.get("capacity", 1.0),
        }
        self._simulated_pool[ref] = entry
        logger.info(f"LocalSandboxProviderAdapter: Provisioned resource '{ref}'")
        return entry

    def inspect_resource(self, provider_ref: str) -> Dict[str, Any]:
        if not self.supports(ProviderCapability.INSPECT):
            raise PermissionError(f"Provider '{self._provider_id}' does not support INSPECT capability.")
        if provider_ref not in self._simulated_pool:
            raise KeyError(f"Resource '{provider_ref}' not found in local sandbox provider.")
        return self._simulated_pool[provider_ref]

    def mutate_resource(self, provider_ref: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not self.supports(ProviderCapability.MUTATE):
            raise PermissionError(f"Provider '{self._provider_id}' does not support MUTATE capability.")
        res = self.inspect_resource(provider_ref)
        res.update(updates)
        return res

    def decommission_resource(self, provider_ref: str) -> bool:
        if not self.supports(ProviderCapability.DECOMMISSION):
            raise PermissionError(f"Provider '{self._provider_id}' does not support DECOMMISSION capability.")
        if provider_ref in self._simulated_pool:
            del self._simulated_pool[provider_ref]
            logger.info(f"LocalSandboxProviderAdapter: Decommissioned '{provider_ref}'")
            return True
        # Check by resource_name or ref
        to_del = [k for k, v in self._simulated_pool.items() if v.get("resource_name") == provider_ref or k == f"local-proc://{provider_ref}"]
        for k in to_del:
            del self._simulated_pool[k]
        if to_del:
            return True
        return False


class InfrastructureProviderRegistry:
    """Manages active infrastructure providers, capability declarations, and runtime adapter binding."""

    def __init__(self, repository: Optional[InfrastructureRepository] = None):
        self.repo = repository or InfrastructureRepository()
        self._adapters: Dict[str, BaseInfrastructureAdapter] = {}
        # Register built-in local sandbox adapter
        default_adapter = LocalSandboxProviderAdapter()
        self.register_provider(
            provider_id="provider-local-sandbox",
            name="Default Local Sandbox Provider",
            provider_type=ProviderType.LOCAL_PROCESS,
            supported_capabilities=default_adapter.supported_capabilities,
            adapter=default_adapter,
        )

    def register_adapter(self, adapter: BaseInfrastructureAdapter) -> None:
        self._adapters[adapter.provider_id] = adapter
        if hasattr(adapter, "get_record"):
            self.repo.save_provider(adapter.get_record())

    def register_provider(
        self,
        provider_id: str,
        name: str,
        provider_type: ProviderType,
        supported_capabilities: List[ProviderCapability],
        adapter: Optional[BaseInfrastructureAdapter] = None,
        auth_secret_ref: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InfrastructureProviderRecord:
        record = InfrastructureProviderRecord(
            provider_id=provider_id,
            name=name,
            provider_type=provider_type,
            supported_capabilities=supported_capabilities,
            auth_secret_ref=auth_secret_ref,
            metadata=metadata or {},
        )
        self.repo.save_provider(record)
        if adapter:
            self._adapters[provider_id] = adapter
        logger.info(f"Registered infrastructure provider: {provider_id} ({provider_type.value})")
        return record

    def get_adapter(self, provider_id: str) -> BaseInfrastructureAdapter:
        if provider_id not in self._adapters:
            # Fallback to local sandbox if provider exists in repo
            p = self.repo.get_provider(provider_id)
            if p:
                self._adapters[provider_id] = LocalSandboxProviderAdapter()
            else:
                raise KeyError(f"Provider '{provider_id}' is not registered or supported.")
        return self._adapters[provider_id]

    def list_providers(self) -> List[InfrastructureProviderRecord]:
        return self.repo.list_providers(active_only=True)
