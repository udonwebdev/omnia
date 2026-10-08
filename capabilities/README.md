# OMNIA MODULE 17 — CAPABILITY REGISTRY & DYNAMIC SKILL SYSTEM

The **Capability Registry & Dynamic Skill System** serves as Omnia's single authoritative source of truth for everything the system can do. It catalogs capabilities with strict metadata regarding environments, platforms, permissions, health, risk classifications, side effects, idempotency, and real-world verification contracts.

---

## 1. Architectural Pipeline

```text
USER INTENT (Natural Language)
        ↓
MODULE 16 — INTENT COMPILER & PLANNER
        ↓
MODULE 17 — CAPABILITY DISCOVERY & PROVIDER MATCHING (`matcher.py`, `registry.py`)
  - Capability Resolution (Health, Latency, Risk, Permissions)
  - Provider Fallback Negotiation (Primary Local -> Secondary Remote/Cloud)
  - Verification Contract Binding
        ↓
VALIDATED TASK GRAPH (`task_graph/models.py`)
        ↓
MODULE 14 — SELF-HEALING EXECUTION (`executor.py`)
  - Pre-execution Capability Health Guard
  - Resource Mutual Exclusion Locks
        ↓
MODULE 13 — MULTIMODAL VISION & SCREEN PERCEPTION (`vision/`)
        ↓
MODULE 15 — PERSISTENT CHECKPOINTS & CRASH RECOVERY (`persistence/`)
  - Capability Revalidation (`CAPABILITY_CHANGED` detection on restart)
        ↓
MODULE 09 — SECURITY & POLICY ENFORCEMENT (`policy_engine.py`)
```

---

## 2. Core Package Structure (`capabilities/`)

- **`models.py`**: Strongly typed data models and enums:
  - `CapabilityCategory`: `DEVICE`, `BROWSER`, `VISION`, `VOICE`, `TELEPHONY`, `MESH`, `SYSTEM`, `MEMORY`, `ORCHESTRATION`.
  - `CapabilityHealth`: `UNKNOWN`, `HEALTHY`, `DEGRADED`, `UNAVAILABLE`, `DISABLED`, `BLOCKED`, `INITIALIZING`, `FAILED`.
  - `CapabilityLifecycle`: `DISCOVERED`, `VALIDATING`, `REGISTERED`, `INITIALIZING`, `READY`, `DEGRADED`, `UNAVAILABLE`, `DISABLED`, `REMOVED`.
  - `SideEffectType`: `NONE`, `READ`, `WRITE`, `DEVICE_CONTROL`, `NETWORK`, `EXTERNAL_COMMUNICATION`, `FINANCIAL`, `DESTRUCTIVE`, `SECURITY_SENSITIVE`.
  - `IdempotencyType`: `IDEMPOTENT`, `CONDITIONALLY_IDEMPOTENT`, `NON_IDEMPOTENT`, `UNKNOWN`.
  - `ReversibilityType`: `REVERSIBLE`, `CONDITIONALLY_REVERSIBLE`, `POTENTIALLY_IRREVERSIBLE`, `IRREVERSIBLE`.
  - `VerificationContract`: Explicit verification mechanism (`DOM_URL_MATCH`, `OCR_TEXT_MATCH`, `PROCESS_EXIT_ZERO`), expected states, and timeouts.
  - `CapabilityProvider`: Providers with priorities, latencies, environments, and costs.
  - `Capability`: Canonical, versioned capability object.
  - `CapabilityLease`: Time-bounded capability provider leases.

- **`registry.py`**: The authoritative `CapabilityRegistry` class:
  - Strict security keys: rejects unauthorized external or unauthenticated registrations.
  - Semantic versioning compatibility checks.
  - Dependency ripple effect: degraded/failed dependencies automatically downgrade downstream dependent capabilities.
  - Multi-provider registration and priority fallback.

- **`health.py`**: Lightweight, asynchronous health probes for ADB, Playwright, OCR, TTS, Vector Memory, and Mesh.

- **`matcher.py`**: Multi-criteria capability and provider scoring engine:
  - Filters out environment/platform mismatches (e.g. Android capabilities on Windows-only hosts).
  - Enforces permission guards and risk level caps.
  - Selects and ranks providers by health, priority, latency, and cost.

- **`builtin_skills.py`**: Catalogs all 12 production capabilities across Omnia:
  - `browser.navigate`, `browser.execute_task`
  - `vision.capture_screen`, `vision.find_element`, `vision.verify_state`
  - `device.android.unlock`, `device.android.youtube`, `device.android.shell`
  - `voice.speak`
  - `memory.search_context`
  - `mesh.execute_command`
  - `telephony.stream_audio`

- **`skill_loader.py`**: Dynamic skill manifest parser with schema validation and trust verification.

---

## 3. Integration with Omnia Core

1. **Module 14 Integration ([`task_graph/executor.py`](file:///c:/Users/ANON%20KFP/Documents/antigravity/charming-hopper/task_graph/executor.py))**:
   - Pre-execution capability health check prevents executing task nodes when their underlying capability is `UNAVAILABLE`, `FAILED`, or `BLOCKED`.
2. **Module 15 Integration ([`persistence/recovery.py`](file:///c:/Users/ANON%20KFP/Documents/antigravity/charming-hopper/persistence/recovery.py))**:
   - Revalidates capability availability during crash recovery classification; flags `CAPABILITY_CHANGED` if a capability goes offline while the host is restarting.
3. **Agent Tools ([`omnia_tools.py`](file:///c:/Users/ANON%20KFP/Documents/antigravity/charming-hopper/omnia_tools.py))**:
   - `query_capability_registry(category)`: Inspect registered capabilities.
   - `check_capability_health(capability_id)`: On-demand health status probes.
   - `list_available_providers(capability_id)`: Query active providers and latencies.

---

## 4. Verification Evidence

- **Unit & Integration Suite ([`test_capability_registry_module17.py`](file:///c:/Users/ANON%20KFP/Documents/antigravity/charming-hopper/test_capability_registry_module17.py))**:
  All 18 tests passed cleanly (Registration, Schema Rejection, Duplicate Handling, Discovery, Environment Mismatch, Health Degradation, Provider Fallback, Permission Guard, Dependency Ripple, Risk Classification, Idempotency, Verification Contract, Dynamic Device, Mesh Provider, Security Rejection, Module 16 Planning, Module 14 Execution Guard, Module 15 Recovery).
- **Real End-to-End Workflow ([`test_capability_e2e_module17.py`](file:///c:/Users/ANON%20KFP/Documents/antigravity/charming-hopper/test_capability_e2e_module17.py))**:
  Full loop verified: User Intent $\to$ Module 16 $\to$ Module 17 Resolution $\to$ Task Graph $\to$ Module 14 Execution $\to$ Module 13 Vision Observation $\to$ Module 15 Checkpoint Persistence.
- **Diagnostic Suite ([`system_check.py`](file:///c:/Users/ANON%20KFP/Documents/antigravity/charming-hopper/system_check.py))**:
  Stage `[9/9]` verified green.
