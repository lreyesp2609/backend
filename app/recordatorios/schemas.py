from pydantic import BaseModel, Field
from typing import Optional
import datetime
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
    date: Optional[datetime.date] = None
    time: Optional[datetime.time] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius: Optional[float] = None


class ReminderCreate(ReminderBase):
    pass

class ReminderOut(ReminderBase):
    id: int
    user_id: int

    class Config:
        orm_mode = True