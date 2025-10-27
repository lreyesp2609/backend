from typing import Optional
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

class MensajeIn(BaseModel):
    contenido: str
    tipo: str = "texto"

class MensajeOut(BaseModel):
    id: int
    remitente_id: int
    remitente_nombre: str | None = None
    grupo_id: int
    contenido: str
    tipo: str
    fecha_creacion: datetime
    leido: bool
    leido_por: int
    
    class Config:
        from_attributes = True

class GrupoConNoLeidos(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = None
    codigo_invitacion: str
    creado_por_id: int
    fecha_creacion: datetime
    mensajes_no_leidos: int = 0
    
    class Config:
        from_attributes = True