# Module 21: Autonomous Resource Scheduler & Concurrency Orchestrator

## 1. Overview
The **Autonomous Resource Scheduler & Concurrency Orchestrator** is Omnia's authoritative arbiter of work admission, resource allocation, and concurrency safety. It determines:
- Which task or mission executes next;
- What physical and logical resources it may acquire;
- When execution begins;
- How to prevent deadlocks, resource starvation, and race conditions.

```text
MODULE 16 (PLAN) → MODULE 14 (READY)
                         ↓
               MODULE 21 SCHEDULER
       [Admission Control & Prioritization]
                         ↓
       [Deterministic Multi-Resource Atomic Reservation]
                         ↓
       [Worker Execution Slot Assignment]
                         ↓
               MODULE 14 EXECUTES
                         ↓
               RESOURCE RELEASE & LEASE REAP
```

---

## 2. Core Invariants
1. **No Execution Without Admission**: A task being ready is not sufficient to execute; it must secure admission from Module 21.
2. **Multi-Resource Atomicity**: Multi-resource allocations are acquired in deterministic alphabetical order by `resource_id`. If any resource is unavailable, all staged allocations are rolled back immediately.
3. **Deadlock Prevention & Resolution**: Wait-for graph cycles are detected via DFS. Victims selected for preemption must be preemptible (`SAFE_TO_PAUSE`, `CHECKPOINT_PREEMPTIBLE`).
4. **Starvation Prevention & Aging**: Tasks waiting past thresholds accumulate fairness credits and aging bonuses, progressively elevating priority.
5. **Bounded Leases**: Reservations carry heartbeated leases. Crashed workers trigger automatic lease expiration and resource reclamation without assuming external actions terminated.
6. **Separation of Concerns**: Module 21 schedules and reserves; Module 14 executes; Module 19 supervises; Module 20 approves; Module 15 persists.

---

## 3. Package Structure
```text
scheduler/
├── __init__.py           # Package exports & singletons
├── models.py             # Enums (ScheduleState, ResourceAccessMode) & Dataclasses
├── resources.py          # Unified ResourceRegistry with capacity management
├── reservations.py       # Atomic multi-resource reservation manager & bounded leases
├── workers.py            # Execution slot manager & capability compatibility
├── scoring.py            # Deterministic, explainable priority & aging scorer
├── deadlock.py           # Wait-for cycle detector & safe victim selector
├── persistence.py        # SQLite persistence manager (Migration v3) & crash reconciler
├── orchestrator.py       # ResourceScheduler core orchestrator & Event Fabric publisher
└── README.md             # Subsystem specification & documentation
```

---

## 4. Database Schema (Migration v3)
The subsystem adds 4 SQLite tables:
- `schedule_requests`: Tracks schedule admissions, dependencies, states, and scores.
- `resource_reservations`: Tracks resource ownership, access modes, and heartbeated leases.
- `execution_slots`: Tracks worker slots, types, capacities, and capability support.
- `scheduling_decisions`: Archives explainable decisions and detected conflicts.

---

## 5. Verification & Diagnostics
- **Unit Test Suite**: `test_resource_scheduler_module21.py` (13/13 PASS)
- **E2E Integration & Concurrency Suite**: `test_scheduler_e2e_module21.py` (2/2 PASS)
