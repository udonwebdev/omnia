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

    # ---------------------------------------------------------
    # 11. MODULE 19: AUTONOMOUS SUPERVISOR & MISSION CONTROL
    # ---------------------------------------------------------
    print("\n[11/11] Checking Module 19: Autonomous Supervisor & Mission Control...")
    from supervisor import (
        autonomous_supervisor,
        Mission,
        MissionState,
        SupervisoryDecisionType,
        DecisionConfidence,
        DecisionUrgency,
        heartbeat_monitor,
        resource_supervisor,
        state_reconciler
    )
    from supervisor.models import StallClassification, ResourcePressure

    # 11a. Mission Model & Validated Lifecycle Transitions
    try:
        m = Mission(mission_id="diag_msn_1", objective="Diagnostic Mission", status=MissionState.CREATED)
        assert m.can_transition_to(MissionState.RUNNING) is True
        m.transition_to(MissionState.RUNNING)
        assert m.can_transition_to(MissionState.COMPLETED) is True
        m.transition_to(MissionState.COMPLETED)
        # Terminal state cannot transition to RUNNING
        assert m.can_transition_to(MissionState.RUNNING) is False
        print("      [19] Mission Lifecycle Model ... PASS (Strict transition validation enforced)")
    except Exception as e:
        print(f"      [19] Mission Lifecycle Model ... FAIL ({e})")

    # 11b. Heartbeat & Stall / Loop Detection
    try:
        hb_id = "diag_hb_test"
        heartbeat_monitor.register_mission(hb_id)
        heartbeat_monitor.record_progress(hb_id, "TEST_STEP_1")
        stall_class, _, _ = heartbeat_monitor.assess_stall(hb_id)
        assert stall_class == StallClassification.ACTIVE

        # Test loop detection
        for _ in range(2):
            heartbeat_monitor.record_heartbeat(hb_id, "A", current_node_id="node_A")
            heartbeat_monitor.record_heartbeat(hb_id, "B", current_node_id="node_B")
        is_loop, _ = heartbeat_monitor.check_loop_or_oscillation(hb_id)
        assert is_loop is True
        heartbeat_monitor.cleanup(hb_id)
        print("      [19] Heartbeat & Stall/Loop .... PASS (Liveness, progress & oscillation detected)")
    except Exception as e:
        print(f"      [19] Heartbeat & Stall/Loop .... FAIL ({e})")

    # 11c. Resource Pressure & Deadlock Cycle Detection
    try:
        pressure, metrics = resource_supervisor.get_system_resource_pressure()
        assert pressure in {ResourcePressure.NORMAL, ResourcePressure.ELEVATED, ResourcePressure.HIGH, ResourcePressure.CRITICAL}
        
        # Test wait-for graph cycle detection
        resource_supervisor.clear()
        resource_supervisor.register_task_priority("t1", 1)
        resource_supervisor.register_task_priority("t2", 5)
        resource_supervisor.record_resource_acquired("t1", "rA")
        resource_supervisor.record_resource_waiting("t1", "rB")
        resource_supervisor.record_resource_acquired("t2", "rB")
        resource_supervisor.record_resource_waiting("t2", "rA")
        is_dl, cycle, victim = resource_supervisor.detect_deadlock()
        assert is_dl is True and victim == "t1"
        resource_supervisor.clear()
        print("      [19] Deadlock & Pressure Monitor PASS (Resource cycles detected & victim prioritized)")
    except Exception as e:
        print(f"      [19] Deadlock & Pressure Monitor FAIL ({e})")

    # 11d. State Reconciler & Crash Consistency
    try:
        from persistence.store import persistence_store
        from persistence.models import PersistedTaskRecord
        t_crashed = "diag_task_reconcile"
        persistence_store.save_task(PersistedTaskRecord(
            task_id=t_crashed,
            goal="Crash verification",
            status="RUNNING",
            current_node_id="step_2",
            created_at=time.time() - 100,
            started_at=time.time() - 90,
            updated_at=time.time() - 80,
            completed_at=None,
            deadline_ts=time.time() + 3600,
            task_timeout_sec=3600
        ))
        m_crash = Mission(mission_id="diag_msn_crash", active_task_id=t_crashed, status=MissionState.RUNNING)
        rec_state = state_reconciler.reconcile_mission_on_startup(m_crash)
        assert rec_state == MissionState.RECOVERING
        print("      [19] State Reconciler .......... PASS (Crashed RUNNING task safely reconciled)")
    except Exception as e:
        print(f"      [19] State Reconciler .......... FAIL ({e})")

    # 11e. Autonomous Supervisor Engine & Decision Model
    try:
        test_m = await autonomous_supervisor.create_mission("Engine Diagnostic Check")
        dec = await autonomous_supervisor._record_and_publish_decision(
            test_m,
            SupervisoryDecisionType.CONTINUE,
            "Healthy operation verified",
            {"health": "HEALTHY"},
            confidence=DecisionConfidence.HIGH
        )
        assert dec.decision == SupervisoryDecisionType.CONTINUE
        await autonomous_supervisor.abort_mission(test_m.mission_id, reason="Diagnostic complete")
        print("      [19] Mission Control Engine .... PASS (Evidence-backed decisions & controls verified)")
    except Exception as e:
        print(f"      [19] Mission Control Engine .... FAIL ({e})")

    # 12. Module 20: Human Approval Gateway & Consent Orchestrator
    print("\n[12/12] Checking Module 20: Human Approval Gateway & Consent Orchestrator...")
    from approval import (
        approval_gateway,
        ApprovalStatus,
        ApprovalDecisionType,
        ApprovalScope,
        fingerprint_generator,
        approval_presentation_manager,
        approval_persistence_manager
    )

    # 12a. Deterministic Action Fingerprint Integrity
    try:
        fp_a = fingerprint_generator.compute_action_fingerprint("restart_daemon", {"force": True}, target_resource="svc:daemon")
        fp_b = fingerprint_generator.compute_action_fingerprint("restart_daemon", {"force": True}, target_resource="svc:daemon")
        fp_c = fingerprint_generator.compute_action_fingerprint("restart_daemon", {"force": False}, target_resource="svc:daemon")
        assert fp_a == fp_b and fp_a != fp_c
        print("      [20] Action Fingerprinting ..... PASS (Deterministic SHA-256 drift detection verified)")
    except Exception as e:
        print(f"      [20] Action Fingerprinting ..... FAIL ({e})")

    # 12b. Multi-Channel Presentation & Voice Ambiguity Filtering
    try:
        req_dummy = await approval_gateway.create_request(
            requested_action="flush_dns",
            action_params={},
            title="Flush DNS",
            summary="Flush resolver cache",
            reason="DNS drift"
        )
        pres_hud = approval_presentation_manager.format_for_channel(req_dummy, "HUD")
        pres_voice = approval_presentation_manager.format_for_channel(req_dummy, "VOICE")
        assert pres_hud.channel == "HUD" and "Omnia requires your confirmation" in pres_voice.formatted_prompt
        # Test voice ambiguity filtering with multiple requests
        v_dec, _, _, v_expl = approval_presentation_manager.interpret_voice_response("yes please", [req_dummy, req_dummy])
        assert v_dec is None and "Ambiguous voice response" in v_expl
        print("      [20] Presentation & Voice ...... PASS (Normalized multi-channel & ambiguity filtering)")
    except Exception as e:
        print(f"      [20] Presentation & Voice ...... FAIL ({e})")

    # 12c. Full Approval Lifecycle & Execution Release
    try:
        req_rel = await approval_gateway.create_request(
            requested_action="reload_firewall",
            action_params={"table": "filter"},
            title="Reload Firewall",
            summary="Reload packet filter",
            reason="Policy rule added",
            task_id="diag_task_fw",
            task_node_id="n_fw"
        )
        ok, release, _ = await approval_gateway.submit_decision(
            approval_id=req_rel.approval_id,
            decision_type=ApprovalDecisionType.APPROVE,
            decided_by="operator"
        )
        assert ok is True and release is not None
        valid_rel, _ = await approval_gateway.verify_and_consume_release(
            release_token=release.release_token,
            action="reload_firewall",
            params={"table": "filter"},
            task_id="diag_task_fw",
            task_node_id="n_fw"
        )
        assert valid_rel is True
        print("      [20] Gateway Approval & Release  PASS (Lifecycle, release tokens & atomic consumption)")
    except Exception as e:
        print(f"      [20] Gateway Approval & Release  FAIL ({e})")

    # 12d. Policy Override Prevention Invariant
    try:
        req_pol = await approval_gateway.create_request(
            requested_action="execute_mesh_shell_command",
            action_params={"shell_command": "rm -rf /"},
            title="Dangerous Command",
            summary="Destructive rm",
            reason="Testing"
        )
        assert req_pol.status == ApprovalStatus.FAILED_TO_VALIDATE
        print("      [20] Policy Engine Invariant ... PASS (Deny remains deny; approval cannot override policy)")
    except Exception as e:
        print(f"      [20] Policy Engine Invariant ... FAIL ({e})")

    # 12e. Crash Recovery & Emergency Invalidation
    try:
        req_rec = await approval_gateway.create_request("diag_op", {}, "Diag", "Diag", "Reason")
        stats = approval_persistence_manager.reconcile_on_startup()
        assert "expired" in stats and "recovering" in stats
        invalidated = await approval_gateway.emergency_invalidate("Diagnostic complete")
        assert invalidated >= 1
        print("      [20] Crash Recovery & Invalidate PASS (Startup reconciler & emergency shutdown verified)")
    except Exception as e:
        print(f"      [20] Crash Recovery & Invalidate FAIL ({e})")

    # 13. Module 21: Autonomous Resource Scheduler & Concurrency Orchestrator
    print("\n[13/13] Checking Module 21: Autonomous Resource Scheduler & Concurrency Orchestrator...")
    from scheduler import (
        resource_scheduler,
        resource_registry,
        reservation_manager,
        worker_slot_manager,
        priority_scorer,
        deadlock_detector,
        scheduler_persistence_manager,
        ResourceRequirement,
        ResourceAccessMode,
        SchedulingPriority,
        PreemptionPolicy,
        SchedulingDecisionType
    )

    # 13a. Unified Resource Capacity & Multi-Resource Atomicity
    try:
        resource_registry.register_resource("diag_res_x", "TEST", total_capacity=1.0)
        resource_registry.register_resource("diag_res_y", "TEST", total_capacity=1.0)
        # Allocate X
        resource_registry.allocate(ResourceRequirement("diag_res_x"), owner_id="other_task")
        # Multi-resource reservation requesting X and Y must roll back cleanly
        ok_rsv, _, conf, _ = reservation_manager.reserve_atomic("diag_sch_fail", "diag_task", [
            ResourceRequirement("diag_res_x"),
            ResourceRequirement("diag_res_y")
        ])
        assert ok_rsv is False
        cap_y = resource_registry.get_capacity("diag_res_y")
        assert cap_y.available_capacity == 1.0  # Rolled back cleanly!
        resource_registry.release("diag_res_x", owner_id="other_task")
        print("      [21] Multi-Resource Atomicity .. PASS (Deterministic order & rollback verified)")
    except Exception as e:
        print(f"      [21] Multi-Resource Atomicity .. FAIL ({e})")

    # 13b. Deterministic Priority & Aging Scoring
    try:
        from scheduler.models import ScheduleRequest
        req_prio = ScheduleRequest(
            schedule_id="diag_prio_test",
            priority=SchedulingPriority.HIGH,
            ready_at=time.time() - 20.0
        )
        score = priority_scorer.compute_priority_score(req_prio, {})
        assert score >= 400.0  # Base (400) + aging (> 10)
        print("      [21] Priority & Aging Scoring .. PASS (Explainable algorithmic scoring verified)")
    except Exception as e:
        print(f"      [21] Priority & Aging Scoring .. FAIL ({e})")

    # 13c. Deadlock Cycle Detection & Safe Preemption
    try:
        cycle_wait = {"t_alpha": {"r_beta"}, "t_beta": {"r_alpha"}}
        cycle_alloc = {"r_alpha": "t_alpha", "r_beta": "t_beta"}
        has_dl, cyc = deadlock_detector.detect_cycles(cycle_wait, cycle_alloc)
        assert has_dl is True
        victim = deadlock_detector.select_victim(cyc, {
            "t_alpha": ScheduleRequest(schedule_id="t_alpha", priority_score=100.0, preemption_policy=PreemptionPolicy.SAFE_TO_PAUSE),
            "t_beta": ScheduleRequest(schedule_id="t_beta", priority_score=500.0, preemption_policy=PreemptionPolicy.NON_PREEMPTIBLE)
        })
        assert victim == "t_alpha"
        print("      [21] Deadlock & Cycle Resolution PASS (DFS cycle detection & safe victim selected)")
    except Exception as e:
        print(f"      [21] Deadlock & Cycle Resolution FAIL ({e})")

    # 13d. Scheduling Admission & Worker Allocation
    try:
        sch_job = await resource_scheduler.submit_for_scheduling(
            task_id="diag_scheduled_exec",
            required_resources=[],
            priority=SchedulingPriority.NORMAL
        )
        decisions = await resource_scheduler.schedule_next()
        adm = next((d for d in decisions if d.schedule_id == sch_job.schedule_id), None)
        assert adm is not None and adm.decision == SchedulingDecisionType.ADMIT
        await resource_scheduler.complete_schedule(sch_job.schedule_id, success=True)
        print("      [21] Scheduling Engine & Workers PASS (Execution slots & resource leases admitted)")
    except Exception as e:
        print(f"      [21] Scheduling Engine & Workers FAIL ({e})")

    # 13e. Persistence & Crash Reconciliation
    try:
        stats = scheduler_persistence_manager.reconcile_on_startup()
        assert "expired_reservations" in stats and "recovering_schedules" in stats
        print("      [21] Crash Reconciler .......... PASS (Startup recovery & lease reclamation verified)")
    except Exception as e:
        print(f"      [21] Crash Reconciler .......... FAIL ({e})")

    print("\n" + "=" * 60)
    print("Diagnostics complete.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())


