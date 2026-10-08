# Module 14: Dynamic Task Graph & Self-Healing Execution Engine

## 1. Overview & Architecture

Module 14 introduces the **Structured Execution & Self-Healing Runtime** to Omnia. Long-running, multi-device autonomous actions cannot rely on trivial sequential scripts where an unhandled exception or unverified action causes silent failure or cascading errors.

Module 14 guarantees the core operational principle:
> **An action returning successfully does NOT mean the task succeeded.**
> Verification of resulting state is mandatory.

```text
               +--------------------------------------+
               |             USER GOAL                |
               +--------------------------------------+
                                  |
                                  v
                       [ Dynamic TaskGraph ]
                                  |
            +---------------------+---------------------+
            |                     |                     |
            v                     v                     v
     [ TaskNode 1 ]        [ TaskNode 2 ]        [ TaskNode 3 ]
    (Acquire Locks)       (Dependencies OK)       (Dependencies OK)
            |                     |                     |
            +----------+----------+----------+----------+
                       |
                       v
             +--------------------+
             |      EXECUTE       |
             +--------------------+
                       |
                       v
             +--------------------+
             |      OBSERVE       |
             +--------------------+
                       |
                       v
             +--------------------+
             |       VERIFY       |
             +--------------------+
                       |
        +--------------+--------------+
        |                             |
     [ PASS ]                      [ FAIL ]
        |                             |
        v                             v
[ Next Node / Done ]        +--------------------+
                            |  CLASSIFY FAILURE  |
                            +--------------------+
                                      |
                     +----------------+----------------+
                     |                |                |
                 [ RETRY ]       [ REPLAN ]        [ ABORT ]
              (Exp. Backoff)   (Fallback Node)   (Fatal Error)
                     |                |                |
                     v                v                v
                 [ Execute ]     [ Task Graph ]   [ Cancel Task ]
```

---

## 2. Core Modules

### `task_graph/models.py`
- **`TaskState` & `NodeState`**: Strict lifecycle states (`PENDING`, `RUNNING`, `VERIFYING`, `COMPLETED`, `FAILED`, `RETRYING`, `REPLANNING`, `PAUSED`, `CANCELLED`).
- **`FailureCategory`**: Granular classification of anomalies (`TRANSIENT`, `ELEMENT_NOT_FOUND`, `UNVERIFIED_STATE`, `STALE_ELEMENT`, `NETWORK_OFFLINE`, `PERMISSION_DENIED`, `RESOURCE_BUSY`, `RESOURCE_DEADLOCK`, `NO_PROGRESS_LOOP`, `FATAL`).
- **`RecoveryStrategy`**: Automated recovery actions (`RETRY`, `REFRESH`, `RECONNECT`, `RECAPTURE`, `REPLAN`, `SKIP_OPTIONAL`, `ABORT`).
- **`TaskNode`**: Encapsulates actions, verifiers, dependencies, idempotency contracts, resource locks, and retry policies.
- **`TaskGraph`**: Directed acyclic task structure managing topological progression, node registration, dynamic replan branching, and context persistence.

### `task_graph/resources.py`
- **`ResourceLockManager`**: Concurrency controller preventing race conditions and deadlocks between browser sessions, desktop pointer devices, ADB devices, and audio endpoints.
- Features: Lock acquisition timeouts, deadlock detection via sorted key ordering, stale lock reclamation, and safe context tracking.

### `task_graph/recovery.py`
- **`RecoveryEngine`**:
  - Automatically categorizes exceptions into `FailureCategory`.
  - Calculates exponential backoff with jitter (`backoff_factor * (2 ^ attempt) + uniform(0, jitter)`).
  - Enforces loop detection: tracks state signatures across attempts and triggers `NO_PROGRESS_LOOP` after repeated identical failed states.
  - Generates adaptive recovery plans based on failure category.

### `task_graph/executor.py`
- **`TaskExecutionEngine`**:
  - Evaluates topological dependencies and executes ready nodes.
  - Handles resource lock acquisition and cleanup per node.
  - Executes the `PLAN → ACT → OBSERVE → VERIFY` loop.
  - Dynamically synthesizes fallback nodes (`_replan_node`) when replanning is requested and within budget (`max_replans`).
  - Supports task cancellation, runtime pausing, and resuming.

---

## 3. Omnia Tool Integration (`omnia_tools.py`)

Module 14 registers 5 new execution governance tools in the Omnia tool suite:
1. `get_active_task_status(task_id)`: Fetches current node status, execution metrics, and history.
2. `cancel_active_task(task_id, reason)`: Gracefully terminates an active task graph.
3. `pause_active_task(task_id)`: Temporarily suspends execution without losing state.
4. `resume_active_task(task_id)`: Resumes execution of a paused task graph.
5. `list_active_orchestration_tasks()`: Enumerates all registered tasks and their lifecycle state.

---

## 4. Test Suite & Diagnostics

Run the Module 14 test suite:
```bash
python test_task_graph_module14.py
```
Outputs:
- Sequential & Dependent execution verification.
- Action success with unverified state rejection.
- Bounded retries with exponential backoff and jitter.
- Resource contention and mutual exclusion.
- Infinite loop detection after zero progress.
- Dynamic replanning fallback injection.
- Mid-flight cancellation and cleanup.
- Pause and resume state synchronization.

Run the holistic system diagnostic suite:
```bash
python system_check.py
```
Validates device mesh, vector memory, Playwright, Event Bus, Module 13 Vision, and Module 14 Task Graph.
