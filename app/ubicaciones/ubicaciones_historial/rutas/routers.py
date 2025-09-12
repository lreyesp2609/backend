from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ....usuarios.security import get_current_user
from ....database.database import get_db
from .schemas import RutaUsuarioCreate, RutaUsuarioRead
from .crud import crud_rutas
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/rutas", tags=["Rutas"])

@router.post("/", 
             response_model=RutaUsuarioRead,
             status_code=status.HTTP_201_CREATED,
             summary="Crear nueva ruta",
             description="Crea una nueva ruta y asigna automáticamente el estado EN_PROGRESO")
def create_ruta(
    ruta: RutaUsuarioCreate, 
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        # 🔥 PASAR EL tipo_ruta_usado que viene en el schema
        return crud_rutas.create_ruta(
            db=db, 
            ruta=ruta, 
            usuario_id=current_user.id,
            tipo_ruta_usado=ruta.tipo_ruta_usado  # 🔥 AGREGAR ESTE PARÁMETRO
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno del servidor: {str(e)}"
        )

@router.get("/{ruta_id}", 
           response_model=RutaUsuarioRead,
           summary="Obtener ruta por ID",
           description="Obtiene una ruta específica por su ID")
def get_ruta(ruta_id: int, db: Session = Depends(get_db)):
    """Obtener una ruta por ID"""
    db_ruta = crud_rutas.get_ruta(db, ruta_id)
    if not db_ruta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Ruta con ID {ruta_id} no encontrada"
        )
    return db_ruta

@router.get("/", 
           response_model=List[RutaUsuarioRead],
           summary="Listar rutas",
           description="Obtiene una lista paginada de todas las rutas")
def list_rutas(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Listar todas las rutas con paginación"""
    if limit > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El límite máximo es 100"
        )
    return crud_rutas.list_rutas(db, skip=skip, limit=limit)

class FinalizarRutaRequest(BaseModel):
    fecha_fin: str
    puntos_gps: Optional[List[dict]] = None
    siguio_ruta_recomendada: Optional[bool] = None
    porcentaje_similitud: Optional[float] = None

@router.post("/{ruta_id}/finalizar", response_model=dict)
def finalizar_ruta_endpoint(
    ruta_id: int, 
    request: FinalizarRutaRequest,
    db: Session = Depends(get_db),
):
    resultado = crud_rutas.finalizar_ruta(
        db, 
        ruta_id, 
        request.fecha_fin,
        request.puntos_gps,
        request.siguio_ruta_recomendada,
        request.porcentaje_similitud
    )
    
    return resultado

@router.post("/{ruta_id}/cancelar", response_model=RutaUsuarioRead)
def cancelar_ruta(
    ruta_id: int, 
    fecha_fin: str,
    db: Session = Depends(get_db)
):
    return crud_rutas.cancelar_ruta(db, ruta_id, fecha_fin)