from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session
from ..database.database import get_db
from ..usuarios.crud import crear_usuario
from ..usuarios.schemas import UsuarioCreate
from fastapi.responses import JSONResponse
from ..usuarios.security import get_current_user
from ..usuarios.models import DatosPersonales
router = APIRouter(prefix="/usuarios", tags=["Usuarios"])

@router.post("/registrar")
def registrar_usuario(
    nombre: str = Form(...),
    apellido: str = Form(...),
    correo: str = Form(...),
    contrasenia: str = Form(...),
    db: Session = Depends(get_db)
):
    usuario_data = UsuarioCreate(
        nombre=nombre,
        apellido=apellido,
        correo=correo,
        contrasenia=contrasenia
    )

    nuevo_usuario = crear_usuario(db, usuario_data)
    if not nuevo_usuario:
        raise HTTPException(status_code=400, detail="USER_ALREADY_EXISTS")
    
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "id": nuevo_usuario.id,
            "correo": nuevo_usuario.usuario,
            "activo": nuevo_usuario.activo
        }
    )

@router.put("/perfil")
def actualizar_perfil(
    nombre: str = Form(...),
    apellido: str = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    datos = db.query(DatosPersonales).filter(
        DatosPersonales.id == current_user.datos_personales_id
    ).first()

    if not datos:
        raise HTTPException(status_code=404, detail="Datos de perfil no encontrados")

    datos.nombre = nombre.strip()
    datos.apellido = apellido.strip()
    db.commit()
    db.refresh(datos)

    return {
        "id": current_user.id,
        "nombre": datos.nombre,
        "apellido": datos.apellido,
        "correo": current_user.usuario
    }