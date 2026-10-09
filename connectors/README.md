# OMNIA MODULE 26: EXTERNAL INTEGRATION & CONNECTOR GATEWAY

The **External Integration & Connector Gateway** serves as Omnia's authoritative, hardened ingress and egress boundary for external third-party services, APIs, and webhooks.

---

## 1. Architectural Invariants

1. **Explicit Identity & Separation**:
   `CONFIGURATION ≠ SECRET ≠ IDENTITY ≠ PERMISSION ≠ CAPABILITY ≠ CONNECTOR`.
2. **Strict SSRF Immunity**:
   - RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) blocked.
   - Loopback (`127.0.0.0/8`, `::1`) blocked.
   - Cloud metadata IPs (`169.254.169.254`, `metadata.google.internal`) blocked.
   - Prohibited schemes (anything except `http://` and `https://`) rejected.
   - DNS pre-resolution checking with re-validation prevents rebinding attacks.
3. **Zero Plaintext Secrets**:
   - Connector configurations and instances store only references to Module 25 secrets (`secret://...` or ID).
   - Dynamic credentials (Bearer tokens, API keys, Basic auth, HMAC keys) are leased on-demand via `ConnectorAuthAdapter` with scoped context managers and guaranteed buffer zeroing upon exit.
4. **Idempotency Guarantee**:
   - All mutating/write operations enforce deterministic request hashing (`sha256(operation + payload + params)`).
   - In-flight reservations block duplicate concurrent executions.
   - Cached responses are returned for duplicate submissions with `cached_idempotent = True`.
   - Write timeouts produce `UNCERTAIN` verification status, preventing dangerous blind retries.
5. **Business Verification vs Transport Status**:
   - HTTP 200 $\neq$ Business Success.
   - `ResponseVerifier` inspects provider-specific error semantics: GraphQL `errors` arrays, Slack `{"ok": false}`, Stripe error statuses.
6. **Resilience & Backoff**:
   - Three-state `CircuitBreaker` (`CLOSED`, `OPEN`, `HALF_OPEN`) with probe intervals.
   - `TokenBucketLimiter` for rate-limiting with upstream `Retry-After` backoff compliance.
   - `RetryDecisionEngine` preventing retries on non-idempotent operations without explicit tokens.
7. **Cryptographic Inbound Webhooks**:
   - Replay protection window tracking delivery IDs and content digests.
   - Cryptographic HMAC-SHA256 signature verification (GitHub `sha256=...`, Stripe `t=...,v1=...`).
   - Normalization and publishing directly into Module 18 Event Fabric.
8. **Distributed Epoch Fencing**:
   - `ConnectorPolicyGuard` verifies Module 22 leader epochs, preventing stale partitioned workers from making external calls.

---

## 2. Directory Structure

```text
connectors/
├── __init__.py               # Package exports & singletons
├── models.py                 # Core dataclasses and enums
├── ssrf.py                   # SSRF defense & target address validation
├── auth.py                   # Module 25 integration & credential leasing
├── circuit_breaker.py        # 3-state circuit breaker pattern
├── rate_limiter.py           # Token bucket rate limiting & backoff
├── retries.py                # Exponential backoff & retry safety engine
├── idempotency.py            # Idempotency token & request hash manager
├── verification.py           # Business response verification engine
├── transport.py              # Socket-level secure HTTP client
├── webhooks.py               # Inbound cryptographic webhook gateway
├── adapters.py               # Provider adapters (GitHub, Stripe, Slack, Custom)
├── persistence.py            # SQLite repository under Migration V8
├── policy_guard.py           # Module 09, 20 & 22 boundary enforcement
└── service.py                # ConnectorGatewayService coordinator
```

---

## 3. Operational Tools

The gateway exposes 8 native tools in `omnia_tools.py`:
- `list_external_connectors`
- `get_connector_definition`
- `create_connector_instance`
- `execute_connector_operation`
- `check_connector_health`
- `reset_connector_circuit`
- `process_inbound_webhook`
- `get_connector_telemetry`

---

## 4. Verification & Testing

- Unit test suite: `python test_connectors_module26.py` (9 tests passed).
- End-to-end socket test suite: `python test_connectors_e2e_module26.py` (5 tests passed against real in-process HTTP mock server).
- Diagnostic check: Stage `[18/18]` in `system_check.py`.
