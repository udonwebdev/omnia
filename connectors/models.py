"""
Data Models, Enums, and Contracts for Omnia Module 26:
External Integration & Connector Gateway
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set, Union, Callable


class OperationType(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    ACTION = "ACTION"
    STREAM = "STREAM"
    WEBHOOK = "WEBHOOK"


class Environment(str, Enum):
    SANDBOX = "SANDBOX"
    TEST = "TEST"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


class ConnectorHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    INITIALIZING = "INITIALIZING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"


class ConnectorLifecycle(str, Enum):
    DISCOVERED = "DISCOVERED"
    VALIDATING = "VALIDATING"
    REGISTERED = "REGISTERED"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    DISABLED = "DISABLED"
    REMOVED = "REMOVED"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"


class IdempotencyStatus(str, Enum):
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


@dataclass
class RateLimitPolicy:
    requests_per_second: float = 10.0
    requests_per_minute: float = 600.0
    burst_limit: int = 20
    max_concurrent_requests: int = 5


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_sec: float = 0.5
    backoff_multiplier: float = 2.0
    max_backoff_sec: float = 10.0
    jitter: bool = True
    retryable_status_codes: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])


@dataclass
class TimeoutPolicy:
    connect_timeout_sec: float = 5.0
    read_timeout_sec: float = 15.0
    total_deadline_sec: float = 30.0


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_probe_interval_sec: float = 15.0
    consecutive_success_threshold: int = 2


@dataclass
class CredentialBinding:
    auth_type: str  # "API_KEY", "BEARER", "OAUTH2", "BASIC", "HMAC", "NONE"
    secret_reference: Optional[str] = None  # URI like "secret://local_encrypted/github_token"
    header_name: str = "Authorization"
    token_prefix: str = "Bearer "
    query_param_name: Optional[str] = None
    hmac_header_name: str = "X-Omnia-Signature"


@dataclass
class ConnectorOperation:
    operation_id: str  # e.g., "github.repository.list", "stripe.payment.create"
    name: str
    operation_type: OperationType
    path: str  # URL path or path template, e.g. "/repos/{owner}/{repo}"
    method: str = "GET"  # "GET", "POST", "PUT", "PATCH", "DELETE"
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    required_scopes: List[str] = field(default_factory=list)
    risk_level: str = "LOW"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    idempotent: bool = True
    requires_approval: bool = False
    rate_limit: Optional[RateLimitPolicy] = None
    retry_policy: Optional[RetryPolicy] = None
    timeout: Optional[TimeoutPolicy] = None
    data_classification: DataClassification = DataClassification.INTERNAL


@dataclass
class ConnectorDefinition:
    connector_id: str  # e.g. "provider.github", "provider.stripe"
    provider_id: str  # e.g. "github", "stripe"
    name: str
    version: str = "1.0.0"
    description: str = ""
    supported_protocols: List[str] = field(default_factory=lambda: ["HTTP"])
    risk_profile: str = "MEDIUM"
    schema_version: str = "1.0.0"
    operations: Dict[str, ConnectorOperation] = field(default_factory=dict)
    default_auth: Optional[CredentialBinding] = None
    rate_limit_policy: RateLimitPolicy = field(default_factory=RateLimitPolicy)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_policy: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    circuit_breaker_config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    status: ConnectorLifecycle = ConnectorLifecycle.REGISTERED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class ConnectorInstance:
    instance_id: str  # e.g. "github.production", "stripe.sandbox"
    connector_id: str
    environment: Environment = Environment.SANDBOX
    base_url: str = ""
    status: ConnectorLifecycle = ConnectorLifecycle.INITIALIZING
    credential_reference: Optional[str] = None
    config_reference: Optional[str] = None
    health: ConnectorHealth = ConnectorHealth.UNKNOWN
    health_message: Optional[str] = None
    last_health_check: Optional[float] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class RequestContext:
    request_id: str = field(default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}")
    task_id: Optional[str] = None
    mission_id: Optional[str] = None
    node_id: str = "local_node"
    actor_id: str = "omnia_system"
    purpose: str = "external_query"
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    deadline_ts: Optional[float] = None
    fencing_epoch: Optional[int] = None
    idempotency_key: Optional[str] = None
    environment: Environment = Environment.SANDBOX


@dataclass
class ConnectorRequest:
    operation_id: str
    instance_id: str
    context: RequestContext
    parameters: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[Any] = None
    query_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorResponse:
    request_id: str
    operation_id: str
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    body: Any = None
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    verification_details: Dict[str, Any] = field(default_factory=dict)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    latency_ms: float = 0.0
    attempts_made: int = 1
    cached_idempotent: bool = False


@dataclass
class WebhookEndpoint:
    webhook_id: str
    endpoint_path: str
    provider_id: str
    secret_reference: Optional[str] = None
    verification_algorithm: str = "HMAC_SHA256"
    max_payload_bytes: int = 1048576  # 1MB
    replay_window_sec: float = 300.0  # 5 minutes
    status: str = "ACTIVE"
    created_at: float = field(default_factory=time.time)
    last_event_at: Optional[float] = None


@dataclass
class WebhookEvent:
    event_id: str
    webhook_id: str
    provider_id: str
    raw_payload: bytes
    headers: Dict[str, str]
    received_at: float = field(default_factory=time.time)
    provider_event_id: Optional[str] = None
    signature_verified: bool = False
    normalized_type: str = "external.generic.event"
    normalized_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PaginationState:
    page_number: int = 1
    page_size: int = 50
    next_cursor: Optional[str] = None
    has_more: bool = False
    max_pages: int = 10
    total_records_retrieved: int = 0


@dataclass
class IdempotencyRecord:
    idempotency_key: str
    operation_id: str
    instance_id: str
    task_id: Optional[str]
    status: IdempotencyStatus
    request_hash: str
    response_payload: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 86400.0)


@dataclass
class ConnectorTelemetry:
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    uncertain_count: int = 0
    retry_count: int = 0
    rate_limit_count: int = 0
    circuit_open_count: int = 0
    webhook_count: int = 0
    webhook_rejected_count: int = 0
    total_latency_ms: float = 0.0
