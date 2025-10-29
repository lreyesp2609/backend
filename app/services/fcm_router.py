from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..database.database import get_db
from ..usuarios.models import Usuario, FCMToken
from ..usuarios.security import get_current_user
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fcm", tags=["FCM - Notificaciones Push"])


# ✅ Schemas
class TokenFCMRequest(BaseModel):
    token: str
    dispositivo: str = "android"  # android, ios, web

class TokenFCMResponse(BaseModel):
    message: str
    token_id: int

class TokensResponse(BaseModel):
    tokens: list
    total: int


# ✅ Endpoint: Registrar o actualizar token FCM
@router.post("/token", response_model=TokenFCMResponse, status_code=status.HTTP_201_CREATED)
async def registrar_token_fcm(
    request: TokenFCMRequest,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user)
):
    """
    Registra o actualiza el token FCM del dispositivo del usuario.
    Si el token ya existe, se actualiza la fecha.
    """
    try:
        # Buscar si ya existe este token para este usuario
        existing_token = db.query(FCMToken).filter(
            FCMToken.usuario_id == user.id,
            FCMToken.token == request.token
        ).first()
        
        if existing_token:
            # Actualizar fecha
            existing_token.updated_at = datetime.now(timezone.utc)
            existing_token.dispositivo = request.dispositivo
            db.commit()
            logger.info(f"🔄 Token FCM actualizado para usuario {user.id}")
            
            return TokenFCMResponse(
                message="Token FCM actualizado correctamente",
                token_id=existing_token.id
            )
        
        # Verificar si existe otro token del mismo dispositivo (reemplazar)
        old_token = db.query(FCMToken).filter(
            FCMToken.usuario_id == user.id,
            FCMToken.dispositivo == request.dispositivo
        ).first()
        
        if old_token:
            # Reemplazar token antiguo
            old_token.token = request.token
            old_token.updated_at = datetime.now(timezone.utc)
            db.commit()
            logger.info(f"🔄 Token FCM reemplazado para usuario {user.id}")
            
            return TokenFCMResponse(
                message="Token FCM reemplazado correctamente",
                token_id=old_token.id
            )
        
        # Crear nuevo token
        nuevo_token = FCMToken(
            usuario_id=user.id,
            token=request.token,
            dispositivo=request.dispositivo
        )
        db.add(nuevo_token)
        db.commit()
        db.refresh(nuevo_token)
        
        logger.info(f"✅ Nuevo token FCM registrado para usuario {user.id}")
        
        return TokenFCMResponse(
            message="Token FCM registrado correctamente",
            token_id=nuevo_token.id
        )
        
    except Exception as e:
        logger.error(f"❌ Error registrando token FCM: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar token FCM"
        )


# ✅ Endpoint: Obtener tokens del usuario actual
@router.get("/tokens", response_model=TokensResponse)
async def obtener_mis_tokens(
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user)
):
    """
    Obtiene todos los tokens FCM registrados del usuario actual
    """
    try:
        tokens = db.query(FCMToken).filter(
            FCMToken.usuario_id == user.id
        ).all()
        
        tokens_data = [
            {
                "id": t.id,
                "token": t.token[:20] + "...",  # Mostrar solo primeros 20 caracteres
                "dispositivo": t.dispositivo,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None
            }
            for t in tokens
        ]
        
        return TokensResponse(
            tokens=tokens_data,
            total=len(tokens_data)
        )
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener tokens"
        )


# ✅ Endpoint: Eliminar token específico
@router.delete("/token/{token_id}")
async def eliminar_token_especifico(
    token_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user)
):
    """
    Elimina un token FCM específico del usuario
    """
    try:
        token = db.query(FCMToken).filter(
            FCMToken.id == token_id,
            FCMToken.usuario_id == user.id
        ).first()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token no encontrado"
            )
        
        db.delete(token)
        db.commit()
        
        logger.info(f"🗑️ Token FCM {token_id} eliminado para usuario {user.id}")
        
        return {"message": "Token eliminado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error eliminando token: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar token"
        )


# ✅ Endpoint: Eliminar todos los tokens del usuario (logout)
@router.delete("/tokens")
async def eliminar_todos_mis_tokens(
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user)
):
    """
    Elimina todos los tokens FCM del usuario (útil al cerrar sesión)
    """
    try:
        cantidad = db.query(FCMToken).filter(
            FCMToken.usuario_id == user.id
        ).delete()
        
        db.commit()
        
        logger.info(f"🗑️ {cantidad} token(s) FCM eliminados para usuario {user.id}")
        
        return {
            "message": f"{cantidad} token(s) eliminado(s) correctamente",
            "cantidad": cantidad
        }
        
    except Exception as e:
        logger.error(f"❌ Error eliminando tokens: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar tokens"
        )