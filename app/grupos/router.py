from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .schemas import *
from .models import *
from .crud import create_grupo
from ..database.database import get_db
from ..usuarios.security import get_current_user
from datetime import datetime, timezone
from ..usuarios.models import Usuario, DatosPersonales
from sqlalchemy import func
from sqlalchemy.orm import Session
from .WebSocket.routers import router as ws_grupos_router

router = APIRouter(prefix="/grupos", tags=["Grupos"])

@router.post("/crear", response_model=GrupoOut)
def create_new_grupo(
    grupo: GrupoCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        new_grupo = create_grupo(db, grupo, current_user.id)
        return new_grupo
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al crear grupo: {str(e)}")

@router.get("/listar", response_model=list[GrupoOut])
def listar_grupos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    grupos_creados = db.query(Grupo).filter(
        Grupo.creado_por_id == current_user.id,
        Grupo.is_deleted == False
    )

    grupos_miembro = db.query(Grupo).join(MiembroGrupo).filter(
        MiembroGrupo.usuario_id == current_user.id,
        MiembroGrupo.activo == True,
        Grupo.is_deleted == False
    )

    grupos = grupos_creados.union(grupos_miembro).all()
    return grupos

@router.post("/unirse/{codigo}", response_model=GrupoOut)
def unirse_a_grupo(
    codigo: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    grupo = db.query(Grupo).filter_by(codigo_invitacion=codigo, is_deleted=False).first()

    if not grupo:
        raise HTTPException(status_code=404, detail="Código de invitación inválido o grupo inexistente")

    if grupo.creado_por_id == current_user.id:
        raise HTTPException(status_code=400, detail="Eres el creador de este grupo, ya perteneces a él")

    # ✅ Buscar si el usuario ya fue miembro (activo o inactivo)
    miembro_existente = db.query(MiembroGrupo).filter_by(
        usuario_id=current_user.id,
        grupo_id=grupo.id
    ).first()

    if miembro_existente:
        # ✅ Si ya existe pero está inactivo, reactivarlo
        if not miembro_existente.activo:
            miembro_existente.activo = True
            miembro_existente.fecha_union = datetime.utcnow()  # Actualizar fecha de reingreso
            db.commit()
            db.refresh(grupo)
            return grupo
        else:
            # Ya está activo
            raise HTTPException(status_code=400, detail="Ya perteneces a este grupo")

    # ✅ Si no existe, crear nuevo miembro
    nuevo_miembro = MiembroGrupo(
        usuario_id=current_user.id,
        grupo_id=grupo.id,
        rol="miembro",
        activo=True,
        fecha_union=datetime.utcnow()
    )

    db.add(nuevo_miembro)
    db.commit()
    db.refresh(grupo)

    return grupo

@router.get("/{grupo_id}/mensajes", response_model=list[MensajeOut])
def obtener_mensajes_grupo(
    grupo_id: int, 
    limit: int = 50, 
    db: Session = Depends(get_db), 
    current_user = Depends(get_current_user)
):
    # Validar existencia del grupo
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id, Grupo.is_deleted == False).first()
    if not grupo:
        raise HTTPException(404, "Grupo no existe")
    
    # Validar membresía o permisos
    miembro = db.query(MiembroGrupo).filter_by(
        usuario_id=current_user.id, 
        grupo_id=grupo_id, 
        activo=True
    ).first()
    if not miembro and grupo.creado_por_id != current_user.id:
        raise HTTPException(403, "No perteneces a este grupo")
    
    from sqlalchemy import case, func

    # 🔥 Consulta mejorada: excluir al remitente del conteo de lecturas
    mensajes = (
        db.query(
            Mensaje,
            func.sum(
                case((LecturaMensaje.usuario_id == current_user.id, 1), else_=0)
            ).label("leido_por_mi"),
            func.count(
                case((LecturaMensaje.usuario_id != Mensaje.remitente_id, LecturaMensaje.id), else_=None)
            ).label("total_lecturas"),
            DatosPersonales.nombre.label("nombre_remitente"),
            DatosPersonales.apellido.label("apellido_remitente")
        )
        .join(Usuario, Usuario.id == Mensaje.remitente_id)
        .join(DatosPersonales, DatosPersonales.id == Usuario.datos_personales_id)
        .outerjoin(LecturaMensaje, Mensaje.id == LecturaMensaje.mensaje_id)
        .filter(Mensaje.grupo_id == grupo_id)
        .group_by(Mensaje.id, DatosPersonales.nombre, DatosPersonales.apellido)
        .order_by(Mensaje.fecha_creacion.desc())
        .limit(limit)
        .all()
    )
    
    resultado = []
    for mensaje, leido_por_mi, total_lecturas, nombre, apellido in reversed(mensajes):
        resultado.append(
            MensajeOut(
                id=mensaje.id,
                remitente_id=mensaje.remitente_id,
                remitente_nombre=f"{nombre} {apellido}",
                grupo_id=mensaje.grupo_id,
                contenido=mensaje.contenido,
                tipo=mensaje.tipo,
                fecha_creacion=mensaje.fecha_creacion,
                entregado=bool(mensaje.entregado_at),  # 🆕 NUEVO
                leido=bool(leido_por_mi > 0),
                leido_por=total_lecturas or 0
            )
        )

    return resultado

@router.post("/{grupo_id}/mensajes/{mensaje_id}/marcar-leido")
def marcar_mensaje_leido(
    grupo_id: int,
    mensaje_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Validar que el mensaje existe y pertenece al grupo
    mensaje = db.query(Mensaje).filter(
        Mensaje.id == mensaje_id,
        Mensaje.grupo_id == grupo_id
    ).first()
    
    if not mensaje:
        raise HTTPException(404, "Mensaje no encontrado")
    
    # 🔥 No permitir que el remitente marque su propio mensaje como leído
    if mensaje.remitente_id == current_user.id:
        return {"message": "No puedes marcar tu propio mensaje como leído", "leido": False}
    
    # Verificar permisos en el grupo
    miembro = db.query(MiembroGrupo).filter_by(
        usuario_id=current_user.id, 
        grupo_id=grupo_id, 
        activo=True
    ).first()
    
    grupo = db.query(Grupo).filter_by(id=grupo_id).first()
    if not miembro and grupo.creado_por_id != current_user.id:
        raise HTTPException(403, "No perteneces a este grupo")
    
    # Verificar si ya fue leído
    lectura_existente = db.query(LecturaMensaje).filter_by(
        mensaje_id=mensaje_id,
        usuario_id=current_user.id
    ).first()
    
    if lectura_existente:
        return {"message": "Mensaje ya marcado como leído", "leido": True}
    
    # Crear registro de lectura
    lectura = LecturaMensaje(
        mensaje_id=mensaje_id,
        usuario_id=current_user.id
    )
    db.add(lectura)
    db.commit()
    
    # 🔥 NUEVO: Calcular total de lecturas (excluyendo al remitente)
    total_lecturas = db.query(func.count(LecturaMensaje.id)).filter(
        LecturaMensaje.mensaje_id == mensaje_id,
        LecturaMensaje.usuario_id != mensaje.remitente_id
    ).scalar() or 0
    
    # 🔥 NUEVO: Notificar por WebSocket usando la función helper
    from .WebSocket.routers import notify_mensaje_leido_sync
    notify_mensaje_leido_sync(grupo_id, mensaje_id, total_lecturas)
    
    return {"message": "Mensaje marcado como leído", "leido": True}

@router.get("/{grupo_id}/integrantes")
def integrantes_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)  # ✅ Agregado paréntesis faltante
):
    """
    Obtiene la lista de integrantes de un grupo
    """
    # Validar existencia del grupo
    grupo = db.query(Grupo).filter(
        Grupo.id == grupo_id, 
        Grupo.is_deleted == False
    ).first()
    
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no existe")
    
    # Validar membresía o permisos
    miembro = db.query(MiembroGrupo).filter(
        MiembroGrupo.usuario_id == current_user.id,
        MiembroGrupo.grupo_id == grupo_id,
        MiembroGrupo.activo == True
    ).first()
    
    if not miembro and grupo.creado_por_id != current_user.id:
        raise HTTPException(status_code=403, detail="No perteneces a este grupo")
    
    # Obtener integrantes del grupo
    integrantes = db.query(
        Usuario.id,
        DatosPersonales.nombre,
        DatosPersonales.apellido,
        MiembroGrupo.rol,
        MiembroGrupo.activo,
        MiembroGrupo.fecha_union
    ).join(
        DatosPersonales, 
        DatosPersonales.id == Usuario.datos_personales_id
    ).join(
        MiembroGrupo, 
        MiembroGrupo.usuario_id == Usuario.id
    ).filter(
        MiembroGrupo.grupo_id == grupo_id
    ).all()
    
    resultado = []
    for usuario_id, nombre, apellido, rol, activo, fecha_union in integrantes:
        resultado.append({
            "usuario_id": usuario_id,
            "nombre_completo": f"{nombre} {apellido}",
            "nombre": nombre,
            "apellido": apellido,
            "rol": rol,
            "activo": activo,
            "fecha_union": fecha_union.isoformat() if fecha_union else None,
            "es_creador": usuario_id == grupo.creado_por_id
        })
    
    return {
        "grupo_id": grupo_id,
        "grupo_nombre": grupo.nombre,
        "total_integrantes": len(resultado),
        "integrantes": resultado
    }

@router.post("/{grupo_id}/salir")
def salir_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    from .crud import salir_de_grupo
    return salir_de_grupo(db, grupo_id, current_user.id)

@router.delete("/eliminar/{grupo_id}")
def eliminar_grupo(
    grupo_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    grupo = db.query(Grupo).filter(
        Grupo.id == grupo_id,
        Grupo.is_deleted == False
    ).first()

    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")

    # Solo el creador puede eliminarlo
    if grupo.creado_por_id != current_user.id:
        raise HTTPException(status_code=403, detail="Solo el creador puede eliminar el grupo")

    # Marcar grupo como eliminado
    grupo.is_deleted = True

    # Desactivar todos los miembros del grupo
    db.query(MiembroGrupo).filter(
        MiembroGrupo.grupo_id == grupo_id
    ).update({"activo": False})

    db.commit()

    return {"message": f"Grupo '{grupo.nombre}' eliminado correctamente"}


@router.post("/{grupo_id}/mensajes/marcar-entregados")
def marcar_mensajes_entregados(
    grupo_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Marca TODOS los mensajes no entregados de un grupo como entregados
    Se llama cuando el usuario recibe FCM (incluso en segundo plano)
    """
    # Validar que el usuario pertenece al grupo
    grupo = db.query(Grupo).filter(
        Grupo.id == grupo_id,
        Grupo.is_deleted == False
    ).first()
    
    if not grupo:
        raise HTTPException(404, "Grupo no encontrado")
    
    miembro = db.query(MiembroGrupo).filter_by(
        usuario_id=current_user.id,
        grupo_id=grupo_id,
        activo=True
    ).first()
    
    if not miembro and grupo.creado_por_id != current_user.id:
        raise HTTPException(403, "No perteneces a este grupo")
    
    # 🔥 MARCAR MENSAJES COMO ENTREGADOS
    mensajes_no_entregados = db.query(Mensaje).filter(
        Mensaje.grupo_id == grupo_id,
        Mensaje.remitente_id != current_user.id,  # No marcar mis propios mensajes
        Mensaje.entregado_at == None
    ).all()
    
    if not mensajes_no_entregados:
        return {
            "message": "No hay mensajes pendientes de entrega",
            "mensajes_marcados": 0
        }
    
    # Marcar como entregados
    mensaje_ids = []
    for mensaje in mensajes_no_entregados:
        mensaje.entregado_at = datetime.now(timezone.utc)
        mensaje_ids.append(mensaje.id)
    
    db.commit()
    
    # 🔥 NOTIFICAR POR WEBSOCKET (si hay usuarios conectados)
    from .WebSocket.routers import manager
    import asyncio
    
    for mensaje_id in mensaje_ids:
        try:
            # Intentar notificar por WebSocket (no bloqueante)
            asyncio.create_task(manager.broadcast(grupo_id, {
                "type": "mensaje_entregado",
                "data": {
                    "mensaje_id": mensaje_id,
                    "entregado": True
                }
            }))
        except:
            pass  # Si no hay loop, ignorar
    
    print(f"📬 {len(mensaje_ids)} mensajes marcados como entregados para grupo {grupo_id}")
    
    return {
        "message": f"{len(mensaje_ids)} mensajes marcados como entregados",
        "mensajes_marcados": len(mensaje_ids),
        "mensaje_ids": mensaje_ids
    }