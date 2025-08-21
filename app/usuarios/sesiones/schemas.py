# app/usuarios/sesiones/schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# ----------------------------
# Respuesta al crear o consultar sesión
# ----------------------------
class SesionAppUsuarioResponse(BaseModel):
    id: int                          # ID de la sesión
    usuario_id: int                  # ID del usuario al que pertenece la sesión
    refresh_token: str               # Token de actualización
    expiracion: datetime             # Fecha y hora de expiración del refresh token
    dispositivo: Optional[str]       # Nombre o tipo del dispositivo (opcional)
    version_app: Optional[str]       # Versión de la app (opcional)
    ip: Optional[str]                # IP desde la que se inició sesión (opcional)
    fecha_inicio: datetime           # Fecha y hora de inicio de la sesión
    ultima_actividad: datetime       # Fecha y hora de la última actividad
    activo: bool                     # Estado de la sesión: activa o inactiva

    class Config:
        orm_mode = True              # Permite convertir automáticamente los modelos SQLAlchemy a Pydantic

# ----------------------------
# Petición para refrescar token
# ----------------------------
class RefreshTokenRequest(BaseModel):
    refresh_token: str               # Token que se envía para obtener un nuevo access token

# ----------------------------
# Respuesta al refrescar token
# ----------------------------
class RefreshTokenResponse(BaseModel):
    access_token: str                # Nuevo access token generado
    token_type: str = "bearer"       # Tipo de token (por defecto "bearer")
