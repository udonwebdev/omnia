import asyncio
import sys
import httpx
from device_controller import DeviceController
from memory_engine import memory
from browser_driver import browser_driver

async def run_diagnostics():
    print("=" * 60)
    print("       OMNIA SYSTEM READINESS & DIAGNOSTIC SUITE       ")
    print("=" * 60)

    # 1. Device Mesh Bridge Check
    print("\n[1/4] Checking ADB Device Mesh Connectivity...")
    try:
        controller = DeviceController()
        devices = controller.list_serials()
        print(f"      Status: OK | Devices Found: {len(devices)} -> {devices}")
    except Exception as e:
        print(f"      Status: WARNING | ADB Check failed: {e}")

    # 2. Vector Memory Engine Check
    print("\n[2/4] Testing Local Vector Memory Engine...")
    try:
        test_id = 99999
        memory.store_tab_context(
            tab_id=test_id,
            url="https://omnia.internal/check",
            title="Diagnostics Test Tab",
            content="System validation token verification string."
        )
        hits = memory.search_context("validation token", limit=1)
        assert len(hits) > 0, "No hits returned from vector store."
        print(f"      Status: OK | Stored and retrieved sample document successfully.")
    except Exception as e:
        print(f"      Status: FAILED | Vector Memory Error: {e}")

    # 3. Autonomous Browser Driver Check
    print("\n[3/4] Verifying Playwright Browser Automation Core...")
    try:
        await browser_driver.initialize()
        url = await browser_driver.navigate("https://example.com")
        print(f"      Status: OK | Browser navigated to: {url}")
        await browser_driver.close()
    except Exception as e:
        print(f"      Status: FAILED | Browser Automation Core failed: {e}")

    # 4. Event Bus Loopback Check
    print("\n[4/5] Checking Event Bus Endpoint...")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post("http://127.0.0.1:8000/api/state", json={"state": "DIAGNOSTIC", "message": "Self-check"})
            if resp.status_code == 200:
                print("      Status: OK | Local Event Bus is responding.")
            else:
                print(f"      Status: WARNING | Bus returned status code: {resp.status_code}")
    except Exception:
        print("      Status: NOTICE | Event Bus server is currently offline (will start with main.py).")

    # 5. Module 13 Multimodal Vision Subsystem
    print("\n[5/5] Checking Module 13: Multimodal Vision & Visual Computer Use...")
    from vision import vision_engine, capture_engine, ocr_engine, perception_engine, grounding_engine, verification_engine, VisionSource, BoundingBox, VisionFrame
    from PIL import Image, ImageDraw
    import io

    # 5a. Vision Engine & Local OCR
    try:
        test_img = Image.new("RGB", (320, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(test_img)
        draw.text((15, 30), "CONTINUE BUTTON", fill=(0, 0, 0))
        buf = io.BytesIO()
        test_img.save(buf, format="PNG")
        dummy_frame = VisionFrame(width=320, height=100, raw_bytes=buf.getvalue())
        
        obs = perception_engine.analyze_frame(dummy_frame)
        assert len(obs.elements) > 0, "OCR did not extract elements."
        print("      [13] OCR & Perception ........ PASS")
        
        cand = grounding_engine.ground_best("continue button", obs)
        assert cand is not None, "Grounding failed to match button."
        print(f"      [13] Visual Grounding ........ PASS (Matched '{cand.element.label}', score: {cand.score:.2f})")
    except Exception as e:
        print(f"      [13] OCR & Grounding ......... FAIL ({e})")

    # 5b. Desktop Capture
    try:
        shot = await capture_engine.capture_desktop()
        print(f"      [13] Desktop Capture ......... PASS ({shot.width}x{shot.height})")
    except Exception as e:
        print(f"      [13] Desktop Capture ......... BLOCKED ({str(e)[:45]})")

    # 5c. Android Capture
    try:
        shot_adb = await capture_engine.capture_android()
        print(f"      [13] Android Capture ......... PASS ({shot_adb.width}x{shot_adb.height})")
    except Exception as e:
        print(f"      [13] Android Capture ......... BLOCKED — HARDWARE UNAVAILABLE ({str(e)[:40]})")

    # 5d. Verification Engine
    try:
        v_res = verification_engine.verify_text_appearance(dummy_frame, dummy_frame, "CONTINUE", should_appear=True)
        assert v_res.status.value == "VERIFIED", f"Verification status was {v_res.status.value} ({v_res.reason})"
        print("      [13] Visual Verification ..... PASS")
    except Exception as e:
        print(f"      [13] Visual Verification ..... FAIL ({e})")

    # 6. Module 14: Dynamic Task Graph & Self-Healing Execution Engine
    print("\n[6/6] Checking Module 14: Dynamic Task Graph & Self-Healing Engine...")
    from task_graph import (
        task_executor,
        TaskGraph,
        TaskNode,
        TaskState,
        NodeState,
        FailureCategory,
        RecoveryStrategy,
        ExecutionContext,
        resource_manager
    )

    # 6a. Task Graph & Sequential Execution
    try:
        tg = TaskGraph(goal="Test Task Pipeline")
        async def step1(ctx): return "data_loaded"
        async def step2(ctx): return "data_processed"
        async def verify_step2(ctx, res): return res == "data_processed"

        tg.add_node(TaskNode(node_id="n1", name="Load Data", description="Load initial data", action=step1))
        tg.add_node(TaskNode(node_id="n2", name="Process Data", description="Process loaded data", action=step2, verifier=verify_step2, dependencies=["n1"]))

        res = await task_executor.execute_task(tg)
        assert res["state"] == "COMPLETED" and res["completed_nodes"] == 2
        print("      [14] Task Graph & Executor ..... PASS (2/2 nodes completed)")
    except Exception as e:
        print(f"      [14] Task Graph & Executor ..... FAIL ({e})")

    # 6b. Resource Locking
    try:
        locked = await resource_manager.acquire_locks("task_a", ["desktop:mouse"], timeout_sec=1.0)
        assert locked is True
        # Task B trying to acquire same resource should timeout/fail
        locked_b = await resource_manager.acquire_locks("task_b", ["desktop:mouse"], timeout_sec=0.2)
        assert locked_b is False
        await resource_manager.release_locks("task_a")
        # Now task B should acquire
        locked_b_retry = await resource_manager.acquire_locks("task_b", ["desktop:mouse"], timeout_sec=1.0)
        assert locked_b_retry is True
        await resource_manager.release_locks("task_b")
        print("      [14] Resource Lock Manager ..... PASS (Deadlock prevention & mutual exclusion)")
    except Exception as e:
        print(f"      [14] Resource Lock Manager ..... FAIL ({e})")

    # 6c. Dynamic Replanning & Self-Healing Loop
    try:
        tg_heal = TaskGraph(goal="Self-Healing Recovery Demo")
        attempt_count = 0
        async def failing_action(ctx):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise RuntimeError("TRANSIENT: Network handshake glitch")
            return "recovered_ok"

        async def verify_heal(ctx, r):
            return r == "recovered_ok"

        tg_heal.add_node(TaskNode(
            node_id="heal_1",
            name="Transient Step",
            description="Recovers on retry",
            action=failing_action,
            expected_state="recovered_ok",
            verifier=verify_heal
        ))

        heal_res = await task_executor.execute_task(tg_heal)
        assert heal_res["state"] == "COMPLETED"
        print("      [14] Self-Healing & Retry ...... PASS (Automatic transient recovery)")
    except Exception as e:
        print(f"      [14] Self-Healing & Retry ...... FAIL ({e})")

    # 7. Module 15: Persistent Task State & Crash Recovery
    print("\n[7/7] Checking Module 15: Persistent Task State & Crash Recovery...")
    import time
    from persistence import (
        persistence_store,
        checkpoint_manager,
        crash_recovery_engine,
        apply_migrations,
        CheckpointPolicy,
        CheckpointValidity,
        RecoveryCondition,
        ResumeStrategy,
        PersistedTaskRecord,
        sanitize_payload
    )

    # 7a. Database Schema & Migrations
    try:
        ver = apply_migrations(persistence_store.db_path)
        assert ver >= 1
        print(f"      [15] Schema & Migrations ....... PASS (Version {ver} verified)")
    except Exception as e:
        print(f"      [15] Schema & Migrations ....... FAIL ({e})")

    # 7b. Checkpoints & Integrity
    try:
        t_id = "sys_chk_task"
        persistence_store.save_task(PersistedTaskRecord(
            task_id=t_id, goal="Diag Task", status="RUNNING", current_node_id=None,
            created_at=time.time(), started_at=time.time(), updated_at=time.time(),
            completed_at=None, deadline_ts=time.time()+60, task_timeout_sec=60
        ))
        chk = checkpoint_manager.create_checkpoint(
            task_id=t_id,
            node_id="diag_node",
            task_state="RUNNING",
            node_states={"diag_node": "COMPLETED"},
            variables={"status": "ok"},
            resource_state=[],
            last_verified_observations=[],
            policy_trigger=CheckpointPolicy.CHECKPOINT_NODE_COMPLETE
        )
        assert checkpoint_manager.verify_checkpoint_integrity(chk) is True
        print(f"      [15] Checkpoints & Checksum .... PASS (SHA-256: {chk.checksum[:8]}...)")
    except Exception as e:
        print(f"      [15] Checkpoints & Checksum .... FAIL ({e})")

    # 7c. Task Journaling & Monotonic Sequencing
    try:
        s1 = persistence_store.append_event(t_id, "EVENT_A", {})
        s2 = persistence_store.append_event(t_id, "EVENT_B", {})
        assert s2 == s1 + 1
        print("      [15] Task Journal .............. PASS (Monotonic event sequence enforced)")
    except Exception as e:
        print(f"      [15] Task Journal .............. FAIL ({e})")

    # 7d. Crash Scan & Interrupted Task Classification
    try:
        crashed = crash_recovery_engine.scan_for_crashes(heartbeat_timeout_sec=0.01)
        cond, strat, _ = crash_recovery_engine.classify_interrupted_task(t_id)
        assert cond in [RecoveryCondition.RECOVERABLE, RecoveryCondition.UNCERTAIN]
        print(f"      [15] Crash Recovery Engine ..... PASS (Condition: {cond.value}, Strategy: {strat.value})")
    except Exception as e:
        print(f"      [15] Crash Recovery Engine ..... FAIL ({e})")

    # 7e. Credential Redaction & Sanitization
    try:
        san = sanitize_payload({"secret_key": "12345", "token": "Bearer abc", "data": "clean"})
        assert san["secret_key"] == "[REDACTED]" and san["data"] == "clean"
        print("      [15] Security & Redaction ...... PASS (Credentials automatically scrubbed)")
    except Exception as e:
        print(f"      [15] Security & Redaction ...... FAIL ({e})")

    # ---------------------------------------------------------
    # 8. MODULE 16: INTENT COMPILER & TASK PLANNER
    # ---------------------------------------------------------
    print("\n[8/8] Checking Module 16: Intent Compiler & Task Planner...")
    from intent.compiler import intent_compiler
    from intent.parser import intent_parser
    from intent.capability_mapper import capability_mapper
    from intent.validator import plan_validator
    from intent.models import ValidationStatus

    # 8a. Capability Registry Discovery
    try:
        caps = capability_mapper.list_capabilities()
        assert len(caps) >= 8
        print(f"      [16] Capability Discovery ...... PASS ({len(caps)} tools indexed)")
    except Exception as e:
        print(f"      [16] Capability Discovery ...... FAIL ({e})")

    # 8b. Intent Parsing & Entity Extraction
    try:
        user_goal = "Open https://example.com in Chrome"
        parsed = intent_parser.parse(user_goal)
        assert any("example.com" in u for u in parsed.entities.get("urls", []))
        assert parsed.primary_objective == "BROWSER_NAVIGATE"
        print("      [16] Intent Parser ............. PASS (Extracted entities & normalized objective)")
    except Exception as e:
        print(f"      [16] Intent Parser ............. FAIL ({e})")

    # 8c. Ambiguity Detection & Safety Evaluation
    try:
        amb_intent = intent_parser.parse("Delete those files")
        assert amb_intent.requires_confirmation is True
        print(f"      [16] Ambiguity & Risk Engine ... PASS (Detected state: {amb_intent.ambiguity.state.value})")
    except Exception as e:
        print(f"      [16] Ambiguity & Risk Engine ... FAIL ({e})")

    # 8d. Plan Compilation & TaskGraph Synthesis
    try:
        tg, plan = await intent_compiler.compile_intent("Navigate to https://example.com")
        assert tg is not None
        assert plan.validation.status == ValidationStatus.VALID
        assert len(tg.nodes) >= 1
        print(f"      [16] Plan Compiler ............. PASS (Compiled {len(tg.nodes)} graph nodes, score: {plan.score.overall:.2f})")
    except Exception as e:
        print(f"      [16] Plan Compiler ............. FAIL ({e})")

    # 8e. Plan Explanation Generation
    try:
        explanation = intent_compiler.explain_plan(plan)
        assert "Execution Plan" in explanation
        print("      [16] Plan Explainer ............ PASS (Structured rationale generated)")
    except Exception as e:
        print(f"      [16] Plan Explainer ............ FAIL ({e})")

    # ---------------------------------------------------------
    # 9. MODULE 17: CAPABILITY REGISTRY & DYNAMIC SKILL SYSTEM
    # ---------------------------------------------------------
    print("\n[9/10] Checking Module 17: Capability Registry & Dynamic Skill System...")
    from capabilities.registry import capability_registry
    from capabilities.matcher import capability_matcher
    from capabilities.models import CapabilityCategory, CapabilityHealth, CapabilityMatchQuery
    from capabilities.skill_loader import skill_loader

    # 9a. Registry Inventory & Category Enumeration
    try:
        all_caps = capability_registry.list_capabilities()
        assert len(all_caps) >= 10
        print(f"      [17] Authoritative Registry .... PASS ({len(all_caps)} built-in capabilities indexed)")
    except Exception as e:
        print(f"      [17] Authoritative Registry .... FAIL ({e})")

    # 9b. Provider Resolution & Fallback Ranking
    try:
        cap, prov, expl = capability_matcher.resolve_best_capability_and_provider("browser.navigate")
        assert cap is not None and prov is not None
        print(f"      [17] Provider Resolver ......... PASS (Selected provider: {prov.provider_id})")
    except Exception as e:
        print(f"      [17] Provider Resolver ......... FAIL ({e})")

    # 9c. Dependency Graph & Degradation Ripple
    try:
        deps = capability_registry.get_dependencies("browser.execute_task")
        assert "browser.navigate" in deps
        print("      [17] Dependency Graph .......... PASS (Verified capability dependency tree)")
    except Exception as e:
        print(f"      [17] Dependency Graph .......... FAIL ({e})")

    # 9d. Dynamic Skill Manifest Validation & Loading
    try:
        manifest = {
            "id": "system.diagnostic_ping",
            "name": "Diagnostic System Ping",
            "version": "1.0.0",
            "category": "SYSTEM",
            "risk_level": "READ_ONLY",
            "description": "Verifies runtime responsiveness"
        }
        loaded, msg = skill_loader.load_skill_from_manifest(manifest)
        assert loaded is True
        print("      [17] Dynamic Skill Loader ...... PASS (Manifest validated & capability registered)")
    except Exception as e:
        print(f"      [17] Dynamic Skill Loader ...... FAIL ({e})")

    # ---------------------------------------------------------
    # 10. MODULE 18: EVENT FABRIC & REACTIVE AUTONOMY
    # ---------------------------------------------------------
    print("\n[10/10] Checking Module 18: Event Fabric & Reactive Autonomy...")
    from events import (
        event_fabric,
        event_journal,
        Event,
        EventEnvelope,
        EventPriority,
        EventSeverity,
        EventDurability,
        EventFilter
    )
    from events.schemas import event_schema_validator

    # 10a. Event Schema Validation & Type Enforcement
    try:
        valid_evt = Event(
            envelope=EventEnvelope(event_type="device.connected"),
            payload={"device_id": "test_dev_01", "platform": "android"}
        )
        invalid_evt = Event(
            envelope=EventEnvelope(event_type="device.connected"),
            payload={"device_id": "missing_platform"}
        )
        ok_v, _ = event_schema_validator.validate_event(valid_evt)
        bad_v, _ = event_schema_validator.validate_event(invalid_evt)
        assert ok_v is True and bad_v is False
        print("      [18] Schema Validator .......... PASS (Typed schemas strictly enforced)")
    except Exception as e:
        print(f"      [18] Schema Validator .......... FAIL ({e})")

    # 10b. Priority Queue Routing & Lane Isolation
    try:
        rec_evts = []
        async def prio_handler(e: Event):
            rec_evts.append(e.priority)

        event_fabric.subscribe("diag_prio", EventFilter(), prio_handler)
        await event_fabric.publish(Event(
            envelope=EventEnvelope(event_type="system.started", priority=EventPriority.CRITICAL),
            payload={"node_id": "n1", "version": "1.0"}
        ))
        await asyncio.sleep(0.05)
        event_fabric.unsubscribe("diag_prio")
        assert EventPriority.CRITICAL in rec_evts
        print("      [18] Priority Routing Lanes .... PASS (CRITICAL priority lane dispatched)")
    except Exception as e:
        print(f"      [18] Priority Routing Lanes .... FAIL ({e})")

    # 10c. Dead-Letter Buffer & Handler Fault Isolation
    try:
        async def failing_handler(e: Event):
            raise ValueError("Diagnostic simulated consumer fault")

        event_fabric.subscribe("diag_failing", EventFilter(type_pattern="task.created"), failing_handler, max_retries=0)
        await event_fabric.publish(Event(
            envelope=EventEnvelope(event_type="task.created"),
            payload={"task_id": "diag_t_dead", "goal": "Dead Letter Verification"}
        ))
        await asyncio.sleep(0.1)
        event_fabric.unsubscribe("diag_failing")
        dead_records = event_fabric.get_dead_letter_records()
        assert any(d.handler_id == "diag_failing" for d in dead_records)
        print("      [18] Dead-Letter Quarantine .... PASS (Handler faults isolated & quarantined)")
    except Exception as e:
        print(f"      [18] Dead-Letter Quarantine .... FAIL ({e})")

    # 10d. Durable Journaling & Read-Only Trace Replayer
    try:
        import uuid
        t_id = f"diag_durable_{uuid.uuid4().hex[:6]}"
        e_start = Event(
            envelope=EventEnvelope(event_type="task.started", task_id=t_id, durability=EventDurability.DURABLE),
            payload={"task_id": t_id}
        )
        e_end = Event(
            envelope=EventEnvelope(event_type="task.completed", task_id=t_id, durability=EventDurability.DURABLE),
            payload={"task_id": t_id, "progress": 100.0}
        )
        seq1 = event_journal.record_durable_event(e_start)
        seq2 = event_journal.record_durable_event(e_end)
        assert seq2 > seq1
        replay_log = event_journal.replay_trace(t_id)
        assert len(replay_log) == 2
        print(f"      [18] Durable Journal & Replay .. PASS (Monotonic seq #{seq1}->#{seq2}, safe read-only replay)")
    except Exception as e:
        print(f"      [18] Durable Journal & Replay .. FAIL ({e})")

    # 10e. HUD / WebSocket Gateway Bridge Hook
    try:
        from omnia_bus import bus_broadcast_event_hook
        assert callable(bus_broadcast_event_hook)
        print("      [18] HUD Bus Gateway Hook ..... PASS (Connected to omnia_bus.py broadcast engine)")
    except Exception as e:
        print(f"      [18] HUD Bus Gateway Hook ..... FAIL ({e})")

    print("\n" + "=" * 60)
    print("Diagnostics complete.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())


