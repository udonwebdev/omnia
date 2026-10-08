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

    print("\n" + "=" * 60)
    print("Diagnostics complete.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())

