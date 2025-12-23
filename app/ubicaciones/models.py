from sqlalchemy import Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.usuarios.models import Usuario
from ..database.database import Base

class UbicacionUsuario(Base):
    __tablename__ = "ubicaciones_usuario"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    latitud = Column(Float, nullable=False)
    longitud = Column(Float, nullable=False)
    direccion_completa = Column(String(255), nullable=True)
    activo = Column(Boolean, default=True)
    
    # ✅ AGREGAR ESTAS RELACIONES AQUÍ
    usuario = relationship("Usuario", back_populates="ubicaciones")
    estados = relationship(
        "EstadoUbicacionUsuario",
        back_populates="ubicacion",
        cascade="all, delete-orphan"
    )

# ✅ MANTENER ESTA LÍNEA AL FINAL
Usuario.ubicaciones = relationship("UbicacionUsuario", back_populates="usuario", cascade="all, delete-orphan")