from pydantic import BaseModel
from typing import Optional
from enum import Enum

class EstadoUbicacionEnum(str, Enum):
    EN_PROGRESO = "EN_PROGRESO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"

class EstadoUbicacionUsuarioBase(BaseModel):
    ubicacion_id: int
    estado: EstadoUbicacionEnum

class EstadoUbicacionUsuarioCreate(EstadoUbicacionUsuarioBase):
    duracion_segundos: Optional[float] = None

class EstadoUbicacionUsuarioResponse(EstadoUbicacionUsuarioBase):
    id: int
    duracion_segundos: Optional[float]
    usuario_id: int

    class Config:
        orm_mode = True
