from sqlalchemy import Column, Float, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import relationship
from ...database.database import Base

class EstadoUbicacion(Base):
    __tablename__ = "estados_ubicacion"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), unique=True, nullable=False)  # EN_PROGRESO, FINALIZADA, etc.
    descripcion = Column(String(200), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    orden = Column(Integer, nullable=True)  # Para ordenar en UI
    
    # Relación inversa
    estados_usuario = relationship("EstadoUbicacionUsuario", back_populates="estado_ubicacion")

class EstadoUbicacionUsuario(Base):
    __tablename__ = "estados_ubicacion_usuario"

    id = Column(Integer, primary_key=True, index=True)
    ubicacion_id = Column(Integer, ForeignKey("ubicaciones_usuario.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    estado_ubicacion_id = Column(Integer, ForeignKey("estados_ubicacion.id"), nullable=False)
    duracion_segundos = Column(Float, nullable=True)

    # Relaciones
    ubicacion = relationship("UbicacionUsuario", back_populates="estados")
    usuario = relationship("Usuario", back_populates="estados_ubicacion")
    estado_ubicacion = relationship("EstadoUbicacion", back_populates="estados_usuario")