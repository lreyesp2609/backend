from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from .models import Reminder
from .schemas import ReminderCreate
from fastapi import HTTPException

def create_reminder(db: Session, reminder_data: ReminderCreate, user_id: int):
    try:
        existing = db.query(Reminder).filter_by(user_id=user_id, title=reminder_data.title).first()
        if existing:
            raise HTTPException(status_code=400, detail="Ya existe un recordatorio con ese título para este usuario")

        # 🔹 Crear recordatorio
        new_reminder = Reminder(
            **reminder_data.dict(),
            user_id=user_id
        )
        db.add(new_reminder)
        db.commit()
        db.refresh(new_reminder)
        return new_reminder

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear recordatorio: {str(e)}")

def list_reminders(db: Session, user_id: int):
    try:
        reminders = db.query(Reminder).filter_by(user_id=user_id).all()
        return reminders
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener recordatorios: {str(e)}")
