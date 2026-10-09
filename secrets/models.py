import time
import json
import re
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

class SecretType(str, Enum):
    API_KEY = "API_KEY"
    ACCESS_TOKEN = "ACCESS_TOKEN"
    REFRESH_TOKEN = "REFRESH_TOKEN"
    PASSWORD = "PASSWORD"
    SSH_KEY = "SSH_KEY"
    PRIVATE_KEY = "PRIVATE_KEY"
    CERTIFICATE = "CERTIFICATE"
    CLIENT_CERTIFICATE = "CLIENT_CERTIFICATE"
    WEBHOOK_SECRET = "WEBHOOK_SECRET"
    DATABASE_CREDENTIAL = "DATABASE_CREDENTIAL"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"
    SIGNING_KEY = "SIGNING_KEY"
    ENCRYPTION_KEY = "ENCRYPTION_KEY"
    SESSION_SECRET = "SESSION_SECRET"
    OAUTH_CREDENTIAL = "OAUTH_CREDENTIAL"
    CUSTOM = "CUSTOM"

class SecretStatus(str, Enum):
    ACTIVE = "ACTIVE"
    STAGED = "STAGED"
    RETIRED = "RETIRED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    COMPROMISED = "COMPROMISED"
    DISABLED = "DISABLED"

    @property
    def is_usable(self) -> bool:
        return self == SecretStatus.ACTIVE

class TrustLevel(str, Enum):
    UNTRUSTED = "UNTRUSTED"
    LIMITED = "LIMITED"
    TRUSTED = "TRUSTED"
    HIGHLY_TRUSTED = "HIGHLY_TRUSTED"
    SYSTEM_ROOT = "SYSTEM_ROOT"

    @property
    def level_score(self) -> int:
        scores = {
            TrustLevel.UNTRUSTED: 0,
            TrustLevel.LIMITED: 1,
            TrustLevel.TRUSTED: 2,
            TrustLevel.HIGHLY_TRUSTED: 3,
            TrustLevel.SYSTEM_ROOT: 4
        }
        return scores[self]

class ProviderHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    AUTH_FAILED = "AUTH_FAILED"
    MISCONFIGURED = "MISCONFIGURED"

class RotationScheduleType(str, Enum):
    MANUAL = "MANUAL"
    BEFORE_EXPIRATION = "BEFORE_EXPIRATION"
    PERIODIC = "PERIODIC"
    ON_DEMAND = "ON_DEMAND"

SECRET_URI_REGEX = re.compile(r"^secret://(?P<provider>[a-zA-Z0-9_\-\.]+)/(?P<path>[a-zA-Z0-9_\-\./]+)(?:#v(?P<version>\d+))?$")

@dataclass
class SecretReference:
    uri: str
    provider: str
    path: str
    version: Optional[int] = None

    @classmethod
    def parse(cls, uri: str) -> "SecretReference":
        match = SECRET_URI_REGEX.match(uri)
        if not match:
            raise ValueError(f"Invalid secret reference URI: '{uri}'. Must match 'secret://<provider>/<path>[#v<version>]'")
        v_str = match.group("version")
        return cls(
            uri=uri,
            provider=match.group("provider"),
            path=match.group("path"),
            version=int(v_str) if v_str else None
        )

    def canonical_id(self) -> str:
        return f"{self.provider}:{self.path}"

@dataclass
class SecretRecord:
    secret_id: str
    name: str
    secret_type: SecretType
    provider: str
    scope: str = "CLUSTER"
    version: int = 1
    status: SecretStatus = SecretStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_rotated_at: Optional[float] = None
    last_used_at: Optional[float] = None
    rotation_policy: Dict[str, Any] = field(default_factory=dict)
    access_policy: Dict[str, Any] = field(default_factory=dict)
    integrity_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Never exposes plaintext credentials in serialization."""
        return {
            "secret_id": self.secret_id,
            "name": self.name,
            "secret_type": self.secret_type.value,
            "provider": self.provider,
            "scope": self.scope,
            "version": self.version,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "last_rotated_at": self.last_rotated_at,
            "last_used_at": self.last_used_at,
            "rotation_policy": self.rotation_policy,
            "access_policy": self.access_policy,
            "integrity_hash": self.integrity_hash
        }

@dataclass
class SecretVersionRecord:
    secret_id: str
    version: int
    status: SecretStatus
    created_at: float
    activated_at: Optional[float]
    retired_at: Optional[float]
    fingerprint: str
    ciphertext: str
    key_id: str
    salt: str
    nonce: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "secret_id": self.secret_id,
            "version": self.version,
            "status": self.status.value,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "retired_at": self.retired_at,
            "fingerprint": self.fingerprint,
            "key_id": self.key_id
        }

@dataclass
class SecretLease:
    lease_id: str
    secret_id: str
    version: int
    requester: str
    purpose: str
    capability: str
    scope: str = "CLUSTER"
    node_id: str = "local_node"
    issued_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 300.0)
    revoked_at: Optional[float] = None
    status: str = "ACTIVE"

    @property
    def is_valid(self) -> bool:
        return self.status == "ACTIVE" and self.revoked_at is None and time.time() < self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "secret_id": self.secret_id,
            "version": self.version,
            "requester": self.requester,
            "purpose": self.purpose,
            "capability": self.capability,
            "scope": self.scope,
            "node_id": self.node_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "revoked_at": self.revoked_at,
            "status": self.status,
            "is_valid": self.is_valid
        }

@dataclass
class SecretAccessRequest:
    requester_identity: str
    secret_id: str
    purpose: str
    capability: str
    scope: str = "CLUSTER"
    node_id: str = "local_node"
    task_id: Optional[str] = None
    mission_id: Optional[str] = None
    version: Optional[int] = None
    ttl_seconds: float = 300.0

@dataclass
class SecretAuditRecord:
    event_id: str
    secret_id: str
    version: int
    requester: str
    purpose: str
    capability: str
    scope: str
    node_id: str
    action: str  # ACQUIRE, ROTATE, REVOKE, COMPROMISE, EXPIRE, STAGE
    result: str  # GRANTED, DENIED, SUCCESS, FAILED
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "secret_id": self.secret_id,
            "version": self.version,
            "requester": self.requester,
            "purpose": self.purpose,
            "capability": self.capability,
            "scope": self.scope,
            "node_id": self.node_id,
            "action": self.action,
            "result": self.result,
            "timestamp": self.timestamp,
            "details": self.details
        }

class SecretHandle:
    """Safe, scoped access wrapper that prevents casual string leakage and encourages RAII-style use."""

    def __init__(self, secret_id: str, version: int, lease: SecretLease, plaintext_value: str, release_cb: Optional[Any] = None, is_valid_cb: Optional[Any] = None):
        self.secret_id = secret_id
        self.version = version
        self.lease = lease
        self._value = plaintext_value
        self._released = False
        self._release_cb = release_cb
        self._is_valid_cb = is_valid_cb

    @property
    def is_active(self) -> bool:
        if self._released:
            return False
        if not self.lease.is_valid:
            return False
        if self._is_valid_cb and not self._is_valid_cb(self.lease.lease_id):
            return False
        return True

    def get_raw_value(self) -> str:
        """Access raw value only when valid and lease is active."""
        if not self.is_active:
            raise RuntimeError(f"SecretHandle for '{self.secret_id}' is expired, revoked, or released.")
        return self._value

    def release(self):
        """Releases the handle and zeroes internal reference."""
        if not self._released:
            self._value = ""
            self._released = True
            if self._release_cb:
                self._release_cb(self.lease.lease_id)

    def __enter__(self) -> str:
        return self.get_raw_value()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def __repr__(self) -> str:
        status = "ACTIVE" if self.is_active else "RELEASED"
        return f"<SecretHandle secret_id='{self.secret_id}' v{self.version} lease='{self.lease.lease_id}' status={status}>"

    def __str__(self) -> str:
        return self.__repr__()

@dataclass
class SecretTelemetry:
    total_secrets: int
    active_leases: int
    expiring_soon_count: int
    revoked_count: int
    compromised_count: int
    access_requests_granted: int
    access_requests_denied: int
    rotation_success_count: int
    rotation_failure_count: int
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_secrets": self.total_secrets,
            "active_leases": self.active_leases,
            "expiring_soon_count": self.expiring_soon_count,
            "revoked_count": self.revoked_count,
            "compromised_count": self.compromised_count,
            "access_requests_granted": self.access_requests_granted,
            "access_requests_denied": self.access_requests_denied,
            "rotation_success_count": self.rotation_success_count,
            "rotation_failure_count": self.rotation_failure_count,
            "last_updated": self.last_updated
        }
