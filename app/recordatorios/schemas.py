from pydantic import BaseModel, validator
from typing import Optional, List
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
    
    days: Optional[List[str]] = None
    time: Optional[datetime_time] = None
    
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius: Optional[float] = None

    @validator('days')
    def validate_days(cls, v):
        if v is None:
            return v
        valid_days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        for day in v:
            if day not in valid_days and not cls._is_valid_date(day):
                raise ValueError(f"Día inválido: {day}")
        return v
    
    @staticmethod
    def _is_valid_date(date_str: str) -> bool:
        try:
            from datetime import datetime
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except:
            return False

class ReminderCreate(ReminderBase):
    pass

class ReminderOut(ReminderBase):
    id: int
    user_id: int

    @validator('days', pre=True)
    def convert_days_to_list(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return [day.strip() for day in v.split(',') if day.strip()]
        return v

    class Config:
        orm_mode = True