"""
Connector Gateway Service for Omnia Module 26:
External Integration & Connector Gateway

Authoritative orchestrator for external connectivity, provider adapters,
rate limiting, circuit breaking, idempotency, security boundaries, and telemetry.
"""

import time
import uuid
import logging
from typing import Dict, Any, Optional, List, Tuple

from connectors.models import (
    ConnectorDefinition, ConnectorInstance, ConnectorOperation,
    ConnectorRequest, ConnectorResponse, RequestContext,
    ConnectorHealth, ConnectorLifecycle, CircuitState, VerificationStatus,
    IdempotencyStatus, ConnectorTelemetry, OperationType, Environment
)
from connectors.transport import secure_transport, SecureTransport
from connectors.auth import connector_auth_adapter, ConnectorAuthAdapter
from connectors.circuit_breaker import circuit_breaker_registry, CircuitOpenError
from connectors.rate_limiter import rate_limiter_registry, RateLimitExceededError
from connectors.retries import retry_engine, RetryDecisionEngine
from connectors.idempotency import IdempotencyManager
from connectors.verification import response_verifier, ResponseVerifier
from connectors.webhooks import webhook_gateway, WebhookGateway
from connectors.policy_guard import connector_policy_guard, ConnectorPolicyGuard, PolicyBlockedError
from connectors.persistence import ConnectorPersistence
from connectors.adapters import (
    ProviderAdapter, GitHubAdapter, StripeAdapter, SlackAdapter, CustomRESTAdapter
)
from events.models import Event, EventEnvelope
from events.fabric import event_fabric

logger = logging.getLogger("Omnia.Connectors.Gateway")


class ConnectorGatewayService:
    """Production gateway coordinating all external API integrations."""

    def __init__(
        self,
        persistence: Optional[ConnectorPersistence] = None,
        node_id: str = "local_node"
    ):
        self.node_id = node_id
        self.persistence = persistence or ConnectorPersistence()
        self.transport = secure_transport
        self.auth_adapter = connector_auth_adapter
        self.policy_guard = connector_policy_guard
        self.idempotency_mgr = IdempotencyManager(self.persistence)
        self.verifier = response_verifier
        self.webhooks = webhook_gateway
        self.webhooks.persistence = self.persistence

        self._definitions: Dict[str, ConnectorDefinition] = {}
        self._instances: Dict[str, ConnectorInstance] = {}
        self._adapters: Dict[str, ProviderAdapter] = {}
        self.telemetry = ConnectorTelemetry()

        # Register standard built-in provider adapters
        self.register_adapter(GitHubAdapter())
        self.register_adapter(StripeAdapter())
        self.register_adapter(SlackAdapter())

        # Load persisted definitions and instances if available
        self._load_from_persistence()

    def _load_from_persistence(self):
        try:
            defs = self.persistence.list_connector_definitions()
            for d in defs:
                if d.connector_id not in self._definitions:
                    self._definitions[d.connector_id] = d
        except Exception as e:
            logger.debug(f"Could not load connector definitions from DB: {e}")

    # --- Adapter & Connector Management ---
    def register_adapter(self, adapter: ProviderAdapter):
        """Registers a provider adapter and its canonical connector definition."""
        self._adapters[adapter.provider_id] = adapter
        definition = adapter.get_definition()
        self.register_connector(definition)

    def register_connector(self, definition: ConnectorDefinition) -> bool:
        """Registers a connector definition into catalog and syncs with Module 17."""
        self._definitions[definition.connector_id] = definition
        self.persistence.save_connector_definition(definition)

        # Sync capabilities into Module 17 Capability Registry
        self._sync_capabilities(definition)

        self._emit_event("connector.registered", {
            "connector_id": definition.connector_id,
            "provider_id": definition.provider_id,
            "version": definition.version
        })
        logger.info(f"Registered connector definition: '{definition.connector_id}' (Provider: {definition.provider_id}).")
        return True

    def get_connector(self, connector_id: str) -> Optional[ConnectorDefinition]:
        return self._definitions.get(connector_id)

    def list_connectors(self) -> List[ConnectorDefinition]:
        return list(self._definitions.values())

    # --- Instance Management ---
    def create_instance(
        self,
        instance_id: str,
        connector_id: str,
        base_url: str,
        environment: Environment = Environment.SANDBOX,
        credential_reference: Optional[str] = None,
        config_reference: Optional[str] = None
    ) -> ConnectorInstance:
        """Configures and activates an instance of a registered connector."""
        defn = self.get_connector(connector_id)
        if not defn:
            raise ValueError(f"Unknown connector definition: '{connector_id}'.")

        instance = ConnectorInstance(
            instance_id=instance_id,
            connector_id=connector_id,
            environment=environment,
            base_url=base_url.rstrip("/"),
            status=ConnectorLifecycle.READY,
            credential_reference=credential_reference or (defn.default_auth.secret_reference if defn.default_auth else None),
            config_reference=config_reference,
            health=ConnectorHealth.HEALTHY,
            created_at=time.time(),
            updated_at=time.time()
        )
        self._instances[instance_id] = instance
        self.persistence.save_connector_instance(instance)

        self._emit_event("connector.ready", {
            "instance_id": instance_id,
            "connector_id": connector_id,
            "environment": environment.value
        })
        logger.info(f"Created connector instance '{instance_id}' for '{connector_id}' at {base_url}.")
        return instance

    def get_instance(self, instance_id: str) -> Optional[ConnectorInstance]:
        if instance_id not in self._instances:
            inst = self.persistence.get_connector_instance(instance_id)
            if inst:
                self._instances[instance_id] = inst
        return self._instances.get(instance_id)

    def list_instances(self) -> List[ConnectorInstance]:
        return list(self._instances.values())

    # --- Capability Registry Integration (Module 17) ---
    def _sync_capabilities(self, definition: ConnectorDefinition):
        """Registers connector operations into Module 17 Capability Registry."""
        try:
            from capabilities.registry import CapabilityRegistry
            from capabilities.models import (
                Capability, CapabilityProvider, CapabilityCategory,
                CapabilityHealth, RiskLevel, SideEffectType, IdempotencyType
            )
            # Register each operation as external.<connector_id>.<operation_id>
            for op_id, op in definition.operations.items():
                cap_id = f"external.{op_id}"
                cap = Capability(
                    id=cap_id,
                    name=op.name,
                    version="1.0.0",
                    description=op.description or f"External connector operation for {op_id}",
                    category=CapabilityCategory.CONNECTOR,
                    input_schema=op.input_schema,
                    output_schema=op.output_schema,
                    provider=CapabilityProvider(
                        provider_id=f"connector.{definition.provider_id}",
                        name=f"{definition.name} Provider",
                        version=definition.version
                    ),
                    health=CapabilityHealth.HEALTHY,
                    risk_level=RiskLevel[op.risk_level] if hasattr(RiskLevel, op.risk_level) else RiskLevel.LOW,
                    side_effect=SideEffectType.READ if op.operation_type == OperationType.READ else SideEffectType.WRITE,
                    idempotency=IdempotencyType.IDEMPOTENT if op.idempotent else IdempotencyType.NON_IDEMPOTENT
                )
                from omnia_core import capability_registry
                capability_registry.register_capability(cap, auth_key="core")
        except Exception as e:
            logger.debug(f"Capability sync for '{definition.connector_id}' bypassed: {e}")

    # --- Operation Execution Pipeline ---
    async def execute_operation(self, request: ConnectorRequest) -> ConnectorResponse:
        """Alias for execute to support explicit semantic calls."""
        return await self.execute(request)

    async def execute(self, request: ConnectorRequest) -> ConnectorResponse:
        """
        Executes a typed connector request through the complete gateway pipeline.
        """
        instance = self.get_instance(request.instance_id)
        if not instance:
            raise ValueError(f"Unknown connector instance: '{request.instance_id}'.")

        definition = self.get_connector(instance.connector_id)
        if not definition:
            raise ValueError(f"Unknown connector definition: '{instance.connector_id}'.")

        operation = definition.operations.get(request.operation_id)
        if not operation:
            raise ValueError(f"Operation '{request.operation_id}' not found in connector '{definition.connector_id}'.")

        self.telemetry.request_count += 1
        t0 = time.perf_counter()

        # 1. Circuit Breaker Evaluation
        breaker = circuit_breaker_registry.get_breaker(definition.connector_id, definition.circuit_breaker_config)
        can_exec, breaker_reason = breaker.can_execute()
        if not can_exec:
            self.telemetry.circuit_open_count += 1
            self._emit_event("connector.circuit_opened", {
                "connector_id": definition.connector_id,
                "failure_count": breaker.failure_count,
                "reason": breaker_reason
            })
            raise CircuitOpenError(f"Request blocked by Circuit Breaker for '{definition.connector_id}': {breaker_reason}")

        # 2. Rate Limiting Check
        limiter = rate_limiter_registry.get_limiter(request.instance_id, definition.rate_limit_policy)
        allowed, wait_sec = limiter.acquire()
        if not allowed:
            self.telemetry.rate_limit_count += 1
            self._emit_event("connector.rate_limited", {
                "connector_id": definition.connector_id,
                "instance_id": request.instance_id,
                "retry_after_sec": wait_sec
            })
            raise RateLimitExceededError(f"Rate limit exceeded for instance '{request.instance_id}'. Retry in {wait_sec:.2f}s.", retry_after_sec=wait_sec)

        try:
            # 3. Policy & Approval Guard (Module 09 + Module 20 + Module 22)
            target_url = f"{instance.base_url}{operation.path}"
            await self.policy_guard.authorize_operation(operation, request.context, target_url, request.parameters)

            # 4. Idempotency Check & Reservation
            idemp_key = request.context.idempotency_key
            req_hash = IdempotencyManager.compute_request_hash(operation.operation_id, request.parameters, request.body)

            if idemp_key:
                can_proceed, cached_resp, idemp_status = self.idempotency_mgr.check_or_reserve(
                    idempotency_key=idemp_key,
                    operation_id=operation.operation_id,
                    instance_id=request.instance_id,
                    request_hash=req_hash,
                    task_id=request.context.task_id
                )
                if not can_proceed:
                    if cached_resp:
                        logger.info(f"IDEMPOTENT_HIT: Returning cached response for key '{idemp_key}'.")
                        return cached_resp
                    elif idemp_status == "IN_FLIGHT_CONFLICT":
                        raise RuntimeError(f"Concurrent in-flight execution conflict for idempotency key '{idemp_key}'.")

            # 5. Prepare Request via Provider Adapter
            adapter = self._adapters.get(definition.provider_id) or CustomRESTAdapter(definition)
            method, rel_path, req_headers, req_query, req_body = adapter.prepare_request(operation, request)
            full_url = f"{instance.base_url}{rel_path}"

            # 6. Authenticate Request via Module 25 Secret Handle
            auth_binding = definition.default_auth
            if instance.credential_reference and auth_binding:
                auth_binding.secret_reference = instance.credential_reference

            # Retry Loop Execution
            attempt = 0
            final_resp = None
            retry_policy = operation.retry_policy or definition.retry_policy

            while True:
                attempt += 1
                with self.auth_adapter.authenticate_request(
                    binding=auth_binding,
                    context=request.context,
                    headers=req_headers,
                    query_params=req_query or {},
                    body=req_body
                ) as (bound_headers, bound_query):

                    # Dispatch HTTP Request via SecureTransport
                    status_code, resp_headers, resp_body, latency_ms, timed_out = await self.transport.execute_http_request(
                        method=method,
                        url=full_url,
                        headers=bound_headers,
                        params=bound_query,
                        json_body=req_body if isinstance(req_body, dict) else None,
                        data_body=req_body if not isinstance(req_body, dict) else None,
                        timeout=operation.timeout or definition.timeout_policy
                    )

                # Check if retryable failure occurred
                retry_after_hdr = resp_headers.get("retry-after") if resp_headers else None
                if retry_after_hdr:
                    try:
                        limiter.handle_retry_after(float(retry_after_hdr))
                    except ValueError:
                        pass

                is_retryable_op, op_reason = RetryDecisionEngine.is_retryable_operation(operation, has_idempotency_key=bool(idemp_key))
                should_retry, retry_delay, retry_reason = False, 0.0, ""

                if not (200 <= status_code < 300) or timed_out:
                    if is_retryable_op:
                        should_retry, retry_delay, retry_reason = RetryDecisionEngine.should_retry(
                            status_code=status_code,
                            attempt=attempt,
                            policy=retry_policy,
                            deadline_ts=request.context.deadline_ts,
                            retry_after_header=retry_after_hdr
                        )

                if should_retry:
                    self.telemetry.retry_count += 1
                    logger.warning(f"RETRYING_OPERATION: {operation.operation_id} failed with {status_code}. Retrying in {retry_delay:.2f}s ({retry_reason}).")
                    import asyncio
                    await asyncio.sleep(retry_delay)
                    continue

                # 7. Response Verification & Business Validation
                ver_status, ver_details, ver_err = self.verifier.verify_response(
                    operation=operation,
                    status_code=status_code,
                    response_body=resp_body,
                    timed_out=timed_out
                )

                final_resp = ConnectorResponse(
                    request_id=request.context.request_id,
                    operation_id=operation.operation_id,
                    status_code=status_code,
                    headers=resp_headers,
                    body=resp_body,
                    verification_status=ver_status,
                    verification_details=ver_details,
                    error_type="VERIFICATION_FAILED" if ver_err else None,
                    error_message=ver_err,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    attempts_made=attempt
                )
                break

            # 8. Circuit Breaker & Telemetry Updates
            if final_resp.verification_status == VerificationStatus.VERIFIED:
                breaker.record_success()
                self.telemetry.success_count += 1
            elif final_resp.verification_status == VerificationStatus.UNCERTAIN:
                breaker.record_failure(final_resp.error_message or "Uncertain state")
                self.telemetry.uncertain_count += 1
                self._emit_event("connector.request.uncertain", {
                    "request_id": request.context.request_id,
                    "connector_id": definition.connector_id,
                    "operation_id": operation.operation_id,
                    "reason": final_resp.error_message or "UNCERTAIN"
                })
            else:
                breaker.record_failure(final_resp.error_message or f"HTTP {final_resp.status_code}")
                self.telemetry.failure_count += 1
                self._emit_event("connector.request.failed", {
                    "request_id": request.context.request_id,
                    "connector_id": definition.connector_id,
                    "operation_id": operation.operation_id,
                    "error_type": final_resp.error_type or "HTTP_ERROR",
                    "error_message": final_resp.error_message or f"Failed with {final_resp.status_code}"
                })

            # 9. Idempotency Record Completion
            if idemp_key:
                idemp_final_status = (
                    IdempotencyStatus.COMPLETED if final_resp.verification_status == VerificationStatus.VERIFIED
                    else (IdempotencyStatus.UNCERTAIN if final_resp.verification_status == VerificationStatus.UNCERTAIN else IdempotencyStatus.FAILED)
                )
                self.idempotency_mgr.record_completion(idemp_key, final_resp, idemp_final_status)

            self.telemetry.total_latency_ms += final_resp.latency_ms

            self._emit_event("connector.request.completed", {
                "request_id": request.context.request_id,
                "connector_id": definition.connector_id,
                "operation_id": operation.operation_id,
                "status_code": final_resp.status_code,
                "verification_status": final_resp.verification_status.value
            })

            return final_resp

        finally:
            limiter.release()

    # Convenience shortcuts
    async def execute_read(self, operation_id: str, instance_id: str, parameters: Dict[str, Any], **kwargs) -> ConnectorResponse:
        ctx = RequestContext(purpose="read_query", **kwargs)
        req = ConnectorRequest(operation_id=operation_id, instance_id=instance_id, context=ctx, parameters=parameters)
        return await self.execute(req)

    async def execute_write(self, operation_id: str, instance_id: str, parameters: Dict[str, Any], body: Any = None, **kwargs) -> ConnectorResponse:
        ctx = RequestContext(purpose="write_mutation", **kwargs)
        req = ConnectorRequest(operation_id=operation_id, instance_id=instance_id, context=ctx, parameters=parameters, body=body)
        return await self.execute(req)

    async def execute_action(self, operation_id: str, instance_id: str, parameters: Dict[str, Any], **kwargs) -> ConnectorResponse:
        ctx = RequestContext(purpose="action_execution", **kwargs)
        req = ConnectorRequest(operation_id=operation_id, instance_id=instance_id, context=ctx, parameters=parameters)
        return await self.execute(req)

    # Health Checks
    async def check_health(self, instance_id: str) -> ConnectorHealth:
        """Probes instance health and updates status."""
        instance = self.get_instance(instance_id)
        if not instance:
            return ConnectorHealth.UNKNOWN

        # Check circuit breaker
        breaker = circuit_breaker_registry.get_breaker(instance.connector_id)
        if breaker.state == CircuitState.OPEN:
            instance.health = ConnectorHealth.DEGRADED
            instance.health_message = "Circuit breaker is OPEN."
        else:
            instance.health = ConnectorHealth.HEALTHY
            instance.health_message = "Operational"

        instance.last_health_check = time.time()
        self.persistence.save_connector_instance(instance)
        return instance.health

    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        """Publishes typed metadata events to Event Fabric with zero plaintext secrets."""
        try:
            import asyncio
            evt = Event(
                envelope=EventEnvelope(
                    event_type=event_type,
                    source=f"connectors.gateway.{self.node_id}"
                ),
                payload=payload
            )
            async def _pub():
                await event_fabric.publish(evt)
                await event_fabric._dispatch_lanes()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_pub())
                else:
                    loop.run_until_complete(_pub())
            except RuntimeError:
                asyncio.run(_pub())
        except Exception as e:
            logger.debug(f"Event emission for '{event_type}' bypassed: {e}")


# Singleton instance
connector_gateway = ConnectorGatewayService()
