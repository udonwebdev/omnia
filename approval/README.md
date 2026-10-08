# Module 20: Human Approval Gateway & Consent Orchestrator

## 1. Overview
The **Human Approval Gateway & Consent Orchestrator** is Omnia's authoritative human consent broker. It creates a secure, persistent, auditable mechanism through which Omnia requests human approval for elevated-risk actions, policy-required operations, or ambiguous intents—then safely continues, modifies, pauses, or aborts execution based on the operator's decision.

```text
POLICY ENGINE / SUPERVISOR / TASK GRAPH
                    ↓
        "Human approval is required."
                    ↓
             APPROVAL GATEWAY
                    ↓
          Create Approval Request
                    ↓
     Compute Deterministic Fingerprint
                    ↓
          Present Request to User
            (HUD / Voice / CLI)
                    ↓
                   WAIT
                    ↓
          Receive & Validate Decision
                    ↓
          Issue Execution Release Token
                    ↓
          MODULE 14 EXECUTION ENGINE
```

---

## 2. Core Invariants
1. **Silence / Timeout != Approval**: Silence, timeout, UI closure, or ambiguous input is NEVER interpreted as consent (`UNKNOWN = NOT APPROVED`, `TIMEOUT = EXPIRED`).
2. **Approval Never Overrides Policy**: If the Policy Engine rejects an action as forbidden, human consent cannot authorize execution (`DENY` remains `DENY`).
3. **Cryptographic Fingerprint Binding**: Approval tokens are strictly bound to an immutable action fingerprint:
   $$\text{Fingerprint} = \text{SHA256}(\text{Action} \parallel \text{Params} \parallel \text{Target} \parallel \text{PlanVersion})$$
   Any parameter mutation, plan modification, or resource drift invalidates the release token.
4. **Single-Use Consumption**: Tokens scoped to `ONCE` are consumed atomically upon node execution, preventing replay attacks.
5. **Conservative Ambiguity Filtering**: When multiple approval requests are pending, generic voice affirmatives ("yes", "proceed") are rejected as ambiguous unless a specific approval ID is provided.

---

## 3. Package Structure
```text
approval/
├── __init__.py           # Package exports & singletons
├── models.py             # Enums (ApprovalStatus, ApprovalType, ApprovalScope) & Dataclasses
├── fingerprints.py       # Deterministic SHA-256 action fingerprint generator & verifier
├── presentation.py       # Multi-channel presentation formatters (HUD, Voice, CLI)
├── persistence.py        # SQLite persistence manager (approval_requests, approval_decisions, approval_releases)
├── gateway.py            # ApprovalGateway orchestrator with atomic transitions & Event Fabric integration
└── README.md             # Subsystem architecture & specification
```

---

## 4. Database Schema (Migration v2)
The subsystem adds 3 transactional SQLite tables:
- `approval_requests`: Tracks full lifecycle, fingerprints, timeouts, and state transitions.
- `approval_decisions`: Stores operator decision records, user IDs, decision channels, and rationales.
- `approval_releases`: Stores cryptographic execution authorization tokens and consumption timestamps.

---

## 5. Event Fabric Integration
Module 20 publishes typed events into Omnia's Event Fabric:
- `approval.created`
- `approval.presented`
- `approval.waiting`
- `approval.approved`
- `approval.rejected`
- `approval.deferred`
- `approval.expired`
- `approval.cancelled`
- `approval.invalidated`
- `approval.released`
- `approval.execution_blocked`

---

## 6. Verification & Test Suites
- Unit test suite: `test_approval_gateway_module20.py` (13/13 PASS)
- E2E test suite: `test_approval_e2e_module20.py` (2/2 PASS)
