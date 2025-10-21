from typing import Dict, Set
from starlette.websockets import WebSocket
import asyncio
import json

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, grupo_id: int, websocket: WebSocket):
        # ❌ NO LLAMAR websocket.accept() aquí, ya fue aceptado
        async with self.lock:
            if grupo_id not in self.active_connections:
                self.active_connections[grupo_id] = set()
            self.active_connections[grupo_id].add(websocket)

    async def disconnect(self, grupo_id: int, websocket: WebSocket):
        async with self.lock:
            conns = self.active_connections.get(grupo_id)
            if conns and websocket in conns:
                conns.remove(websocket)
                if not conns:
                    del self.active_connections[grupo_id]

    async def broadcast(self, grupo_id: int, message: dict, exclude: WebSocket | None = None):
        conns = list(self.active_connections.get(grupo_id, []))
        to_remove = []
        for conn in conns:
            if conn is exclude:
                continue
            try:
                await conn.send_text(json.dumps(message))
            except Exception:
                to_remove.append(conn)
        if to_remove:
            async with self.lock:
                for r in to_remove:
                    self.active_connections.get(grupo_id, set()).discard(r)