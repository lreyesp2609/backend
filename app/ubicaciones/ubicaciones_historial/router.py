from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.database import get_db
from ...ubicaciones.ubicaciones_historial import crud, schemas
from ...usuarios.security import get_current_user
from ...usuarios.models import Usuario

router = APIRouter(
    prefix="/estados_ubicacion",
    tags=["Estados de Ubicación"]
)

@router.post("/", response_model=schemas.EstadoUbicacionUsuarioResponse)
def crear_estado_ubicacion(
    estado: schemas.EstadoUbicacionUsuarioCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
):
    return crud.crear_estado_ubicacion(db, estado, current_user)
