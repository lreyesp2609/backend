from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .schemas import GrupoCreate, GrupoOut
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