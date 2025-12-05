from sqlalchemy import Column, Float, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship
from ....database.database import Base

class Transporte(Base):
    __tablename__ = "transportes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)
    descripcion = Column(String, nullable=True)

class RutaUsuario(Base):
    __tablename__ = "rutas_usuario"

    id = Column(Integer, primary_key=True, index=True)
    transporte_id = Column(Integer, ForeignKey("transportes.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    distancia_total = Column(Float, nullable=False)
    duracion_total = Column(Float, nullable=False)
    geometria = Column(String, nullable=False)
    fecha_inicio = Column(DateTime, nullable=False)
    fecha_fin = Column(DateTime, nullable=True)
    tipo_ruta_usado = Column(String(20), nullable=True)
    
    estado_ruta_id = Column(Integer, ForeignKey("estados_ubicacion.id"), nullable=False, default=1)  # Estado de la RUTA
    estado_usuario_id = Column(Integer, ForeignKey("estados_ubicacion_usuario.id"), nullable=True)  # Referencia al estado del USUARIO en esa UBICACIÓN

    transporte = relationship("Transporte")
    estado_ruta = relationship("EstadoUbicacion", foreign_keys=[estado_ruta_id])
    estado_usuario = relationship("EstadoUbicacionUsuario")
    segmentos = relationship("SegmentoRuta", back_populates="ruta", cascade="all, delete-orphan")

class SegmentoRuta(Base):
    __tablename__ = "segmentos_ruta"

    id = Column(Integer, primary_key=True, index=True)
    ruta_id = Column(Integer, ForeignKey("rutas_usuario.id"))
    distancia = Column(Float, nullable=False)
    duracion = Column(Float, nullable=False)

    ruta = relationship("RutaUsuario", back_populates="segmentos")
    pasos = relationship("PasoRuta", back_populates="segmento", cascade="all, delete-orphan")

class PasoRuta(Base):
    __tablename__ = "pasos_ruta"

    id = Column(Integer, primary_key=True, index=True)
    segmento_id = Column(Integer, ForeignKey("segmentos_ruta.id"))
    instruccion = Column(String, nullable=False)
    distancia = Column(Float, nullable=False)
    duracion = Column(Float, nullable=False)
    tipo = Column(Integer, nullable=True)

    segmento = relationship("SegmentoRuta", back_populates="pasos")