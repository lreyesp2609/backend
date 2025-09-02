from sqlalchemy import Column, Float, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship
from ....database.database import Base

from sqlalchemy import Enum

class Transporte(Base):
    __tablename__ = "transportes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)
    descripcion = Column(String, nullable=True)

class RutaUsuario(Base):
    __tablename__ = "rutas_usuario"

    id = Column(Integer, primary_key=True, index=True)
    estado_id = Column(Integer, ForeignKey("estados_ubicacion_usuario.id"))
    transporte_id = Column(Integer, ForeignKey("transportes.id"), nullable=False)
    distancia_total = Column(Float, nullable=False)
    duracion_total = Column(Float, nullable=False)
    geometria = Column(String, nullable=False)
    fecha_inicio = Column(DateTime, nullable=False)
    fecha_fin = Column(DateTime, nullable=True)

    transporte = relationship("Transporte")
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