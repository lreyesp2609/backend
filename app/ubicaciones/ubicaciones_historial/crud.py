from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.ubicaciones.ubicaciones_historial import models, schemas
from app.usuarios.models import Usuario

def crear_estado_ubicacion(db: Session, estado_data: schemas.EstadoUbicacionUsuarioCreate, usuario: Usuario):
    ubicacion = db.query(models.UbicacionUsuario).filter(models.UbicacionUsuario.id == estado_data.ubicacion_id).first()
    if not ubicacion:
        raise HTTPException(status_code=404, detail="Ubicación no encontrada")

    nuevo_estado = models.EstadoUbicacionUsuario(
        ubicacion_id=estado_data.ubicacion_id,
        usuario_id=usuario.id,
        estado=estado_data.estado,
        duracion_segundos=estado_data.duracion_segundos
    )
    db.add(nuevo_estado)
    db.commit()
    db.refresh(nuevo_estado)
    return nuevo_estado

def listar_estados_usuario(db: Session, usuario_id: int):
    return db.query(models.EstadoUbicacionUsuario).filter(models.EstadoUbicacionUsuario.usuario_id == usuario_id).all()

def listar_todos_estados(db: Session):
    """Obtener todos los estados de ubicación"""
    return db.query(models.EstadoUbicacionUsuario).all()