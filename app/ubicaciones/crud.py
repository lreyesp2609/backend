from sqlalchemy.orm import Session
from ..ubicaciones.models import UbicacionUsuario
from ..ubicaciones.schemas import UbicacionUsuarioCreate, UbicacionUsuarioUpdate

def crear_ubicacion(db: Session, usuario_id: int, ubicacion: UbicacionUsuarioCreate):
    db_ubicacion = UbicacionUsuario(
        usuario_id=usuario_id,
        nombre=ubicacion.nombre,
        latitud=ubicacion.latitud,
        longitud=ubicacion.longitud,
        direccion_completa=ubicacion.direccion_completa
    )
    db.add(db_ubicacion)
    db.commit()
    db.refresh(db_ubicacion)
    return db_ubicacion

def obtener_ubicaciones(db: Session, usuario_id: int):
    return db.query(UbicacionUsuario).filter(UbicacionUsuario.usuario_id == usuario_id).all()

def obtener_ubicacion(db: Session, ubicacion_id: int, usuario_id: int):
    return db.query(UbicacionUsuario).filter(
        UbicacionUsuario.id == ubicacion_id,
        UbicacionUsuario.usuario_id == usuario_id
    ).first()

def actualizar_ubicacion(db: Session, ubicacion_id: int, usuario_id: int, datos: UbicacionUsuarioUpdate):
    db_ubicacion = obtener_ubicacion(db, ubicacion_id, usuario_id)
    if not db_ubicacion:
        return None
    for key, value in datos.dict(exclude_unset=True).items():
        setattr(db_ubicacion, key, value)
    db.commit()
    db.refresh(db_ubicacion)
    return db_ubicacion

def eliminar_ubicacion(db: Session, ubicacion_id: int, usuario_id: int):
    db_ubicacion = obtener_ubicacion(db, ubicacion_id, usuario_id)
    if not db_ubicacion:
        return None
    db.delete(db_ubicacion)
    db.commit()
    return db_ubicacion
