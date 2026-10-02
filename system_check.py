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
    print("\n[4/4] Checking Event Bus Endpoint...")
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.post("http://127.0.0.1:8000/api/state", json={"state": "DIAGNOSTIC", "message": "Self-check"})
            if resp.status_code == 200:
                print("      Status: OK | Local Event Bus is responding.")
            else:
                print(f"      Status: WARNING | Bus returned status code: {resp.status_code}")
    except Exception:
        print("      Status: NOTICE | Event Bus server is currently offline (will start with main.py).")

    print("\n" + "=" * 60)
    print("Diagnostics complete.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
