from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .schemas import ReminderCreate, ReminderOut, ReminderUpdate
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

@router.patch("/{reminder_id}/toggle")
def toggle_reminder(reminder_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    reminder = db.query(Reminder).filter_by(id=reminder_id, user_id=current_user.id, is_deleted=False).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado")
    
    reminder.is_active = not reminder.is_active
    db.commit()
    db.refresh(reminder)
    return reminder

@router.delete("/{reminder_id}/delete")
def delete_reminder(reminder_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    reminder = db.query(Reminder).filter_by(id=reminder_id, user_id=current_user.id, is_deleted=False).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado")
    
    reminder.is_deleted = True
    db.commit()
    return {"detail": "Recordatorio eliminado"}

@router.put("/{reminder_id}/editar", response_model=ReminderOut)
def edit_reminder(
    reminder_id: int,
    reminder_update: ReminderUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Convertir a dict y filtrar valores None
    update_data = reminder_update.dict(exclude_unset=True)
    
    # 🔵 LOGS AGREGADOS
    print(f"🔵 REQUEST BODY RECIBIDO: {update_data}")
    print(f"🔵 reminder_type = {update_data.get('reminder_type')}")
    print(f"🔵 Editando reminder_id = {reminder_id}")
    
    updated_reminder = update_reminder(db, reminder_id, current_user.id, update_data)
    return updated_reminder