# ════════════════════════════════════════════════════════════
# 🔌 ENDPOINTS REST - Tracking Pasivo
# Archivo: app/tracking/router.py
# ════════════════════════════════════════════════════════════

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from ..database.database import get_db
from ..usuarios.security import get_current_user
from ..services.passive_tracking_service import PassiveTrackingService
from .schemas import *

import logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/tracking",
    tags=["Tracking Pasivo GPS"]
)


@router.post("/gps/punto", status_code=status.HTTP_201_CREATED)
async def guardar_punto_gps(
    request: PuntoGPSRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    📍 Guarda un punto GPS del tracking pasivo
    
    Android envía esto cada 30-60 segundos en background
    """
    try:
        service = PassiveTrackingService(db)
        
        success = service.guardar_punto_gps(
            usuario_id=current_user.id,
            latitud=request.lat,
            longitud=request.lon,
            precision=request.precision,
            velocidad=request.velocidad
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error guardando punto GPS"
            )
        
        return {
            "success": True,
            "message": "Punto GPS guardado correctamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en guardar_punto_gps: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )


@router.post("/gps/lote", status_code=status.HTTP_201_CREATED)
async def guardar_lote_puntos_gps(
    request: LotePuntosGPSRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    📦 Guarda múltiples puntos GPS en un solo request
    
    Más eficiente cuando Android tiene varios puntos acumulados
    """
    try:
        service = PassiveTrackingService(db)
        
        cantidad = service.guardar_lote_puntos_gps(
            usuario_id=current_user.id,
            puntos=request.puntos
        )
        
        return {
            "success": True,
            "puntos_guardados": cantidad,
            "message": f"{cantidad} puntos GPS guardados correctamente"
        }
        
    except Exception as e:
        logger.error(f"Error en guardar_lote_puntos_gps: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando lote: {str(e)}"
        )


@router.get("/viajes", response_model=List[ViajeDetectadoResponse])
async def obtener_mis_viajes(
    skip: int = 0,
    limit: int = 50,
    ubicacion_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🚶 Obtiene los viajes detectados automáticamente
    """
    try:
        from ..services.passive_tracking_service import ViajeDetectado
        
        query = db.query(ViajeDetectado).filter(
            ViajeDetectado.usuario_id == current_user.id
        )
        
        if ubicacion_id:
            query = query.filter(
                ViajeDetectado.ubicacion_destino_id == ubicacion_id
            )
        
        viajes = query.order_by(
            ViajeDetectado.fecha_inicio.desc()
        ).offset(skip).limit(limit).all()
        
        return viajes
        
    except Exception as e:
        logger.error(f"Error obteniendo viajes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/patrones", response_model=List[PatronPredictibilidadResponse])
async def obtener_mis_patrones(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    📊 Obtiene los patrones de predictibilidad detectados
    """
    try:
        from ..services.passive_tracking_service import PatronPredictibilidad
        
        patrones = db.query(PatronPredictibilidad).filter(
            PatronPredictibilidad.usuario_id == current_user.id
        ).order_by(
            PatronPredictibilidad.predictibilidad.desc()
        ).all()
        
        return patrones
        
    except Exception as e:
        logger.error(f"Error obteniendo patrones: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/estadisticas", response_model=EstadisticasTrackingResponse)
async def obtener_estadisticas_tracking(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    📈 Obtiene estadísticas del tracking pasivo
    """
    try:
        from ..services.passive_tracking_service import (
            ViajeDetectado, 
            PatronPredictibilidad,
            PuntoGPSRaw
        )
        from sqlalchemy import func, and_
        from datetime import datetime, timedelta
        
        # Total de viajes
        total_viajes = db.query(func.count(ViajeDetectado.id)).filter(
            ViajeDetectado.usuario_id == current_user.id
        ).scalar() or 0
        
        # Viajes este mes
        inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
        viajes_mes = db.query(func.count(ViajeDetectado.id)).filter(
            and_(
                ViajeDetectado.usuario_id == current_user.id,
                ViajeDetectado.fecha_inicio >= inicio_mes
            )
        ).scalar() or 0
        
        # Distancia total
        distancia_total = db.query(func.sum(ViajeDetectado.distancia_metros)).filter(
            ViajeDetectado.usuario_id == current_user.id
        ).scalar() or 0.0
        
        # Patrones detectados
        patrones = db.query(PatronPredictibilidad).filter(
            PatronPredictibilidad.usuario_id == current_user.id
        ).all()
        
        total_patrones = len(patrones)
        patrones_predecibles = len([p for p in patrones if p.es_predecible])
        
        # Puntos GPS este mes
        puntos_mes = db.query(func.count(PuntoGPSRaw.id)).filter(
            and_(
                PuntoGPSRaw.usuario_id == current_user.id,
                PuntoGPSRaw.timestamp >= inicio_mes
            )
        ).scalar() or 0
        
        return EstadisticasTrackingResponse(
            total_viajes=total_viajes,
            viajes_este_mes=viajes_mes,
            distancia_total_km=round(distancia_total / 1000, 2),
            total_patrones=total_patrones,
            patrones_predecibles=patrones_predecibles,
            puntos_gps_este_mes=puntos_mes
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/viaje/{viaje_id}")
async def eliminar_viaje(
    viaje_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🗑️ Elimina un viaje detectado
    """
    try:
        from ..services.passive_tracking_service import ViajeDetectado
        
        viaje = db.query(ViajeDetectado).filter(
            ViajeDetectado.id == viaje_id,
            ViajeDetectado.usuario_id == current_user.id
        ).first()
        
        if not viaje:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Viaje no encontrado"
            )
        
        db.delete(viaje)
        db.commit()
        
        return {"message": "Viaje eliminado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando viaje: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/patron/{patron_id}/resetear-notificacion")
async def resetear_notificacion_patron(
    patron_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🔄 Resetea el estado de notificación de un patrón
    
    Útil si el usuario ya cambió su ruta y quiere que se vuelva a analizar
    """
    try:
        from ..services.passive_tracking_service import PatronPredictibilidad
        
        patron = db.query(PatronPredictibilidad).filter(
            PatronPredictibilidad.id == patron_id,
            PatronPredictibilidad.usuario_id == current_user.id
        ).first()
        
        if not patron:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patrón no encontrado"
            )
        
        patron.notificacion_enviada = False
        patron.fecha_ultima_notificacion = None
        db.commit()
        
        return {"message": "Notificación reseteada, se volverá a analizar"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reseteando notificación: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )