from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class PasoRutaBase(BaseModel):
    instruccion: str = Field(..., description="Instrucción del paso")
    distancia: float = Field(..., ge=0, description="Distancia en kilómetros")
    duracion: float = Field(..., ge=0, description="Duración en segundos")
    tipo: Optional[int] = Field(None, description="Tipo de paso")

class PasoRutaCreate(PasoRutaBase):
    pass

class PasoRutaRead(PasoRutaBase):
    id: int

    class Config:
        from_attributes = True

class SegmentoRutaBase(BaseModel):
    distancia: float = Field(..., ge=0, description="Distancia del segmento")
    duracion: float = Field(..., ge=0, description="Duración del segmento")

class SegmentoRutaCreate(SegmentoRutaBase):
    pasos: List[PasoRutaCreate] = Field(..., description="Pasos del segmento")

class SegmentoRutaRead(SegmentoRutaBase):
    id: int
    pasos: List[PasoRutaRead]

    class Config:
        from_attributes = True

class RutaUsuarioBase(BaseModel):
    distancia_total: float = Field(..., ge=0, description="Distancia total en kilómetros")
    duracion_total: float = Field(..., ge=0, description="Duración total en segundos")
    geometria: str = Field(..., description="Geometría de la ruta")
    fecha_inicio: datetime = Field(..., description="Fecha y hora de inicio")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha y hora de finalización")

class RutaUsuarioCreate(RutaUsuarioBase):
    tipo_ruta_usado: Optional[str] = None
    ubicacion_id: int
    transporte_texto: str
    segmentos: List[SegmentoRutaCreate]

class RutaUsuarioRead(RutaUsuarioBase):
    tipo_ruta_usado: Optional[str] = None
    id: int
    segmentos: List[SegmentoRutaRead]
