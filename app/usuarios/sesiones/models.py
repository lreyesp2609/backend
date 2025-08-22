from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from ...database.database import Base
from datetime import datetime

class SesionAppUsuario(Base):
    __tablename__ = "sesiones_app_usuario"
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    refresh_token = Column(String(255), nullable=False, unique=True)
    expiracion = Column(DateTime, nullable=False)
    dispositivo = Column(String(100))
    version_app = Column(String(20))
    ip = Column(String(50))
    fecha_inicio = Column(DateTime, default=datetime.utcnow)
    ultima_actividad = Column(DateTime, default=datetime.utcnow)
    activo = Column(Boolean, default=True)

    usuario = relationship("Usuario")
