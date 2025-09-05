from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.database import get_db
from .ucb_service import UCBService
from pydantic import BaseModel
from typing import Optional
from ..usuarios.security import get_current_user  # Importar autenticación
import logging

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/ml",
    tags=["Machine Learning"]
)

# Schemas para requests/responses
class TipoRutaRequest(BaseModel):
    ubicacion_id: int

class TipoRutaResponse(BaseModel):
    tipo_ruta: str
    usuario_id: int
    ubicacion_id: int
    confidence: Optional[float] = None

class FeedbackRequest(BaseModel):
    tipo_usado: str
    completada: bool
    ubicacion_id: int
    distancia: Optional[float] = None
    duracion: Optional[float] = None

class FeedbackResponse(BaseModel):
    status: str
    mensaje: str

@router.post("/recomendar-tipo-ruta", response_model=TipoRutaResponse)
def recomendar_tipo_ruta(
    request: TipoRutaRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Android Studio llama este endpoint para saber qué tipo de ruta generar.
    """
    try:
        ucb_service = UCBService(db)
        # ✅ AHORA SÍ pasar ubicacion_id
        tipo_recomendado = ucb_service.seleccionar_tipo_ruta(
            usuario_id=current_user.id,
            ubicacion_id=request.ubicacion_id  # ✅ Pasar la ubicación
        )
        
        return TipoRutaResponse(
            tipo_ruta=tipo_recomendado,
            usuario_id=current_user.id,
            ubicacion_id=request.ubicacion_id
        )
    except Exception as e:
        logger.error(f"Error en recomendar_tipo_ruta: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Error al recomendar tipo de ruta: {str(e)}"
        )

@router.post("/feedback-ruta", response_model=FeedbackResponse)
def registrar_feedback_ruta(
    feedback: FeedbackRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Android Studio llama este endpoint cuando el usuario termina (o cancela) la ruta.
    """
    try:
        ucb_service = UCBService(db)
        # ✅ PASAR ubicacion_id correctamente
        ucb_service.actualizar_feedback(
            usuario_id=current_user.id,
            tipo_usado=feedback.tipo_usado,
            completada=feedback.completada,
            ubicacion_id=feedback.ubicacion_id,  # ✅ Pasar ubicacion_id
            distancia=feedback.distancia,
            duracion=feedback.duracion
        )
        
        estado = "completada" if feedback.completada else "cancelada"
        return FeedbackResponse(
            status="success",
            mensaje=f"Feedback registrado: ruta {feedback.tipo_usado} {estado}"
        )
    except Exception as e:
        logger.error(f"Error en registrar_feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al registrar feedback: {str(e)}"
        )

@router.get("/stats")
def obtener_mis_estadisticas(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
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
    current_user=Depends(get_current_user)
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
