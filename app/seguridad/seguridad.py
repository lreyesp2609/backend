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
from ..ubicaciones.models import UbicacionUsuario

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/seguridad",
    tags=["Seguridad en Rutas"]
)


def traducir_tipo_ruta(tipo_ingles: str) -> str:
    """
    Traduce los tipos de ruta de inglés a español
    """
    traducciones = {
        "shortest": "Más corta",
        "fastest": "Más rápida",
        "recommended": "Recomendada"
    }
    return traducciones.get(tipo_ingles, tipo_ingles)

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

# ══════════════════════════════════════════════════════════
# ENDPOINT /validar-rutas
# ══════════════════════════════════════════════════════════

@router.post("/validar-rutas", response_model=ValidarRutasResponse)
def validar_rutas_seguridad(
    request: ValidarRutasRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        # 1️⃣ Obtener ubicación del destino
        ubicacion_destino = db.query(UbicacionUsuario).filter(
            UbicacionUsuario.id == request.ubicacion_id
        ).first()
        
        if not ubicacion_destino:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ubicación de destino no encontrada"
            )
        
        # 2️⃣ Obtener zonas PROPIAS del usuario
        validador = ValidadorSeguridadPersonal(db, current_user.id)
        zonas_propias = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id == current_user.id,
            ZonaPeligrosaUsuario.activa == True
        ).all()

        # 🔥 CREAR SET DE IDs Y TAMBIÉN SET DE "HUELLAS" (nombre + coordenadas)
        zonas_ids_propias = {z.id for z in zonas_propias}

        # Crear huellas únicas para detectar zonas adoptadas (mismo nombre + coordenadas)
        def crear_huella_zona(zona):
            """Crea una huella única para comparar zonas (nombre + centro)"""
            if not zona.poligono:
                return None
            centro = zona.poligono[0]
            # Redondear a 5 decimales para evitar diferencias mínimas
            lat = round(centro['lat'], 5)
            lon = round(centro['lon'], 5)
            return f"{zona.nombre.lower().strip()}:{lat}:{lon}"

        huellas_propias = {
            crear_huella_zona(z) for z in zonas_propias 
            if crear_huella_zona(z) is not None
        }

        logger.info(f"🔒 Zonas propias del usuario: {len(zonas_propias)}")
        logger.debug(f"🔍 Huellas propias: {huellas_propias}")
        
        # 3️⃣ 🚀 NUEVO: Obtener zonas PÚBLICAS cerca del DESTINO
        from .geometria import calcular_distancia_haversine

        zonas_publicas_cercanas = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id != current_user.id,
            ZonaPeligrosaUsuario.activa == True
        ).all()

        # Filtrar por distancia al destino (10km)
        zonas_publicas_filtradas = []
        radio_busqueda_metros = 10_000  # 10km

        for zona in zonas_publicas_cercanas:
            centro = zona.poligono[0] if zona.poligono else None
            if not centro:
                continue
            
            distancia = calcular_distancia_haversine(
                ubicacion_destino.latitud, ubicacion_destino.longitud,
                centro['lat'], centro['lon']
            )
            
            if distancia <= radio_busqueda_metros:
                zonas_publicas_filtradas.append(zona)
        
        logger.info(f"🌍 Zonas públicas cerca del destino: {len(zonas_publicas_filtradas)}")
        
        # 4️⃣ Obtener recomendación de ML (UCB)
        ucb_service = UCBService(db)
        tipo_ml_recomendado = ucb_service.seleccionar_tipo_ruta(
            usuario_id=current_user.id,
            ubicacion_id=request.ubicacion_id
        )
        
        logger.info(f"🤖 ML recomienda '{tipo_ml_recomendado}'")
        
        # 5️⃣ Validar cada ruta contra TODAS las zonas (propias + públicas)
        rutas_validadas = []

        for ruta in request.rutas:
            puntos_ruta = validador._decode_polyline(ruta.geometry)
            
            # Validar contra zonas PROPIAS
            validacion_propias = validador.validar_ruta(
                geometry_polyline=ruta.geometry,
                metadata={
                    'tipo': ruta.tipo,
                    'distance': ruta.distance,
                    'duration': ruta.duration
                }
            )
            
            # 🚀 VALIDAR CONTRA ZONAS PÚBLICAS
            zonas_publicas_detectadas = []

            for zona_publica in zonas_publicas_filtradas:
                # 🔥 VERIFICACIÓN 1: Saltar si es del usuario (por ID)
                if zona_publica.id in zonas_ids_propias:
                    logger.debug(f"⏭️ Saltando zona {zona_publica.id} (es del usuario por ID)")
                    continue
                
                # 🔥 VERIFICACIÓN 2: Saltar si es una zona ADOPTADA (mismo nombre + coords)
                huella_publica = crear_huella_zona(zona_publica)
                if huella_publica and huella_publica in huellas_propias:
                    logger.debug(f"⏭️ Saltando zona '{zona_publica.nombre}' (adoptada por el usuario)")
                    continue
                
                # Validar intersección
                resultado_zona = validador._analizar_zona_con_deteccion_puentes(
                    zona_publica,
                    puntos_ruta,
                    metadata={
                        'tipo': ruta.tipo,
                        'distance': ruta.distance,
                        'duration': ruta.duration
                    }
                )
                
                if resultado_zona['es_interseccion_real']:
                    centro = zona_publica.poligono[0] if zona_publica.poligono else None
                    if centro:
                        distancia_km = calcular_distancia_haversine(
                            ubicacion_destino.latitud, ubicacion_destino.longitud,
                            centro['lat'], centro['lon']
                        ) / 1000.0

                        zonas_publicas_detectadas.append({
                            'zona_id': zona_publica.id,
                            'nombre': zona_publica.nombre,
                            'nivel_peligro': zona_publica.nivel_peligro,
                            'tipo': zona_publica.tipo,
                            'distancia_km': round(distancia_km, 1),
                            'puede_guardar': True,
                            'porcentaje_ruta': resultado_zona['porcentaje']
                        })
            
            # Combinar zonas propias + públicas
            todas_zonas_detectadas = validacion_propias['zonas_detectadas'] + [
                {
                    'zona_id': z['zona_id'],
                    'nombre': z['nombre'],
                    'nivel_peligro': z['nivel_peligro'],
                    'tipo': z.get('tipo'),
                    'porcentaje_ruta': z['porcentaje_ruta']
                }
                for z in zonas_publicas_detectadas
            ]
            
            # Determinar si es segura
            es_segura = len(todas_zonas_detectadas) == 0
            
            # Calcular nivel de riesgo máximo
            nivel_riesgo = max(
                [z['nivel_peligro'] for z in todas_zonas_detectadas],
                default=0
            )
            
            # Generar mensaje
            if es_segura:
                mensaje = None
            elif len(zonas_publicas_detectadas) > 0 and len(validacion_propias['zonas_detectadas']) == 0:
                # Solo detectó zonas públicas (no propias)
                mensaje = f"⚠️ Esta ruta pasa por {len(zonas_publicas_detectadas)} zona(s) reportada(s) por otros usuarios"
            elif len(validacion_propias['zonas_detectadas']) > 0:
                # Detectó zonas propias (con o sin públicas)
                mensaje = validacion_propias['mensaje']
            else:
                mensaje = validacion_propias['mensaje']
            
            # Crear objeto de respuesta
            ruta_validada = RutaValidada(
                tipo=ruta.tipo,
                es_segura=es_segura,
                nivel_riesgo=nivel_riesgo,
                zonas_detectadas=[
                    ZonaDetectada(
                        zona_id=z['zona_id'],
                        nombre=z['nombre'],
                        nivel_peligro=z['nivel_peligro'],
                        tipo=z.get('tipo'),
                        porcentaje_ruta=z['porcentaje_ruta']
                    )
                    for z in todas_zonas_detectadas
                ],
                mensaje=mensaje,
                distancia=ruta.distance,
                duracion=ruta.duration,
                zonas_publicas_detectadas=zonas_publicas_detectadas if zonas_publicas_detectadas else None
            )
            
            rutas_validadas.append(ruta_validada)
        
        # 6️⃣ Determinar mejor ruta y advertencias
        todas_seguras = all(rv.es_segura for rv in rutas_validadas)
        
        mejor_ruta_segura = None
        ruta_menos_peligrosa = None
        nivel_riesgo_minimo = 999
        
        for rv in rutas_validadas:
            if rv.es_segura:
                mejor_ruta_segura = rv.tipo
                break
            else:
                if rv.nivel_riesgo < nivel_riesgo_minimo:
                    nivel_riesgo_minimo = rv.nivel_riesgo
                    ruta_menos_peligrosa = rv.tipo
        
        # Generar advertencia general
        advertencia_general = None
        if not todas_seguras:
            if mejor_ruta_segura is None:
                # 🔥 TRADUCIR nombre de ruta
                nombre_ruta_traducido = traducir_tipo_ruta(ruta_menos_peligrosa)
                
                if nivel_riesgo_minimo >= 4:
                    advertencia_general = f"TODAS las rutas pasan por zonas de ALTO RIESGO. Recomendamos la ruta '{nombre_ruta_traducido}' (menos peligrosa)."
                else:
                    advertencia_general = f"Todas las rutas pasan por zonas con riesgo. Mantente alerta. Ruta recomendada: '{nombre_ruta_traducido}'."
            else:
                # 🔥 TRADUCIR nombre de ruta
                nombre_ruta_traducido = traducir_tipo_ruta(mejor_ruta_segura)
                advertencia_general = f"✅ Usa la ruta '{nombre_ruta_traducido}' (segura). Evita las otras que pasan por zonas peligrosas."

        # Contar zonas activas del usuario
        total_zonas = len(zonas_propias)
        
        respuesta = ValidarRutasResponse(
            rutas_validadas=rutas_validadas,
            tipo_ml_recomendado=tipo_ml_recomendado,
            todas_seguras=todas_seguras,
            mejor_ruta_segura=traducir_tipo_ruta(mejor_ruta_segura or ruta_menos_peligrosa),  # 🔥 TRADUCIR
            advertencia_general=advertencia_general,
            total_zonas_usuario=total_zonas,
            zonas_publicas_encontradas=len(zonas_publicas_filtradas)
        )
                
        logger.info(f"📊 VALIDACIÓN COMPLETA:")
        logger.info(f"   Todas seguras: {todas_seguras}")
        logger.info(f"   Mejor ruta: {mejor_ruta_segura or ruta_menos_peligrosa}")
        logger.info(f"   Zonas públicas encontradas: {len(zonas_publicas_filtradas)}")
        logger.info(f"   Advertencia: {advertencia_general}")
        
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

@router.post("/verificar-ubicacion-actual", response_model=VerificarUbicacionResponse)
def verificar_ubicacion_actual(
    request: VerificarUbicacionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🚨 ALERTA EN TIEMPO REAL: Verifica si el usuario está en zona peligrosa
    
    **Flujo:**
    1. Android envía ubicación actual cada 30-60 segundos (background)
    2. Backend verifica contra zonas del usuario
    3. Si está en zona peligrosa → Retorna alerta
    4. Android muestra notificación INMEDIATA (NO guarda nada)
    
    **Caso de Uso:**
    - Usuario caminando → Entra a zona marcada como peligrosa
    - Backend detecta → Retorna alerta
    - Android muestra: "⚠️ ZONA PELIGROSA: Callejón oscuro - Nivel Alto"
    """
    try:
        from .models import ZonaPeligrosaUsuario
        from .geometria import calcular_distancia_haversine
        
        # 1. Obtener zonas activas del usuario
        zonas = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id == current_user.id,
            ZonaPeligrosaUsuario.activa == True
        ).all()
        
        if not zonas:
            return VerificarUbicacionResponse(
                hay_peligro=False,
                zonas_detectadas=[],
                mensaje_alerta=None
            )
        
        # 2. Verificar cada zona
        zonas_detectadas = []
        nivel_peligro_maximo = 0
        
        for zona in zonas:
            # Obtener centro de la zona (primer punto del polígono)
            centro = zona.poligono[0] if zona.poligono else None
            if not centro:
                continue
            
            radio_zona = zona.radio_metros or 200
            
            # Calcular distancia al centro
            distancia = calcular_distancia_haversine(
                request.lat, request.lon,
                centro['lat'], centro['lon']
            )
            
            # ¿Está dentro del radio?
            dentro = distancia <= radio_zona
            
            if dentro:
                zonas_detectadas.append(ZonaPeligrosaDetectada(
                    zona_id=zona.id,
                    nombre=zona.nombre,
                    nivel_peligro=zona.nivel_peligro,
                    tipo=zona.tipo,
                    distancia_al_centro=round(distancia, 1),
                    dentro_de_zona=True
                ))
                
                nivel_peligro_maximo = max(nivel_peligro_maximo, zona.nivel_peligro)
        
        # 3. Generar mensaje de alerta
        mensaje_alerta = None
        if zonas_detectadas:
            if nivel_peligro_maximo >= 4:
                mensaje_alerta = f"⚠️ ZONA DE ALTO RIESGO: {zonas_detectadas[0].nombre}"
            elif nivel_peligro_maximo == 3:
                mensaje_alerta = f"⚠️ ZONA DE RIESGO MODERADO: {zonas_detectadas[0].nombre}"
            else:
                mensaje_alerta = f"ℹ️ Zona marcada: {zonas_detectadas[0].nombre}"
        
        return VerificarUbicacionResponse(
            hay_peligro=len(zonas_detectadas) > 0,
            zonas_detectadas=zonas_detectadas,
            mensaje_alerta=mensaje_alerta
        )
        
    except Exception as e:
        logger.error(f"Error verificando ubicación: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al verificar ubicación: {str(e)}"
        )
    
# ══════════════════════════════════════════════════════════
# NUEVOS ENDPOINTS PARA ZONAS COMPARTIDAS
# ══════════════════════════════════════════════════════════

@router.get("/zonas-sugeridas", response_model=List[ZonaPeligrosaResponse])
def obtener_zonas_sugeridas(
    lat: float,
    lon: float,
    radio_km: float = 10.0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    🌍 Obtiene zonas peligrosas PÚBLICAS cerca de una ubicación
    
    - Busca zonas de otros usuarios en un radio determinado
    - Excluye las zonas que el usuario YA tiene guardadas
    - Filtra por distancia al centro de cada zona
    
    **Caso de uso:** Usuario de Guayaquil visita Quevedo
    """
    try:
        from .geometria import calcular_distancia_haversine
        
        # 1. Obtener TODAS las zonas activas de OTROS usuarios
        zonas_publicas = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id != current_user.id,
            ZonaPeligrosaUsuario.activa == True
        ).all()
        
        logger.info(f"📊 Total zonas públicas en BD: {len(zonas_publicas)}")
        
        # 2. Obtener IDs de zonas que el usuario YA tiene
        zonas_propias = db.query(ZonaPeligrosaUsuario.id).filter(
            ZonaPeligrosaUsuario.usuario_id == current_user.id,
            ZonaPeligrosaUsuario.activa == True
        ).all()
        
        ids_propias = {z.id for z in zonas_propias}
        logger.info(f"🔒 Usuario tiene {len(ids_propias)} zonas propias")
        
        # 3. Filtrar zonas cercanas
        zonas_cercanas = []
        radio_metros = radio_km * 1000
        
        for zona in zonas_publicas:
            # Saltar si el usuario ya tiene esta zona (caso improbable pero posible)
            if zona.id in ids_propias:
                continue
            
            # Obtener centro de la zona
            centro = zona.poligono[0] if zona.poligono else None
            if not centro:
                continue
            
            # Calcular distancia
            distancia = calcular_distancia_haversine(
                lat, lon,
                centro['lat'], centro['lon']
            )
            
            # ¿Está dentro del radio?
            if distancia <= radio_metros:
                zonas_cercanas.append(zona)
        
        logger.info(f"✅ {len(zonas_cercanas)} zonas sugeridas para mostrar")
        
        return zonas_cercanas
        
    except Exception as e:
        logger.error(f"Error obteniendo zonas sugeridas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener zonas sugeridas: {str(e)}"
        )


@router.post("/adoptar-zona/{zona_id}", response_model=ZonaPeligrosaResponse)
def adoptar_zona_sugerida(
    zona_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    💾 Guarda una zona pública como zona PERSONAL del usuario
    
    **Flujo:**
    1. Busca la zona original
    2. Crea una COPIA para el usuario actual
    3. Mantiene mismo nombre, nivel, coordenadas
    4. El usuario ahora "tiene" esa zona
    """
    try:
        # 1. Buscar zona original
        zona_original = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.id == zona_id,
            ZonaPeligrosaUsuario.activa == True
        ).first()
        
        if not zona_original:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Zona sugerida no encontrada"
            )
        
        # 2. Verificar que NO sea del usuario (seguridad)
        if zona_original.usuario_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Esta zona ya es tuya"
            )
        
        # 3. Verificar que el usuario no tenga ya una zona con el mismo nombre
        existe = db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id == current_user.id,
            ZonaPeligrosaUsuario.nombre == zona_original.nombre,
            ZonaPeligrosaUsuario.activa == True
        ).first()
        
        if existe:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ya tienes una zona llamada '{zona_original.nombre}'"
            )
        
        # 4. Crear COPIA de la zona para el usuario
        nueva_zona = ZonaPeligrosaUsuario(
            usuario_id=current_user.id,
            nombre=zona_original.nombre,
            poligono=zona_original.poligono,  # Copiar el polígono completo
            nivel_peligro=zona_original.nivel_peligro,
            tipo=zona_original.tipo,
            notas=f"Adoptada de zona comunitaria • {zona_original.notas or ''}".strip(),
            radio_metros=zona_original.radio_metros,
            activa=True
        )
        
        db.add(nueva_zona)
        db.commit()
        db.refresh(nueva_zona)
        
        logger.info(f"✅ Usuario {current_user.id} adoptó zona '{nueva_zona.nombre}' (ID: {nueva_zona.id})")
        
        return nueva_zona
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adoptando zona: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al adoptar zona: {str(e)}"
        )