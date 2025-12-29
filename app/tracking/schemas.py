
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime


# ══════════════════════════════════════════════════════════
# PUNTO GPS
# ══════════════════════════════════════════════════════════

class PuntoGPSRequest(BaseModel):
    """Request para guardar un punto GPS"""
    lat: float = Field(..., description="Latitud")
    lon: float = Field(..., description="Longitud")
    precision: Optional[float] = Field(None, description="Precisión en metros")
    velocidad: Optional[float] = Field(None, description="Velocidad en m/s")
    
    @validator('lat')
    def validar_latitud(cls, v):
        if not -90 <= v <= 90:
            raise ValueError('Latitud debe estar entre -90 y 90')
        return v
    
    @validator('lon')
    def validar_longitud(cls, v):
        if not -180 <= v <= 180:
            raise ValueError('Longitud debe estar entre -180 y 180')
        return v


class PuntoGPSBatchItem(BaseModel):
    """Item de un lote de puntos GPS"""
    lat: float
    lon: float
    timestamp: str  # ISO format
    precision: Optional[float] = None
    velocidad: Optional[float] = None


class LotePuntosGPSRequest(BaseModel):
    """Request para guardar múltiples puntos GPS"""
    puntos: List[PuntoGPSBatchItem] = Field(..., min_items=1, max_items=100)


# ══════════════════════════════════════════════════════════
# VIAJE DETECTADO
# ══════════════════════════════════════════════════════════

class ViajeDetectadoResponse(BaseModel):
    """Response de un viaje detectado"""
    id: int
    usuario_id: int
    ubicacion_origen_id: Optional[int]
    ubicacion_destino_id: Optional[int]
    lat_inicio: float
    lon_inicio: float
    lat_fin: float
    lon_fin: float
    fecha_inicio: datetime
    fecha_fin: datetime
    distancia_metros: float
    duracion_segundos: int
    
    class Config:
        from_attributes = True


class ViajeDetalladoResponse(ViajeDetectadoResponse):
    """Response detallado con geometría"""
    geometria: str
    hash_trayectoria: Optional[str]
    
    # Información adicional calculada
    distancia_km: float
    duracion_minutos: int
    velocidad_promedio_kmh: float
    
    @validator('distancia_km', always=True, pre=True)
    def calcular_distancia_km(cls, v, values):
        return round(values.get('distancia_metros', 0) / 1000, 2)
    
    @validator('duracion_minutos', always=True, pre=True)
    def calcular_duracion_minutos(cls, v, values):
        return round(values.get('duracion_segundos', 0) / 60)
    
    @validator('velocidad_promedio_kmh', always=True, pre=True)
    def calcular_velocidad(cls, v, values):
        distancia_m = values.get('distancia_metros', 0)
        duracion_s = values.get('duracion_segundos', 1)
        if duracion_s == 0:
            return 0.0
        velocidad_ms = distancia_m / duracion_s
        return round(velocidad_ms * 3.6, 2)  # Convertir m/s a km/h


# ══════════════════════════════════════════════════════════
# PATRÓN DE PREDICTIBILIDAD
# ══════════════════════════════════════════════════════════

class PatronPredictibilidadResponse(BaseModel):
    """Response de un patrón de predictibilidad"""
    id: int
    usuario_id: int
    ubicacion_destino_id: int
    total_viajes: int
    viajes_ruta_similar: int
    predictibilidad: float
    es_predecible: bool
    notificacion_enviada: bool
    fecha_ultima_notificacion: Optional[datetime]
    fecha_analisis: datetime
    fecha_actualizacion: datetime
    
    # Campos calculados
    predictibilidad_porcentaje: int
    nivel_riesgo: str  # "BAJO", "MEDIO", "ALTO"
    
    @validator('predictibilidad_porcentaje', always=True, pre=True)
    def calcular_porcentaje(cls, v, values):
        return round(values.get('predictibilidad', 0) * 100)
    
    @validator('nivel_riesgo', always=True, pre=True)
    def calcular_nivel_riesgo(cls, v, values):
        pred = values.get('predictibilidad', 0)
        if pred >= 0.80:
            return "ALTO"
        elif pred >= 0.60:
            return "MEDIO"
        else:
            return "BAJO"
    
    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════
# ESTADÍSTICAS
# ══════════════════════════════════════════════════════════

class EstadisticasTrackingResponse(BaseModel):
    """Estadísticas generales del tracking pasivo"""
    total_viajes: int
    viajes_este_mes: int
    distancia_total_km: float
    total_patrones: int
    patrones_predecibles: int
    puntos_gps_este_mes: int
    
    # Campos calculados
    promedio_viajes_dia: float = 0.0
    porcentaje_predictibilidad: float = 0.0
    
    @validator('promedio_viajes_dia', always=True)
    def calcular_promedio_dia(cls, v, values):
        viajes_mes = values.get('viajes_este_mes', 0)
        from datetime import datetime
        dias_mes = datetime.utcnow().day
        if dias_mes == 0:
            return 0.0
        return round(viajes_mes / dias_mes, 1)
    
    @validator('porcentaje_predictibilidad', always=True)
    def calcular_porcentaje_pred(cls, v, values):
        total = values.get('total_patrones', 0)
        predecibles = values.get('patrones_predecibles', 0)
        if total == 0:
            return 0.0
        return round((predecibles / total) * 100, 1)


# ══════════════════════════════════════════════════════════
# ANÁLISIS ESPECÍFICO
# ══════════════════════════════════════════════════════════

class AnalisisRutaRequest(BaseModel):
    """Request para analizar una ruta específica"""
    ubicacion_destino_id: int
    forzar_analisis: bool = False  # Forzar incluso si hay <5 viajes


class AnalisisRutaResponse(BaseModel):
    """Response del análisis de una ruta"""
    ubicacion_destino_id: int
    total_viajes: int
    suficientes_datos: bool
    predictibilidad: Optional[float] = None
    es_predecible: Optional[bool] = None
    mensaje: str
    viajes_por_ruta: Optional[List[dict]] = None  # Agrupación de viajes similares