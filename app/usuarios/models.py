from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
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