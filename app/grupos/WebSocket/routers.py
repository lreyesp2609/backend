from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jwt import ExpiredSignatureError
from sqlalchemy.orm import Session, joinedload
import json
import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from sqlalchemy import func, and_, or_
from ...database.database import SessionLocal
from ..models import Grupo, MiembroGrupo, Mensaje, LecturaMensaje
from ...usuarios.models import Usuario
from ...usuarios.security import get_current_user_ws, SECRET_KEY, ALGORITHM
from .ws_manager import WebSocketManager, UbicacionManager, grupo_notification_manager
from ...services.fcm_service import fcm_service
from ...usuarios.models import FCMToken


router = APIRouter(prefix="/ws", tags=["WebSocket"])

manager = WebSocketManager()
ubicacion_manager = UbicacionManager()


@router.websocket("/ping")
async def websocket_ping(websocket: WebSocket):
    """Endpoint de prueba sin autenticación"""
    print("🏓 PING WebSocket alcanzado")
    await websocket.accept()
    await websocket.send_text(json.dumps({"message": "pong"}))
    
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Recibido: {data}")
            await websocket.send_text(json.dumps({"echo": data}))
    except WebSocketDisconnect:
        print("🏓 PING WebSocket cerrado")

@router.websocket("/notificaciones")
async def websocket_notificaciones(websocket: WebSocket):
    await websocket.accept()
    print("✅ WebSocket aceptado correctamente")
    
    user = None
    user_id = None  # ✅ AGREGAR ESTA VARIABLE
    current_token = None
    revalidation_task = None
    
    try:
        db = SessionLocal()
        try:
            # Extraer token
            auth = websocket.headers.get("authorization")
            if auth and auth.startswith("Bearer "):
                current_token = auth.split(" ", 1)[1]
            else:
                current_token = websocket.query_params.get("token")
            
            if not current_token:
                print("❌ Token no proporcionado")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Token no proporcionado"
                }))
                await websocket.close(code=1008)
                return
            
            try:
                payload = jwt.decode(current_token, SECRET_KEY, algorithms=[ALGORITHM])
                usuario_id = payload.get("id_usuario")
                
                if usuario_id is None:
                    raise Exception("Token inválido: falta id_usuario")
                
                user = db.query(Usuario).options(
                    joinedload(Usuario.datos_personales)
                ).filter(
                    Usuario.id == usuario_id,
                    Usuario.activo == True
                ).first()
                
                if not user:
                    raise Exception("Usuario no encontrado o inactivo")
                
                # ✅ GUARDAR user_id ANTES DE CERRAR LA SESIÓN
                user_id = user.id
                print(f"🔔 Usuario {user_id} autenticado para notificaciones")
                
            except ExpiredSignatureError:
                print(f"❌ Token expirado")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "code": "TOKEN_EXPIRED",
                    "message": "Token expirado"
                }))
                await websocket.close(code=1008)
                return
                
            except JWTError as e:
                print(f"❌ Token inválido: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "code": "TOKEN_INVALID",
                    "message": f"Token inválido: {str(e)}"
                }))
                await websocket.close(code=1008)
                return
            
            except Exception as e:
                print(f"❌ Error de autenticación: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": str(e)
                }))
                await websocket.close(code=1008)
                return
            
            # Marcar mensajes como entregados
            print(f"🔔 Verificando mensajes no entregados para usuario {user_id}...")  # ✅ Usar user_id
            
            grupos_usuario = db.query(Grupo).outerjoin(
                MiembroGrupo,
                and_(
                    MiembroGrupo.grupo_id == Grupo.id,
                    MiembroGrupo.usuario_id == user_id,  # ✅ Usar user_id
                    MiembroGrupo.activo == True
                )
            ).filter(
                Grupo.is_deleted == False,
                or_(
                    Grupo.creado_por_id == user_id,  # ✅ Usar user_id
                    MiembroGrupo.id != None
                )
            ).all()
            
            print(f"🔔 Usuario pertenece a {len(grupos_usuario)} grupos")
            
            mensajes_entregados_por_grupo = {}
            total_mensajes_marcados = 0
            
            for grupo in grupos_usuario:
                mensajes_no_entregados = db.query(Mensaje).filter(
                    Mensaje.grupo_id == grupo.id,
                    Mensaje.remitente_id != user_id,  # ✅ Usar user_id
                    Mensaje.entregado_at == None
                ).all()
                
                if mensajes_no_entregados:
                    print(f"📦 Grupo {grupo.id} ({grupo.nombre}): {len(mensajes_no_entregados)} mensajes sin entregar")
                    
                    for mensaje in mensajes_no_entregados:
                        mensaje.entregado_at = datetime.now(timezone.utc)
                        total_mensajes_marcados += 1
                    
                    db.commit()
                    mensajes_entregados_por_grupo[grupo.id] = [m.id for m in mensajes_no_entregados]
            
            if total_mensajes_marcados > 0:
                print(f"✅ Total de mensajes marcados como entregados: {total_mensajes_marcados}")
            else:
                print(f"ℹ️ No hay mensajes pendientes de entrega")
            
        finally:
            db.close()
            print("🔒 Sesión DB cerrada después de autenticación (notificaciones)")
        
        # ✅ AHORA SÍ PUEDES USAR user_id (es un primitivo, no un objeto SQLAlchemy)
        await grupo_notification_manager.connect_user(user_id, websocket)  # ✅ Usar user_id
        
        if mensajes_entregados_por_grupo:
            print(f"📤 Enviando notificaciones de entrega a remitentes...")
            
            for grupo_id, mensaje_ids in mensajes_entregados_por_grupo.items():
                for mensaje_id in mensaje_ids:
                    asyncio.create_task(manager.broadcast(grupo_id, {
                        "type": "mensaje_entregado",
                        "data": {
                            "mensaje_id": mensaje_id,
                            "entregado": True
                        }
                    }))
                    print(f"📬 Notificación de entrega programada para mensaje {mensaje_id}")
            
            print(f"✅ {len(sum(mensajes_entregados_por_grupo.values(), []))} notificaciones programadas")
        
        await grupo_notification_manager.notify_unread_count_changed(user_id)  # ✅ Usar user_id
        
        async def revalidate_token():
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
                            
                            debe_loguear = (
                                ultimo_tiempo_reportado is None or
                                abs(minutos_restantes - ultimo_tiempo_reportado) > 0.5 or
                                contador_checks % 5 == 0 or
                                minutos_restantes < 3
                            )
                            
                            if debe_loguear:
                                print(f"🔔⏱️ Token notificaciones - Check #{contador_checks}: {minutos_restantes:.1f} min restantes")
                                ultimo_tiempo_reportado = minutos_restantes
                            
                            if tiempo_restante <= 0:
                                print(f"🔔❌ TOKEN EXPIRADO hace {abs(minutos_restantes):.1f} minutos")
                                print(f"🔔❌ Usuario: {user_id if user_id else 'desconocido'}")  # ✅ Usar user_id
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "code": "TOKEN_EXPIRED",
                                    "message": "Tu sesión ha expirado. Reconecta con un nuevo token."
                                }))
                                await websocket.close(code=1008)
                                break
                            
                            if tiempo_restante < 120:
                                print(f"🔔⚠️ TOKEN POR EXPIRAR: {minutos_restantes:.1f} min")
                                await websocket.send_text(json.dumps({
                                    "type": "warning",
                                    "code": "TOKEN_EXPIRING_SOON",
                                    "message": "Tu sesión expirará pronto. Por favor, actualiza tu token.",
                                    "seconds_remaining": int(tiempo_restante)
                                }))
                        
                except JWTError as e:
                    print(f"🔔❌ TOKEN INVÁLIDO O EXPIRADO")
                    print(f"🔔❌ Usuario: {user_id if user_id else 'desconocido'}")  # ✅ Usar user_id
                    print(f"🔔❌ Error: {e}")
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
                        print(f"🔔🔄 Token de notificaciones actualizado para usuario {user_id}")  # ✅ Usar user_id
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
        print(f"🔔 WebSocket notificaciones desconectado para usuario {user_id if user_id else 'desconocido'}")  # ✅ Usar user_id
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
        
        # ✅ USAR user_id EN VEZ DE user
        if user_id:  # ✅ Cambiar "if user:" por "if user_id:"
            await grupo_notification_manager.disconnect_user(user_id)  # ✅ Usar user_id
        
        print(f"🔔 Limpieza completada para usuario {user_id if user_id else 'desconocido'}")  # ✅ Usar user_id

@router.websocket("/{grupo_id}/ubicaciones")
async def websocket_ubicaciones(websocket: WebSocket, grupo_id: int):
    # ✅ ACEPTAR PRIMERO (igual que el chat)
    await websocket.accept()
    print("📍 WebSocket de ubicaciones aceptado, iniciando validaciones...")
    
    user_id = None
    nombre_completo = None
    current_token = None
    heartbeat_task = None
    revalidation_task = None
    
    try:
        # ═══════════════════════════════════════════════════════
        # 1️⃣ AUTENTICACIÓN (abre DB, valida, cierra)
        # ═══════════════════════════════════════════════════════
        db = SessionLocal()
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
            
            # Validar token
            try:
                payload = jwt.decode(current_token, SECRET_KEY, algorithms=[ALGORITHM])
                user_id = payload.get("id_usuario")
                
                if user_id is None:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Token inválido"
                    }))
                    await websocket.close(code=1008)
                    return
                    
            except ExpiredSignatureError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Token expirado"
                }))
                await websocket.close(code=1008)
                return
            except JWTError as e:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Token inválido: {str(e)}"
                }))
                await websocket.close(code=1008)
                return
            
            # Buscar usuario
            user = db.query(Usuario).options(
                joinedload(Usuario.datos_personales)
            ).filter(
                Usuario.id == user_id,
                Usuario.activo == True
            ).first()
            
            if not user:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Usuario no encontrado o inactivo"
                }))
                await websocket.close(code=1008)
                return
            
            nombre_completo = f"{user.datos_personales.nombre} {user.datos_personales.apellido}"
            print(f"📍 Usuario validado: ID={user_id}, nombre={nombre_completo}")
            
            # Validar grupo
            grupo = db.query(Grupo).filter(
                Grupo.id == grupo_id, 
                Grupo.is_deleted == False
            ).first()
            
            if not grupo:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Grupo {grupo_id} no encontrado"
                }))
                await websocket.close(code=1008)
                return
            
            # Validar permisos
            miembro = db.query(MiembroGrupo).filter_by(
                usuario_id=user_id,
                grupo_id=grupo_id,
                activo=True
            ).first()
            
            if not miembro and grupo.creado_por_id != user_id:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"Usuario no pertenece al grupo {grupo_id}"
                }))
                await websocket.close(code=1008)
                return
            
            grupo_nombre = grupo.nombre
            es_creador_grupo = (grupo.creado_por_id == user_id)
            print(f"📍 Permisos validados: grupo={grupo_nombre}, es_creador={es_creador_grupo}")

        finally:
            db.close()
            print("🔒 Sesión DB cerrada después de autenticación (ubicaciones)")
        
        # ═══════════════════════════════════════════════════════
        # 2️⃣ FORZAR DESCONEXIÓN DE ZOMBIE (después de accept)
        # ═══════════════════════════════════════════════════════
        await ubicacion_manager.force_disconnect_if_exists(grupo_id, user_id)
        
        # ═══════════════════════════════════════════════════════
        # 3️⃣ CONECTAR AL MANAGER
        # ═══════════════════════════════════════════════════════
        await ubicacion_manager.connect_ubicacion(grupo_id, user_id, websocket)
        
        # ═══════════════════════════════════════════════════════
        # 4️⃣ TAREA DE REVALIDACIÓN
        # ═══════════════════════════════════════════════════════
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
                            
                            if tiempo_restante <= 0:
                                await websocket.send_text(json.dumps({
                                    "type": "error",
                                    "code": "TOKEN_EXPIRED",
                                    "message": "Tu sesión ha expirado"
                                }))
                                await websocket.close(code=1008)
                                break
                            
                            if tiempo_restante < 120:
                                await websocket.send_text(json.dumps({
                                    "type": "warning",
                                    "code": "TOKEN_EXPIRING_SOON",
                                    "message": "Tu sesión expirará pronto",
                                    "seconds_remaining": int(tiempo_restante)
                                }))
                except JWTError:
                    await websocket.close(code=1008)
                    break
                except Exception as e:
                    print(f"❌ Error en revalidación: {e}")
                    break
        
        revalidation_task = asyncio.create_task(revalidate_token())
        
        # ═══════════════════════════════════════════════════════
        # 5️⃣ ENVIAR UBICACIONES INICIALES
        # ═══════════════════════════════════════════════════════
        ubicaciones_actuales = ubicacion_manager.get_ubicaciones_grupo(grupo_id)
        await websocket.send_text(json.dumps({
            "type": "ubicaciones_iniciales",
            "ubicaciones": [
                {
                    "user_id": uid,
                    "nombre": data["nombre"],
                    "lat": data["lat"],
                    "lon": data["lon"],
                    "timestamp": data["timestamp"],
                    "es_creador": data.get("es_creador", False)
                }
                for uid, data in ubicaciones_actuales.items()
                if uid != user_id
            ]
        }))
        
        await websocket.send_text(json.dumps({
            "type": "system",
            "message": f"Conectado a ubicaciones del grupo {grupo_nombre}",
            "grupo_id": grupo_id
        }))
        
        # ═══════════════════════════════════════════════════════
        # 6️⃣ HEARTBEAT
        # ═══════════════════════════════════════════════════════
        async def heartbeat():
            while True:
                await asyncio.sleep(30)
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except:
                    break
        
        heartbeat_task = asyncio.create_task(heartbeat())
        
        # ═══════════════════════════════════════════════════════
        # 7️⃣ LOOP PRINCIPAL
        # ═══════════════════════════════════════════════════════
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            
            # Manejar refresh de token
            if payload.get("type") == "refresh_token":
                new_token = payload.get("token")
                if new_token:
                    try:
                        jwt.decode(new_token, SECRET_KEY, algorithms=[ALGORITHM])
                        current_token = new_token
                        await websocket.send_text(json.dumps({
                            "type": "token_refreshed",
                            "message": "Token actualizado correctamente"
                        }))
                    except JWTError:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Token inválido"
                        }))
                continue
            
            # Manejar ubicación
            if payload.get("type") == "ubicacion":
                lat = payload.get("lat")
                lon = payload.get("lon")
                
                if lat is not None and lon is not None:
                    data = {
                        "nombre": nombre_completo,
                        "lat": lat,
                        "lon": lon,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "es_creador": es_creador_grupo
                    }
                    await ubicacion_manager.broadcast_ubicacion(grupo_id, user_id, data)
            
            # Manejar pong
            elif payload.get("type") == "pong":
                pass
    
    except WebSocketDisconnect:
        print(f"📍 Usuario {user_id} desconectado de ubicaciones")
    except Exception as e:
        print(f"❌ Error en WebSocket de ubicaciones: {e}")
        traceback.print_exc()
    finally:
        # Limpiar tareas
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if revalidation_task:
            revalidation_task.cancel()
            try:
                await revalidation_task
            except asyncio.CancelledError:
                pass
        
        # Desconectar del manager
        if user_id:
            await ubicacion_manager.disconnect_ubicacion(grupo_id, user_id)
        
        print(f"📍 Limpieza completada para usuario {user_id if user_id else 'desconocido'}")

async def enviar_fcm_en_background(
    tokens: list,
    grupo_id: int,
    grupo_nombre: str,
    remitente_nombre: str,
    mensaje: str,
    timestamp: int,
    db_session: Session
):
    """
    🚀 Envía FCM en background sin bloquear el WebSocket
    """
    try:
        print(f"📤 ════════════════════════════════════════")
        print(f"📤 ENVIANDO FCM EN BACKGROUND")
        print(f"📤 ════════════════════════════════════════")
        print(f"   Dispositivos: {len(tokens)}")
        print(f"   Grupo: {grupo_nombre}")
        print(f"   Remitente: {remitente_nombre}")
        print(f"   Mensaje: {mensaje[:50]}...")
        
        resultado = await fcm_service.enviar_mensaje_a_grupo(
            tokens=tokens,
            grupo_id=grupo_id,
            grupo_nombre=grupo_nombre,
            remitente_nombre=remitente_nombre,
            mensaje=mensaje,
            timestamp=timestamp
        )
        
        print(f"✅ ════════════════════════════════════════")
        print(f"✅ FCM BACKGROUND COMPLETADO")
        print(f"✅ ════════════════════════════════════════")
        print(f"   Exitosos: {resultado['exitosos']}/{len(tokens)}")
        print(f"   Fallidos: {resultado['fallidos']}")
        
        # 🧹 Limpiar tokens inválidos
        if resultado['tokens_invalidos']:
            print(f"⚠️ {len(resultado['tokens_invalidos'])} tokens inválidos detectados")
            
            if resultado['exitosos'] > 0 or resultado['fallidos'] < len(tokens):
                for token_invalido in resultado['tokens_invalidos']:
                    db_session.query(FCMToken).filter(
                        FCMToken.token == token_invalido
                    ).delete()
                db_session.commit()
                print(f"🗑️ Tokens inválidos eliminados de la BD")
            else:
                print(f"⚠️ TODOS los envíos fallaron, NO se eliminan tokens")
    
    except Exception as e:
        print(f"❌ Error en FCM background: {e}")
        import traceback
        traceback.print_exc()
        # ✅ Hacer rollback si hay error
        try:
            db_session.rollback()
        except:
            pass
    
    finally:
        # ✅ CRÍTICO: Siempre cerrar la sesión al terminar
        try:
            db_session.close()
            print("🔒 Sesión DB de FCM background cerrada")
        except Exception as e:
            print(f"⚠️ Error cerrando sesión FCM: {e}")

@router.websocket("/{grupo_id}")
async def websocket_grupo(websocket: WebSocket, grupo_id: int):
    await websocket.accept()
    print("🔹 WebSocket aceptado, iniciando validaciones...")
    
    user = None
    user_id = None
    user_nombre_completo = None  # ✅ NUEVA VARIABLE
    current_token = None
    revalidation_task = None
    
    try:
        # ═══════════════════════════════════════════════════════
        # 1️⃣ AUTENTICACIÓN (abre DB, valida, cierra)
        # ═══════════════════════════════════════════════════════
        db = SessionLocal()
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
            user = await get_current_user_ws(websocket, db)
            
            # ✅ CARGAR datos_personales con eager loading
            user = db.query(Usuario).options(
                joinedload(Usuario.datos_personales)
            ).filter(Usuario.id == user.id).first()
            
            if not user:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Usuario no encontrado"
                }))
                await websocket.close(code=1008)
                return
            
            # ✅ EXTRAER datos a variables simples INMEDIATAMENTE
            user_id = user.id
            user_activo = user.activo
            user_nombre_completo = f"{user.datos_personales.nombre} {user.datos_personales.apellido}"
            
            print(f"🔹 Usuario conectado: ID={user_id}, activo={user_activo}, nombre={user_nombre_completo}")
            
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
                usuario_id=user_id,  # ✅ USAR user_id
                grupo_id=grupo_id, 
                activo=True
            ).first()
            
            es_creador = grupo.creado_por_id == user_id  # ✅ USAR user_id
            print(f"🔹 Miembro encontrado: {miembro}, Es creador: {es_creador}")
            
            if not miembro and not es_creador:
                print(f"❌ Usuario {user_id} no pertenece al grupo {grupo_id}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "No tienes acceso a este grupo"
                }))
                await websocket.close(code=1008)
                return

            websocket.usuario_id = user_id  # ✅ USAR user_id

            # Marcar mensajes como leídos al conectar
            mensajes_no_leidos = db.query(Mensaje).outerjoin(
                LecturaMensaje,
                and_(
                    LecturaMensaje.mensaje_id == Mensaje.id,
                    LecturaMensaje.usuario_id == user_id  # ✅ USAR user_id
                )
            ).filter(
                Mensaje.grupo_id == grupo_id,
                Mensaje.remitente_id != user_id,  # ✅ USAR user_id
                LecturaMensaje.id == None
            ).all()

            mensajes_no_entregados = db.query(Mensaje).filter(
                Mensaje.grupo_id == grupo_id,
                Mensaje.remitente_id != user_id,
                Mensaje.entregado_at == None
            ).all()

            if mensajes_no_entregados:
                print(f"📦 Marcando {len(mensajes_no_entregados)} mensajes como entregados")
                for mensaje in mensajes_no_entregados:
                    mensaje.entregado_at = datetime.now(timezone.utc)
                db.commit()
                
                # Notificar al remitente que sus mensajes fueron entregados
                for mensaje in mensajes_no_entregados:
                    await manager.broadcast(grupo_id, {
                        "type": "mensaje_entregado",
                        "data": {
                            "mensaje_id": mensaje.id,
                            "entregado": True
                        }
                    })
                    print(f"📬 Mensaje {mensaje.id} marcado como entregado")
            
            # Marcar mensajes como leídos al conectar
            if mensajes_no_leidos:
                print(f"📖 Marcando {len(mensajes_no_leidos)} mensajes como leídos")
                for mensaje in mensajes_no_leidos:
                    lectura = LecturaMensaje(
                        mensaje_id=mensaje.id,
                        usuario_id=user_id,
                        leido_at=datetime.now(timezone.utc)
                    )
                    db.add(lectura)
                db.commit()
                print(f"✅ {len(mensajes_no_leidos)} mensajes marcados como leídos")
                
                # 🆕 NOTIFICAR A TODOS los usuarios conectados sobre las lecturas
                for mensaje in mensajes_no_leidos:
                    # Calcular nuevo total de lecturas (sin incluir al remitente)
                    total_lecturas = db.query(func.count(LecturaMensaje.id)).filter(
                        LecturaMensaje.mensaje_id == mensaje.id,
                        LecturaMensaje.usuario_id != mensaje.remitente_id
                    ).scalar() or 0
                    
                    # Broadcast de actualización
                    await manager.broadcast(grupo_id, {
                        "type": "mensaje_leido",
                        "data": {
                            "mensaje_id": mensaje.id,
                            "leido_por": total_lecturas
                        }
                    })
                    print(f"📢 Broadcast: mensaje {mensaje.id} ahora tiene {total_lecturas} lecturas")

            # Notificar contador actualizado
            await grupo_notification_manager.notify_unread_count_changed(user_id, db)
            
        finally:
            db.close()  # ← CERRAR DB después de autenticación
            print("🔒 Sesión DB cerrada después de autenticación")
        
        # ═══════════════════════════════════════════════════════
        # 2️⃣ CONECTAR AL MANAGER (sin DB)
        # ═══════════════════════════════════════════════════════
        await manager.connect(grupo_id, user_id, websocket)  # ✅ USAR user_id
        print(f"✅ Usuario {user_id} conectado al grupo {grupo_id}")  # ✅ USAR user_id

        # ═══════════════════════════════════════════════════════
        # 3️⃣ TAREA DE REVALIDACIÓN (sin DB)
        # ═══════════════════════════════════════════════════════
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
                            print(f"⏱️ Token válido. Expira en {tiempo_restante/60:.1f} minutos")
                            
                            if tiempo_restante <= 0:
                                print(f"❌ Token expiró")
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
                    print(f"⚠️ Token expirado o inválido: {e}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "code": "TOKEN_EXPIRED",
                        "message": "Tu sesión ha expirado."
                    }))
                    await websocket.close(code=1008)
                    break
                except Exception as e:
                    print(f"❌ Error en revalidación: {e}")
                    break
        
        revalidation_task = asyncio.create_task(revalidate_token())

        # Obtener nombre del grupo (necesitamos abrir DB brevemente)
        db = SessionLocal()
        try:
            grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
            grupo_nombre = grupo.nombre if grupo else "Grupo"
        finally:
            db.close()

        await websocket.send_text(json.dumps({
            "type": "system",
            "message": f"Conectado al grupo {grupo_nombre}",
            "grupo_id": grupo_id
        }))

        # ═══════════════════════════════════════════════════════
        # 4️⃣ LOOP PRINCIPAL (sin DB abierta permanentemente)
        # ═══════════════════════════════════════════════════════
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
                        print(f"🔄 Token actualizado para usuario {user_id}")
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
            
            if action == "mensaje":
                contenido = data.get("contenido", "").strip()
                tipo = data.get("tipo", "texto")
                temp_id = data.get("temp_id")  # 🆕 CAPTURAR temp_id del cliente
                
                if not contenido:
                    continue

                db = SessionLocal()
                try:
                    # 1️⃣ Guardar mensaje en BD
                    mensaje = Mensaje(
                        remitente_id=user_id,
                        grupo_id=grupo_id,
                        contenido=contenido,
                        tipo=tipo,
                        fecha_creacion=datetime.now(timezone.utc),
                        entregado_at=None
                    )
                    db.add(mensaje)
                    db.commit()
                    db.refresh(mensaje)

                    # 2️⃣ Marcar como leído para el remitente
                    lectura = LecturaMensaje(
                        mensaje_id=mensaje.id,
                        usuario_id=user_id,
                        leido_at=datetime.now(timezone.utc)
                    )
                    db.add(lectura)
                    db.commit()
                    print(f"✅ Mensaje {mensaje.id} guardado")

                    # 3️⃣ Obtener miembros del grupo
                    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
                    miembros = db.query(MiembroGrupo).filter_by(grupo_id=grupo_id, activo=True).all()
                    miembros_ids = [m.usuario_id for m in miembros]
                    if grupo.creado_por_id not in miembros_ids:
                        miembros_ids.append(grupo.creado_por_id)

                    # 4️⃣ Verificar si hay usuarios conectados
                    hay_usuarios_conectados = False
                    for miembro_id in miembros_ids:
                        if miembro_id != user_id:
                            if manager.is_user_connected_to_group(grupo_id, miembro_id):
                                hay_usuarios_conectados = True
                                break

                    # 5️⃣ Si hay usuarios conectados, marcar como entregado inmediatamente
                    if hay_usuarios_conectados:
                        mensaje.entregado_at = datetime.now(timezone.utc)
                        db.commit()
                        print(f"📬 Mensaje {mensaje.id} entregado inmediatamente (hay usuarios conectados)")

                    # 6️⃣ Calcular lecturas reales (excluyendo al remitente)
                    total_lecturas = db.query(func.count(LecturaMensaje.id)).filter(
                        LecturaMensaje.mensaje_id == mensaje.id,
                        LecturaMensaje.usuario_id != mensaje.remitente_id
                    ).scalar() or 0

                    # 7️⃣ Preparar mensaje para WebSocket
                    out = {
                        "type": "mensaje",
                        "data": {
                            "id": mensaje.id,
                            "temp_id": temp_id,  # 🆕 DEVOLVER temp_id al cliente
                            "remitente_id": mensaje.remitente_id,
                            "remitente_nombre": user_nombre_completo,
                            "grupo_id": mensaje.grupo_id,
                            "contenido": mensaje.contenido,
                            "tipo": mensaje.tipo,
                            "fecha_creacion": mensaje.fecha_creacion.isoformat(),
                            "entregado": bool(mensaje.entregado_at),
                            "leido": False,
                            "leido_por": total_lecturas
                        }
                    }

                    # 8️⃣ ENVIAR por WebSocket
                    print(f"📤 Enviando mensaje por WebSocket - temp_id={temp_id}, id_real={mensaje.id}")
                    print(f"📤 Enviando mensaje por WebSocket - entregado={bool(mensaje.entregado_at)}, leido_por={total_lecturas}")
                    
                    # 🔥 BROADCAST (esto enviará el mensaje a todos los conectados)
                    enviado_exitosamente = await manager.broadcast(grupo_id, out)
                    
                    # 🔥 CRÍTICO: Si se entregó exitosamente pero aún no está marcado como entregado en BD
                    if enviado_exitosamente and not mensaje.entregado_at:
                        mensaje.entregado_at = datetime.now(timezone.utc)
                        db.commit()
                        db.refresh(mensaje)
                        print(f"📬 Mensaje {mensaje.id} marcado como entregado después del broadcast exitoso")
                        
                        # Notificar al remitente que el mensaje fue entregado
                        await manager.broadcast(grupo_id, {
                            "type": "mensaje_entregado",
                            "data": {
                                "mensaje_id": mensaje.id,
                                "entregado": True
                            }
                        })
                        print(f"📢 Notificación de entrega enviada para mensaje {mensaje.id}")

                    # 9️⃣ Actualizar contadores y preparar FCM
                    tokens_para_fcm = []
                    
                    for miembro_id in miembros_ids:
                        if miembro_id != user_id:
                            await grupo_notification_manager.notify_unread_count_changed(miembro_id, db)
                            esta_conectado = manager.is_user_connected_to_group(grupo_id, miembro_id)
                            
                            if esta_conectado:
                                print(f"ℹ️ Usuario {miembro_id} conectado, no FCM")
                                continue
                            
                            mensajes_no_leidos = db.query(func.count(Mensaje.id)).outerjoin(
                                LecturaMensaje, 
                                and_(
                                    LecturaMensaje.mensaje_id == Mensaje.id,
                                    LecturaMensaje.usuario_id == miembro_id
                                )
                            ).filter(
                                Mensaje.grupo_id == grupo_id,
                                Mensaje.remitente_id != miembro_id,
                                LecturaMensaje.id == None
                            ).scalar() or 0
                            
                            if mensajes_no_leidos > 0:
                                tokens_usuario = db.query(FCMToken).filter(
                                    FCMToken.usuario_id == miembro_id
                                ).all()
                                tokens_para_fcm.extend([t.token for t in tokens_usuario])
                                print(f"📱 Usuario {miembro_id}: {mensajes_no_leidos} no leídos")

                    # 🔟 Preparar datos para FCM ANTES de cerrar DB
                    fcm_data = None
                    if tokens_para_fcm:
                        fcm_data = {
                            'tokens': tokens_para_fcm,
                            'grupo_id': grupo_id,
                            'grupo_nombre': grupo.nombre,
                            'remitente_nombre': user_nombre_completo,
                            'mensaje': contenido,
                            'timestamp': int(mensaje.fecha_creacion.timestamp() * 1000)
                        }

                finally:
                    db.close()
                    print("🔒 Sesión DB cerrada después de procesar mensaje")

                # 1️⃣1️⃣ Lanzar FCM en background (DESPUÉS de cerrar DB)
                if fcm_data:
                    asyncio.create_task(enviar_fcm_en_background(
                        tokens=fcm_data['tokens'],
                        grupo_id=fcm_data['grupo_id'],
                        grupo_nombre=fcm_data['grupo_nombre'],
                        remitente_nombre=fcm_data['remitente_nombre'],
                        mensaje=fcm_data['mensaje'],
                        timestamp=fcm_data['timestamp'],
                        db_session=SessionLocal()
                    ))
                    print(f"🚀 FCM programado para {len(fcm_data['tokens'])} dispositivos")

    except WebSocketDisconnect:
        print(f"🔹 WebSocket desconectado para usuario {user.id if user else 'desconocido'}")
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
        
        if user:
            await manager.disconnect(grupo_id, user_id)            
            
            # Actualizar contador final (abre/cierra DB)
            try:
                print(f"🔔 Actualizando contador final")
                await grupo_notification_manager.notify_unread_count_changed(user.id)  # Sin db
            except Exception as e:
                print(f"⚠️ Error actualizando contador: {e}")
        
        print(f"🔹 Usuario {user_id if user_id else 'desconocido'} desconectado del grupo {grupo_id}")


def notify_mensaje_leido_sync(grupo_id: int, mensaje_id: int, leido_por: int):
    """
    Notifica de forma síncrona que un mensaje fue leído
    """
    import asyncio
    
    try:
        # Obtener el event loop actual si existe
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No hay loop, crear uno temporal
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Ejecutar y cerrar
            loop.run_until_complete(manager.broadcast(grupo_id, {
                "type": "mensaje_leido",
                "data": {
                    "mensaje_id": mensaje_id,
                    "leido_por": leido_por
                }
            }))
            loop.close()
            return
        
        # Si hay loop corriendo, usar create_task
        asyncio.create_task(manager.broadcast(grupo_id, {
            "type": "mensaje_leido",
            "data": {
                "mensaje_id": mensaje_id,
                "leido_por": leido_por
            }
        }))
        print(f"📢 Notificación programada: mensaje {mensaje_id} con {leido_por} lecturas")
    except Exception as e:
        print(f"⚠️ Error al notificar mensaje leído: {e}")


