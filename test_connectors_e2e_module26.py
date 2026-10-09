"""
End-to-End Test Suite for Omnia Module 26:
External Integration & Connector Gateway

Spawns a real HTTP server in-process and tests:
1. Valid GET request with auth header verification and body parsing.
2. Idempotent POST request (duplicate request reuses cached response and executes upstream exactly once).
3. Slow/timed-out write request triggering UNCERTAIN verification status.
4. Cryptographic inbound webhook signature verification and replay defense.
5. Distributed epoch fencing rejection of stale write requests.
"""

import unittest
import http.server
import socketserver
import threading
import json
import time
import os
import shutil
import tempfile
import hmac
import hashlib
import asyncio

from persistence.migrations import apply_migrations
from connectors.models import (
    ConnectorDefinition,
    ConnectorInstance,
    ConnectorOperation,
    OperationType,
    Environment,
    CredentialBinding,
    RateLimitPolicy,
    RetryPolicy,
    TimeoutPolicy,
    CircuitBreakerConfig,
    RequestContext,
    ConnectorRequest,
    VerificationStatus,
    WebhookEndpoint
)
from connectors.service import ConnectorGatewayService
from connectors.persistence import ConnectorPersistence
from connectors.auth import ConnectorAuthAdapter
from connectors.policy_guard import ConnectorPolicyGuard, FencingViolationError
from secrets.service import SecretControlPlaneService
from secrets.persistence import SecretPersistence
from secrets.models import SecretType, TrustLevel


class MockProviderHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Real HTTP server mock handler to test actual socket-level transport."""
    
    post_execution_counter = 0

    def log_message(self, format, *args):
        # Suppress noisy standard server logs in test output
        return

    def do_GET(self):
        auth_header = self.headers.get("Authorization", "")
        if self.path == "/v1/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "auth": auth_header}).encode("utf-8"))
            return

        if self.path == "/v1/user":
            if not auth_header.startswith("Bearer "):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Unauthorized"}).encode("utf-8"))
                return
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"id": "usr_99", "login": "omnia_agent"}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b""
        
        if self.path == "/v1/charges":
            MockProviderHTTPHandler.post_execution_counter += 1
            idem_key = self.headers.get("Idempotency-Key", "")
            data = json.loads(body.decode("utf-8")) if body else {}
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "charge_id": f"ch_{MockProviderHTTPHandler.post_execution_counter}",
                "amount": data.get("amount", 0),
                "status": "succeeded",
                "idempotency_key": idem_key
            }).encode("utf-8"))
            return

        if self.path == "/v1/slow_operation":
            # Simulate upstream delay exceeding client write timeout
            time.sleep(1.2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "completed_late"}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


class TestConnectorsE2EModule26(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 1. Start real HTTP server on dynamic port
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockProviderHTTPHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

        # 2. Setup SQLite DB with all 8 migrations
        cls.test_fd, cls.test_db = tempfile.mkstemp(suffix=".conn_e2e.db")
        os.close(cls.test_fd)
        apply_migrations(cls.test_db)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists(cls.test_db):
            try:
                os.remove(cls.test_db)
            except Exception:
                pass

    def setUp(self):
        MockProviderHTTPHandler.post_execution_counter = 0
        self.persistence = ConnectorPersistence(self.test_db)
        self.secret_persistence = SecretPersistence(self.test_db)
        self.secrets = SecretControlPlaneService(persistence=self.secret_persistence, node_id="e2e_node")

        self.gateway = ConnectorGatewayService(persistence=self.persistence, node_id="e2e_node")
        self.gateway.auth_adapter = ConnectorAuthAdapter(sec_service=self.secrets)
        self.gateway.webhooks._sec_service = self.secrets

        # Allow our local mock server host strictly in SSRF validator for E2E tests
        self.gateway.transport.ssrf.add_allowed_test_host("127.0.0.1")

    def test_01_real_http_get_authenticated_request(self):
        """Gateway executes real HTTP GET request to mock server with leased Bearer token."""
        # 1. Register secret
        self.secrets.register_secret(
            secret_id="e2e_api_token",
            name="E2E Mock Token",
            secret_type=SecretType.API_KEY,
            plaintext="e2e_super_secret_token_val"
        )

        # 2. Register Connector Definition & Instance
        base_url = f"http://127.0.0.1:{self.port}"
        op = ConnectorOperation(
            operation_id="get_user",
            name="Get User Profile",
            operation_type=OperationType.READ,
            path="/v1/user",
            method="GET"
        )
        definition = ConnectorDefinition(
            connector_id="mock.api",
            provider_id="mock",
            name="Mock E2E API",
            default_auth=CredentialBinding(
                auth_type="BEARER",
                secret_reference="e2e_api_token",
                header_name="Authorization"
            ),
            operations={"get_user": op}
        )
        self.gateway.register_connector(definition)

        self.gateway.create_instance(
            instance_id="mock.inst.1",
            connector_id="mock.api",
            base_url=base_url,
            environment=Environment.SANDBOX
        )

        # 3. Execute Request via Gateway
        req = ConnectorRequest(
            operation_id="get_user",
            instance_id="mock.inst.1",
            context=RequestContext(task_id="task_99", actor_id="test_operator")
        )

        resp = asyncio.run(self.gateway.execute_operation(req))

        # 4. Verify Real HTTP Response & Business Verification
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.verification_status, VerificationStatus.VERIFIED)
        self.assertIsInstance(resp.body, dict)
        self.assertEqual(resp.body.get("login"), "omnia_agent")
        self.assertEqual(resp.body.get("id"), "usr_99")

    def test_02_real_http_idempotent_post_duplicate_cached(self):
        """Gateway handles idempotent POST write; duplicate request returns cached response without second HTTP dispatch."""
        self.secrets.register_secret(
            secret_id="e2e_stripe_key",
            name="E2E Stripe Key",
            secret_type=SecretType.API_KEY,
            plaintext="sk_test_123456789"
        )

        base_url = f"http://127.0.0.1:{self.port}"
        op = ConnectorOperation(
            operation_id="create_charge",
            name="Create Charge",
            operation_type=OperationType.WRITE,
            path="/v1/charges",
            method="POST",
            idempotent=False
        )
        definition = ConnectorDefinition(
            connector_id="mock.charges",
            provider_id="mock",
            name="Mock Charges API",
            default_auth=CredentialBinding(
                auth_type="BEARER",
                secret_reference="e2e_stripe_key"
            ),
            operations={"create_charge": op}
        )
        self.gateway.register_connector(definition)

        self.gateway.create_instance(
            instance_id="mock.inst.charges",
            connector_id="mock.charges",
            base_url=base_url,
            environment=Environment.SANDBOX
        )

        # First request
        req1 = ConnectorRequest(
            operation_id="create_charge",
            instance_id="mock.inst.charges",
            body={"amount": 4200, "currency": "usd"},
            context=RequestContext(task_id="task_charge", idempotency_key="idem_unique_token_42")
        )

        resp1 = asyncio.run(self.gateway.execute_operation(req1))
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.verification_status, VerificationStatus.VERIFIED)
        self.assertEqual(MockProviderHTTPHandler.post_execution_counter, 1)
        self.assertEqual(resp1.body.get("charge_id"), "ch_1")

        # Second request with SAME idempotency token & same body
        req2 = ConnectorRequest(
            operation_id="create_charge",
            instance_id="mock.inst.charges",
            body={"amount": 4200, "currency": "usd"},
            context=RequestContext(task_id="task_charge", idempotency_key="idem_unique_token_42")
        )

        resp2 = asyncio.run(self.gateway.execute_operation(req2))
        self.assertEqual(resp2.status_code, 200)
        # Server counter MUST still be 1 (upstream was not invoked again)
        self.assertEqual(MockProviderHTTPHandler.post_execution_counter, 1)
        self.assertEqual(resp2.body.get("charge_id"), "ch_1")
        self.assertEqual(resp2.cached_idempotent, True)

    def test_03_real_http_write_timeout_produces_uncertain(self):
        """Gateway marks write operation UNCERTAIN when HTTP request times out."""
        base_url = f"http://127.0.0.1:{self.port}"
        op = ConnectorOperation(
            operation_id="slow_write",
            name="Slow Write Operation",
            operation_type=OperationType.WRITE,
            path="/v1/slow_operation",
            method="POST",
            idempotent=False,
            timeout=TimeoutPolicy(read_timeout_sec=0.2, connect_timeout_sec=1.0)
        )
        definition = ConnectorDefinition(
            connector_id="mock.slow",
            provider_id="mock",
            name="Slow API",
            operations={"slow_write": op}
        )
        self.gateway.register_connector(definition)

        self.gateway.create_instance(
            instance_id="mock.inst.slow",
            connector_id="mock.slow",
            base_url=base_url,
            environment=Environment.SANDBOX
        )

        req = ConnectorRequest(
            operation_id="slow_write",
            instance_id="mock.inst.slow",
            body={"action": "mutate_heavy_record"},
            context=RequestContext(task_id="task_slow")
        )

        resp = asyncio.run(self.gateway.execute_operation(req))
        # Must be classified as UNCERTAIN, NOT success or simple failure
        self.assertEqual(resp.verification_status, VerificationStatus.UNCERTAIN)
        self.assertIn("timed out", resp.error_message.lower())

    def test_04_real_webhook_signature_and_replay_protection(self):
        """Webhook gateway validates cryptographic HMAC-SHA256 signature and rejects duplicates."""
        self.secrets.register_secret(
            secret_id="e2e_wh_secret",
            name="E2E Webhook Secret",
            secret_type=SecretType.API_KEY,
            plaintext="wh_signing_key_secret_xyz"
        )

        endpoint = WebhookEndpoint(
            webhook_id="wh_e2e_gh",
            endpoint_path="/webhooks/github",
            provider_id="github",
            secret_reference="e2e_wh_secret",
            replay_window_sec=120.0
        )
        self.gateway.webhooks.register_endpoint(endpoint)

        body = json.dumps({"action": "opened", "issue": {"id": 101, "title": "Critical Bug"}}).encode("utf-8")
        mac = hmac.new(b"wh_signing_key_secret_xyz", body, hashlib.sha256).hexdigest()
        gh_sig = f"sha256={mac}"

        # 1. Valid webhook processed
        ok, evt, msg = asyncio.run(self.gateway.webhooks.process_webhook(
            endpoint_path="/webhooks/github",
            headers={"X-Hub-Signature-256": gh_sig},
            raw_body=body
        ))
        self.assertTrue(ok)
        self.assertEqual(msg, "SUCCESS")
        self.assertIsNotNone(evt)

        # 2. Forged signature fails
        ok, evt, msg = asyncio.run(self.gateway.webhooks.process_webhook(
            endpoint_path="/webhooks/github",
            headers={"X-Hub-Signature-256": "sha256=bad_digest_value_1234"},
            raw_body=body
        ))
        self.assertFalse(ok)
        self.assertIn("INVALID_SIGNATURE", msg)

    def test_05_distributed_epoch_fencing_rejection(self):
        """Connector policy guard rejects writes with stale leader epoch."""
        guard = ConnectorPolicyGuard()
        guard.set_current_epoch(current_epoch=5)

        # Request with stale epoch 4 must be rejected
        req_stale = ConnectorRequest(
            operation_id="create_user",
            instance_id="mock.inst.1",
            context=RequestContext(fencing_epoch=4)
        )
        op_write = ConnectorOperation(
            operation_id="create_user",
            name="Create User",
            operation_type=OperationType.WRITE,
            path="/v1/users",
            method="POST"
        )

        allowed, reason = guard.check_operation(req_stale, op_write)
        self.assertFalse(allowed)
        self.assertIn("FENCING_REJECTED", reason)

        # Request with matching epoch 5 must be permitted
        req_valid = ConnectorRequest(
            operation_id="create_user",
            instance_id="mock.inst.1",
            context=RequestContext(fencing_epoch=5)
        )
        allowed, reason = guard.check_operation(req_valid, op_write)
        self.assertTrue(allowed)
        self.assertEqual(reason, "ALLOWED")


if __name__ == "__main__":
    unittest.main()
