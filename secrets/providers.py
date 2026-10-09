import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List

from secrets.models import ProviderHealth, SecretType, SecretStatus, SecretRecord, SecretVersionRecord
from secrets.encryption import encryption_engine, EncryptionEngine
from secrets.persistence import SecretPersistence

logger = logging.getLogger("Omnia.Secrets.Providers")

class SecretUnavailableError(RuntimeError):
    """Raised when a requested secret cannot be retrieved securely from any provider."""
    pass

class SecretProvider(ABC):
    """Abstract interface for pluggable secret backend providers."""

    def __init__(self, name: str):
        self.name = name
        self.health: ProviderHealth = ProviderHealth.HEALTHY

    @abstractmethod
    def get_secret(self, secret_id: str, version: Optional[int] = None) -> Tuple[str, int]:
        """Retrieves plaintext secret and active version number."""
        pass

    @abstractmethod
    def store_secret(self, secret_id: str, plaintext: str, version: int = 1) -> SecretVersionRecord:
        """Stores a new version of the secret."""
        pass

    @abstractmethod
    def check_health(self) -> ProviderHealth:
        """Evaluates health of the provider backend."""
        pass

class LocalEncryptedStoreProvider(SecretProvider):
    """Default secure local store with envelope encryption at rest."""

    def __init__(self, persistence: Optional[SecretPersistence] = None, enc_engine: Optional[EncryptionEngine] = None):
        super().__init__("local_encrypted")
        self.persistence = persistence or SecretPersistence()
        self.enc_engine = enc_engine or encryption_engine

    def get_secret(self, secret_id: str, version: Optional[int] = None) -> Tuple[str, int]:
        meta = self.persistence.get_secret_metadata(secret_id)
        if not meta:
            raise SecretUnavailableError(f"Secret '{secret_id}' not found in local encrypted store.")

        target_ver = version or meta.version
        ver_record = self.persistence.get_secret_version(secret_id, target_ver)
        if not ver_record:
            raise SecretUnavailableError(f"Secret '{secret_id}' version {target_ver} not found.")

        if ver_record.status not in [SecretStatus.ACTIVE, SecretStatus.STAGED]:
            raise SecretUnavailableError(f"Secret '{secret_id}' v{target_ver} is not active ({ver_record.status.value}).")

        plaintext = self.enc_engine.decrypt(
            ver_record.ciphertext,
            ver_record.salt,
            ver_record.nonce,
            ver_record.key_id
        )
        return plaintext, target_ver

    def store_secret(self, secret_id: str, plaintext: str, version: int = 1) -> SecretVersionRecord:
        key_id = "kek_v1"
        ct_b64, salt_b64, nonce_b64, fingerprint = self.enc_engine.encrypt(plaintext, key_id=key_id)

        ver_record = SecretVersionRecord(
            secret_id=secret_id,
            version=version,
            status=SecretStatus.ACTIVE,
            created_at=time.time(),
            activated_at=time.time(),
            retired_at=None,
            fingerprint=fingerprint,
            ciphertext=ct_b64,
            key_id=key_id,
            salt=salt_b64,
            nonce=nonce_b64
        )
        self.persistence.save_secret_version(ver_record)
        return ver_record

    def check_health(self) -> ProviderHealth:
        try:
            # Self-test encryption engine
            ct, s, n, _ = self.enc_engine.encrypt("health_probe")
            plain = self.enc_engine.decrypt(ct, s, n)
            assert plain == "health_probe"
            self.health = ProviderHealth.HEALTHY
        except Exception as e:
            logger.error(f"LocalEncryptedStore health probe failed: {e}")
            self.health = ProviderHealth.DEGRADED
        return self.health

class EnvironmentSecretProvider(SecretProvider):
    """Secure provider resolving secrets from environment variables (e.g. OMNIA_SECRET_<ID>)."""

    def __init__(self, prefix: str = "OMNIA_SECRET_"):
        super().__init__("environment")
        self.prefix = prefix

    def _env_key(self, secret_id: str) -> str:
        clean_id = secret_id.replace("/", "_").replace(".", "_").replace("-", "_").upper()
        return f"{self.prefix}{clean_id}"

    def get_secret(self, secret_id: str, version: Optional[int] = None) -> Tuple[str, int]:
        env_var = self._env_key(secret_id)
        val = os.environ.get(env_var)
        if not val:
            raise SecretUnavailableError(f"Environment variable '{env_var}' for secret '{secret_id}' is not set.")
        return val, 1

    def store_secret(self, secret_id: str, plaintext: str, version: int = 1) -> SecretVersionRecord:
        env_var = self._env_key(secret_id)
        os.environ[env_var] = plaintext
        return SecretVersionRecord(
            secret_id=secret_id,
            version=version,
            status=SecretStatus.ACTIVE,
            created_at=time.time(),
            activated_at=time.time(),
            retired_at=None,
            fingerprint="env_secret",
            ciphertext="[ENV_VARIABLE]",
            key_id="env",
            salt="",
            nonce=""
        )

    def check_health(self) -> ProviderHealth:
        self.health = ProviderHealth.HEALTHY
        return self.health

class MemoryVaultProvider(SecretProvider):
    """In-memory volatile enclave for testing and transient runtime session keys."""

    def __init__(self):
        super().__init__("memory_vault")
        self._vault: Dict[str, Dict[int, str]] = {}

    def get_secret(self, secret_id: str, version: Optional[int] = None) -> Tuple[str, int]:
        if secret_id not in self._vault:
            raise SecretUnavailableError(f"Secret '{secret_id}' not found in memory vault.")
        versions = self._vault[secret_id]
        ver = version or max(versions.keys())
        if ver not in versions:
            raise SecretUnavailableError(f"Secret '{secret_id}' version {ver} not found in memory vault.")
        return versions[ver], ver

    def store_secret(self, secret_id: str, plaintext: str, version: int = 1) -> SecretVersionRecord:
        if secret_id not in self._vault:
            self._vault[secret_id] = {}
        self._vault[secret_id][version] = plaintext
        return SecretVersionRecord(
            secret_id=secret_id,
            version=version,
            status=SecretStatus.ACTIVE,
            created_at=time.time(),
            activated_at=time.time(),
            retired_at=None,
            fingerprint="mem_vault",
            ciphertext="[MEMORY_ENCLAVE]",
            key_id="memory",
            salt="",
            nonce=""
        )

    def check_health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY

class ProviderManager:
    """Manages prioritized provider chains and strictly prevents plaintext fallback."""

    def __init__(self):
        self._providers: Dict[str, SecretProvider] = {}
        self._priority: List[str] = []

    def register_provider(self, provider: SecretProvider, is_primary: bool = False):
        self._providers[provider.name] = provider
        if is_primary:
            if provider.name in self._priority:
                self._priority.remove(provider.name)
            self._priority.insert(0, provider.name)
        elif provider.name not in self._priority:
            self._priority.append(provider.name)

    def get_provider(self, name: str) -> Optional[SecretProvider]:
        return self._providers.get(name)

    def resolve_secret(self, secret_id: str, preferred_provider: Optional[str] = None, version: Optional[int] = None) -> Tuple[str, int, str]:
        """
        Attempts to resolve secret through preferred provider, then fallback chain.
        Returns: (plaintext, version, provider_name)
        Raises SecretUnavailableError if all secure providers fail.
        """
        chain = []
        if preferred_provider and preferred_provider in self._providers:
            chain.append(preferred_provider)
        for p in self._priority:
            if p not in chain:
                chain.append(p)

        last_err = None
        for p_name in chain:
            provider = self._providers[p_name]
            if provider.check_health() == ProviderHealth.UNAVAILABLE:
                continue
            try:
                plaintext, ver = provider.get_secret(secret_id, version=version)
                return plaintext, ver, p_name
            except Exception as e:
                last_err = e
                continue

        # Strictly fail-closed: NO PLAINTEXT FALLBACK EVER
        raise SecretUnavailableError(f"SECRET_UNAVAILABLE: Failed to resolve '{secret_id}' across providers {chain}. ({last_err})")
