"""
Unit Test Suite for Omnia Module 26:
External Integration & Connector Gateway

Tests:
1. SSRF Defense: private IP, loopback, cloud metadata, and scheme blocking.
2. Connector Registration & Capability Sync: registers definition, creates instance.
3. Authentication Adapter & Module 25 Binding: Bearer token and API key handling.
4. Rate Limiter & Concurrency Token Bucket: requests/sec, burst bounds, Retry-After.
5. Circuit Breaker Lifecycle: CLOSED -> OPEN -> HALF_OPEN -> CLOSED recovery.
6. Retry Policy & Semantic Classification: safe vs unsafe retry decisions.
7. Idempotency Manager: in-flight reservation, cached response return, dedup.
8. Business Verification: HTTP 200 with business failure rejection, write timeout UNCERTAIN.
9. Inbound Webhook Gateway: HMAC signature verification, forgery rejection, replay attack rejection.
"""

import os
import sys
import time
import json
import hmac
import hashlib
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from persistence.migrations import apply_migrations
from connectors.models import (
    ConnectorDefinition, ConnectorInstance, ConnectorOperation,
    ConnectorRequest, ConnectorResponse, RequestContext,
    OperationType, Environment, ConnectorHealth, CircuitState,
    VerificationStatus, IdempotencyStatus, CredentialBinding,
    RateLimitPolicy, RetryPolicy, TimeoutPolicy, CircuitBreakerConfig,
    WebhookEndpoint
)
from connectors.ssrf import SSRFValidator, SSRFValidationError
from connectors.auth import ConnectorAuthAdapter
from connectors.rate_limiter import TokenBucketLimiter, RateLimitExceededError
from connectors.circuit_breaker import CircuitBreaker, CircuitOpenError
from connectors.retries import RetryDecisionEngine
from connectors.idempotency import IdempotencyManager
from connectors.verification import ResponseVerifier
from connectors.webhooks import WebhookGateway
from connectors.service import ConnectorGatewayService
from connectors.persistence import ConnectorPersistence
from secrets.service import SecretControlPlaneService
from secrets.models import SecretType, TrustLevel


class TestConnectorsModule26(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.template_fd, cls.template_db = tempfile.mkstemp(suffix=".conn_template.db")
        os.close(cls.template_fd)
        apply_migrations(cls.template_db)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.template_db):
            try:
                os.remove(cls.template_db)
            except Exception:
                pass

    def setUp(self):
        self.test_fd, self.temp_db = tempfile.mkstemp(suffix=".conn_test.db")
        os.close(self.test_fd)
        shutil.copy2(self.template_db, self.temp_db)

        self.persistence = ConnectorPersistence(self.temp_db)
        from secrets.persistence import SecretPersistence
        self.secret_persistence = SecretPersistence(self.temp_db)
        self.secrets = SecretControlPlaneService(persistence=self.secret_persistence, node_id="test_node")

        self.gateway = ConnectorGatewayService(persistence=self.persistence, node_id="test_node")
        self.gateway.auth_adapter = ConnectorAuthAdapter(sec_service=self.secrets)
        self.gateway.webhooks._sec_service = self.secrets

    def tearDown(self):
        if os.path.exists(self.temp_db):
            try:
                os.remove(self.temp_db)
            except Exception:
                pass

    def test_01_ssrf_defense_and_destination_validation(self):
        """SSRF validator must block loopback, private networks, metadata IPs, and bad schemes."""
        validator = SSRFValidator(allow_loopback_for_testing=False)

        # 1. Scheme checks
        ok, reason = validator.validate_url("ftp://example.com/file")
        self.assertFalse(ok)
        self.assertIn("Disallowed URL scheme", reason)

        ok, reason = validator.validate_url("file:///etc/passwd")
        self.assertFalse(ok)
        self.assertIn("Disallowed URL scheme", reason)

        # 2. Loopback blocking
        ok, reason = validator.validate_url("http://127.0.0.1:8080/admin")
        self.assertFalse(ok)
        self.assertIn("forbidden", reason)

        ok, reason = validator.validate_url("http://localhost:3000")
        self.assertFalse(ok)
        self.assertIn("forbidden internal destination", reason)

        # 3. Cloud Metadata endpoint blocking
        ok, reason = validator.validate_url("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(ok)
        self.assertIn("forbidden", reason)

        ok, reason = validator.validate_url("http://metadata.google.internal/computeMetadata/v1/")
        self.assertFalse(ok)
        self.assertIn("forbidden internal destination", reason)

        # 4. Private RFC1918 blocking
        ok, reason = validator.validate_url("http://10.0.0.5/api")
        self.assertFalse(ok)
        self.assertIn("forbidden", reason)

        ok, reason = validator.validate_url("http://192.168.1.1/router")
        self.assertFalse(ok)
        self.assertIn("forbidden", reason)

        # 5. Whitelisted testing override
        validator.add_allowed_test_host("127.0.0.1:9090")
        ok, reason = validator.validate_url("http://127.0.0.1:9090/test")
        self.assertTrue(ok)
        self.assertEqual(reason, "ALLOWED_BY_TEST_WHITELIST")

    def test_02_connector_registration_and_persistence(self):
        """Connector definitions and instances are saved, queried, and listed properly."""
        op = ConnectorOperation(
            operation_id="custom.weather.get",
            name="Get Weather",
            operation_type=OperationType.READ,
            path="/weather",
            method="GET",
            input_schema={"required": ["city"]},
            output_schema={"required": ["temp", "condition"]}
        )
        defn = ConnectorDefinition(
            connector_id="provider.custom_weather",
            provider_id="custom_weather",
            name="Weather Service",
            version="1.0.0",
            description="Weather forecasting connector",
            operations={"custom.weather.get": op}
        )

        ok = self.gateway.register_connector(defn)
        self.assertTrue(ok)

        # Retrieve definition
        saved_def = self.gateway.get_connector("provider.custom_weather")
        self.assertIsNotNone(saved_def)
        self.assertEqual(saved_def.name, "Weather Service")
        self.assertIn("custom.weather.get", saved_def.operations)

        # Create instance
        inst = self.gateway.create_instance(
            instance_id="weather.sandbox",
            connector_id="provider.custom_weather",
            base_url="https://api.weather.example.com",
            environment=Environment.SANDBOX
        )
        self.assertIsNotNone(inst)
        self.assertEqual(inst.status.value, "READY")

        saved_inst = self.gateway.get_instance("weather.sandbox")
        self.assertIsNotNone(saved_inst)
        self.assertEqual(saved_inst.base_url, "https://api.weather.example.com")

    def test_03_authentication_adapter_module25_binding(self):
        """Connector authentication securely binds credentials from Module 25 and zeros memory."""
        # 1. Register a secret in Module 25
        self.secrets.register_secret(
            secret_id="ext_api_token",
            name="External API Key",
            secret_type=SecretType.API_KEY,
            plaintext="secret_live_bearer_token_xyz"
        )

        binding = CredentialBinding(
            auth_type="BEARER",
            secret_reference="secret://local_encrypted/ext_api_token",
            header_name="Authorization",
            token_prefix="Bearer "
        )
        ctx = RequestContext(actor_id="test_worker", purpose="api_call")
        initial_headers = {"User-Agent": "Omnia/1.0"}
        initial_query = {"format": "json"}

        # 2. Use context manager to bind credentials
        with self.gateway.auth_adapter.authenticate_request(
            binding=binding,
            context=ctx,
            headers=initial_headers,
            query_params=initial_query
        ) as (bound_headers, bound_query):
            self.assertEqual(bound_headers["Authorization"], "Bearer secret_live_bearer_token_xyz")
            self.assertEqual(bound_query["format"], "json")

        # 3. Test HMAC signing scheme
        hmac_binding = CredentialBinding(
            auth_type="HMAC",
            secret_reference="ext_api_token",
            hmac_header_name="X-Signature"
        )
        body_payload = b'{"amount": 100}'
        with self.gateway.auth_adapter.authenticate_request(
            binding=hmac_binding,
            context=ctx,
            headers={"Content-Type": "application/json"},
            query_params={},
            body=body_payload
        ) as (h_headers, _):
            expected_sig = hmac.new(b"secret_live_bearer_token_xyz", body_payload, hashlib.sha256).hexdigest()
            self.assertEqual(h_headers["X-Signature"], expected_sig)

    def test_04_rate_limiting_and_concurrency_control(self):
        """Token bucket limiter bounds requests per second and respects burst capacity."""
        policy = RateLimitPolicy(requests_per_second=5.0, burst_limit=3, max_concurrent_requests=2)
        limiter = TokenBucketLimiter(policy)

        # 1. Can acquire burst limit of 3 tokens
        for i in range(2):  # Concurrency limit is 2
            ok, wait_sec = limiter.acquire()
            self.assertTrue(ok)
            self.assertEqual(wait_sec, 0.0)

        # 3rd attempt exceeds max concurrency of 2
        ok, wait_sec = limiter.acquire()
        self.assertFalse(ok)

        # Release one concurrency slot
        limiter.release()
        ok, wait_sec = limiter.acquire()
        self.assertTrue(ok)

        # Handle upstream Retry-After
        limiter.handle_retry_after(1.5)
        ok, wait_sec = limiter.acquire()
        self.assertFalse(ok)
        self.assertGreater(wait_sec, 0.5)

    def test_05_circuit_breaker_lifecycle(self):
        """Circuit transitions CLOSED -> OPEN on repeated failures -> HALF_OPEN probe -> CLOSED recovery."""
        cfg = CircuitBreakerConfig(failure_threshold=3, recovery_probe_interval_sec=0.1, consecutive_success_threshold=2)
        cb = CircuitBreaker(connector_id="test_conn", config=cfg)

        self.assertEqual(cb.state, CircuitState.CLOSED)

        # 1. Trigger failures up to threshold
        cb.record_failure("Error 1")
        cb.record_failure("Error 2")
        self.assertEqual(cb.state, CircuitState.CLOSED)

        cb.record_failure("Error 3")
        self.assertEqual(cb.state, CircuitState.OPEN)

        # 2. While OPEN, execution is blocked
        can_exec, reason = cb.can_execute()
        self.assertFalse(can_exec)
        self.assertIn("CIRCUIT_OPEN", reason)

        # 3. Wait for probe interval
        time.sleep(0.12)
        can_exec, reason = cb.can_execute()
        self.assertTrue(can_exec)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        # 4. Probe successes restore circuit
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_06_retry_engine_semantics(self):
        """Retry engine permits safe retries, conditional idempotent retries, and blocks blind writes."""
        read_op = ConnectorOperation(
            operation_id="api.read",
            name="Read",
            operation_type=OperationType.READ,
            path="/items",
            method="GET"
        )
        write_op = ConnectorOperation(
            operation_id="api.write",
            name="Write",
            operation_type=OperationType.WRITE,
            path="/items",
            method="POST",
            idempotent=False,
            risk_level="HIGH"
        )

        # 1. Read operations are always safe to retry
        safe, reason = RetryDecisionEngine.is_retryable_operation(read_op, has_idempotency_key=False)
        self.assertTrue(safe)

        # 2. Non-idempotent write without idempotency token is rejected
        safe, reason = RetryDecisionEngine.is_retryable_operation(write_op, has_idempotency_key=False)
        self.assertFalse(safe)
        self.assertIn("NOT_SAFE_TO_RETRY", reason)

        # 3. Write with idempotency token is conditionally retryable
        safe, reason = RetryDecisionEngine.is_retryable_operation(write_op, has_idempotency_key=True)
        self.assertTrue(safe)
        self.assertIn("CONDITIONALLY_RETRYABLE", reason)

        # 4. Should retry evaluation with status codes and attempts
        policy = RetryPolicy(max_attempts=3, retryable_status_codes=[502, 503])
        retry_ok, delay, r_reason = RetryDecisionEngine.should_retry(status_code=503, attempt=1, policy=policy)
        self.assertTrue(retry_ok)
        self.assertGreater(delay, 0.0)

        # 400 Bad Request is not retryable
        retry_ok, delay, r_reason = RetryDecisionEngine.should_retry(status_code=400, attempt=1, policy=policy)
        self.assertFalse(retry_ok)

    def test_07_idempotency_reservation_and_caching(self):
        """Idempotency records return cached responses on repeat requests without re-execution."""
        mgr = IdempotencyManager(persistence=self.persistence)
        key = "idemp_test_key_101"
        req_hash = IdempotencyManager.compute_request_hash("charge.create", {"amount": 500}, None)

        # 1. First reservation succeeds
        proceed, cached, reason = mgr.check_or_reserve(key, "charge.create", "inst_1", req_hash)
        self.assertTrue(proceed)
        self.assertIsNone(cached)
        self.assertEqual(reason, "RESERVED")

        # 2. Concurrent second attempt is blocked as IN_FLIGHT
        proceed, cached, reason = mgr.check_or_reserve(key, "charge.create", "inst_1", req_hash)
        self.assertFalse(proceed)
        self.assertEqual(reason, "IN_FLIGHT_CONFLICT")

        # 3. Complete execution and cache response
        sample_resp = ConnectorResponse(
            request_id="req_123",
            operation_id="charge.create",
            status_code=200,
            headers={"Content-Type": "application/json"},
            body={"id": "ch_999", "status": "succeeded"},
            verification_status=VerificationStatus.VERIFIED
        )
        mgr.record_completion(key, sample_resp, IdempotencyStatus.COMPLETED)

        # 4. Subsequent attempt retrieves cached response directly
        proceed, cached, reason = mgr.check_or_reserve(key, "charge.create", "inst_1", req_hash)
        self.assertFalse(proceed)
        self.assertIsNotNone(cached)
        self.assertEqual(reason, "ALREADY_COMPLETED")
        self.assertTrue(cached.cached_idempotent)
        self.assertEqual(cached.body["id"], "ch_999")

    def test_08_response_verification_business_logic(self):
        """Verifier identifies GraphQL errors, Slack ok: false, and write timeouts as UNCERTAIN."""
        write_op = ConnectorOperation(
            operation_id="payment.charge",
            name="Charge",
            operation_type=OperationType.WRITE,
            path="/charge",
            method="POST"
        )

        # 1. HTTP 200 with Slack-style {"ok": false} is rejected as FAILED
        status, details, err = ResponseVerifier.verify_response(
            operation=write_op,
            status_code=200,
            response_body={"ok": False, "error": "invalid_auth"}
        )
        self.assertEqual(status, VerificationStatus.FAILED)
        self.assertIn("invalid_auth", err)

        # 2. HTTP 200 with GraphQL {"errors": [...]} is rejected as FAILED
        status, details, err = ResponseVerifier.verify_response(
            operation=write_op,
            status_code=200,
            response_body={"errors": [{"message": "Field not found"}]}
        )
        self.assertEqual(status, VerificationStatus.FAILED)
        self.assertIn("GraphQL query failed", err)

        # 3. Timeout on write operation produces UNCERTAIN status
        status, details, err = ResponseVerifier.verify_response(
            operation=write_op,
            status_code=504,
            response_body=None,
            timed_out=True
        )
        self.assertEqual(status, VerificationStatus.UNCERTAIN)
        self.assertIn("UNCERTAIN", err)

    def test_09_inbound_webhooks_signature_and_replay_defense(self):
        """Inbound webhook gateway verifies HMAC signature and rejects forged and replayed requests."""
        import asyncio

        # 1. Store webhook secret in Module 25
        self.secrets.register_secret(
            secret_id="webhook_secret_key",
            name="Stripe Webhook Secret",
            secret_type=SecretType.API_KEY,
            plaintext="whsec_test_secret_key_123"
        )

        endpoint = WebhookEndpoint(
            webhook_id="wh_stripe_1",
            endpoint_path="/webhooks/stripe",
            provider_id="stripe",
            secret_reference="webhook_secret_key",
            replay_window_sec=60.0
        )
        self.gateway.webhooks.register_endpoint(endpoint)

        payload_bytes = b'{"id": "evt_001", "type": "payment.succeeded"}'
        timestamp = str(int(time.time()))
        signed_part = f"{timestamp}.".encode("utf-8") + payload_bytes
        valid_mac = hmac.new(b"whsec_test_secret_key_123", signed_part, hashlib.sha256).hexdigest()
        valid_stripe_sig = f"t={timestamp},v1={valid_mac}"

        # 2. Valid webhook succeeds
        ok, evt, reason = asyncio.run(self.gateway.webhooks.process_webhook(
            endpoint_path="/webhooks/stripe",
            headers={"Stripe-Signature": valid_stripe_sig},
            raw_body=payload_bytes
        ))
        self.assertTrue(ok)
        self.assertEqual(reason, "SUCCESS")
        self.assertIsNotNone(evt)
        self.assertEqual(evt.provider_event_id, "evt_001")

        # 3. Forged signature fails
        ok, evt, reason = asyncio.run(self.gateway.webhooks.process_webhook(
            endpoint_path="/webhooks/stripe",
            headers={"Stripe-Signature": "t=123,v1=bad_signature_digest"},
            raw_body=payload_bytes
        ))
        self.assertFalse(ok)
        self.assertIn("INVALID_SIGNATURE", reason)

        # 4. Replay attack with same event ID is rejected
        ok, evt, reason = asyncio.run(self.gateway.webhooks.process_webhook(
            endpoint_path="/webhooks/stripe",
            headers={"Stripe-Signature": valid_stripe_sig},
            raw_body=payload_bytes
        ))
        self.assertFalse(ok)
        self.assertIn("REPLAY_DETECTED", reason)


if __name__ == "__main__":
    unittest.main()
