from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from .models import Reminder
from .schemas import ReminderCreate
from fastapi import HTTPException
import locale

try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES')
    except locale.Error:
        pass

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

        reminder_dict = reminder_data.dict()
        
        print(f"🔍 DEBUG CREATE REMINDER:")
        print(f"   days tipo: {type(reminder_dict.get('days'))}")
        print(f"   days valor: {reminder_dict.get('days')}")

        new_reminder = Reminder(
            **reminder_dict,
            user_id=user_id
        )

        db.add(new_reminder)
        db.commit()
        db.refresh(new_reminder)
        
        print(f"✅ Recordatorio guardado en BD:")
        print(f"   ID: {new_reminder.id}")
        print(f"   days en BD: {new_reminder.days}")
        
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
        reminders = db.query(Reminder).filter_by(
            user_id=user_id,
            is_deleted=False
        ).all()
        return reminders
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener recordatorios: {str(e)}")
    
def update_reminder(db: Session, reminder_id: int, user_id: int, reminder_data: dict):
    try:
        reminder = db.query(Reminder).filter_by(
            id=reminder_id, 
            user_id=user_id, 
            is_deleted=False
        ).first()
        
        if not reminder:
            raise HTTPException(
                status_code=404, 
                detail="Recordatorio no encontrado"
            )
        
        # Actualizar solo los campos proporcionados
        for key, value in reminder_data.items():
            if value is not None:
                setattr(reminder, key, value)
        
        db.commit()
        db.refresh(reminder)
        return reminder
        
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Error al actualizar recordatorio: {str(e)}"
        )