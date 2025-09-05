# app/ml/router.py (actualizado con JWT)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from .ucb_service import UCBService
from pydantic import BaseModel
from typing import Optional
from ..usuarios.security import get_current_user  # Importar autenticación

router = APIRouter(
    prefix="/ml",
    tags=["Machine Learning"]
)

# Schemas para requests/responses
class TipoRutaResponse(BaseModel):
    tipo_ruta: str
    usuario_id: int
    confidence: Optional[float] = None

class FeedbackRequest(BaseModel):
    tipo_usado: str
    completada: bool
    distancia: Optional[float] = None
    duracion: Optional[float] = None

class FeedbackResponse(BaseModel):
    status: str
    mensaje: str

@router.get("/recomendar-tipo-ruta", response_model=TipoRutaResponse)
def recomendar_tipo_ruta(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)  # JWT en header
):
    """
    Android Studio llama este endpoint para saber qué tipo de ruta generar.
    Usa el JWT del header para identificar al usuario.
    """
    try:
        ucb_service = UCBService(db)
        tipo_recomendado = ucb_service.seleccionar_tipo_ruta(current_user.id)
        
        return TipoRutaResponse(
            tipo_ruta=tipo_recomendado,
            usuario_id=current_user.id
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error al recomendar tipo de ruta: {str(e)}"
        )

@router.post("/feedback-ruta", response_model=FeedbackResponse)
def registrar_feedback_ruta(
    feedback: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)  # JWT en header
):
    """
    Android Studio llama este endpoint cuando el usuario termina (o cancela) la ruta.
    Usa el JWT del header para identificar al usuario.
    """
    try:
        ucb_service = UCBService(db)
        ucb_service.actualizar_feedback(
            usuario_id=current_user.id,  # Usar usuario del JWT
            tipo_usado=feedback.tipo_usado,
            completada=feedback.completada,
            distancia=feedback.distancia,
            duracion=feedback.duracion
        )
        
        estado = "completada" if feedback.completada else "cancelada"
        return FeedbackResponse(
            status="success",
            mensaje=f"Feedback registrado: ruta {feedback.tipo_usado} {estado}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al registrar feedback: {str(e)}"
        )

@router.get("/stats")
def obtener_mis_estadisticas(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)  # JWT en header
):
    """
    Devuelve las estadísticas del algoritmo UCB del usuario autenticado.
    """
    try:
        ucb_service = UCBService(db)
        stats = ucb_service.obtener_estadisticas(current_user.id)
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener estadísticas: {str(e)}"
        )

@router.post("/reset-bandit")
def resetear_mi_bandit(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)  # JWT en header
):
    """
    Resetea el aprendizaje del usuario autenticado.
    """
    try:
        ucb_service = UCBService(db)
        ucb_service.resetear_usuario(current_user.id)
        return {"status": "success", "mensaje": "Tu bandit ha sido reseteado"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al resetear bandit: {str(e)}"
        )