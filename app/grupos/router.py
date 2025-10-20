from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .schemas import GrupoCreate, GrupoOut
from .models import Grupo, MiembroGrupo
from .crud import create_grupo
from ..database.database import get_db
from ..usuarios.security import get_current_user
from datetime import datetime

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
    # Buscar los grupos creados por el usuario
    grupos_creados = db.query(Grupo).filter(
        Grupo.creado_por_id == current_user.id,
        Grupo.is_deleted == False
    )

    # Buscar los grupos donde el usuario es miembro (por MiembroGrupo)
    grupos_miembro = db.query(Grupo).join(MiembroGrupo).filter(
        MiembroGrupo.usuario_id == current_user.id,
        Grupo.is_deleted == False
    )

    # Unir ambos conjuntos sin duplicados
    grupos = grupos_creados.union(grupos_miembro).all()

    return grupos

@router.post("/unirse/{codigo}", response_model=GrupoOut)
def unirse_a_grupo(
    codigo: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # 1️⃣ Buscar grupo activo por el código de invitación
    grupo = db.query(Grupo).filter_by(codigo_invitacion=codigo, is_deleted=False).first()

    if not grupo:
        raise HTTPException(status_code=404, detail="Código de invitación inválido o grupo inexistente")

    # 2️⃣ Verificar si el usuario es el creador del grupo
    if grupo.creado_por_id == current_user.id:
        raise HTTPException(status_code=400, detail="Eres el creador de este grupo, ya perteneces a él")

    # 3️⃣ Verificar si el usuario ya pertenece al grupo
    miembro_existente = db.query(MiembroGrupo).filter_by(
        usuario_id=current_user.id,
        grupo_id=grupo.id
    ).first()

    if miembro_existente:
        raise HTTPException(status_code=400, detail="Ya perteneces a este grupo")

    # 4️⃣ Crear nuevo miembro del grupo
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