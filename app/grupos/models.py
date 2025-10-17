from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from ..database.database import Base

class Grupo(Base):
    __tablename__ = "grupos"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String)
    codigo_invitacion = Column(String(10), unique=True, index=True)
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)

    creado_por = relationship("Usuario", backref="grupos_creados")
    miembros = relationship("MiembroGrupo", back_populates="grupo", cascade="all, delete-orphan")
    
    is_deleted = Column(Boolean, default=False)  # Para "eliminación lógica"


class MiembroGrupo(Base):
    __tablename__ = "miembros_grupo"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    grupo_id = Column(Integer, ForeignKey("grupos.id"), nullable=False)
    rol = Column(String(50), default="miembro")  # valores: "admin", "miembro", "moderador", etc.
    activo = Column(Boolean, default=True)
    fecha_union = Column(DateTime, default=datetime.utcnow)

    usuario = relationship("Usuario", backref="grupos_miembro")
    grupo = relationship("Grupo", back_populates="miembros")

class InvitacionGrupo(Base):
    __tablename__ = "invitaciones_grupo"
    id = Column(Integer, primary_key=True, index=True)
    grupo_id = Column(Integer, ForeignKey("grupos.id"), nullable=False)
    codigo = Column(String(12), unique=True, nullable=False)
    creado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    usado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    fecha_uso = Column(DateTime, nullable=True)
    activo = Column(Boolean, default=True)

    grupo = relationship("Grupo")
    creado_por = relationship("Usuario", foreign_keys=[creado_por_id])
    usado_por = relationship("Usuario", foreign_keys=[usado_por_id])