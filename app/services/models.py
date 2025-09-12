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