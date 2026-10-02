import asyncio
import httpx
from omnia_bus import app
import uvicorn

async def dry_run():
    config = uvicorn.Config(app, host="127.0.0.1", port=8006, log_level="error")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(1)
    
    try:
        async with httpx.AsyncClient() as client:
            # 1. Test Ingestion endpoint
            payload = {
                "tab_id": 99,
                "url": "https://flightdeals.com/booking/123",
                "title": "Cheap Flights - Paris to New York",
                "content": "Special fare discount ticket confirmed for transatlantic route.",
                "timestamp": 123456789.0
            }
            resp_ingest = await client.post("http://127.0.0.1:8006/api/context/tab", json=payload)
            assert resp_ingest.status_code == 200
            print("[BUS-TEST] /api/context/tab: OK", resp_ingest.json())

            # 2. Test Query endpoint
            resp_query = await client.get("http://127.0.0.1:8006/api/context/query?q=ticket+to+New+York")
            assert resp_query.status_code == 200
            data = resp_query.json()
            assert len(data["matches"]) > 0
            print("[BUS-TEST] /api/context/query: OK - Found Match:", data["matches"][0]["title"])
            
    finally:
        server.should_exit = True
        await server_task
        print("[BUS-TEST] Clean shutdown.")

if __name__ == "__main__":
    asyncio.run(dry_run())
