from pydantic import BaseModel
from datetime import datetime

class GrupoCreate(BaseModel):
    nombre: str
    descripcion: str | None = None

class GrupoOut(BaseModel):
    id: int
    nombre: str
    descripcion: str | None = None
    codigo_invitacion: str
    creado_por_id: int
    fecha_creacion: datetime

    class Config:
        orm_mode = True