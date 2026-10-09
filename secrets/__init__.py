# Forward standard library secrets functions so local package doesn't shadow Python stdlib
import sys as _sys
import os as _os
import importlib.util as _util

_stdlib_file = _os.path.join(_sys.base_prefix, "Lib", "secrets.py")
if not _os.path.exists(_stdlib_file):
    for _p in _sys.path:
        _cand = _os.path.join(_p, "secrets.py")
        if _os.path.exists(_cand) and _cand != _os.path.abspath(__file__):
            _stdlib_file = _cand
            break

if _os.path.exists(_stdlib_file):
    _spec = _util.spec_from_file_location("_stdlib_secrets", _stdlib_file)
    _stdlib = _util.module_from_spec(_spec)
    _spec.loader.exec_module(_stdlib)
    token_hex = _stdlib.token_hex
    token_bytes = _stdlib.token_bytes
    token_urlsafe = _stdlib.token_urlsafe
    choice = _stdlib.choice
    randbelow = _stdlib.randbelow
    randbits = _stdlib.randbits
    compare_digest = _stdlib.compare_digest


from secrets.models import (
    SecretType,
    SecretStatus,
    TrustLevel,
    ProviderHealth,
    RotationScheduleType,
    SecretReference,
    SecretRecord,
    SecretVersionRecord,
    SecretLease,
    SecretAccessRequest,
    SecretAuditRecord,
    SecretHandle,
    SecretTelemetry
)
from secrets.encryption import KeyManager, EncryptionEngine, key_manager, encryption_engine
from secrets.memory_guard import SecureContext, MemoryGuard, memory_guard
from secrets.redaction import RedactionEngine, redaction_engine
from secrets.persistence import SecretPersistence
from secrets.providers import (
    SecretUnavailableError,
    SecretProvider,
    LocalEncryptedStoreProvider,
    EnvironmentSecretProvider,
    MemoryVaultProvider,
    ProviderManager
)
from secrets.access import AccessDeniedError, SecretAccessAuthorizer
from secrets.leases import LeaseManager
from secrets.rotation import RotationEngine
from secrets.revocation import RevocationEngine
from secrets.audit import SecretAuditLogger
from secrets.telemetry import SecretTelemetryCollector
from secrets.service import SecretControlPlaneService

# Authoritative Module 25 Singleton Service
secrets_service = SecretControlPlaneService()

__all__ = [
    "SecretType",
    "SecretStatus",
    "TrustLevel",
    "ProviderHealth",
    "RotationScheduleType",
    "SecretReference",
    "SecretRecord",
    "SecretVersionRecord",
    "SecretLease",
    "SecretAccessRequest",
    "SecretAuditRecord",
    "SecretHandle",
    "SecretTelemetry",
    "KeyManager",
    "EncryptionEngine",
    "key_manager",
    "encryption_engine",
    "SecureContext",
    "MemoryGuard",
    "memory_guard",
    "RedactionEngine",
    "redaction_engine",
    "SecretPersistence",
    "SecretUnavailableError",
    "SecretProvider",
    "LocalEncryptedStoreProvider",
    "EnvironmentSecretProvider",
    "MemoryVaultProvider",
    "ProviderManager",
    "AccessDeniedError",
    "SecretAccessAuthorizer",
    "LeaseManager",
    "RotationEngine",
    "RevocationEngine",
    "SecretAuditLogger",
    "SecretTelemetryCollector",
    "SecretControlPlaneService",
    "secrets_service"
]
