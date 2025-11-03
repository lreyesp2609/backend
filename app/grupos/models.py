from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, UniqueConstraint
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

class Mensaje(Base):
    __tablename__ = "mensajes"
    id = Column(Integer, primary_key=True, index=True)
    remitente_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    grupo_id = Column(Integer, ForeignKey("grupos.id"), nullable=False)
    contenido = Column(Text, nullable=False)
    tipo = Column(String(20), default="texto")  # texto, imagen, system, etc.
    fecha_creacion = Column(DateTime, default=datetime.utcnow)

    remitente = relationship("Usuario")
    grupo = relationship("Grupo")
    lecturas = relationship("LecturaMensaje", back_populates="mensaje", cascade="all, delete-orphan")

class LecturaMensaje(Base):
    __tablename__ = "lecturas_mensajes"
    
    id = Column(Integer, primary_key=True, index=True)
    mensaje_id = Column(Integer, ForeignKey("mensajes.id", ondelete="CASCADE"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    leido_at = Column(DateTime, default=datetime.utcnow)
    
    # Evitar duplicados: un usuario solo puede leer un mensaje una vez
    __table_args__ = (
        UniqueConstraint('mensaje_id', 'usuario_id', name='uix_mensaje_usuario'),
    )
    
    # Relaciones
    mensaje = relationship("Mensaje", back_populates="lecturas")
    usuario = relationship("Usuario")