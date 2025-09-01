from enum import Enum
from sqlalchemy import Column, Enum as SqlEnum, Float, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.ubicaciones.models import UbicacionUsuario
from ...usuarios.models import Usuario
from ...database.database import Base

class EstadoUbicacion(str, Enum):
    EN_PROGRESO = "EN_PROGRESO"
    FINALIZADA = "FINALIZADA"
    CANCELADA = "CANCELADA"

class EstadoUbicacionUsuario(Base):
    __tablename__ = "estados_ubicacion_usuario"

    id = Column(Integer, primary_key=True, index=True)
    ubicacion_id = Column(Integer, ForeignKey("ubicaciones_usuario.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    estado = Column(SqlEnum(EstadoUbicacion), default=EstadoUbicacion.EN_PROGRESO, nullable=False)
    duracion_segundos = Column(Float, nullable=True)

    ubicacion = relationship("UbicacionUsuario", back_populates="estados")
    usuario = relationship("Usuario", back_populates="estados_ubicacion")

UbicacionUsuario.estados = relationship(
    "EstadoUbicacionUsuario",
    back_populates="ubicacion",
    cascade="all, delete-orphan"
)

Usuario.estados_ubicacion = relationship(
    "EstadoUbicacionUsuario",
    back_populates="usuario",
    cascade="all, delete-orphan"
)
