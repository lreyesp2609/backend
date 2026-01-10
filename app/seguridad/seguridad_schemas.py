from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict
from datetime import datetime

class PuntoGeografico(BaseModel):
    """Punto geográfico simple"""
    lat: float = Field(..., description="Latitud")
    lon: float = Field(..., description="Longitud")

class ZonaPeligrosaCreate(BaseModel):
    """Crear nueva zona peligrosa"""
    nombre: str = Field(..., max_length=100, description="Nombre descriptivo de la zona")
    lat: float = Field(..., description="Latitud del centro de la zona")
    lon: float = Field(..., description="Longitud del centro de la zona")
    radio_metros: int = Field(default=200, ge=50, le=1000, description="Radio en metros (50-1000)")
    nivel_peligro: int = Field(default=3, ge=1, le=5, description="Nivel de peligro (1-5)")
    tipo: Optional[str] = Field(None, max_length=50, description="Tipo: asalto, trafico_pesado, poca_iluminacion, otro")
    notas: Optional[str] = Field(None, max_length=500, description="Notas personales")

class ZonaPeligrosaUpdate(BaseModel):
    """Actualizar zona peligrosa existente"""
    nombre: Optional[str] = Field(None, max_length=100)
    nivel_peligro: Optional[int] = Field(None, ge=1, le=5)
    tipo: Optional[str] = Field(None, max_length=50)
    notas: Optional[str] = Field(None, max_length=500)
    activa: Optional[bool] = None

class ZonaPeligrosaResponse(BaseModel):
    """Respuesta de zona peligrosa"""
    id: int
    usuario_id: int
    nombre: str
    poligono: List[Dict[str, float]]
    nivel_peligro: int
    tipo: Optional[str]
    activa: bool
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime]
    notas: Optional[str]
    radio_metros: Optional[int]
    
    class Config:
        from_attributes = True
        
class RutaParaValidar(BaseModel):
    """Ruta que será validada"""
    tipo: str = Field(..., description="fastest, shortest, recommended")
    geometry: str = Field(..., description="Polyline encoded de la ruta")
    distance: Optional[float] = Field(None, description="Distancia en metros")
    duration: Optional[float] = Field(None, description="Duración en segundos")

class ZonaDetectada(BaseModel):
    """Zona peligrosa detectada en una ruta"""
    zona_id: int
    nombre: str
    nivel_peligro: int
    tipo: Optional[str]
    porcentaje_ruta: float = Field(..., description="Porcentaje de la ruta que pasa por esta zona")

class RutaValidada(BaseModel):
    """Resultado de validación de una ruta"""
    tipo: str
    es_segura: bool
    nivel_riesgo: int = Field(..., ge=0, le=5, description="0=Segura, 5=Muy peligrosa")
    zonas_detectadas: List[ZonaDetectada]
    mensaje: Optional[str] = None
    distancia: Optional[float] = None
    duracion: Optional[float] = None

class ValidarRutasRequest(BaseModel):
    """Request para validar múltiples rutas"""
    rutas: List[RutaParaValidar] = Field(..., min_items=1, max_items=10)
    ubicacion_id: int

    @validator('rutas')
    def validar_tipos_unicos(cls, rutas):
        tipos = [r.tipo for r in rutas]
        if len(tipos) != len(set(tipos)):
            raise ValueError("No puede haber rutas con el mismo tipo")
        return rutas

class ValidarRutasResponse(BaseModel):
    """Response con rutas validadas"""
    rutas_validadas: List[RutaValidada]
    tipo_ml_recomendado: str
    todas_seguras: bool
    mejor_ruta_segura: Optional[str] = None
    advertencia_general: Optional[str] = None
    total_zonas_usuario: int = Field(..., description="Total de zonas peligrosas activas del usuario")

# ==========================================
# SCHEMAS PARA ESTADÍSTICAS
# ==========================================

class EstadisticasSeguridad(BaseModel):
    """Estadísticas de seguridad del usuario"""
    total_zonas: int
    zonas_por_tipo: Dict[str, int]
    zonas_por_nivel: Dict[int, int]
    zonas_activas: int
    zonas_inactivas: int
    rutas_validadas_historico: int
    rutas_con_advertencias: int


class VerificarUbicacionRequest(BaseModel):
    """Request para verificar si una ubicación está en zona peligrosa"""
    lat: float
    lon: float

class ZonaPeligrosaDetectada(BaseModel):
    """Zona peligrosa detectada en la ubicación actual"""
    zona_id: int
    nombre: str
    nivel_peligro: int
    tipo: Optional[str]
    distancia_al_centro: float  # en metros
    dentro_de_zona: bool

class VerificarUbicacionResponse(BaseModel):
    """Respuesta de verificación de ubicación"""
    hay_peligro: bool
    zonas_detectadas: List[ZonaPeligrosaDetectada]
    mensaje_alerta: Optional[str] = None