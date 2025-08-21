from sqlalchemy.orm import Session
from .models import SesionAppUsuario
from datetime import datetime

def crear_sesion(
    db: Session,
    usuario_id: int,
    refresh_token: str,
    expiracion: datetime,
    dispositivo: str = None,
    version_app: str = None,
    ip: str = None
):
    sesion = SesionAppUsuario(
        usuario_id=usuario_id,
        refresh_token=refresh_token,
        expiracion=expiracion,
        dispositivo=dispositivo,
        version_app=version_app,
        ip=ip,
        fecha_inicio=datetime.utcnow(),
        ultima_actividad=datetime.utcnow(),
        activo=True
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion

def inhabilitar_sesion(db: Session, refresh_token: str):
    sesion = db.query(SesionAppUsuario).filter_by(refresh_token=refresh_token, activo=True).first()
    if sesion:
        sesion.activo = False
        db.commit()
    return sesion

def obtener_sesion(db: Session, refresh_token: str):
    sesion = db.query(SesionAppUsuario).filter_by(refresh_token=refresh_token).first()
    if not sesion:
        return None
    
    # Verificar expiración
    if sesion.expiracion < datetime.utcnow():
        sesion.activo = False
        db.commit()
        return None

    # Si todavía está activa
    if not sesion.activo:
        return None

    return sesion