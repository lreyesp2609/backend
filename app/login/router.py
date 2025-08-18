from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database.database import get_db
from .schemas import LoginRequest, LoginResponse
from .crud import login_usuario
from fastapi import Form

router = APIRouter(prefix="/login", tags=["Login"])

@router.post("/", response_model=LoginResponse)
def login(
    correo: str = Form(...),
    contrasenia: str = Form(...),
    db: Session = Depends(get_db)
):
    token = login_usuario(db, correo, contrasenia)
    if not token:
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos")
    return {"access_token": token, "token_type": "bearer"}