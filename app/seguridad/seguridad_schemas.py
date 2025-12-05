from pydantic import BaseModel, Field, validator, root_validator
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
    id: int
    nombre: str
    nivel_peligro: int
    tipo: str | None
    notas: str | None
    activa: bool
    poligono: List[Dict[str, float]]  # Lista de puntos del círculo
    radio_metros: int | None
    fecha_creacion: str
    # 🔥 NUEVO: Campo calculado que SÍ se serializa
    centro: Optional[Dict[str, float]] = None
    
    @root_validator(pre=False)
    def calcular_centro(cls, values):
        """
        🔥 Calcula el centro del polígono automáticamente
        Se ejecuta DESPUÉS de cargar los datos
        """
        poligono = values.get('poligono')
        
        if poligono and len(poligono) > 0:
            lat_sum = sum(p['lat'] for p in poligono)
            lon_sum = sum(p['lon'] for p in poligono)
            n = len(poligono)
            
            values['centro'] = {
                'lat': lat_sum / n,
                'lon': lon_sum / n
            }
        else:
            values['centro'] = None
        
        return values
    
    class Config:
        orm_mode = True
        
        
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