from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import json
import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError

from ...database.database import SessionLocal
from ..models import Grupo, MiembroGrupo, Mensaje, LecturaMensaje
from ...usuarios.security import get_current_user_ws, SECRET_KEY, ALGORITHM
from .ws_manager import WebSocketManager, UbicacionManager, grupo_notification_manager

router = APIRouter()
manager = WebSocketManager()
ubicacion_manager = UbicacionManager()

@router.websocket("/ws/grupos/{grupo_id}")
async def websocket_grupo(websocket: WebSocket, grupo_id: int):
    await websocket.accept()
    print("🔹 WebSocket aceptado, iniciando validaciones...")
    
    db = SessionLocal()
    user = None
    current_token = None
    revalidation_task = None
    
    try:
        # Extraer token inicial
        auth = websocket.headers.get("authorization")
        if auth and auth.startswith("Bearer "):
            current_token = auth.split(" ", 1)[1]
        else:
            current_token = websocket.query_params.get("token")
        
        if not current_token:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Token no proporcionado"
            }))
            await websocket.close(code=1008)
            return
        
        # Autenticar usuario
        try:
            user = await get_current_user_ws(websocket, db)
            print(f"🔹 Usuario conectado: ID={user.id}, activo={user.activo}")
        except Exception as e:
            print(f"❌ Error al autenticar WebSocket: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Autenticación fallida: {str(e)}"
            }))
            await websocket.close(code=1008)
            return

        # Validar grupo
        grupo = db.query(Grupo).filter(Grupo.id == grupo_id, Grupo.is_deleted == False).first()
        if not grupo:
            print(f"❌ Grupo {grupo_id} no encontrado")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Grupo no encontrado"
            }))
            await websocket.close(code=1008)
            return
        print(f"🔹 Grupo encontrado: ID={grupo.id}, creado_por_id={grupo.creado_por_id}")

        # Verificar permisos
        miembro = db.query(MiembroGrupo).filter_by(
            usuario_id=user.id, 
            grupo_id=grupo_id, 
            activo=True
        ).first()
        
        es_creador = grupo.creado_por_id == user.id
        print(f"🔹 Miembro encontrado: {miembro}, Es creador: {es_creador}")
        
        if not miembro and not es_creador:
            print(f"❌ Usuario {user.id} no pertenece al grupo {grupo_id}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "No tienes acceso a este grupo"
            }))
            await websocket.close(code=1008)
            return

        # Agregar a conexiones activas
        async with manager.lock:
            if grupo_id not in manager.active_connections:
                manager.active_connections[grupo_id] = set()
            manager.active_connections[grupo_id].add(websocket)
        
        print(f"✅ Usuario {user.id} conectado al grupo {grupo_id}")

        # 🆕 Tarea de revalidación CORREGIDA
        async def revalidate_token():
            """Revalida el token cada 60 segundos"""
            while True:
                await asyncio.sleep(60)
                try:
                    if current_token:
                        payload = jwt.decode(current_token, SECRET_KEY, algorithms=[ALGORITHM])
                        
                        exp_timestamp = payload.get("exp")
                        if exp_timestamp:
                            # ✅ CORRECCIÓN: Usar timezone.utc
                            ahora = datetime.now(timezone.utc).timestamp()
                            tiempo_restante = exp_timestamp - ahora
                            print(f"⏱️ Token válido. Expira en {tiempo_restante/60:.1f} minutos")
                            
                            if tiempo_restante <= 0:
                                print(f"❌ Token expiró hace {abs(tiempo_restante)/60:.1f} minutos")
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "code": "TOKEN_EXPIRED",
                                    "message": "Tu sesión ha expirado. Reconecta con un nuevo token."
                                }))
                                await websocket.close(code=1008)
                                break
                            
                            if tiempo_restante < 120:
                                await websocket.send_text(json.dumps({
                                    "type": "warning",
                                    "code": "TOKEN_EXPIRING_SOON",
                                    "message": "Tu sesión expirará pronto. Por favor, actualiza tu token.",
                                    "seconds_remaining": int(tiempo_restante)
                                }))
                        
                except JWTError as e:
                    print(f"⚠️ Token expirado o inválido para usuario {user.id}: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "TOKEN_EXPIRED",
                        "message": "Tu sesión ha expirado. Reconecta con un nuevo token."
                    }))
                    await websocket.close(code=1008)
                    break
                except Exception as e:
                    print(f"❌ Error en revalidación: {e}")
                    break
        
        revalidation_task = asyncio.create_task(revalidate_token())

        await websocket.send_text(json.dumps({
            "type": "system",
            "message": f"Conectado al grupo {grupo.nombre}",
            "grupo_id": grupo_id
        }))

        # 🔄 Bucle de recepción de mensajes
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                continue

            action = payload.get("action")
            data = payload.get("data", {})

            if action == "refresh_token":
                new_token = data.get("token")
                if new_token:
                    try:
                        jwt.decode(new_token, SECRET_KEY, algorithms=[ALGORITHM])
                        current_token = new_token
                        print(f"🔄 Token actualizado para usuario {user.id}")
                        await websocket.send_text(json.dumps({
                            "type": "token_refreshed",
                            "message": "Token actualizado correctamente"
                        }))
                    except JWTError:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Token inválido proporcionado"
                        }))
                continue

            # ✅ CORRECCIÓN: Agregar registro de lectura automática
            if action == "mensaje":
                contenido = data.get("contenido", "").strip()
                tipo = data.get("tipo", "texto")
                if not contenido:
                    continue

                # ✅ Usar timezone.utc
                mensaje = Mensaje(
                    remitente_id=user.id,
                    grupo_id=grupo_id,
                    contenido=contenido,
                    tipo=tipo,
                    fecha_creacion=datetime.now(timezone.utc)
                )
                db.add(mensaje)
                db.commit()
                db.refresh(mensaje)

                # 🆕 AGREGAR: Marcar automáticamente como leído para el remitente
                lectura = LecturaMensaje(
                    mensaje_id=mensaje.id,
                    usuario_id=user.id,
                    leido_at=datetime.now(timezone.utc)
                )
                db.add(lectura)
                db.commit()
                print(f"✅ Mensaje {mensaje.id} marcado como leído por usuario {user.id}")

                # 🆕 NOTIFICAR a todos los miembros del grupo sobre cambio en no leídos
                miembros = db.query(MiembroGrupo).filter_by(grupo_id=grupo_id, activo=True).all()
                miembros_ids = [m.usuario_id for m in miembros]

                # Agregar también al creador si no está en la lista
                if grupo.creado_por_id not in miembros_ids:
                    miembros_ids.append(grupo.creado_por_id)

                # Notificar a cada miembro (excepto al remitente)
                for miembro_id in miembros_ids:
                    if miembro_id != user.id:
                        await grupo_notification_manager.notify_unread_count_changed(miembro_id, db)


                out = {
                    "type": "mensaje",
                    "data": {
                        "id": mensaje.id,
                        "remitente_id": mensaje.remitente_id,
                        "grupo_id": mensaje.grupo_id,
                        "contenido": mensaje.contenido,
                        "tipo": mensaje.tipo,
                        "fecha_creacion": mensaje.fecha_creacion.isoformat(),
                        "leido": True,      # Para el remitente siempre True
                        "leido_por": 1      # Empezar en 1
                    }
                }
                await manager.broadcast(grupo_id, out)

            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            else:
                await websocket.send_text(json.dumps({
                    "type": "error", 
                    "message": "Acción no reconocida"
                }))

    except WebSocketDisconnect:
        print(f"🔹 WebSocket desconectado normalmente para usuario {user.id if user else 'desconocido'}")
    except Exception as e:
        print(f"❌ Excepción en WebSocket: {e}")
        traceback.print_exc()
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Error interno del servidor"
            }))
        except:
            pass
    finally:
        if revalidation_task:
            revalidation_task.cancel()
            try:
                await revalidation_task
            except asyncio.CancelledError:
                print("🔹 Tarea de revalidación cancelada")
        
        await manager.disconnect(grupo_id, websocket)
        db.close()
        user_id = user.id if user else "desconocido"
        print(f"🔹 Usuario {user_id} desconectado del grupo {grupo_id}")


@router.websocket("/ws/grupos/{grupo_id}/ubicaciones")
async def websocket_ubicaciones(websocket: WebSocket, grupo_id: int):
    await websocket.accept()
    print("📍 WebSocket de ubicaciones aceptado")
    
    db = SessionLocal()
    user = None
    current_token = None
    heartbeat_task = None
    revalidation_task = None  # 🆕 Tarea de revalidación
    
    try:
        # Autenticar
        auth = websocket.headers.get("authorization")
        if auth and auth.startswith("Bearer "):
            current_token = auth.split(" ", 1)[1]
        else:
            current_token = websocket.query_params.get("token")
        
        if not current_token:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Token no proporcionado"
            }))
            await websocket.close(code=1008)
            return
        
        # Autenticar usuario
        try:
            user = await get_current_user_ws(websocket, db)
            print(f"📍 Usuario conectado a ubicaciones: ID={user.id}")
        except Exception as e:
            print(f"❌ Error al autenticar WebSocket ubicaciones: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Autenticación fallida: {str(e)}"
            }))
            await websocket.close(code=1008)
            return
        
        # Validar grupo y permisos
        grupo = db.query(Grupo).filter(Grupo.id == grupo_id, Grupo.is_deleted == False).first()
        if not grupo:
            print(f"❌ Grupo {grupo_id} no encontrado")
            await websocket.close(code=1008)
            return
        
        miembro = db.query(MiembroGrupo).filter_by(
            usuario_id=user.id, 
            grupo_id=grupo_id, 
            activo=True
        ).first()
        
        if not miembro and grupo.creado_por_id != user.id:
            print(f"❌ Usuario {user.id} no pertenece al grupo {grupo_id}")
            await websocket.close(code=1008)
            return
        
        # Conectar
        await ubicacion_manager.connect_ubicacion(grupo_id, user.id, websocket)
        
        # Obtener nombre del usuario
        nombre_completo = f"{user.datos_personales.nombre} {user.datos_personales.apellido}"
        
        # 🆕 Tarea de revalidación de token
        async def revalidate_token():
            """Revalida el token cada 60 segundos"""
            while True:
                await asyncio.sleep(60)
                try:
                    if current_token:
                        payload = jwt.decode(current_token, SECRET_KEY, algorithms=[ALGORITHM])
                        
                        exp_timestamp = payload.get("exp")
                        if exp_timestamp:
                            ahora = datetime.now(timezone.utc).timestamp()
                            tiempo_restante = exp_timestamp - ahora
                            print(f"📍⏱️ Token ubicaciones válido. Expira en {tiempo_restante/60:.1f} minutos")
                            
                            if tiempo_restante <= 0:
                                print(f"📍❌ Token expiró hace {abs(tiempo_restante)/60:.1f} minutos")
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "code": "TOKEN_EXPIRED",
                                    "message": "Tu sesión ha expirado. Reconecta con un nuevo token."
                                }))
                                await websocket.close(code=1008)
                                break
                            
                            if tiempo_restante < 120:
                                await websocket.send_text(json.dumps({
                                    "type": "warning",
                                    "code": "TOKEN_EXPIRING_SOON",
                                    "message": "Tu sesión expirará pronto. Por favor, actualiza tu token.",
                                    "seconds_remaining": int(tiempo_restante)
                                }))
                        
                except JWTError as e:
                    print(f"📍⚠️ Token expirado o inválido para usuario {user.id}: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "TOKEN_EXPIRED",
                        "message": "Tu sesión ha expirado. Reconecta con un nuevo token."
                    }))
                    await websocket.close(code=1008)
                    break
                except Exception as e:
                    print(f"📍❌ Error en revalidación: {e}")
                    break
        
        revalidation_task = asyncio.create_task(revalidate_token())
        
        # Enviar ubicaciones actuales del grupo
        ubicaciones_actuales = ubicacion_manager.get_ubicaciones_grupo(grupo_id)
        await websocket.send_text(json.dumps({
            "type": "ubicaciones_iniciales",
            "ubicaciones": [
                {
                    "user_id": uid,
                    "nombre": data["nombre"],
                    "lat": data["lat"],
                    "lon": data["lon"],
                    "timestamp": data["timestamp"]
                }
                for uid, data in ubicaciones_actuales.items()
                if uid != user.id  # No enviar la propia
            ]
        }))
        
        await websocket.send_text(json.dumps({
            "type": "system",
            "message": f"Conectado a ubicaciones del grupo {grupo.nombre}",
            "grupo_id": grupo_id
        }))
        
        # Heartbeat cada 30s
        async def heartbeat():
            while True:
                await asyncio.sleep(30)
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except:
                    break
        
        heartbeat_task = asyncio.create_task(heartbeat())
        
        # Bucle de recepción
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            
            # 🆕 Refresh token
            if payload.get("type") == "refresh_token":
                new_token = payload.get("token")
                if new_token:
                    try:
                        jwt.decode(new_token, SECRET_KEY, algorithms=[ALGORITHM])
                        current_token = new_token
                        print(f"📍🔄 Token actualizado para usuario {user.id}")
                        await websocket.send_text(json.dumps({
                            "type": "token_refreshed",
                            "message": "Token actualizado correctamente"
                        }))
                    except JWTError:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Token inválido proporcionado"
                        }))
                continue
            
            if payload.get("type") == "ubicacion":
                lat = payload.get("lat")
                lon = payload.get("lon")
                
                if lat is not None and lon is not None:
                    data = {
                        "nombre": nombre_completo,
                        "lat": lat,
                        "lon": lon,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    await ubicacion_manager.broadcast_ubicacion(grupo_id, user.id, data)
            
            elif payload.get("type") == "pong":
                pass  # Respuesta al ping
    
    except WebSocketDisconnect:
        print(f"📍 Usuario {user.id if user else 'desconocido'} desconectado de ubicaciones")
    except Exception as e:
        print(f"❌ Error en WebSocket ubicaciones: {e}")
        traceback.print_exc()
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Error interno del servidor"
            }))
        except:
            pass
    finally:
        # 🆕 Cancelar tareas
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                print("📍 Tarea de heartbeat cancelada")
        
        if revalidation_task:
            revalidation_task.cancel()
            try:
                await revalidation_task
            except asyncio.CancelledError:
                print("📍 Tarea de revalidación cancelada")
        
        if user:
            await ubicacion_manager.disconnect_ubicacion(grupo_id, user.id)
        
        db.close()
        user_id = user.id if user else "desconocido"
        print(f"📍 Usuario {user_id} desconectado del grupo {grupo_id} (ubicaciones)")

@router.websocket("/ws/notificaciones")
async def websocket_notificaciones(websocket: WebSocket):
    """
    WebSocket para recibir notificaciones globales de grupos
    (mensajes no leídos, nuevos grupos, etc.)
    """
    await websocket.accept()
    print("🔔 WebSocket de notificaciones aceptado")
    
    db = SessionLocal()
    user = None
    current_token = None
    revalidation_task = None
    
    try:
        # Extraer token
        auth = websocket.headers.get("authorization")
        if auth and auth.startswith("Bearer "):
            current_token = auth.split(" ", 1)[1]
        else:
            current_token = websocket.query_params.get("token")
        
        if not current_token:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "Token no proporcionado"
            }))
            await websocket.close(code=1008)
            return
        
        # Autenticar
        try:
            user = await get_current_user_ws(websocket, db)
            print(f"🔔 Usuario {user.id} autenticado para notificaciones")
        except Exception as e:
            print(f"❌ Error al autenticar: {e}")
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": f"Autenticación fallida: {str(e)}"
            }))
            await websocket.close(code=1008)
            return
        
        # Conectar usuario
        await grupo_notification_manager.connect_user(user.id, websocket)
        
        # Enviar estado inicial
        await grupo_notification_manager.notify_unread_count_changed(user.id, db)
        
        # 🆕 Tarea de revalidación de token mejorada
        async def revalidate_token():
            """Revalida el token cada 60 segundos y muestra el tiempo de expiración"""
            contador_checks = 0
            ultimo_tiempo_reportado = None
            
            while True:
                await asyncio.sleep(60)
                contador_checks += 1
                
                try:
                    if current_token:
                        payload = jwt.decode(current_token, SECRET_KEY, algorithms=[ALGORITHM])
                        
                        exp_timestamp = payload.get("exp")
                        if exp_timestamp:
                            ahora = datetime.now(timezone.utc).timestamp()
                            tiempo_restante = exp_timestamp - ahora
                            minutos_restantes = tiempo_restante / 60
                            
                            # 🆕 Solo loguear si hay cambios significativos o cada 5 checks
                            debe_loguear = (
                                ultimo_tiempo_reportado is None or
                                abs(minutos_restantes - ultimo_tiempo_reportado) > 0.5 or
                                contador_checks % 5 == 0 or
                                minutos_restantes < 3
                            )
                            
                            if debe_loguear:
                                print(f"🔔⏱️ Token notificaciones - Check #{contador_checks}: {minutos_restantes:.1f} min restantes")
                                ultimo_tiempo_reportado = minutos_restantes
                            
                            # Si expiró
                            if tiempo_restante <= 0:
                                print(f"🔔❌ ════════════════════════════════════════")
                                print(f"🔔❌ TOKEN EXPIRADO hace {abs(minutos_restantes):.1f} minutos")
                                print(f"🔔❌ Usuario: {user.id if user else 'desconocido'}")
                                print(f"🔔❌ ════════════════════════════════════════")
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "code": "TOKEN_EXPIRED",
                                    "message": "Tu sesión ha expirado. Reconecta con un nuevo token."
                                }))
                                await websocket.close(code=1008)
                                break
                            
                            # Si está por expirar (menos de 2 minutos)
                            if tiempo_restante < 120:
                                print(f"🔔⚠️ ════════════════════════════════════════")
                                print(f"🔔⚠️ TOKEN POR EXPIRAR: {minutos_restantes:.1f} min")
                                print(f"🔔⚠️ Se recomienda renovar")
                                print(f"🔔⚠️ ════════════════════════════════════════")
                                await websocket.send_text(json.dumps({
                                    "type": "warning",
                                    "code": "TOKEN_EXPIRING_SOON",
                                    "message": "Tu sesión expirará pronto. Por favor, actualiza tu token.",
                                    "seconds_remaining": int(tiempo_restante)
                                }))
                        
                except JWTError as e:
                    print(f"🔔❌ ════════════════════════════════════════")
                    print(f"🔔❌ TOKEN INVÁLIDO O EXPIRADO")
                    print(f"🔔❌ Usuario: {user.id if user else 'desconocido'}")
                    print(f"🔔❌ Error: {e}")
                    print(f"🔔❌ ════════════════════════════════════════")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "TOKEN_EXPIRED",
                        "message": "Tu sesión ha expirado. Reconecta con un nuevo token."
                    }))
                    await websocket.close(code=1008)
                    break
                except Exception as e:
                    print(f"🔔❌ Error en revalidación del token: {e}")
                    break
        
        revalidation_task = asyncio.create_task(revalidate_token())
        
        # Mantener conexión viva
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            
            if payload.get("action") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif payload.get("action") == "refresh_token":
                new_token = payload.get("data", {}).get("token")
                if new_token:
                    try:
                        jwt.decode(new_token, SECRET_KEY, algorithms=[ALGORITHM])
                        current_token = new_token
                        print(f"🔔🔄 Token de notificaciones actualizado para usuario {user.id}")
                        await websocket.send_text(json.dumps({
                            "type": "token_refreshed",
                            "message": "Token actualizado correctamente"
                        }))
                    except JWTError:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Token inválido proporcionado"
                        }))
    
    except WebSocketDisconnect:
        print(f"🔔 WebSocket notificaciones desconectado para usuario {user.id if user else 'desconocido'}")
    except Exception as e:
        print(f"❌ Error en WebSocket notificaciones: {e}")
        traceback.print_exc()
    finally:
        if revalidation_task:
            revalidation_task.cancel()
            try:
                await revalidation_task
            except asyncio.CancelledError:
                print("🔔 Tarea de revalidación de token cancelada")
        
        if user:
            await grupo_notification_manager.disconnect_user(user.id)
        db.close()