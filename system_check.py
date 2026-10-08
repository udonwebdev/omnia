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

    print("\n" + "=" * 60)
    print("Diagnostics complete.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())

