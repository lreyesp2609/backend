from sqlalchemy import Column, DateTime, Integer, String, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from ..database.database import Base

class Rol(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False, unique=True)
    descripcion = Column(String)

class DatosPersonales(Base):
    __tablename__ = "datos_personales"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)

class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(50), nullable=False, unique=True)
    contrasenia = Column(String(255), nullable=False)
    datos_personales_id = Column(Integer, ForeignKey("datos_personales.id"), nullable=False)
    rol_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    activo = Column(Boolean, default=True)

    datos_personales = relationship("DatosPersonales")
    rol = relationship("Rol")
    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")
    fcm_tokens = relationship("FCMToken", back_populates="usuario", cascade="all, delete-orphan")
    zonas_peligrosas = relationship("ZonaPeligrosaUsuario", back_populates="usuario", cascade="all, delete-orphan")
    
    # ✅ AGREGAR ESTA RELACIÓN
    estados_ubicacion = relationship(
        "EstadoUbicacionUsuario",
        back_populates="usuario",
        cascade="all, delete-orphan"
    )

class FCMToken(Base):
    __tablename__ = "fcm_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    dispositivo = Column(String(50), default="android")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    usuario = relationship("Usuario", back_populates="fcm_tokens")