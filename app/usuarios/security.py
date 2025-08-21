# security.py
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import JWTError, jwt
import os
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from ..usuarios.sesiones.models import SesionAppUsuario
from ..database.database import get_db

# Configuración bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

# Duración de tokens
ACCESS_TOKEN_EXPIRE_PROD = 60*24      # 1 día en minutos
ACCESS_TOKEN_EXPIRE_RECORDAR_PROD = 60*24*30  # 30 días si marca recordar

# Duración de prueba
ACCESS_TOKEN_EXPIRE_TEST = 10 / 60     # 10 segundos en minutos
ACCESS_TOKEN_EXPIRE_RECORDAR_TEST = 20 / 60  # 20 segundos

# Hash de password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# Crear JWT
def create_access_token(data: dict, expires_delta: int):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# OAuth2 para leer token del header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login/")

def decodificar_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id = payload.get("id_usuario")
        if usuario_id is None:
            raise HTTPException(status_code=401, detail="TOKEN_INVALIDO")

    except JWTError:
        # Aunque el token haya expirado, buscamos la sesión y la inhabilitamos
        from ..usuarios.sesiones.crud import obtener_sesion
        sesion = obtener_sesion(db, token)  # Buscar por refresh o access token según tu modelo
        if sesion:
            sesion.activo = False
            db.commit()
        raise HTTPException(status_code=401, detail="TOKEN_INVALIDO")

    # Verificar sesión activa normalmente
    sesion = db.query(SesionAppUsuario).filter_by(usuario_id=usuario_id, activo=True).first()
    if sesion and sesion.expiracion < datetime.utcnow():
        sesion.activo = False
        db.commit()
        raise HTTPException(status_code=401, detail="TOKEN_INVALIDO")

    return payload

