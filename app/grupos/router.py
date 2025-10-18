from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .schemas import GrupoCreate, GrupoOut
from .models import Grupo, MiembroGrupo
from .crud import create_grupo
from ..database.database import get_db
from ..usuarios.security import get_current_user

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
