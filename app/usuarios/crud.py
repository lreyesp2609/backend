from sqlalchemy.orm import Session
from ..usuarios.models import Usuario, DatosPersonales, Rol
from ..usuarios.schemas import UsuarioCreate
from ..usuarios.security import hash_password
import logging

logger = logging.getLogger(__name__)

def crear_usuario(db: Session, usuario: UsuarioCreate):
    try:
        # Revisar si ya existe usuario con el mismo correo
        if db.query(Usuario).filter(Usuario.usuario == usuario.correo).first():
            logger.info(f"❌ Usuario {usuario.correo} ya existe")
            return None

        # Crear datos personales
        datos = DatosPersonales(nombre=usuario.nombre, apellido=usuario.apellido)
        db.add(datos)
        db.flush()  # Obtiene el ID antes del commit

        # Buscar rol 'usuario' por defecto
        rol = db.query(Rol).filter(Rol.nombre == "usuario").first()
        if not rol:
            logger.error("❌ Rol 'usuario' no existe")
            db.rollback()
            return None

        # Crear usuario
        nuevo_usuario = Usuario(
            usuario=usuario.correo,
            contrasenia=hash_password(usuario.contrasenia),
            datos_personales_id=datos.id,
            rol_id=rol.id,
            activo=True
        )
        db.add(nuevo_usuario)
        db.commit()
        db.refresh(nuevo_usuario)
        logger.info(f"✅ Usuario creado con id {nuevo_usuario.id}")
        return nuevo_usuario

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error creando usuario: {e}")
        return None
