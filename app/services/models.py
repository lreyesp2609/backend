from sqlalchemy import Boolean, Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database.database import Base
from ..ubicaciones.models import UbicacionUsuario

class BanditSimple(Base):
    __tablename__ = "bandit"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    ubicacion_id = Column(Integer, ForeignKey("ubicaciones_usuario.id"), nullable=False)  # 👈 se enlaza a la tabla correcta
    tipo_ruta = Column(String(20), nullable=False)  # 'fastest' o 'shortest'
    total_usos = Column(Integer, default=0)
    total_rewards = Column(Integer, default=0)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow)

    ubicacion = relationship("UbicacionUsuario")


class HistorialRutas(Base):
    __tablename__ = "historial_rutas"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    ubicacion_id = Column(Integer, ForeignKey("ubicaciones_usuario.id"), nullable=False)
    tipo_seleccionado = Column(String(20), nullable=False)
    distancia = Column(Float, nullable=True)
    duracion = Column(Float, nullable=True)
    fecha_inicio = Column(DateTime, nullable=False)
    fecha_fin = Column(DateTime, nullable=True)

class ComportamientoRuta(Base):
    __tablename__ = "comportamiento_rutas"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    ubicacion_id = Column(Integer, ForeignKey("ubicaciones_usuario.id"), nullable=False)
    ruta_id = Column(Integer, ForeignKey("rutas_usuario.id"), nullable=False)
    
    # DATOS CLAVE para detectar desobediencia
    ruta_recomendada_geometria = Column(String, nullable=False)  # La que le sugeriste
    ruta_real_geometria = Column(String, nullable=True)          # La que realmente siguió
    
    siguio_recomendacion = Column(Boolean, default=True)         # ¿Siguió tu ruta?
    porcentaje_similitud = Column(Float, default=100.0)         # % de similitud (0-100)
    
    # CONTADORES para el patrón
    veces_desobedecido = Column(Integer, default=0)              # Consecutivas que no siguió
    alerta_mostrada = Column(Boolean, default=False)            # ¿Ya se le alertó?
    
    fecha_creacion = Column(DateTime, default=datetime.utcnow)


# ══════════════════════════════════════════════════════════
# MODELOS DE BASE DE DATOS
# ══════════════════════════════════════════════════════════

from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database.database import Base

class PuntoGPSRaw(Base):
    """
    📍 Puntos GPS crudos grabados en segundo plano
    Se guardan automáticamente sin que el usuario haga nada
    """
    __tablename__ = "puntos_gps_raw"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    precision_metros = Column(Float, nullable=True)
    velocidad = Column(Float, nullable=True)
    
    __table_args__ = (
        {'mysql_engine': 'InnoDB'}
    )


class ViajeDetectado(Base):
    """
    🚶 Viajes detectados automáticamente
    Sistema identifica: "Usuario fue de A → B"
    """
    __tablename__ = "viajes_detectados"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ubicacion_origen_id = Column(Integer, ForeignKey("ubicaciones_usuario.id"), nullable=True)
    ubicacion_destino_id = Column(Integer, ForeignKey("ubicaciones_usuario.id"), nullable=True, index=True)
    lat_inicio = Column(Float, nullable=False)
    lon_inicio = Column(Float, nullable=False)
    lat_fin = Column(Float, nullable=False)
    lon_fin = Column(Float, nullable=False)
    fecha_inicio = Column(DateTime, nullable=False, index=True)
    fecha_fin = Column(DateTime, nullable=False)
    geometria = Column(Text, nullable=False)
    distancia_metros = Column(Float, nullable=False)
    duracion_segundos = Column(Integer, nullable=False)
    hash_trayectoria = Column(String(64), nullable=True, index=True)


class PatronPredictibilidad(Base):
    """
    ⚠️ Patrones de predictibilidad detectados
    """
    __tablename__ = "patrones_predictibilidad"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    ubicacion_destino_id = Column(Integer, ForeignKey("ubicaciones_usuario.id"), nullable=False)
    total_viajes = Column(Integer, nullable=False)
    viajes_ruta_similar = Column(Integer, nullable=False)
    predictibilidad = Column(Float, nullable=False)
    es_predecible = Column(Boolean, default=False)
    notificacion_enviada = Column(Boolean, default=False)
    fecha_ultima_notificacion = Column(DateTime, nullable=True)
    fecha_analisis = Column(DateTime, default=datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
