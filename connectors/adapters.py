"""
Provider Adapter Interfaces and Concrete Implementations for Omnia Module 26:
External Integration & Connector Gateway

Provides isolated, provider-specific request preparation, path mapping, and response parsing.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple

from connectors.models import (
    ConnectorDefinition, ConnectorOperation, ConnectorRequest,
    OperationType, CredentialBinding, RateLimitPolicy, RetryPolicy
)


class ProviderAdapter(ABC):
    """Abstract interface implemented by provider-specific adapters."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique provider identifier (e.g. 'github', 'stripe', 'slack', 'custom_rest')."""
        pass

    @abstractmethod
    def get_definition(self) -> ConnectorDefinition:
        """Returns the canonical ConnectorDefinition for this provider."""
        pass

    @abstractmethod
    def prepare_request(
        self,
        operation: ConnectorOperation,
        request: ConnectorRequest
    ) -> Tuple[str, str, Dict[str, str], Optional[Dict[str, Any]], Optional[Any]]:
        """
        Prepares HTTP request parameters:
        Returns (method, path, headers, query_params, body).
        """
        pass


class GitHubAdapter(ProviderAdapter):
    """Adapter for GitHub REST API v3."""

    @property
    def provider_id(self) -> str:
        return "github"

    def get_definition(self) -> ConnectorDefinition:
        ops = {
            "github.repository.get": ConnectorOperation(
                operation_id="github.repository.get",
                name="Get Repository",
                operation_type=OperationType.READ,
                path="/repos/{owner}/{repo}",
                method="GET",
                description="Retrieves metadata for a GitHub repository.",
                output_schema={"required": ["id", "name", "full_name"]}
            ),
            "github.issue.create": ConnectorOperation(
                operation_id="github.issue.create",
                name="Create Issue",
                operation_type=OperationType.WRITE,
                path="/repos/{owner}/{repo}/issues",
                method="POST",
                description="Creates a new issue in a GitHub repository.",
                input_schema={"required": ["title"]},
                output_schema={"required": ["id", "number", "title"]},
                risk_level="MEDIUM",
                idempotent=False
            )
        }
        return ConnectorDefinition(
            connector_id="provider.github",
            provider_id="github",
            name="GitHub Connector",
            version="1.0.0",
            description="GitHub REST API Connector",
            operations=ops,
            default_auth=CredentialBinding(
                auth_type="BEARER",
                header_name="Authorization",
                token_prefix="Bearer "
            ),
            rate_limit_policy=RateLimitPolicy(requests_per_second=10.0, burst_limit=30)
        )

    def prepare_request(
        self,
        operation: ConnectorOperation,
        request: ConnectorRequest
    ) -> Tuple[str, str, Dict[str, str], Optional[Dict[str, Any]], Optional[Any]]:
        path = operation.path
        params = dict(request.parameters)
        for k, v in list(params.items()):
            token = f"{{{k}}}"
            if token in path:
                path = path.replace(token, str(v))
                del params[k]

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Omnia-Connector-Gateway/1.0"
        }
        headers.update(request.headers)

        body = request.body if request.body is not None else (params if operation.method in ("POST", "PUT", "PATCH") else None)
        query = request.query_params if request.query_params else (params if operation.method == "GET" else None)

        return operation.method, path, headers, query, body


class StripeAdapter(ProviderAdapter):
    """Adapter for Stripe Payments REST API."""

    @property
    def provider_id(self) -> str:
        return "stripe"

    def get_definition(self) -> ConnectorDefinition:
        ops = {
            "stripe.customer.retrieve": ConnectorOperation(
                operation_id="stripe.customer.retrieve",
                name="Retrieve Customer",
                operation_type=OperationType.READ,
                path="/v1/customers/{customer_id}",
                method="GET",
                description="Retrieves a customer by customer ID.",
                output_schema={"required": ["id", "object"]}
            ),
            "stripe.payment.create": ConnectorOperation(
                operation_id="stripe.payment.create",
                name="Create Payment Intent",
                operation_type=OperationType.ACTION,
                path="/v1/payment_intents",
                method="POST",
                description="Creates a new payment intent.",
                input_schema={"required": ["amount", "currency"]},
                output_schema={"required": ["id", "amount", "currency", "status"]},
                risk_level="HIGH",
                requires_approval=True,
                idempotent=True  # Supports Idempotency-Key header
            )
        }
        return ConnectorDefinition(
            connector_id="provider.stripe",
            provider_id="stripe",
            name="Stripe Connector",
            version="1.0.0",
            description="Stripe Financial and Payments API",
            operations=ops,
            default_auth=CredentialBinding(
                auth_type="BEARER",
                header_name="Authorization",
                token_prefix="Bearer "
            ),
            risk_profile="HIGH"
        )

    def prepare_request(
        self,
        operation: ConnectorOperation,
        request: ConnectorRequest
    ) -> Tuple[str, str, Dict[str, str], Optional[Dict[str, Any]], Optional[Any]]:
        path = operation.path
        params = dict(request.parameters)
        for k, v in list(params.items()):
            token = f"{{{k}}}"
            if token in path:
                path = path.replace(token, str(v))
                del params[k]

        headers = {
            "User-Agent": "Omnia-Stripe-Connector/1.0"
        }
        if request.context.idempotency_key:
            headers["Idempotency-Key"] = request.context.idempotency_key
        headers.update(request.headers)

        body = request.body if request.body is not None else params
        return operation.method, path, headers, request.query_params, body


class SlackAdapter(ProviderAdapter):
    """Adapter for Slack Web API."""

    @property
    def provider_id(self) -> str:
        return "slack"

    def get_definition(self) -> ConnectorDefinition:
        ops = {
            "slack.chat.postMessage": ConnectorOperation(
                operation_id="slack.chat.postMessage",
                name="Post Chat Message",
                operation_type=OperationType.ACTION,
                path="/api/chat.postMessage",
                method="POST",
                description="Posts a message to a Slack channel.",
                input_schema={"required": ["channel", "text"]},
                output_schema={"required": ["ok"]},
                risk_level="LOW"
            )
        }
        return ConnectorDefinition(
            connector_id="provider.slack",
            provider_id="slack",
            name="Slack Connector",
            version="1.0.0",
            description="Slack Web API Connector",
            operations=ops,
            default_auth=CredentialBinding(
                auth_type="BEARER",
                header_name="Authorization",
                token_prefix="Bearer "
            )
        )

    def prepare_request(
        self,
        operation: ConnectorOperation,
        request: ConnectorRequest
    ) -> Tuple[str, str, Dict[str, str], Optional[Dict[str, Any]], Optional[Any]]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        headers.update(request.headers)
        body = request.body if request.body is not None else request.parameters
        return operation.method, operation.path, headers, request.query_params, body


class CustomRESTAdapter(ProviderAdapter):
    """Generic adapter for custom and user-defined HTTP REST services."""

    def __init__(self, definition: ConnectorDefinition):
        self._definition = definition

    @property
    def provider_id(self) -> str:
        return self._definition.provider_id

    def get_definition(self) -> ConnectorDefinition:
        return self._definition

    def prepare_request(
        self,
        operation: ConnectorOperation,
        request: ConnectorRequest
    ) -> Tuple[str, str, Dict[str, str], Optional[Dict[str, Any]], Optional[Any]]:
        path = operation.path
        params = dict(request.parameters)
        for k, v in list(params.items()):
            token = f"{{{k}}}"
            if token in path:
                path = path.replace(token, str(v))
                del params[k]

        headers = dict(request.headers)
        body = request.body if request.body is not None else (params if operation.method in ("POST", "PUT", "PATCH") else None)
        query = request.query_params if request.query_params else (params if operation.method == "GET" else None)
        return operation.method, path, headers, query, body
