from pydantic import BaseModel, field_validator
from typing import Optional, List, Union
from datetime import time as datetime_time
from enum import Enum

class ReminderType(str, Enum):
    LOCATION = "location"
    DATETIME = "datetime"
    BOTH = "both"

class TriggerType(str, Enum):
    ENTER = "enter"
    EXIT = "exit"
    BOTH = "both"

class SoundType(str, Enum):
    DEFAULT = "default"
    GENTLE = "gentle"
    ALERT = "alert"
    CHIME = "chime"

class ReminderBase(BaseModel):
    title: str
    description: Optional[str] = None
    reminder_type: ReminderType
    trigger_type: TriggerType
    vibration: bool = False
    sound: bool = False
    sound_type: Optional[SoundType] = None
    
    # ✅ Aceptar string o lista en la entrada
    days: Optional[Union[str, List[str]]] = None
    time: Optional[datetime_time] = None
    
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius: Optional[float] = None

    @field_validator('days')
    @classmethod
    def normalize_days(cls, v):
        """Convertir days a string si viene como lista"""
        if v is None:
            return None
        if isinstance(v, list):
            # Unir la lista con comas
            return ','.join(v)
        if isinstance(v, str):
            # Ya es string, devolverlo tal cual
            return v
        raise ValueError("days debe ser una lista o un string")

class ReminderCreate(ReminderBase):
    pass

class ReminderOut(ReminderBase):
    id: int
    user_id: int
    is_active: bool = True
    is_deleted: bool = False

    @field_validator('days', mode='before')
    @classmethod
    def convert_days_to_string(cls, v):
        """
        ✅ CORRECCIÓN: Mantener days como STRING en la respuesta
        El frontend se encarga de convertirlo a lista con su DaysTypeAdapter
        """
        if v is None:
            return None
        
        # Si ya es string, devolverlo tal cual
        if isinstance(v, str):
            return v
        
        # Si por alguna razón es una lista, convertirla a string
        if isinstance(v, list):
            return ','.join(v)
        
        return v

    class Config:
        from_attributes = True