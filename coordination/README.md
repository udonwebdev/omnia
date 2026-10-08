# Module 22: Distributed Coordination, Leader Election & Worker Consensus

## 1. Objective & Core Invariants

Module 22 serves as Omnia's authoritative **Distributed Coordination Layer**.

When multiple Omnia processes, workers, machines, or mesh nodes participate in the same autonomous system, Module 22 provides the coordination primitives required to act as one coherent control plane.

### Core Architectural Invariants
1. **Discovery is NOT Authorization**: Mesh discovery informs Omnia what peers exist; Module 22 determines which node is authoritative and verifies node trust state before enrolling them in quorum calculations.
2. **Scheduling is NOT Distributed Ownership**: The Resource Scheduler (Module 21) decides what should run next; Module 22 prevents multiple nodes from concurrently executing the same task or mission via exclusive ownership claims.
3. **Monotonic Epochs & Fencing Tokens**: Every leadership election increments a monotonic epoch. Authoritative commands must carry the active epoch and a valid fencing token. Stale epochs (`FENCED_STALE_EPOCH`) and expired leases are strictly rejected.
4. **Quorum Majority Calculus**: Quorum is strictly $\lfloor N / 2 \rfloor + 1$ over active cluster nodes. Minority partitions can never elect a leader, issue fencing tokens, or claim authoritative ownership.
5. **Lease-Bound Distributed Locks & Claims**: All locks and ownership claims have bounded lease durations. If a node crashes, its leases are safely reaped upon expiration or startup reconciliation.

---

## 2. Architecture & Subsystems

```text
MULTIPLE OMNIA NODES
        ↓
CLUSTER MEMBERSHIP (coordination/membership.py)
        ↓
LEADER ELECTION & MONOTONIC EPOCHS (coordination/election.py)
        ↓
DISTRIBUTED TASK & MISSION CLAIMS (coordination/ownership.py)
        ↓
LEASE-BOUND DISTRIBUTED LOCKS (coordination/ownership.py)
        ↓
DURABILITY & CRASH RECONCILER (coordination/persistence.py)
        ↓
COORDINATION SERVICE & EVENT FABRIC (coordination/service.py)
```

---

## 3. Subsystem Breakdown

### 3.1 Cluster Membership (`membership.py`)
- **Stable Identity**: Cryptographic fingerprints (`SHA-256(node_id:node_name:platform:ts)`).
- **Node Lifecycle**: `JOINING` -> `ACTIVE` -> `SUSPECTED` -> `UNREACHABLE` -> `QUARANTINED` / `LEFT`.
- **Heartbeat & Failure Detector**: Heartbeats must arrive within 15s; dead nodes are marked suspected and isolated from quorum.
- **Quorum Calculus**: $\lfloor N / 2 \rfloor + 1$ computed against total registered non-quarantined nodes.

### 3.2 Leader Election & Consensus (`election.py`)
- **Election Loop**: Nodes initiate election with monotonic epoch increment.
- **Quorum Voting**: Candidate must win a majority of active trusted nodes.
- **Leadership Lease**: Leader receives a time-bounded lease (`10.0s`) and a unique fencing token (`fence_ep<epoch>_<uuid>`).
- **Fencing Enforcer**: Commands verified against epoch and token; stale commands rejected.

### 3.3 Exclusive Work Ownership (`ownership.py`)
- **Distributed Task Contracts**: Nodes claim exclusive ownership of a task or mission before execution.
- **Conflict Prevention**: Rejects duplicate execution attempts (`CLAIM_CONFLICT`) by remote nodes.
- **Lease Expiration & Reaping**: Expired claims are reclaimed and failover events broadcasted.
- **Distributed Locks**: Mutual exclusion on resources (`device:<id>`, `browser:<session>`).

### 3.4 Durability & Crash Reconciliation (`persistence.py`)
- **Schema Migration V4**: SQLite tables `cluster_nodes`, `leadership_leases`, `distributed_ownership_claims`, `distributed_locks`.
- **Startup Reconciliation**: Reaps expired leases, cleans orphan locks, and marks active claims as `EXPIRED` if lease expired during a crash.

### 3.5 Integration with Omnia Subsystems
- **Task Graph Executor (`task_graph/executor.py`)**: Checks distributed task ownership prior to starting task execution; blocks duplicate runs (`OWNERSHIP_BLOCKED`) and releases claims upon task completion.
- **Event Fabric (`events/schemas.py`)**: Emits and validates typed events (`coordination.started`, `leader.elected`, `leader.lost`, `node.joined`, `ownership.claimed`, `ownership.released`, `ownership.expired`, `ownership.rejected`, `split_brain.detected`).
- **Omnia Tools (`omnia_tools.py`)**: Exposes `get_coordination_status`, `list_cluster_members`, `claim_task_ownership`, and `start_cluster_election`.

---

## 4. Verification

Module 22 is verified by:
- `test_coordination_module22.py`: 10 unit tests covering stable identities, quorum math, failure detection, election, fencing token rejection, ownership conflicts, distributed locks, lease reaping, and durability.
- `test_coordination_e2e_module22.py`: E2E verification of multi-node duplicate task execution prevention and minority partition split-brain resilience.
- `system_check.py`: Stage `[14/14]` comprehensive end-to-end readiness diagnostic check.
