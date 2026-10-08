# Module 23: Distributed State Synchronization, Replication & Reconciliation Engine

## 1. Objective & Core Invariants

Module 23 serves as Omnia's authoritative **Distributed State Synchronization, Replication & Reconciliation Layer**.

Building on the node identity, membership, epochs, leases, ownership, and fencing established in Module 22, Module 23 answers:
> Once Omnia knows which node owns a piece of state, how does that state safely propagate to other authorized nodes and converge after failures, disconnects, lag, restart, or partition?

### Core Architectural Invariants
1. **Explicit State Classification**: Every namespace declares its replication policy (`AUTHORITATIVE`, `REPLICATED`, `DERIVED`, `EPHEMERAL`, `LOCAL_ONLY`, `SENSITIVE`). Default behavior for unknown state is `DO NOT REPLICATE`. Sensitive state (`secrets`, `audio_buffers`) is strictly isolated and never leaves the local node.
2. **Deterministic Versioning & Epoch Fencing**: State synchronization never relies on wall-clock timestamps alone. Monotonic epochs take absolute precedence over revisions. Stale epochs (`source_epoch < current_epoch`) are rejected with `FENCED_STALE_EPOCH`.
3. **Module 22 Authority**: Before applying any ownership-sensitive update (such as task state), Module 22 ownership contracts are verified (`coordination_service.get_task_owner()`).
4. **Idempotency & Out-of-Order Gap Detection**: Duplicate delta delivery produces exactly one logical state transition. Version gaps (e.g. received revision 101 when local is 97) trigger delta buffering and catch-up requests rather than silent state corruption.
5. **Cryptographic Integrity & Frozen Snapshots**: Frozen snapshots carry cryptographic content hashes (`SHA-256`). Synchronization is never reported successful without verifying state hash matching.
6. **Explicit Anti-Entropy & Conflict Logging**: Divergence is detected through hierarchical hash comparison (`namespace` $\rightarrow$ `entity`). Conflicts are logged with diagnostic evidence rather than blindly overwritten.

---

## 2. Architecture & Data Flow

```text
AUTHORITATIVE STATE MUTATION
        ↓
REPLICATION SERVICE (replication/service.py)
        ↓
NAMESPACE POLICY CHECK (replication/namespaces.py)
        ↓
CREATE DELTA & HASH (replication/deltas.py)
        ↓
DURABLE PERSISTENCE (replication/persistence.py)
        ↓
EVENT FABRIC BROADCAST (events/schemas.py)
        ↓
REMOTE NODE RECEIVES DELTA
        ↓
VALIDATE EPOCH FENCING & OWNERSHIP (replication/versioning.py)
        ↓
APPLY IDEMPOTENTLY & DRAIN BUFFERS (replication/deltas.py)
        ↓
UPDATE SYNC CURSOR & ACKNOWLEDGE (replication/models.py)
```

---

## 3. Subsystem Breakdown

### 3.1 Namespaces & Classification (`namespaces.py`)
- Defines authoritative namespaces: `tasks`, `missions`, `schedules`, `capabilities`.
- Defines non-replicated / sensitive namespaces: `secrets`, `audio_buffers`, `ephemeral_frames`.
- Enforces security rule: Unknown namespaces default to non-replicated.

### 3.2 Deterministic Versioning & Epoch Fencing (`versioning.py`)
- Compares versions without timestamp heuristics: evaluates `epoch`, `revision`, and causal lineage.
- Enforces Module 22 epoch fencing: rejects incoming deltas from previous epochs.

### 3.3 Incremental Deltas & Buffering (`deltas.py`)
- Operations: `CREATE`, `UPDATE`, `PATCH`, `DELETE`, `REPLACE`.
- Deduplication cache ensures repeated delivery of the same delta is safe.
- Out-of-order buffer retains future revisions until preceding gaps are closed.

### 3.4 Snapshots & Integrity Verification (`snapshots.py`, `integrity.py`)
- Freezes point-in-time namespace state partitions.
- Computes SHA-256 Merkle-like root hashes over entity records.
- Verifies checksums prior to installing snapshot data.

### 3.5 Anti-Entropy Reconciliation & Conflicts (`reconciliation.py`, `conflicts.py`)
- Compares root namespace hashes across peers.
- Pinpoints mismatched entities and resolves via deterministic policy (`EPOCH_WINS` $\rightarrow$ `OWNER_WINS` $\rightarrow$ `REVISION_WINS` $\rightarrow$ `ESCALATE`).
- Records conflicts with evidence logs (`replication_conflicts` table).

### 3.6 Backpressure & Transport (`backpressure.py`, `transport.py`)
- Tracks peer lag and queue depth.
- Automatically triggers snapshot fallback when peer lag exceeds threshold.
- Integrates with Module 12 (`mesh_replicator` / `mesh_registry`).

### 3.7 Durability & Persistence (`persistence.py`)
- Implements Schema Version 5 migration:
  - `replication_namespaces`
  - `replication_state_records`
  - `replication_deltas`
  - `replication_snapshots`
  - `replication_sync_cursors`
  - `replication_conflicts`

---

## 4. Operational Tools & HUD Integration

The following tools are registered in `omnia_tools.py`:
- `get_replication_status()`: Telemetry on active namespaces, applied deltas, lag, and divergence.
- `list_replication_namespaces()`: Lists configured state namespaces and their security policies.
- `trigger_state_reconciliation(namespace_id)`: Initiates anti-entropy evaluation.

---

## 5. Verification

Module 23 is verified by:
- `test_replication_module23.py`: 8 unit tests covering secret isolation, versioning, epoch fencing, duplicate delta idempotency, revision gap buffering, snapshot verification, and anti-entropy.
- `test_replication_e2e_module23.py`: 3-node cluster tests covering continuous delta stream propagation, offline node reconnect with snapshot catch-up, and epoch failover fencing.
- `system_check.py`: Stage `[15/15]` end-to-end diagnostic readiness test.
