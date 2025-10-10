from sqlalchemy.orm import Session
from app.usuarios.models import Rol, Usuario, DatosPersonales
from passlib.context import CryptContext
import logging

logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def create_default_roles_and_admin(db: Session):
    roles_por_crear = [
        {"nombre": "usuario", "descripcion": "Usuario regular"},
        {"nombre": "administrador", "descripcion": "Usuario con privilegios de administrador"}
    ]

    # Crear roles
    for rol_data in roles_por_crear:
        rol_existente = db.query(Rol).filter(Rol.nombre == rol_data["nombre"]).first()
        if rol_existente:
            logger.info(f"✅ Rol '{rol_data['nombre']}' ya existe")
            continue

        nuevo_rol = Rol(nombre=rol_data["nombre"], descripcion=rol_data["descripcion"])
        try:
            db.add(nuevo_rol)
            db.commit()
            db.refresh(nuevo_rol)
            logger.info(f"✅ Rol '{rol_data['nombre']}' creado correctamente con id {nuevo_rol.id}")
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error creando rol '{rol_data['nombre']}': {e}")
            raise

    # Crear usuario administrador inicial
    rol_admin = db.query(Rol).filter(Rol.nombre == "administrador").first()
    if not rol_admin:
        raise Exception("❌ Rol 'administrador' no encontrado, no se puede crear el admin inicial")

    admin_existente = db.query(Usuario).filter(Usuario.usuario == "lreyesp@gmail.com").first()
    if admin_existente:
        logger.info("✅ Usuario administrador ya existe")
        return

    # 1️⃣ Crear datos personales del admin
    datos_admin = DatosPersonales(nombre="Admin", apellido="Principal")
    try:
        db.add(datos_admin)
        db.commit()
        db.refresh(datos_admin)
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error creando datos personales del admin: {e}")
        raise

    # 2️⃣ Crear usuario admin usando el ID de DatosPersonales
    nuevo_admin = Usuario(
        usuario="lreyesp@gmail.com",
        contrasenia=hash_password("123456"),
        rol_id=rol_admin.id,
        datos_personales_id=datos_admin.id,
        activo=True
    )

    try:
        db.add(nuevo_admin)
        db.commit()
        db.refresh(nuevo_admin)
        logger.info(f"✅ Usuario administrador creado correctamente con id {nuevo_admin.id}")
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error creando usuario administrador: {e}")
        raise
