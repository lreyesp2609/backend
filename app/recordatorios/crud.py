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

        # ✅ CORRECCIÓN: No convertir days, ya viene como string desde el validator
        reminder_dict = reminder_data.dict()
        
        # ❌ ELIMINAR ESTAS LÍNEAS:
        # if reminder_dict.get('days'):
        #     reminder_dict['days'] = ','.join(reminder_dict['days'])
        
        # ✅ El campo 'days' ya viene como string "Lunes,Martes,..."
        # gracias al validator normalize_days() en schemas.py
        
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
