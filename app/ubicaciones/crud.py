from sqlalchemy.orm import Session
from ..ubicaciones.models import UbicacionUsuario
from ..ubicaciones.schemas import UbicacionUsuarioCreate, UbicacionUsuarioUpdate

def verificar_nombre_duplicado(db: Session, usuario_id: int, nombre: str, ubicacion_id: int = None):
    query = db.query(UbicacionUsuario).filter(
        UbicacionUsuario.usuario_id == usuario_id,
        UbicacionUsuario.nombre == nombre,
        UbicacionUsuario.activo == True
    )
    if ubicacion_id:
        query = query.filter(UbicacionUsuario.id != ubicacion_id)
    return query.first() is not None


def crear_ubicacion(db: Session, usuario_id: int, ubicacion: UbicacionUsuarioCreate):
    if verificar_nombre_duplicado(db, usuario_id, ubicacion.nombre):
        return None

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
    return db.query(UbicacionUsuario).filter(
        UbicacionUsuario.usuario_id == usuario_id,
        UbicacionUsuario.activo == True
    ).all()


def obtener_ubicacion(db: Session, ubicacion_id: int, usuario_id: int):
    return db.query(UbicacionUsuario).filter(
        UbicacionUsuario.id == ubicacion_id,
        UbicacionUsuario.usuario_id == usuario_id,
        UbicacionUsuario.activo == True
    ).first()


def actualizar_ubicacion(db: Session, ubicacion_id: int, usuario_id: int, datos: UbicacionUsuarioUpdate):
    db_ubicacion = obtener_ubicacion(db, ubicacion_id, usuario_id)
    if not db_ubicacion:
        return None

    if datos.nombre and verificar_nombre_duplicado(db, usuario_id, datos.nombre, ubicacion_id):
        return "DUPLICATE_NAME"

    for key, value in datos.model_dump(exclude_unset=True).items():
        setattr(db_ubicacion, key, value)

    db.commit()
    db.refresh(db_ubicacion)
    return db_ubicacion

def eliminar_ubicacion(db: Session, ubicacion_id: int, usuario_id: int):
    db_ubicacion = obtener_ubicacion(db, ubicacion_id, usuario_id)
    if not db_ubicacion:
        return None

    db_ubicacion.activo = False  # Eliminación lógica
    db.commit()
    db.refresh(db_ubicacion)
    return db_ubicacion
