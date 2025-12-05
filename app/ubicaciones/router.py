from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database.database import get_db
from ..ubicaciones.crud import crear_ubicacion, obtener_ubicaciones, obtener_ubicacion, actualizar_ubicacion, eliminar_ubicacion
from ..ubicaciones.schemas import UbicacionUsuarioCreate, UbicacionUsuarioUpdate, UbicacionUsuarioResponse
from ..usuarios.security import get_current_user

router = APIRouter(
    prefix="/ubicaciones",
    tags=["Ubicaciones"]
)

@router.post("/", response_model=UbicacionUsuarioResponse)
def crear_ubicacion_usuario(
    ubicacion: UbicacionUsuarioCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    nueva_ubicacion = crear_ubicacion(db, current_user.id, ubicacion)
    if not nueva_ubicacion:
        raise HTTPException(status_code=400, detail="LOCATION_NAME_ALREADY_EXISTS")
    return nueva_ubicacion

@router.get("/", response_model=List[UbicacionUsuarioResponse])
def listar_ubicaciones(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return obtener_ubicaciones(db, current_user.id)

@router.get("/{ubicacion_id}", response_model=UbicacionUsuarioResponse)
def obtener_ubicacion_usuario(
    ubicacion_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    ubicacion = obtener_ubicacion(db, ubicacion_id, current_user.id)
    if not ubicacion:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")
    return ubicacion

@router.put("/{ubicacion_id}", response_model=UbicacionUsuarioResponse)
def actualizar_ubicacion_usuario(
    ubicacion_id: int,
    datos: UbicacionUsuarioUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    ubicacion = actualizar_ubicacion(db, ubicacion_id, current_user.id, datos)
    if not ubicacion:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")
    if ubicacion == "DUPLICATE_NAME":
        raise HTTPException(status_code=400, detail="LOCATION_NAME_ALREADY_EXISTS")
    return ubicacion

@router.delete("/{ubicacion_id}", response_model=UbicacionUsuarioResponse)
def eliminar_ubicacion_usuario(
    ubicacion_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    ubicacion = eliminar_ubicacion(db, ubicacion_id, current_user.id)
    if not ubicacion:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")
    return ubicacion