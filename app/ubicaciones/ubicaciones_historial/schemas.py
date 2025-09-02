from pydantic import BaseModel
from typing import Optional

# Schema para EstadoUbicacion
class EstadoUbicacionBase(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    activo: bool = True
    orden: Optional[int] = None

class EstadoUbicacionCreate(EstadoUbicacionBase):
    pass

class EstadoUbicacionResponse(EstadoUbicacionBase):
    id: int

    class Config:
        from_attributes = True

# Schema para EstadoUbicacionUsuario actualizado
class EstadoUbicacionUsuarioCreate(BaseModel):
    ubicacion_id: int
    usuario_id: int
    estado_ubicacion_id: int  # Cambiado de 'estado' a 'estado_ubicacion_id'
    duracion_segundos: Optional[float] = None

class EstadoUbicacionUsuarioResponse(BaseModel):
    id: int
    ubicacion_id: int
    usuario_id: int
    estado_ubicacion_id: int
    duracion_segundos: Optional[float]
    estado_ubicacion: EstadoUbicacionResponse  # Incluir datos del estado

    class Config:
        from_attributes = True