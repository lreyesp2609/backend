from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database.database import Base

class ZonaPeligrosaUsuario(Base):
    """
    🔒 ZONAS PELIGROSAS PERSONALIZADAS POR USUARIO
    Cada usuario define sus propias zonas inseguras de forma 100% privada
    """
    __tablename__ = "zonas_peligrosas_usuario"
    
    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)

    
    # Información de la zona
    nombre = Column(String(100), nullable=False)  # "Callejón cerca de casa", "Zona oscura", etc.
    poligono = Column(JSON, nullable=False)  # Lista de puntos: [{"lat": -1.028, "lon": -79.461}, ...]
    
    # Nivel de peligro (1-5)
    nivel_peligro = Column(Integer, default=3, nullable=False)  # 1=Bajo, 3=Medio, 5=Muy Alto
    
    # Tipo de peligro (opcional)
    tipo = Column(String(50), nullable=True)  # "asalto", "trafico_pesado", "poca_iluminacion", "otro"
    
    # Estado
    activa = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    fecha_creacion = Column(DateTime, default=datetime.utcnow, nullable=False)
    fecha_actualizacion = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Notas personales del usuario
    notas = Column(String(500), nullable=True)  # "Aquí me asaltaron", "Muy oscuro de noche", etc.
    
    # Radio en metros (para zonas circulares)
    radio_metros = Column(Integer, nullable=True)  # Solo si es zona circular
    
    # Relación con Usuario
    usuario = relationship("Usuario", back_populates="zonas_peligrosas")
    
    def __repr__(self):
        return f"<ZonaPeligrosa(id={self.id}, usuario={self.usuario_id}, nombre='{self.nombre}', nivel={self.nivel_peligro})>"

