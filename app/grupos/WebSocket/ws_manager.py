from typing import Dict, Set
from starlette.websockets import WebSocket
import asyncio
import json
from ..models import Grupo, MiembroGrupo, Mensaje, LecturaMensaje
from sqlalchemy.orm import Session

class WebSocketManager:
    def __init__(self):
        # ✅ CAMBIO: Ahora mapea grupo_id -> {user_id -> WebSocket}
        self.active_connections: Dict[int, Dict[int, WebSocket]] = {}
        self.lock = asyncio.Lock()

    async def connect(self, grupo_id: int, user_id: int, websocket: WebSocket):
        """
        ✅ ACTUALIZADO: Ahora recibe user_id para rastrear quién está conectado
        """
        async with self.lock:
            if grupo_id not in self.active_connections:
                self.active_connections[grupo_id] = {}
            self.active_connections[grupo_id][user_id] = websocket
            print(f"✅ Usuario {user_id} conectado al grupo {grupo_id}")
            print(f"   Total usuarios conectados al grupo: {len(self.active_connections[grupo_id])}")

    async def disconnect(self, grupo_id: int, user_id: int):
        """
        ✅ ACTUALIZADO: Ahora recibe user_id en lugar de websocket
        """
        async with self.lock:
            if grupo_id in self.active_connections:
                if user_id in self.active_connections[grupo_id]:
                    del self.active_connections[grupo_id][user_id]
                    print(f"🔌 Usuario {user_id} desconectado del grupo {grupo_id}")
                
                # Limpiar grupo si no hay usuarios
                if not self.active_connections[grupo_id]:
                    del self.active_connections[grupo_id]
                    print(f"🧹 Grupo {grupo_id} sin usuarios conectados, limpiado")

    def is_user_connected_to_group(self, grupo_id: int, user_id: int) -> bool:
        """
        🆕 NUEVO: Verifica si un usuario específico está conectado a un grupo
        
        Returns:
            bool: True si el usuario está conectado al WebSocket del grupo
        """
        return (
            grupo_id in self.active_connections and 
            user_id in self.active_connections[grupo_id]
        )

    async def broadcast(self, grupo_id: int, message: dict, exclude_user_id: int | None = None):
        """
        ✅ ACTUALIZADO: Ahora excluye por user_id en lugar de WebSocket
        """
        if grupo_id not in self.active_connections:
            print(f"⚠️ Grupo {grupo_id} no tiene conexiones activas")
            return
        
        # ✅ CRÍTICO: Copiar snapshot FUERA del lock para evitar bloqueos
        connections_snapshot = {}
        async with self.lock:
            grupo_connections = self.active_connections.get(grupo_id, {})
            
            # 🔥 CORRECCIÓN DEL BUG: Migrar set a dict si es necesario
            if isinstance(grupo_connections, set):
                print(f"🔄 Migrando conexiones del grupo {grupo_id} de set a dict...")
                new_dict = {}
                for ws in grupo_connections:
                    if hasattr(ws, 'usuario_id'):  # Si el websocket tiene usuario_id
                        new_dict[ws.usuario_id] = ws
                self.active_connections[grupo_id] = new_dict
                connections_snapshot = dict(new_dict)
            elif isinstance(grupo_connections, dict):
                connections_snapshot = dict(grupo_connections)
            else:
                print(f"❌ ERROR: Conexiones del grupo {grupo_id} en formato desconocido: {type(grupo_connections)}")
                return
        
        if not connections_snapshot:
            print(f"⚠️ No hay usuarios conectados al grupo {grupo_id} para broadcast")
            return
        
        print(f"📤 Broadcasting a {len(connections_snapshot)} usuarios en grupo {grupo_id}")
        if exclude_user_id:
            print(f"   (Excluyendo usuario {exclude_user_id})")
        
        disconnected_users = []
        enviados_exitosos = 0
        
        for user_id, websocket in connections_snapshot.items():
            if user_id == exclude_user_id:
                print(f"   ⏭️ Saltando usuario {user_id} (remitente)")
                continue
            
            try:
                await websocket.send_text(json.dumps(message))
                enviados_exitosos += 1
                print(f"   ✅ Mensaje enviado a usuario {user_id}")
            except Exception as e:
                print(f"   ❌ Error enviando a usuario {user_id}: {e}")
                disconnected_users.append(user_id)
        
        print(f"📊 Broadcast completado: {enviados_exitosos} exitosos, {len(disconnected_users)} fallidos")
        
        # Limpiar usuarios desconectados
        if disconnected_users:
            async with self.lock:
                for user_id in disconnected_users:
                    if grupo_id in self.active_connections:
                        self.active_connections[grupo_id].pop(user_id, None)
                        print(f"🧹 Usuario {user_id} removido por desconexión")
    
    def get_connected_users(self, grupo_id: int) -> list[int]:
        """
        🆕 NUEVO: Obtiene lista de user_ids conectados a un grupo
        
        Returns:
            list[int]: Lista de IDs de usuarios conectados
        """
        if grupo_id in self.active_connections:
            return list(self.active_connections[grupo_id].keys())
        return []


class UbicacionManager:
    def __init__(self):
        self.active_locations: dict[int, dict[int, WebSocket]] = {}
        self.ubicaciones: dict[int, dict[int, dict]] = {}
        self.lock = asyncio.Lock()
    
    async def connect_ubicacion(self, grupo_id: int, user_id: int, websocket: WebSocket):
        async with self.lock:
            if grupo_id not in self.active_locations:
                self.active_locations[grupo_id] = {}
            
            # 🔥 SI YA HAY CONEXIÓN, CERRARLA ANTES
            if user_id in self.active_locations[grupo_id]:
                old_ws = self.active_locations[grupo_id][user_id]
                try:
                    await old_ws.close(code=1000, reason="Nueva conexión establecida")
                    print(f"🔄 Conexión anterior cerrada para usuario {user_id} en grupo {grupo_id}")
                except Exception as e:
                    print(f"⚠️ Error al cerrar conexión anterior: {e}")
            
            # Registrar nueva conexión
            self.active_locations[grupo_id][user_id] = websocket
            print(f"✅ Usuario {user_id} conectado a ubicaciones del grupo {grupo_id}")
            print(f"   Total usuarios conectados al grupo: {len(self.active_locations[grupo_id])}")
    
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
                    "timestamp": data["timestamp"],
                    "es_creador": data.get("es_creador", False)
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

class GrupoNotificationManager:
    def __init__(self):
        # Mapea user_id -> WebSocket para notificaciones globales
        self.user_connections: Dict[int, WebSocket] = {}
        self.lock = asyncio.Lock()
    
    async def connect_user(self, user_id: int, websocket: WebSocket):
        """Conecta un usuario para recibir notificaciones globales"""
        async with self.lock:
            self.user_connections[user_id] = websocket
            print(f"🔔 Usuario {user_id} conectado a notificaciones globales")
    
    async def disconnect_user(self, user_id: int):
        """Desconecta un usuario de notificaciones globales"""
        async with self.lock:
            self.user_connections.pop(user_id, None)
            print(f"🔔 Usuario {user_id} desconectado de notificaciones globales")
    
    async def is_user_connected(self, user_id: int) -> bool:
        """
        ⚠️ DEPRECATED: Este método solo verifica notificaciones globales
        Usar manager.is_user_connected_to_group() para verificar conexión al grupo
        """
        async with self.lock:
            return user_id in self.user_connections
    
    async def notify_unread_count_changed(self, user_id: int, db: Session = None):
        """
        Notifica a un usuario específico sobre cambios en mensajes no leídos.
        
        ⚠️ IMPORTANTE: Si no se proporciona 'db', se crea una sesión temporal
        que se cierra automáticamente. Esto es CRÍTICO para WebSockets.
        """
        websocket = self.user_connections.get(user_id)
        if not websocket:
            return
        
        # 🔥 CLAVE: Crear sesión temporal si no se proporciona
        should_close_db = False
        if db is None:
            from ...database.database import SessionLocal
            db = SessionLocal()
            should_close_db = True
        
        try:
            # Calcular mensajes no leídos por grupo
            from sqlalchemy import func, and_, or_
            
            grupos_query = (
                db.query(Grupo)
                .outerjoin(MiembroGrupo, and_(
                    MiembroGrupo.grupo_id == Grupo.id,
                    MiembroGrupo.usuario_id == user_id,
                    MiembroGrupo.activo == True
                ))
                .filter(
                    Grupo.is_deleted == False,
                    or_(
                        Grupo.creado_por_id == user_id,
                        MiembroGrupo.id != None
                    )
                )
                .all()
            )
            
            grupos_no_leidos = []
            for grupo in grupos_query:
                count = (
                    db.query(func.count(Mensaje.id))
                    .outerjoin(LecturaMensaje, and_(
                        LecturaMensaje.mensaje_id == Mensaje.id,
                        LecturaMensaje.usuario_id == user_id
                    ))
                    .filter(
                        Mensaje.grupo_id == grupo.id,
                        Mensaje.remitente_id != user_id,
                        LecturaMensaje.id == None
                    )
                    .scalar() or 0
                )
                
                grupos_no_leidos.append({
                    "grupo_id": grupo.id,
                    "mensajes_no_leidos": count
                })
            
            # Enviar notificación
            await websocket.send_text(json.dumps({
                "type": "unread_count_update",
                "data": grupos_no_leidos
            }))
            print(f"📊 Enviado conteo de no leídos a usuario {user_id}")
            
        except Exception as e:
            print(f"❌ Error al notificar usuario {user_id}: {e}")
            await self.disconnect_user(user_id)
        
        finally:
            # 🔥 CRÍTICO: Cerrar sesión si la creamos nosotros
            if should_close_db:
                db.close()

# Instancia global
grupo_notification_manager = GrupoNotificationManager()