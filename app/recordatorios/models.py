from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, Date, Time
from sqlalchemy.orm import relationship
from enum import Enum as PyEnum
from ..database.database import Base

class ReminderType(PyEnum):
    LOCATION = "location"
    DATETIME = "datetime"
    BOTH = "both"


class TriggerType(PyEnum):
    ENTER = "enter"
    EXIT = "exit"
    BOTH = "both"


class SoundType(PyEnum):
    DEFAULT = "default"
    GENTLE = "gentle"
    ALERT = "alert"
    CHIME = "chime"


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    description = Column(String, nullable=True)

    # Cambiado a String para producción
    reminder_type = Column(String(50), nullable=False)
    trigger_type = Column(String(50), nullable=False)
    sound_type = Column(String(50), nullable=True)

    vibration = Column(Boolean, default=False)
    sound = Column(Boolean, default=False)

    # Campos de fecha y hora
    days = Column(String, nullable=True)
    time = Column(Time, nullable=True)

    # Campos de ubicación
    location = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    radius = Column(Float, nullable=True)

    # Relación con usuario
    user_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    user = relationship("Usuario", back_populates="reminders")

    # NUEVOS CAMPOS
    is_active = Column(Boolean, default=True)  # Para habilitar/deshabilitar
    is_deleted = Column(Boolean, default=False)  # Para "eliminación lógica"