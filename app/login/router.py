from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session
from ..database.database import get_db
from .schemas import LoginResponse
from .crud import login_usuario
from fastapi.responses import JSONResponse
from ..usuarios.security import *
from ..usuarios.models import Usuario
from datetime import datetime, timedelta
from fastapi import Query
from ..usuarios.sesiones.crud import crear_sesion, obtener_sesion

router = APIRouter(prefix="/login", tags=["Login"])

@router.post("/")
def login(
    correo: str = Form(...),
    contrasenia: str = Form(...),
    recordarme: bool = Form(False),
    dispositivo: str = Form(None),
    version_app: str = Form(None),
    ip: str = Form(None),
    db: Session = Depends(get_db)
):
    usuario = db.query(Usuario).filter(Usuario.usuario == correo, Usuario.activo==True).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")

    # Verificar contraseña
    from ..usuarios.security import verify_password
    if not verify_password(contrasenia, usuario.contrasenia):
        raise HTTPException(status_code=401, detail="INVALID_CREDENTIALS")

    # Determinar expiración
    # 🔹 En producción usar ACCESS_TOKEN_EXPIRE_PROD y ACCESS_TOKEN_EXPIRE_RECORDAR_PROD
    # 🔹 Para pruebas rápidas usar ACCESS_TOKEN_EXPIRE_TEST y ACCESS_TOKEN_EXPIRE_RECORDAR_TEST
    if recordarme:
        expiracion = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_RECORDAR_TEST)
        duracion_token = ACCESS_TOKEN_EXPIRE_RECORDAR_TEST
    else:
        expiracion = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_TEST)
        duracion_token = ACCESS_TOKEN_EXPIRE_TEST

    # Crear token
    token = create_access_token({"sub": correo, "id_usuario": usuario.id, "rol": usuario.rol.nombre}, duracion_token)

    # Guardar sesión
    crear_sesion(db, usuario.id, token, expiracion, dispositivo, version_app, ip)

    return JSONResponse({
        "access_token": token,
        "token_type": "bearer"
    })

@router.get("/decodificar")
def decodificar(
    payload: dict = Depends(decodificar_token),
    db: Session = Depends(get_db)
):
    correo = payload.get("sub")

    usuario = (
        db.query(Usuario)
        .filter(Usuario.usuario == correo, Usuario.activo == True)
        .first()
    )

    if not usuario:
        raise HTTPException(status_code=404, detail="USUARIO_NO_ENCONTRADO")
    
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "id": usuario.id,
            "nombre": usuario.datos_personales.nombre,
            "apellido": usuario.datos_personales.apellido,
            "activo": usuario.activo,
            "id_rol": usuario.rol.id,
            "rol": usuario.rol.nombre,
        }
    )