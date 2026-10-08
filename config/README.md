# Omnia Module 24 — Distributed Configuration, Policy & Runtime Control Plane

## 1. Architectural Mission

Module 24 establishes Omnia's authoritative control plane for managing, validating, versioning, distributing, activating, rolling back, and auditing **runtime configuration and operational control settings across the cluster**.

This is:
- **NOT** a `.env` loader.
- **NOT** a replacement for the Module 09 Security & Policy Engine.
- **NOT** a new persistence layer (uses Module 15 SQLite tables via Schema Migration V6).
- **NOT** a new event bus (publishes typed events to Module 18 Event Fabric).
- **NOT** a new coordination system (coordinates with Module 22 for leader authority).
- **NOT** a new replication protocol (uses Module 23's `"config"` namespace for cluster propagation).

---

## 2. Core Architecture & Pipeline

```text
DEFINE SCHEMA & CONSTRAINTS
            ↓
PROPOSE CONFIGURATION VERSION
            ↓
STRICT RUNTIME VALIDATION & SECRET MASKING
            ↓
OPTIMISTIC CONCURRENCY CHECK (parent_version)
            ↓
IMMUTABLE SNAPSHOT (content_hash)
            ↓
STAGE VERSION
            ↓
MULTI-NODE ROLLOUT (CANARY / ROLLING / ALL_AT_ONCE)
            ↓
NODE ACTIVATION & VERIFICATION
    ├── SUCCESS: ADVANCE BATCH
    └── FAILURE (> threshold): HALT & SAFE ROLLBACK
            ↓
CONTINUOUS DRIFT DETECTION & AUDITING
```

---

## 3. Scope Precedence Hierarchy

Configuration values resolve deterministically using a strict precedence order:

1. **DEVICE** (Precedence 4): Hardware or device-specific overrides (e.g. `camera_high_res` capture FPS).
2. **NODE** (Precedence 3): Specific machine/node overrides (e.g. local worker concurrency, headless mode).
3. **CLUSTER** (Precedence 2): Authoritative cluster-wide configuration active across all nodes.
4. **GLOBAL** (Precedence 1): Cross-cluster default profile settings.
5. **SCHEMA_DEFAULT**: Built-in default defined in code.

---

## 4. Key Subsystem Components

| Component | File | Responsibility |
|---|---|---|
| **Models & Schemas** | [`config/models.py`](models.py) | Enums (`ConfigType`, `ConfigScope`, `RolloutStrategy`, `RuntimeMutability`), dataclasses (`ConfigSchema`, `ConfigVersion`, `ConfigRollout`, `DriftRecord`). |
| **Default Schemas** | [`config/defaults.py`](defaults.py) | 32 built-in schemas across 11 domains (`system`, `execution`, `vision`, `browser`, `mesh`, `coordination`, `replication`, `scheduler`, `supervisor`, `approval`, `security`). |
| **Validation Engine** | [`config/validation.py`](validation.py) | Type checking, range bounds, secret URI format checks, dependency constraints, and node compatibility checks. |
| **Diff & Masking** | [`config/diff.py`](diff.py) | Granular diff calculation, secret reference redaction, and risk tier scoring (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`). |
| **Persistence Repository** | [`config/persistence.py`](persistence.py) | SQLite data store managing schemas, versions, values, rollouts, and drift records under Schema Migration V6. |
| **Rollout Orchestrator** | [`config/rollout.py`](rollout.py) | Multi-node staged execution supporting `ALL_AT_ONCE`, `ROLLING`, `CANARY`, and `MANUAL` with failure thresholds. |
| **Rollback Engine** | [`config/rollback.py`](rollback.py) | Automatic and manual safe atomic reversion to parent or historical stable versions. |
| **Drift Detector** | [`config/drift.py`](drift.py) | Audits node parameters against cluster authority, distinguishing authorized overrides from unauthorized drift. |
| **Control Plane Service** | [`config/service.py`](service.py) | Public API facade unifying proposal, staging, rollout, rollback, drift inspection, and telemetry. |

---

## 5. Security & Secret Isolation Invariant

- **Zero Plaintext Secrets**: Secrets are never stored in configuration strings. They must reference secure vaults via URIs: `secret://<provider>/<key_path>` (e.g. `secret://vault/api_auth_token`).
- **Automatic Masking**: Any key marked `is_secret=True`, having type `SECRET_REF`, or containing `secret://` is automatically redacted to `[SECRET_MASKED]` or `[MASKED]` in diffs, event payloads, logs, and external status outputs.
- **Human Approval Gating**: Any configuration mutation evaluated as `HIGH` or `CRITICAL` risk automatically emits `config.approval_required` for authorization by Module 20 Human Approval Gateway.

---

## 6. Verification & Test Suite

- **Unit Test Suite**: [`test_config_module24.py`](../test_config_module24.py) (11/11 PASS)
  - Schema registry, types, and bounds
  - Secret URI enforcement and raw credential blocking
  - Cross-key dependency checks (`heartbeat_period_sec` < `lease_ttl_sec`)
  - Scope precedence hierarchy (`DEVICE` > `NODE` > `CLUSTER` > `GLOBAL`)
  - Optimistic concurrency and parent version collision handling
  - Rollout strategy batching and failure thresholds
  - Atomic rollback and version status lifecycle
  - Drift detection and reconciliation tracking
- **E2E Integration Suite**: [`test_config_e2e_module24.py`](../test_config_e2e_module24.py) (3/3 PASS)
  - 3-node cluster canary deployment
  - Worker node failure triggering automated rollback
  - Unauthorized node parameter drift detection and convergence
- **Diagnostic Suite**: [`system_check.py`](../system_check.py) Stage `[16/16]` PASS.
