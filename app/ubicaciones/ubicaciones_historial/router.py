from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database.database import get_db
from app.ubicaciones.ubicaciones_historial import crud, schemas
from app.usuarios.security import get_current_user

router = APIRouter(
    prefix="/estados_ubicacion",
    tags=["Estados de Ubicación"]
)

@router.get("/tipos-estado", response_model=List[schemas.EstadoUbicacionResponse])
def listar_tipos_estado(db: Session = Depends(get_db)):
    """Obtener todos los tipos de estado disponibles"""
    from app.ubicaciones.ubicaciones_historial.models import EstadoUbicacion
    return db.query(EstadoUbicacion).filter(EstadoUbicacion.activo == True).order_by(EstadoUbicacion.orden).all()