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
class UbicacionManager:
    def __init__(self):
        self.active_locations: dict[int, dict[int, WebSocket]] = {}
        self.ubicaciones: dict[int, dict[int, dict]] = {}
        self.lock = asyncio.Lock()
    
    async def connect_ubicacion(self, grupo_id: int, user_id: int, websocket: WebSocket):
        async with self.lock:
            if grupo_id not in self.active_locations:
                self.active_locations[grupo_id] = {}
            self.active_locations[grupo_id][user_id] = websocket
            print(f"📍 Usuario {user_id} conectado a ubicaciones del grupo {grupo_id}")
    
    async def disconnect_ubicacion(self, grupo_id: int, user_id: int):
        async with self.lock:
            if grupo_id in self.active_locations:
                self.active_locations[grupo_id].pop(user_id, None)
                if not self.active_locations[grupo_id]:
                    del self.active_locations[grupo_id]
            
            # Limpiar ubicación
            if grupo_id in self.ubicaciones:
                self.ubicaciones[grupo_id].pop(user_id, None)
            
            print(f"📍 Usuario {user_id} desconectado de ubicaciones del grupo {grupo_id}")
    
    async def broadcast_ubicacion(self, grupo_id: int, user_id: int, data: dict):
        """Envía la ubicación a todos los miembros del grupo"""
        async with self.lock:
            # Guardar ubicación en memoria
            if grupo_id not in self.ubicaciones:
                self.ubicaciones[grupo_id] = {}
            
            self.ubicaciones[grupo_id][user_id] = data
            
            # Broadcast a todos los conectados del grupo
            if grupo_id in self.active_locations:
                mensaje = json.dumps({
                    "type": "ubicacion_update",
                    "user_id": user_id,
                    "nombre": data["nombre"],
                    "lat": data["lat"],
                    "lon": data["lon"],
                    "timestamp": data["timestamp"]
                })
                
                for uid, ws in self.active_locations[grupo_id].items():
                    try:
                        await ws.send_text(mensaje)
                    except:
                        pass
    
    def get_ubicaciones_grupo(self, grupo_id: int) -> dict:
        """Obtiene todas las ubicaciones activas de un grupo"""
        return self.ubicaciones.get(grupo_id, {})

ubicacion_manager = UbicacionManager()