# OMNIA — MODULE 25: SECRETS, CREDENTIALS & SECURE IDENTITY LIFECYCLE

## Architecture Overview

Module 25 establishes Omnia's authoritative, production-grade credential and identity subsystem. It enforces the fundamental invariant:

$$\text{CONFIGURATION} \neq \text{SECRET} \neq \text{IDENTITY} \neq \text{PERMISSION} \neq \text{CAPABILITY}$$

Secrets represent cryptographic keys, tokens, passwords, and sensitive identity material that must **never** be exposed in logs, diagnostics, task checkpoints, replication streams, event payloads, or LLM system prompts.

```
       REQUEST
          │
          ▼
   WHO, WHAT, WHY, WHERE, WHEN
   (SecretAccessAuthorizer)
          │
  ┌───────┴───────┐
  │ Authorized?   │─── NO ──► AccessDeniedError / Audit Log
  └───────┬───────┘
         YES
          │
          ▼
   LeaseManager (Issues short-lived lease)
          │
          ▼
   ProviderManager (Local Encrypted / Vault / Env)
          │
          ▼
   Envelope Encryption (KEK -> DEK AES-GCM / HMAC Authenticated)
          │
          ▼
   SecretHandle (RAII Scoped Handle + Memory Guard)
          │
          ▼
   RedactionEngine (Scrubbing known secrets & patterns)
          │
          ▼
   Audit Logger & Event Fabric (Zero Plaintext Metadata Events)
```

---

## Core Security Invariants

1. **Zero Plaintext at Rest & in Flight**:
   - Secrets are encrypted at rest using envelope encryption (Master Seed $\rightarrow$ KEK $\rightarrow$ DEK) with AES-GCM-256 (or authenticated HMAC keystream fallback).
   - Plaintext is decrypted strictly on-demand inside scoped `SecretHandle` or `SecureContext` contexts and immediately zeroed from memory buffers upon exit.
2. **Contextual Purpose Binding**:
   - Credential acquisition requires an authoritative tuple: `(Requester, Purpose, Capability, Node Trust, Scope)`.
   - Access is restricted to declared purpose bounds (e.g. `payment.process`, `cloud.llm.inference`). Cross-boundary or purpose violations are denied and logged to `secret_audit_log`.
3. **Lease-Bound Access**:
   - Secrets are never handed out indefinitely. Callers receive a time-bound lease (`lease_id`, `expires_at`).
   - If a lease expires, is released, or revoked, the in-memory `SecretHandle` immediately rejects further access via dynamic callback validation.
4. **Zero-Downtime Safe Rotation**:
   - Four-stage rotation protocol: `OLD ACTIVE` $\rightarrow$ `NEW STAGED` $\rightarrow$ validation probe $\rightarrow$ `NEW ACTIVE` $\rightarrow$ `OLD RETIRED`.
   - If the pre-activation probe fails, the system safely falls back to the old active version with zero service disruption.
5. **Immediate Invalidation on Compromise**:
   - Marking a secret compromised immediately revokes all active leases, kills existing in-memory handles, and transitions metadata to `COMPROMISED`.
6. **Multi-Layer Redaction & Injection Defense**:
   - All registered secrets are indexed by prefix and hash in `RedactionEngine`.
   - Logs, HUD events, error traces, and prompt templates are scrubbed of API keys, bearer tokens, private keys, and prompt-injection extraction attacks.

---

## Data Model & Schema (Migration V7)

Module 25 introduces Schema Migration Version 7:

- `secret_metadata`: Authoritative metadata catalog (`secret_id`, `name`, `secret_type`, `provider`, `scope`, `version`, `status`, `expires_at`, `access_policy`, `rotation_policy`, `integrity_hash`).
- `secret_versions`: Encrypted versions at rest (`secret_id`, `version`, `ciphertext`, `key_id`, `salt`, `nonce`, `fingerprint`, `status`, `created_at`).
- `secret_leases`: Active access leases (`lease_id`, `secret_id`, `version`, `requester`, `purpose`, `node_id`, `issued_at`, `expires_at`, `revoked_at`, `revocation_reason`).
- `secret_audit_log`: Immutable append-only audit trail (`audit_id`, `timestamp`, `secret_id`, `version`, `requester`, `action`, `result`, `scope`, `node_id`, `details`).

---

## Omnia Tool Interfaces

Module 25 exposes 8 first-class operational tools in `omnia_tools.py`:

| Tool | Description |
|---|---|
| `get_secret_metadata` | Inspect non-sensitive secret metadata, active version, status, and policy. |
| `acquire_secret_lease` | Contextually acquire a short-lived lease token for an authorized operation. |
| `release_secret_lease` | Explicitly release and terminate an active lease when an operation finishes. |
| `rotate_secret` | Execute a zero-downtime rotation to a new credential version with safe fallback. |
| `revoke_secret` | Immediately revoke a secret, disabling further acquisition and terminating leases. |
| `mark_secret_compromised` | Mark a secret compromised under a security incident ID and kill all active leases. |
| `get_secrets_telemetry` | View aggregate access grants, denials, rotation, and revocation metrics. |
| `redact_sensitive_text` | Scrub sensitive credentials, keys, and tokens from text or prompt strings. |

---

## Verification & Diagnostics

- **Unit Tests**: `test_secrets_module25.py` (8 test suites covering envelope encryption, contextual authorization, purpose binding, human approval gating, zero-downtime rotation, revocation, lease expiration, and redaction).
- **E2E Tests**: `test_secrets_e2e_module25.py` (Multi-node trust boundaries, zero plaintext replication, incident compromise handling, and crash recovery).
- **System Readiness**: `system_check.py` Stage `[17/17]` verifies end-to-end integration across all 25 modules.
