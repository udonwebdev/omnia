# OMNIA MODULE 18: EVENT FABRIC & REACTIVE AUTONOMY

## 1. Overview & Architectural Role

The **Event Fabric** is Omnia's central nervous system for reactive, asynchronous, and self-healing autonomy. Unlike synchronous command execution pipelines, the Event Fabric handles typed, immutable facts representing state changes across all hardware, perception, execution, planning, and security subsystems.

```text
       DEVICE EVENT / HARDWARE TELEMETRY / USER INTENT
                              │
                              ▼
               ┌──────────────────────────────┐
               │         EVENT FABRIC         │
               │   - Schema Validation        │
               │   - Priority Routing Lanes   │
               │   - Sliding Deduplication    │
               │   - High-Freq Coalescing     │
               └──────────────┬───────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
   [EPHEMERAL]          [OPERATIONAL]          [DURABLE]
 UI/Cursor/Telemetry     Task Graph Steps     Audit / Policy /
 In-Memory Only          State Bus Broadcast  SQLite Journal
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                              ▼
                 REACTIVE AUTONOMY HANDLERS
             - Deadlock / Degraded Detection
             - Self-Healing Graph Mutations
             - Dynamic Fallback Interventions
             - HUD WebSocket Streaming
```

---

## 2. Strong Typing & Envelope Contract

Every message published through the Event Fabric is wrapped in a strongly-typed `EventEnvelope`:

```python
@dataclass
class EventEnvelope:
    event_id: str                      # Deterministic or unique UUID
    event_type: str                    # Dot-namespaced family (e.g. task.started)
    event_version: str = "1.0.0"       # Event schema version
    occurred_at: float                 # Sensor/creation timestamp
    published_at: float                # Dispatch timestamp
    source: str                        # Emitting subsystem (e.g. module.14.executor)
    subject: Optional[str]             # Specific entity ID (e.g. phone_001)
    correlation_id: str                # Trace identifier spanning intent to completion
    causation_id: Optional[str]        # Parent event ID that triggered this event
    task_id: Optional[str]             # Active task graph identifier
    priority: EventPriority            # CRITICAL (4), HIGH (3), NORMAL (2), LOW (1)
    severity: EventSeverity            # INFO, NOTICE, WARNING, ERROR, CRITICAL
    durability: EventDurability        # EPHEMERAL, OPERATIONAL, DURABLE
    schema_version: str = "1.0.0"
```

---

## 3. Durability Tiers

1. **`EPHEMERAL`**:
   - Zero disk I/O.
   - High-throughput UI mouse trajectories, visual gaze frames, low-priority sensor ticks.
   - Eligible for backpressure shedding when queues reach capacity thresholds.

2. **`OPERATIONAL`**:
   - In-memory event stream across running subsystems.
   - Broadcasted to the HUD and client interfaces over WebSockets (`/ws/hud`).

3. **`DURABLE`**:
   - Persisted synchronously to SQLite `task_events` with guaranteed monotonic sequence numbers per task.
   - Enables crash recovery and analytical reconstruction without re-executing real-world side effects.

---

## 4. Priority Routing Lanes & Handler Isolation

The Event Fabric routes events through four discrete priority lanes:
- `CRITICAL`: Immediate pre-emptive dispatch (policy blocks, panic stops, safety violations).
- `HIGH`: Real-time reactive autonomy (device disconnections, hardware timeouts, step failures).
- `NORMAL`: Standard lifecycle events (`task.started`, `task.node_completed`, `intent.compiled`).
- `LOW`: Background telemetry and metrics.

### Fault Isolation & Dead-Letter Quarantine
Consumer handlers run in isolated async tasks. If a consumer raises an exception:
1. The fabric performs exponential backoff retries up to `max_retries`.
2. If retries are exhausted, the event and the offending exception stack trace are quarantined in the **Dead-Letter Buffer** (`DeadLetterRecord`), preventing cascade crashes across other subscribers.

---

## 5. Safe Read-Only Analytical Replay

The Event Journal provides trace reconstruction via `event_journal.replay_trace(task_id)`:
- Reconstructs exact historical execution narratives.
- **Safety Guarantee**: Purely read-only analytical inspection. Replay NEVER invokes external tools, device ADB bridges, or browser actions.

---

## 6. Verification Status

- **Unit Suite**: `test_event_fabric_module18.py` (20/20 PASS)
- **E2E Suite**: `test_event_fabric_e2e_module18.py` (PASS — Intent $\to$ Capability $\to$ Execution $\to$ Reactive Fallback)
- **System Readiness**: `system_check.py` Section `[10/10]` (PASS across all 5 checks)
