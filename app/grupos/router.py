from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .schemas import *
from .models import *
from .crud import create_grupo
from ..database.database import get_db
from ..usuarios.security import get_current_user
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session
from .WebSocket.routers import router as ws_grupos_router

router = APIRouter(prefix="/grupos", tags=["Grupos"])

router.include_router(ws_grupos_router)

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

    miembro_existente = db.query(MiembroGrupo).filter_by(
        usuario_id=current_user.id,
        grupo_id=grupo.id
    ).first()

    if miembro_existente:
        raise HTTPException(status_code=400, detail="Ya perteneces a este grupo")

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
    # Validaciones existentes
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id, Grupo.is_deleted == False).first()
    if not grupo: 
        raise HTTPException(404, "Grupo no existe")
    
    miembro = db.query(MiembroGrupo).filter_by(
        usuario_id=current_user.id, 
        grupo_id=grupo_id, 
        activo=True
    ).first()
    
    if not miembro and grupo.creado_por_id != current_user.id:
        raise HTTPException(403, "No perteneces a este grupo")
    
    # 🆕 Query corregido
    from sqlalchemy import case
    
    mensajes = db.query(
        Mensaje,
        # ✅ Verificar si el usuario actual leyó este mensaje
        func.sum(
            case((LecturaMensaje.usuario_id == current_user.id, 1), else_=0)
        ).label("leido_por_mi"),
        # ✅ Contar cuántas personas leyeron el mensaje
        func.count(LecturaMensaje.id).label("total_lecturas")
    ).outerjoin(
        LecturaMensaje, 
        Mensaje.id == LecturaMensaje.mensaje_id
    ).filter(
        Mensaje.grupo_id == grupo_id
    ).group_by(
        Mensaje.id
    ).order_by(
        Mensaje.fecha_creacion.desc()
    ).limit(limit).all()
    
    # Formatear respuesta
    resultado = []
    for mensaje, leido_por_mi, total_lecturas in reversed(mensajes):
        resultado.append(MensajeOut(
            id=mensaje.id,
            remitente_id=mensaje.remitente_id,
            grupo_id=mensaje.grupo_id,
            contenido=mensaje.contenido,
            tipo=mensaje.tipo,
            fecha_creacion=mensaje.fecha_creacion,
            leido=bool(leido_por_mi > 0),
            leido_por=total_lecturas or 0
        ))
    
    return resultado

@router.post("/{grupo_id}/mensajes/{mensaje_id}/marcar-leido")
def marcar_mensaje_leido(
    grupo_id: int,
    mensaje_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Marca un mensaje como leído por el usuario actual
    """
    # Validar que el mensaje existe y pertenece al grupo
    mensaje = db.query(Mensaje).filter(
        Mensaje.id == mensaje_id,
        Mensaje.grupo_id == grupo_id
    ).first()
    
    if not mensaje:
        raise HTTPException(404, "Mensaje no encontrado")
    
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
    
    return {"message": "Mensaje marcado como leído", "leido": True}