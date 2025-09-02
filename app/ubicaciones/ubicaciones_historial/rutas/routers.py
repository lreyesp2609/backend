from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ....database.database import get_db
from .schemas import RutaUsuarioCreate, RutaUsuarioRead
from .crud import crud_rutas

router = APIRouter(prefix="/rutas", tags=["Rutas"])

@router.post("/", 
             response_model=RutaUsuarioRead,
             status_code=status.HTTP_201_CREATED,
             summary="Crear nueva ruta",
             description="Crea una nueva ruta y asigna automáticamente el estado EN_PROGRESO")
def create_ruta(ruta: RutaUsuarioCreate, db: Session = Depends(get_db)):
    """Crear una nueva ruta de usuario con estado automático"""
    try:
        return crud_rutas.create_ruta(db, ruta)
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

@router.delete("/{ruta_id}", 
              response_model=dict,
              summary="Eliminar ruta",
              description="Elimina una ruta específica por su ID")
def delete_ruta(ruta_id: int, db: Session = Depends(get_db)):
    """Eliminar una ruta por ID"""
    success = crud_rutas.delete_ruta(db, ruta_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Ruta con ID {ruta_id} no encontrada"
        )
    return {"message": f"Ruta {ruta_id} eliminada correctamente"}
