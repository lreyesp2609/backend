from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from .models import Reminder
from .schemas import ReminderCreate
from fastapi import HTTPException
import locale


try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    locale.setlocale(locale.LC_TIME, 'es_ES')

def create_reminder(db: Session, reminder_data: ReminderCreate, user_id: int):
    try:
        # Verificar si ya existe
        existing = db.query(Reminder).filter_by(
            user_id=user_id, 
            title=reminder_data.title
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400, 
                detail="Ya existe un recordatorio con ese título"
            )

        # Convertir lista de días a string separado por comas
        reminder_dict = reminder_data.dict()
        if reminder_dict.get('days'):
            reminder_dict['days'] = ','.join(reminder_dict['days'])

        new_reminder = Reminder(
            **reminder_dict,
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
        raise HTTPException(
            status_code=500, 
            detail=f"Error al crear recordatorio: {str(e)}"
        )
    
def list_reminders(db: Session, user_id: int):
    try:
        reminders = db.query(Reminder).filter_by(user_id=user_id).all()
        return reminders
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener recordatorios: {str(e)}")
