import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database.database import get_db
from ..usuarios.security import get_current_user
from .models import ZonaPeligrosaUsuario
from .seguridad_schemas import *
from .validador_seguridad_personal import *
from ..services.ucb_service import UCBService
from .geometria import *

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/seguridad",
    tags=["Seguridad en Rutas"]
)

# ==========================================
# 1. MARCAR ZONA PELIGROSA
# ==========================================

@router.post("/marcar-zona", response_model=ZonaPeligrosaResponse, status_code=status.HTTP_201_CREATED)
def marcar_zona_peligrosa(
    zona: ZonaPeligrosaCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        # Validar coordenadas
        if not validar_coordenadas(zona.lat, zona.lon):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coordenadas inválidas"
            )
        
        # 🔥 GUARDAR EL CENTRO ORIGINAL COMO PRIMER PUNTO
        poligono = [
            {"lat": zona.lat, "lon": zona.lon}  # ✅ Centro primero
        ]
        
        # Luego agregar los puntos del círculo
        puntos_circulo = crear_poligono_circular(
            lat=zona.lat,
            lon=zona.lon,
            radio_metros=zona.radio_metros
        )
        poligono.extend(puntos_circulo)  # Agregar puntos del borde
        
        # Crear zona en BD
        nueva_zona = ZonaPeligrosaUsuario(
            usuario_id=current_user.id,
            nombre=zona.nombre,
            poligono=poligono,  # Ahora el primer punto ES el centro
            nivel_peligro=zona.nivel_peligro,
            tipo=zona.tipo,
            notas=zona.notas,
            radio_metros=zona.radio_metros,
            activa=True
        )
        
        db.add(nueva_zona)
        db.commit()
        db.refresh(nueva_zona)
        
        logger.info(f"✅ Usuario {current_user.id} marcó zona peligrosa: '{zona.nombre}' "
                   f"(nivel {zona.nivel_peligro})")
        
        return nueva_zona
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marcando zona peligrosa: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al marcar zona peligrosa: {str(e)}"
        )

# ==========================================
# 2. OBTENER MIS ZONAS PELIGROSAS
# ==========================================

@router.get("/mis-zonas", response_model=List[ZonaPeligrosaResponse])
def obtener_mis_zonas_peligrosas(
    activas_solo: bool = True,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    📍 Obtiene las zonas peligrosas del usuario autenticado
    
    **Parámetros:**
    - **activas_solo**: Si True, solo devuelve zonas activas
    """
    try:
        query = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id == current_user.id
        )
        
        if activas_solo:
            query = query.filter(ZonaPeligrosaUsuario.activa == True)
        
        zonas = query.order_by(ZonaPeligrosaUsuario.fecha_creacion.desc()).all()
        
        logger.info(f"Usuario {current_user.id} consultó {len(zonas)} zonas peligrosas")
        return zonas
        
    except Exception as e:
        logger.error(f"Error obteniendo zonas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener zonas peligrosas"
        )

# ==========================================
# 3. VALIDAR RUTAS (ENDPOINT MÁS IMPORTANTE)
# ==========================================

@router.post("/validar-rutas", response_model=ValidarRutasResponse)
def validar_rutas_seguridad(
    request: ValidarRutasRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        # Inicializar validador para este usuario
        validador = ValidadorSeguridadPersonal(db, current_user.id)
        
        # Obtener recomendación de ML (UCB)
        ucb_service = UCBService(db)
        tipo_ml_recomendado = ucb_service.seleccionar_tipo_ruta(
            usuario_id=current_user.id,
            ubicacion_id=request.ubicacion_id
        )
        
        logger.info(f"🤖 ML recomienda '{tipo_ml_recomendado}' para usuario {current_user.id}, "
                   f"ubicación {request.ubicacion_id}")
        
        # Validar cada ruta
        rutas_para_validar = [
            {
                'tipo': ruta.tipo,
                'geometry': ruta.geometry,
                'distance': ruta.distance,
                'duration': ruta.duration
            }
            for ruta in request.rutas
        ]
        
        rutas_validadas_raw = validador.validar_multiples_rutas(rutas_para_validar)
        
        # Convertir a schema de respuesta
        rutas_validadas = []
        for rv in rutas_validadas_raw:
            zonas_detectadas = [
                ZonaDetectada(
                    zona_id=z['zona_id'],
                    nombre=z['nombre'],
                    nivel_peligro=z['nivel_peligro'],
                    tipo=z.get('tipo'),
                    porcentaje_ruta=z['porcentaje_ruta']
                )
                for z in rv['zonas_detectadas']
            ]
            
            rutas_validadas.append(RutaValidada(
                tipo=rv['tipo'],
                es_segura=rv['es_segura'],
                nivel_riesgo=rv['nivel_riesgo'],
                zonas_detectadas=zonas_detectadas,
                mensaje=rv['mensaje'],
                distancia=rv.get('distance'),
                duracion=rv.get('duration')
            ))
        
        # Determinar si todas son seguras
        todas_seguras = all(rv.es_segura for rv in rutas_validadas)
        
        # Encontrar la mejor ruta segura
        mejor_ruta_segura = None
        for rv in rutas_validadas:
            if rv.es_segura:
                mejor_ruta_segura = rv.tipo
                break
        
        # Generar advertencia general si ninguna es segura
        advertencia_general = None
        if not todas_seguras and mejor_ruta_segura is None:
            nivel_minimo = min(rv.nivel_riesgo for rv in rutas_validadas)
            if nivel_minimo >= 4:
                advertencia_general = "TODAS las rutas pasan por zonas de alto riesgo."
            else:
                advertencia_general = "Todas las rutas pasan por zonas con cierto nivel de riesgo. Mantente alerta."
        
        # Contar zonas activas del usuario
        total_zonas = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id == current_user.id,
            ZonaPeligrosaUsuario.activa == True
        ).count()
        
        respuesta = ValidarRutasResponse(
            rutas_validadas=rutas_validadas,
            tipo_ml_recomendado=tipo_ml_recomendado,
            todas_seguras=todas_seguras,
            mejor_ruta_segura=mejor_ruta_segura,
            advertencia_general=advertencia_general,
            total_zonas_usuario=total_zonas
        )
        
        logger.info(f"✅ Validación completa para usuario {current_user.id}: "
                   f"Todas seguras={todas_seguras}, ML recomienda={tipo_ml_recomendado}")
        
        return respuesta
        
    except Exception as e:
        logger.error(f"Error validando rutas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al validar rutas: {str(e)}"
        )

# ==========================================
# 4. ACTUALIZAR ZONA PELIGROSA
# ==========================================

@router.patch("/zona/{zona_id}", response_model=ZonaPeligrosaResponse)
def actualizar_zona_peligrosa(
    zona_id: int,
    zona_update: ZonaPeligrosaUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    ✏️ Actualiza una zona peligrosa existente
    
    Solo el propietario de la zona puede actualizarla.
    """
    try:
        # Buscar zona
        zona = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.id == zona_id,
            ZonaPeligrosaUsuario.usuario_id == current_user.id
        ).first()
        
        if not zona:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Zona no encontrada o no tienes permiso para modificarla"
            )
        
        # Actualizar campos
        if zona_update.nombre is not None:
            zona.nombre = zona_update.nombre
        if zona_update.nivel_peligro is not None:
            zona.nivel_peligro = zona_update.nivel_peligro
        if zona_update.tipo is not None:
            zona.tipo = zona_update.tipo
        if zona_update.notas is not None:
            zona.notas = zona_update.notas
        if zona_update.activa is not None:
            zona.activa = zona_update.activa
        
        db.commit()
        db.refresh(zona)
        
        logger.info(f"✅ Usuario {current_user.id} actualizó zona {zona_id}")
        return zona
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando zona: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar zona"
        )

# ==========================================
# 5. ELIMINAR ZONA PELIGROSA
# ==========================================

@router.delete("/zona/{zona_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_zona_peligrosa(
    zona_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🗑️ Elimina una zona peligrosa
    
    Solo el propietario puede eliminarla.
    """
    try:
        zona = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.id == zona_id,
            ZonaPeligrosaUsuario.usuario_id == current_user.id
        ).first()
        
        if not zona:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Zona no encontrada"
            )
        
        db.delete(zona)
        db.commit()
        
        logger.info(f"🗑️ Usuario {current_user.id} eliminó zona {zona_id}")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando zona: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al eliminar zona"
        )

# ==========================================
# 6. OBTENER ESTADÍSTICAS DE SEGURIDAD
# ==========================================

@router.get("/estadisticas", response_model=EstadisticasSeguridad)
def obtener_estadisticas_seguridad(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    📊 Obtiene estadísticas de seguridad del usuario
    """
    try:
        validador = ValidadorSeguridadPersonal(db, current_user.id)
        stats = validador.obtener_estadisticas_seguridad()
        
        # TODO: Agregar histórico de rutas validadas cuando se implemente
        stats['rutas_validadas_historico'] = 0
        stats['rutas_con_advertencias'] = 0
        
        return EstadisticasSeguridad(**stats)
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener estadísticas"
        )

# ==========================================
# 7. DESACTIVAR/ACTIVAR ZONA TEMPORAL
# ==========================================

@router.patch("/zona/{zona_id}/toggle")
def toggle_zona_activa(
    zona_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🔄 Activa/Desactiva una zona sin eliminarla
    
    Útil para zonas que solo son peligrosas en ciertos momentos.
    """
    try:
        zona = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.id == zona_id,
            ZonaPeligrosaUsuario.usuario_id == current_user.id
        ).first()
        
        if not zona:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Zona no encontrada"
            )
        
        zona.activa = not zona.activa
        db.commit()
        db.refresh(zona)
        
        estado = "activada" if zona.activa else "desactivada"
        logger.info(f"🔄 Usuario {current_user.id} {estado} zona {zona_id}")
        
        return {
            "zona_id": zona_id,
            "activa": zona.activa,
            "mensaje": f"Zona {estado} correctamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggle zona: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al cambiar estado de zona"
        )