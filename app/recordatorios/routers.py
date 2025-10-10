from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .schemas import ReminderCreate, ReminderOut
from .crud import *
from ..database.database import get_db
from ..usuarios.security import get_current_user

router = APIRouter(prefix="/reminders", tags=["Reminders"])

@router.post("/crear", response_model=ReminderOut)
def create_new_reminder(
    reminder: ReminderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        new_reminder = create_reminder(db, reminder, current_user.id)
        return new_reminder
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creating reminder: {str(e)}")

@router.get("/listar", response_model=list[ReminderOut])
def get_user_reminders(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return list_reminders(db, current_user.id)