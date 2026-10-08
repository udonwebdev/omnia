# OMNIA MODULE 19: AUTONOMOUS SUPERVISOR & MISSION CONTROL

## 1. Overview & Core Mission

The **Autonomous Supervisor & Mission Control** layer provides high-level supervisory governance over Omnia's multi-step, long-running operations.

While Module 14 executes task graphs, Module 19 continuously evaluates:
> **"Is the entire mission still healthy, progressing, safe, and aligned with reality?"**

```text
               ┌─────────────────────────────────────────┐
               │                 MISSION                 │
               │   - Multi-Task Objective                │
               │   - Bounded Recovery Budget             │
               │   - Explicit State Machine              │
               └────────────────────┬────────────────────┘
                                    │
                                    ▼
               ┌─────────────────────────────────────────┐
               │          AUTONOMOUS SUPERVISOR          │
               │   - Periodic Adaptive Loop              │
               │   - Event-Driven Reactive Handler       │
               │   - Heartbeat & Liveness Tracker        │
               │   - Wait-Graph Deadlock Detector        │
               │   - State Consistency Reconciler        │
               └────────────────────┬────────────────────┘
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
  [CONTINUE]                   [RECOVER]                     [REPLAN]
Normal Progress             Transient Fault             Oscillating Loop /
Verified In Reality         Recovery Initiated          Capability Outage
       │                            │                            │
       └────────────────────────────┼────────────────────────────┘
                                    │
                                    ▼
                       EVIDENCE-BACKED DECISION
```

---

## 2. Execution vs. Supervision Boundary

| Responsibility | Module 14 (Executor) | Module 19 (Supervisor) |
| :--- | :--- | :--- |
| **Primary Role** | Runs individual task nodes | Assesses overall mission health & progress |
| **Actions** | Clicks buttons, runs commands | Issues structured decisions (`CONTINUE`, `PAUSE`, `RECOVER`, `REPLAN`, `ABORT`) |
| **Failure Response**| Local step retry | Global recovery budget tracking & escalation ladder |
| **Deadlock Handling**| Acquires & releases locks | Detects wait-for graph cycles and preempts victims |
| **Crash Recovery** | Restores checkpoint state | Reconciles reality vs persisted DB before resumption |

---

## 3. Mission States & Lifecycle

Supported states:
`CREATED`, `PLANNING`, `READY`, `RUNNING`, `WAITING`, `PAUSED`, `DEGRADED`, `RECOVERING`, `REPLANNING`, `AWAITING_APPROVAL`, `COMPLETED`, `FAILED`, `ABORTING`, `ABORTED`, `TIMED_OUT`, `CANCELLED`, `UNKNOWN`.

State transitions are strictly validated in `supervisor.models.VALID_MISSION_TRANSITIONS`. Arbitrary state jumps are blocked.

---

## 4. Heartbeat & Stall Detection

The `HeartbeatMonitor` distinguishes:
- **`ALIVE`**: Process tick received within 30 seconds.
- **`ACTIVE`**: Meaningful progress (node completed, state verified, resource acquired) within `expected_progress_interval_sec`.
- **`STALLED`**: Alive but no progress beyond `warning_threshold_sec`.
- **`NO_PROGRESS`**: Exceeded `hard_timeout_sec`.
- **`LOOP` / `OSCILLATION`**: Repeated identical observations ($N \ge 4$) or oscillating node transitions ($A \to B \to A \to B$).

---

## 5. Deadlock Detection in Resource Wait-Graph

The `ResourceSupervisor` monitors exclusive locks across concurrent tasks:
- Constructs a directed wait-for graph ($T_1 \to R_1 \to T_2 \to R_2 \to T_1$).
- Runs cycle detection via DFS recursion.
- When a cycle is detected, selects the lowest-priority task as victim to pause or replan, resolving deadlocks deterministically without destructive side-effects.

---

## 6. State Reconciliation on Restart

The `StateReconciler` inspects database records upon startup:
- If a task or mission was recorded as `RUNNING` in SQLite but the process died with no heartbeat:
  - **Never assumes `RUNNING`**.
  - Marks state as `UNCERTAIN` or `RECOVERING`.
  - Re-evaluates verified device connectivity and recent checkpoints before safely resuming.

---

## 7. Structured Decision Model

Every nontrivial decision produces an evidence-backed `SupervisoryDecision`:
```python
@dataclass
class SupervisoryDecision:
    decision_id: str
    mission_id: str
    task_id: Optional[str]
    decision: SupervisoryDecisionType
    reason: str
    evidence: Dict[str, Any]
    confidence: DecisionConfidence
    urgency: DecisionUrgency
    recommended_action: str
    policy_reference: Optional[str]
    created_at: float
```

---

## 8. Verification Suite

- **Unit Suite**: `test_autonomous_supervisor_module19.py` (15/15 PASS)
- **E2E Suite**: `test_supervisor_e2e_module19.py` (Section 48 failure injection & recovery + Section 49 crash reconciliation PASS)
- **System Readiness**: `system_check.py` Stage `[11/11]` (All 5 checks PASS)
