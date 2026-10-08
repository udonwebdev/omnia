# OMNIA MODULE 16 — INTENT COMPILER & TASK PLANNER

The **Intent Compiler & Task Planner** translates natural language user intents into structured, validated, dependency-ordered, and self-healing executable task graphs.

---

## 1. Architecture & Pipeline

```text
USER INTENT (Natural Language)
        ↓
INTENT PARSER & NORMALIZATION (`parser.py`)
  - Entity extraction (URLs, Applications, Devices, Times)
  - Objective normalization
  - Prompt injection detection & defense
  - Ambiguity scoring & clarification triggers
        ↓
CONTEXT RESOLUTION (`resolver.py`)
  - Active ADB mesh devices
  - Open browser sessions & current URL
  - Vector memory associative recall
        ↓
CAPABILITY MAPPING (`capability_mapper.py`)
  - Dynamic discovery of Omnia tools
  - Parameter contracts, risks, idempotency & preconditions
        ↓
TASK DECOMPOSITION (`decomposer.py`)
  - Subtask breakdown with explicit preconditions and postconditions
  - Deterministic verification strategy assignment
        ↓
PLAN VALIDATION & RISK ANALYSIS (`validator.py`)
  - DFS cycle detection
  - Capability & dependency resolution
  - Resource lock conflict detection
  - Heuristic plan scoring (0.00 – 1.00)
        ↓
TASK GRAPH SYNTHESIS (`compiler.py`)
  - Conversion to Module 14 `TaskGraph` & `TaskNode` models
  - Plan versioning (V1, V2 upon failure replanning)
  - Human-readable explanation generation
        ↓
MODULE 14 (Self-Healing Execution) & MODULE 15 (Durable Checkpoints & Persistence)
```

---

## 2. Key Components

- **`intent/models.py`**: Strongly typed data structures (`UserIntent`, `AmbiguityDetail`, `AmbiguityState`, `CapabilityMetadata`, `PlannedStep`, `PlanScore`, `ValidationStatus`, `ValidationReport`, `PlanVersion`, `CompiledPlan`).
- **`intent/parser.py`**: Robust NLP parser handling conversational pleasantries, entity recognition, prompt injection defense, and ambiguity evaluation.
- **`intent/resolver.py`**: Asynchronously enriches user intentions with active device, browser, and memory state.
- **`intent/capability_mapper.py`**: Maps and catalogs Omnia tools (browser, shell, adb, vision, memory, voice) with metadata on reversibility, risk, idempotency, and required locks.
- **`intent/decomposer.py`**: Breaks down intentions into discrete steps equipped with unambiguous verification strategies.
- **`intent/validator.py`**: Rigorously analyzes graph validity, safety bounds, destructive risks, cycles, and missing prerequisites.
- **`intent/compiler.py`**: High-level coordinator that produces Module 14 graphs, notifies the HUD event bus, stores versioned plans, and provides dynamic replanning on step failure.

---

## 3. Integration with Omnia Core

Module 16 exposes two primary agent tools in `omnia_tools.py`:
1. `compile_user_intent_plan(natural_language_goal: str)`: Parses, resolves, validates, and compiles user goals into ready-to-run `TaskGraph` plans.
2. `explain_execution_plan(plan_id: str)`: Returns a structured explanation of the steps, safety constraints, risk levels, and verification criteria for a compiled plan.

---

## 4. Verification & Testing

Module 16 is verified via the 12-test suite in `test_intent_module16.py` and diagnostic stage `[8/8]` in `system_check.py`:
- Entity extraction & target resolution
- Contextual pronoun disambiguation & clarification questions
- Prompt injection immunity
- Cyclic dependency detection
- Full-circle execution through Module 14 executor and Module 15 persistence
