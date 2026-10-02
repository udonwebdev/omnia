import asyncio
import httpx
from omnia_bus import app
import uvicorn

async def dry_run():
    # Spin up server in background task
    config = uvicorn.Config(app, host="127.0.0.1", port=8005, log_level="error")
    server = uvicorn.Server(config)
    
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(1) # Give server time to bind
    
    try:
        async with httpx.AsyncClient() as client:
            # 1. Test HUD UI route
            resp_hud = await client.get("http://127.0.0.1:8005/hud")
            assert resp_hud.status_code == 200
            assert "OMNIA HUD // CORE INTERFACE" in resp_hud.text
            print("[DRY-RUN] HUD UI Route: OK (200)")

            # 2. Test State Broadcast API
            resp_state = await client.post(
                "http://127.0.0.1:8005/api/state",
                json={"state": "SYSTEM_IDLE", "message": "Dry-run verification test"}
            )
            assert resp_state.status_code == 200
            assert resp_state.json() == {"status": "broadcast_complete"}
            print("[DRY-RUN] State Broadcast API: OK (200)")
            
    finally:
        server.should_exit = True
        await server_task
        print("[DRY-RUN] Bus server shutdown cleanly.")

if __name__ == "__main__":
    asyncio.run(dry_run())
