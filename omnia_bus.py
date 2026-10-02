import asyncio
from typing import Set, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
from pathlib import Path
from memory_engine import memory
from telephony_gateway import telephony_router

app = FastAPI(title="Omnia Event Bus")
app.include_router(telephony_router)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast_json(self, data: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

class TabContextPayload(BaseModel):
    tab_id: int
    url: str
    title: str
    content: str
    timestamp: float

@app.websocket("/ws/hud")
async def hud_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/hud", response_class=HTMLResponse)
async def get_hud_ui():
    hud_file = Path(__file__).parent / "hud" / "index.html"
    if hud_file.exists():
        return hud_file.read_text(encoding="utf-8")
    return "<h1>HUD template not found. Run module setup.</h1>"

@app.post("/api/state")
async def set_state(payload: Dict[str, Any]):
    await manager.broadcast_json({
        "type": "STATE_CHANGE",
        "state": payload.get("state", "UNKNOWN"),
        "message": payload.get("message", "")
    })
    return {"status": "broadcast_complete"}

@app.post("/api/context/tab")
async def ingest_tab(payload: TabContextPayload):
    memory.store_tab_context(
        tab_id=payload.tab_id,
        url=payload.url,
        title=payload.title,
        content=payload.content
    )
    return {"status": "indexed", "url": payload.url}

@app.get("/api/context/query")
async def query_context(q: str, limit: int = 3):
    matches = memory.search_context(query=q, limit=limit)
    return {"matches": matches}

def start_bus_server(host: str = "127.0.0.1", port: int = 8000):
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    return server
