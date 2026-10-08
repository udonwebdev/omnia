# Module 15: Persistent Task State & Crash Recovery

## 1. Overview & Core Philosophy

Module 15 introduces **Durable Task State, Checkpointing, and Crash Recovery** to the Omnia autonomous orchestration framework.

Operational Guarantee:
> **Omnia must be able to lose its process without losing its understanding of what it was doing — while still refusing to blindly trust its old state after reality may have changed.**

The recovery philosophy is:
```text
REMEMBER
   ↓
REVALIDATE
   ↓
DECIDE
   ↓
RESUME / ROLLBACK / REPLAN / ABORT
```
never:
```text
LOAD LAST STATE
   ↓
CONTINUE BLINDLY
```

---

## 2. Architecture & Subsystem Components

```text
                                  +------------------------------------+
                                  |         CRASH RECOVERY ENGINE      |
                                  +------------------------------------+
                                                     |
                                   Scan Crashed / Interrupted Tasks
                                                     |
                                                     v
                                  +------------------------------------+
                                  |   CHECKPOINT INTEGRITY & FRESHNESS |
                                  |    (SHA-256 Checksum Validation)   |
                                  +------------------------------------+
                                                     |
                 +-----------------------------------+-----------------------------------+
                 |                                   |                                   |
                 v                                   v                                   v
      [ RECOVERABLE (Safe) ]               [ UNCERTAIN (Risky) ]               [ CORRUPTED / STALE ]
                 |                                   |                                   |
         RESUME_FROM_CHECKPOINT             REVALIDATE_AND_RESUME                 ABORT_TASK
                 |                                   |                                   |
                 v                                   v                                   v
       [ Resume Execution ]              Inspect Real-World Reality             Log Forensic Error
                                              (DOM / Vision / API)
```

### Modules in `persistence/`:
1. **`models.py`**:
   - `RecoveryCondition`: `RECOVERABLE`, `UNCERTAIN`, `STALE`, `CORRUPTED`, `UNSAFE_TO_RESUME`.
   - `ResumeStrategy`: `RESUME_FROM_CHECKPOINT`, `REVALIDATE_AND_RESUME`, `ROLLBACK_TO_CHECKPOINT`, `REPLAN_FROM_CURRENT_STATE`, `ABORT_TASK`.
   - `CheckpointValidity`: `VALID`, `STALE`, `INVALID`, `UNKNOWN`.
   - `CheckpointPolicy`: `CHECKPOINT_TASK_START`, `CHECKPOINT_NODE_COMPLETE`, `CHECKPOINT_BEFORE_RISKY_ACTION`, `CHECKPOINT_AFTER_VERIFICATION`.
   - Data records: `PersistedTaskRecord`, `PersistedNodeRecord`, `PersistedCheckpoint`, `PersistedJournalEvent`, `PersistedResourceLock`, `TaskHeartbeat`.

2. **`migrations.py`**:
   - Transactional, repeat-safe schema migrations.
   - Automatic pre-migration snapshot database backups in `persistence_backups/`.
   - Tracks version in `schema_migrations`.

3. **`store.py`**:
   - SQLite engine with foreign keys, indexing, and connection management.
   - Automatic credential redaction (`sanitize_payload`) scrubbing passwords, bearer tokens, API keys, and credit cards from persisted records and journals.
   - Monotonic event sequence enforcement per task.
   - Process heartbeat tracking and stale lock reclamation.

4. **`checkpoints.py`**:
   - Cryptographic SHA-256 checksums across critical task state, node states, and variables.
   - Pre-action checkpoints for non-idempotent actions (`NOT_SAFE_TO_RETRY`).
   - Tamper-evident corruption detection.

5. **`recovery.py`**:
   - `CrashRecoveryEngine`: Scans for dead processes, classifies interrupted tasks, and provides real-world environmental revalidation hooks.
   - Records recovery decisions durably into `recovery_attempts` table.

---

## 3. Database Schema

- **`tasks`**: `task_id` (PK), `goal`, `status`, `current_node_id`, `created_at`, `started_at`, `updated_at`, `completed_at`, `deadline_ts`, `attempt_count`, `replan_count`, `metadata_json`.
- **`task_nodes`**: `(task_id, node_id)` (PK), `name`, `status`, `attempt_count`, `idempotency`, `dependencies_json`, `last_verification_status`, `last_error_category`.
- **`task_checkpoints`**: `checkpoint_id` (PK), `task_id`, `node_id`, `timestamp`, `checksum`, `task_state`, `node_states_json`, `variables_json`, `policy_trigger`.
- **`task_events`**: `event_id` (PK), `task_id`, `sequence_number` (Unique per task), `event_type`, `payload_json`.
- **`task_resource_locks`**: `lock_id`, `resource_id` (Unique), `task_id`, `heartbeat_ts`, `process_id`.
- **`task_heartbeats`**: `task_id` (PK), `heartbeat_ts`, `current_node_id`, `process_id`.
- **`recovery_attempts`**: `attempt_id` (PK), `task_id`, `condition`, `strategy`, `decision_reason`, `success`.

---

## 4. Verification & Testing

### Automated Test Suite: `test_persistence_module15.py`
Run tests:
```bash
python -m unittest test_persistence_module15.py -v
```
Verifies:
1. `test_database_initialization_and_migrations`: Fresh DB setup, tables, indexes, idempotence.
2. `test_task_lifecycle_persistence_and_journaling`: Monotonic sequence ordering and durable state.
3. `test_checkpoint_atomicity_and_tamper_detection`: Checksum generation and altered state rejection.
4. `test_security_redaction_in_persistence`: Recursive credential and token scrubbing.
5. `test_crash_recovery_classification_and_stale_locks`: Expired heartbeat detection and lock reclamation.
6. `test_real_world_revalidation_decision`: Revalidation against external realities.
7. `test_genuine_process_crash_and_restart_recovery`: Child process abruptly killed with `os._exit(42)` and successfully restored and completed on restart.
8. `test_uncertain_action_recovery_with_real_world_inspection`: External order completion detected post-crash to prevent duplicate execution.

All 8 tests PASS with exit code 0.
