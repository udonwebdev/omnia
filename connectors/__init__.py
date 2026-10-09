"""
Omnia Module 26: External Integration & Connector Gateway

Authoritative subsystem for secure external connectivity, provider adapters,
SSRF defense, rate limiting, circuit breaking, idempotency, response verification,
and inbound webhook processing.
"""

from connectors.models import (
    OperationType,
    Environment,
    ConnectorHealth,
    ConnectorLifecycle,
    CircuitState,
    VerificationStatus,
    DataClassification,
    IdempotencyStatus,
    RateLimitPolicy,
    RetryPolicy,
    TimeoutPolicy,
    CircuitBreakerConfig,
    CredentialBinding,
    ConnectorOperation,
    ConnectorDefinition,
    ConnectorInstance,
    RequestContext,
    ConnectorRequest,
    ConnectorResponse,
    WebhookEndpoint,
    WebhookEvent,
    PaginationState,
    IdempotencyRecord,
    ConnectorTelemetry
)

from connectors.ssrf import (
    SSRFValidator,
    SSRFValidationError,
    ssrf_validator
)

from connectors.transport import (
    SecureTransport,
    secure_transport
)

from connectors.auth import (
    ConnectorAuthAdapter,
    connector_auth_adapter
)

from connectors.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    circuit_breaker_registry
)

from connectors.rate_limiter import (
    TokenBucketLimiter,
    RateLimiterRegistry,
    RateLimitExceededError,
    rate_limiter_registry
)

from connectors.retries import (
    RetryDecisionEngine,
    retry_engine
)

from connectors.idempotency import (
    IdempotencyManager
)

from connectors.verification import (
    ResponseVerifier,
    response_verifier
)

from connectors.webhooks import (
    WebhookGateway,
    webhook_gateway
)

from connectors.policy_guard import (
    ConnectorPolicyGuard,
    PolicyBlockedError,
    ApprovalRequiredError,
    FencingViolationError,
    connector_policy_guard
)

from connectors.persistence import (
    ConnectorPersistence
)

from connectors.adapters import (
    ProviderAdapter,
    GitHubAdapter,
    StripeAdapter,
    SlackAdapter,
    CustomRESTAdapter
)

from connectors.service import (
    ConnectorGatewayService,
    connector_gateway
)

__all__ = [
    # Models
    "OperationType",
    "Environment",
    "ConnectorHealth",
    "ConnectorLifecycle",
    "CircuitState",
    "VerificationStatus",
    "DataClassification",
    "IdempotencyStatus",
    "RateLimitPolicy",
    "RetryPolicy",
    "TimeoutPolicy",
    "CircuitBreakerConfig",
    "CredentialBinding",
    "ConnectorOperation",
    "ConnectorDefinition",
    "ConnectorInstance",
    "RequestContext",
    "ConnectorRequest",
    "ConnectorResponse",
    "WebhookEndpoint",
    "WebhookEvent",
    "PaginationState",
    "IdempotencyRecord",
    "ConnectorTelemetry",

    # Components
    "SSRFValidator",
    "SSRFValidationError",
    "ssrf_validator",
    "SecureTransport",
    "secure_transport",
    "ConnectorAuthAdapter",
    "connector_auth_adapter",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "circuit_breaker_registry",
    "TokenBucketLimiter",
    "RateLimiterRegistry",
    "RateLimitExceededError",
    "rate_limiter_registry",
    "RetryDecisionEngine",
    "retry_engine",
    "IdempotencyManager",
    "ResponseVerifier",
    "response_verifier",
    "WebhookGateway",
    "webhook_gateway",
    "ConnectorPolicyGuard",
    "PolicyBlockedError",
    "ApprovalRequiredError",
    "FencingViolationError",
    "connector_policy_guard",
    "ConnectorPersistence",

    # Adapters
    "ProviderAdapter",
    "GitHubAdapter",
    "StripeAdapter",
    "SlackAdapter",
    "CustomRESTAdapter",

    # Service & Gateway
    "ConnectorGatewayService",
    "connector_gateway"
]
