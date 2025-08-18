from sqlalchemy.orm import Session
from ..usuarios.models import Usuario
from ..usuarios.security import verify_password, create_access_token
import logging

logger = logging.getLogger(__name__)

def login_usuario(db: Session, correo: str, contrasenia: str):
    usuario = db.query(Usuario).filter(Usuario.usuario == correo, Usuario.activo == True).first()
    if not usuario:
        logger.info(f"❌ Usuario {correo} no encontrado o inactivo")
        return None
    
    if not verify_password(contrasenia, usuario.contrasenia):
        logger.info(f"❌ Contraseña incorrecta para {correo}")
        return None
    
    # Crear JWT
    token = create_access_token({"sub": usuario.usuario, "rol": usuario.rol.nombre})
    return token
