from sqlalchemy.orm import Session
from app.usuarios.models import Rol
import logging

logger = logging.getLogger(__name__)

def create_default_roles(db: Session):
    rol_existente = db.query(Rol).filter(Rol.nombre == "usuario").first()
    if rol_existente:
        logger.info("✅ Rol 'usuario' ya existe")
        return

    nuevo_rol = Rol(nombre="usuario", descripcion="Usuario regular")
    try:
        db.add(nuevo_rol)
        db.commit()
        db.refresh(nuevo_rol)
        logger.info(f"✅ Rol 'usuario' creado correctamente con id {nuevo_rol.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error creando rol 'usuario': {e}")
        raise