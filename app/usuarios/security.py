from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError, ExpiredSignatureError
import os
import secrets
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, WebSocket
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..usuarios.models import Usuario
from ..database.database import get_db

# bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

# Expiraciones
ACCESS_TOKEN_EXPIRE_MINUTES = 15           # Access token 15 minutos
REFRESH_TOKEN_EXPIRE_DAYS = 180            # Refresh token 6 meses

# Hash de password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# Crear access token JWT
def create_access_token(data: dict, expires_delta: int = ACCESS_TOKEN_EXPIRE_MINUTES):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_delta)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Crear refresh token aleatorio
def create_refresh_token():
    return secrets.token_urlsafe(64)

# OAuth2 para leer token del header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login/")

# Decodificar access token
def decodificar_token(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id = payload.get("id_usuario")
        if usuario_id is None:
            raise HTTPException(status_code=401, detail="TOKEN_INVALIDO")
    except JWTError:
        raise HTTPException(status_code=401, detail="TOKEN_INVALIDO")
    return payload

def get_current_user(payload: dict = Depends(decodificar_token), db: Session = Depends(get_db)):
    usuario_id = payload.get("id_usuario")
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.activo==True).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="USUARIO_NO_ENCONTRADO")
    return usuario

# WebSocket authentication - SIMPLIFICADO Y CORREGIDO
async def get_current_user_ws(websocket: WebSocket, db: Session):
    """
    Autentica usuario desde WebSocket validando el token JWT
    """
    token = None
    
    # Extraer token del header o query params
    auth = websocket.headers.get("authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    else:
        token = websocket.query_params.get("token")

    if not token:
        raise Exception("Token no proporcionado")

    try:
        payload = jwt.decode(
            token, 
            SECRET_KEY, 
            algorithms=[ALGORITHM]
        )
        
        usuario_id = payload.get("id_usuario")
        if usuario_id is None:
            raise Exception("Token inválido: falta id_usuario")
        
    except ExpiredSignatureError:
        raise Exception("Token expirado")
    except JWTError as e:
        raise Exception(f"Token inválido: {str(e)}")

    # Buscar usuario en la base de datos
    usuario = db.query(Usuario).filter(
        Usuario.id == usuario_id, 
        Usuario.activo == True
    ).first()
    
    if not usuario:
        raise Exception("Usuario no encontrado o inactivo")

    return usuario