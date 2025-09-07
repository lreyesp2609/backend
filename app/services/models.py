from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
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
