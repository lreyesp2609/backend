from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc
import math
import logging
from .models import PuntoGPSRaw, ViajeDetectado, PatronPredictibilidad

logger = logging.getLogger(__name__)


class PassiveTrackingService:
    """
    📍 Servicio de tracking GPS pasivo - VERSIÓN PRODUCCIÓN
    
    Mejoras implementadas:
    - ✅ Manejo correcto de timezones (UTC)
    - ✅ Detección inteligente de movimiento vs quieto
    - ✅ Validación de distancia total antes de finalizar viaje
    - ✅ Sistema robusto de notificaciones predictivas
    - ✅ Logs detallados para debugging
    """
    
    # Configuración para PRODUCCIÓN
    DISTANCIA_MINIMA_VIAJE = 50      # metros (ajustar a 200 en producción)
    TIEMPO_MINIMO_VIAJE = 30         # segundos (ajustar a 120 en producción)
    RADIO_DESTINO_METROS = 100        # radio para ubicaciones conocidas
    PUNTOS_QUIETO_REQUERIDOS = 6      # puntos para confirmar que está quieto
    DISTANCIA_QUIETO_METROS = 30      # distancia promedio para considerar quieto
    UMBRAL_SIMILITUD_TRAYECTORIA = 0.50
    MIN_VIAJES_ANALISIS = 5
    UMBRAL_PREDICTIBILIDAD = 0.60
    VENTANA_TIEMPO_PUNTOS = 30        # minutos hacia atrás para buscar puntos
    
    def __init__(self, db: Session):
        self.db = db
    
    async def guardar_lote_puntos_gps(
        self,
        usuario_id: int,
        puntos: List
    ) -> int:
        """
        📦 Guarda múltiples puntos GPS en un solo request
        """
        try:
            puntos_guardados = 0
            
            for punto_data in puntos:
                try:
                    timestamp_str = punto_data.timestamp if hasattr(punto_data, 'timestamp') else None
                    
                    if timestamp_str and isinstance(timestamp_str, str):
                        timestamp = datetime.fromisoformat(
                            timestamp_str.replace('Z', '+00:00')
                        )
                    else:
                        timestamp = datetime.now(timezone.utc)
                    
                    punto = PuntoGPSRaw(
                        usuario_id=usuario_id,
                        latitud=punto_data.lat,
                        longitud=punto_data.lon,
                        timestamp=timestamp,
                        precision_metros=punto_data.precision if hasattr(punto_data, 'precision') else None,
                        velocidad=punto_data.velocidad if hasattr(punto_data, 'velocidad') else None
                    )
                    
                    self.db.add(punto)
                    puntos_guardados += 1
                    
                except Exception as e:
                    logger.error(f"Error guardando punto individual: {e}")
                    continue
            
            self.db.commit()
            
            # Intentar detectar viaje después de guardar
            await self._intentar_detectar_viaje(usuario_id)
            
            logger.info(f"📦 {puntos_guardados} puntos GPS guardados para usuario {usuario_id}")
            
            return puntos_guardados
            
        except Exception as e:
            logger.error(f"Error en guardar_lote_puntos_gps: {e}")
            self.db.rollback()
            raise

    async def _intentar_detectar_viaje(self, usuario_id: int):
        """
        🧠 LÓGICA MEJORADA DE DETECCIÓN - FIX APLICADO
        
        CAMBIO CRÍTICO: Buscar puntos DESPUÉS de saber cuál es el último viaje,
        no basarse en el "último punto" que puede estar desactualizado
        """
        try:
            # ═══════════════════════════════════════════════════════
            # PASO 1: Determinar desde cuándo buscar puntos
            # ═══════════════════════════════════════════════════════
            ultimo_viaje = self.db.query(ViajeDetectado).filter(
                ViajeDetectado.usuario_id == usuario_id
            ).order_by(ViajeDetectado.fecha_fin.desc()).first()
            
            if ultimo_viaje:
                desde = ultimo_viaje.fecha_fin
                logger.info(f"🔍 Buscando desde último viaje: {desde} UTC")
            else:
                # FIX: En lugar de buscar "último punto" y restarle 30 min,
                # buscar directamente desde hace 2 horas
                desde = datetime.now(timezone.utc) - timedelta(hours=2)
                logger.info(f"🔍 Sin viajes previos, buscando desde: {desde} UTC")
            
            # ═══════════════════════════════════════════════════════
            # PASO 2: Obtener puntos GPS desde la fecha calculada
            # ═══════════════════════════════════════════════════════
            puntos = self.db.query(PuntoGPSRaw).filter(
                PuntoGPSRaw.usuario_id == usuario_id,
                PuntoGPSRaw.timestamp >= desde
            ).order_by(PuntoGPSRaw.timestamp).all()
            
            logger.info(f"📊 Puntos GPS encontrados: {len(puntos)}")
            
            if puntos:
                logger.info(f"   Rango temporal: {puntos[0].timestamp} → {puntos[-1].timestamp}")
                duracion_total = (puntos[-1].timestamp - puntos[0].timestamp).total_seconds()
                logger.info(f"   Duración: {duracion_total:.0f}s ({duracion_total/60:.1f} min)")
            
            # ═══════════════════════════════════════════════════════
            # PASO 3: Validar cantidad mínima de puntos
            # ═══════════════════════════════════════════════════════
            if len(puntos) < self.PUNTOS_QUIETO_REQUERIDOS:
                logger.info(f"⏭️ Insuficientes puntos: {len(puntos)} < {self.PUNTOS_QUIETO_REQUERIDOS}")
                return
            
            # ═══════════════════════════════════════════════════════
            # PASO 4: Calcular distancia total del recorrido
            # ═══════════════════════════════════════════════════════
            distancia_total = self._calcular_distancia_total_ruta(puntos)
            logger.info(f"📏 Distancia total recorrida: {distancia_total:.1f}m")
            
            # ═══════════════════════════════════════════════════════
            # PASO 5: Verificar si está quieto AHORA
            # ═══════════════════════════════════════════════════════
            esta_quieto = self._esta_quieto(puntos)
            
            # ═══════════════════════════════════════════════════════
            # PASO 6: Decidir si finalizar viaje
            # ═══════════════════════════════════════════════════════
            if distancia_total >= self.DISTANCIA_MINIMA_VIAJE:
                if esta_quieto:
                    logger.info(f"✅ CONDICIONES CUMPLIDAS:")
                    logger.info(f"   ✓ Distancia: {distancia_total:.1f}m >= {self.DISTANCIA_MINIMA_VIAJE}m")
                    logger.info(f"   ✓ Usuario quieto confirmado")
                    logger.info(f"   → Finalizando viaje...")
                    
                    await self._finalizar_viaje_en_progreso(usuario_id, puntos)
                else:
                    logger.info(f"🏃 Usuario AÚN en movimiento:")
                    logger.info(f"   ✓ Distancia acumulada: {distancia_total:.1f}m")
                    logger.info(f"   ✗ No está quieto todavía")
                    logger.info(f"   → Esperando más puntos...")
            else:
                if esta_quieto:
                    logger.info(f"⏭️ Movimiento INSIGNIFICANTE:")
                    logger.info(f"   ✗ Distancia: {distancia_total:.1f}m < {self.DISTANCIA_MINIMA_VIAJE}m")
                    logger.info(f"   ✓ Usuario quieto")
                    logger.info(f"   → Viaje descartado (probablemente ruido GPS)")
                else:
                    logger.info(f"🚶 Movimiento menor en progreso:")
                    logger.info(f"   ✗ Distancia: {distancia_total:.1f}m < {self.DISTANCIA_MINIMA_VIAJE}m")
                    logger.info(f"   ✗ Usuario en movimiento")
                    logger.info(f"   → Esperando más datos...")
                    
        except Exception as e:
            logger.error(f"❌ Error detectando viaje: {e}")
            import traceback
            traceback.print_exc()

    def _esta_quieto(self, puntos: List[PuntoGPSRaw]) -> bool:
        """
        🎯 Verifica si el usuario está quieto analizando los últimos N puntos
        
        Retorna True si la distancia promedio entre los últimos puntos
        es menor al umbral configurado
        """
        if len(puntos) < self.PUNTOS_QUIETO_REQUERIDOS:
            logger.debug(f"   Insuficientes puntos para verificar: {len(puntos)} < {self.PUNTOS_QUIETO_REQUERIDOS}")
            return False
        
        ultimos = puntos[-self.PUNTOS_QUIETO_REQUERIDOS:]
        distancias = []
        
        logger.debug(f"   Analizando últimos {self.PUNTOS_QUIETO_REQUERIDOS} puntos:")
        
        for i in range(len(ultimos) - 1):
            dist = self._calcular_distancia_haversine(
                ultimos[i].latitud, ultimos[i].longitud,
                ultimos[i+1].latitud, ultimos[i+1].longitud
            )
            distancias.append(dist)
            logger.debug(f"      Punto {i}→{i+1}: {dist:.1f}m")
        
        if not distancias:
            return False
        
        promedio = sum(distancias) / len(distancias)
        esta_quieto = promedio < self.DISTANCIA_QUIETO_METROS
        
        logger.info(f"   📏 Distancia promedio últimos {self.PUNTOS_QUIETO_REQUERIDOS} puntos: {promedio:.1f}m")
        logger.info(f"   {'✅' if esta_quieto else '❌'} Usuario {'QUIETO' if esta_quieto else 'EN MOVIMIENTO'} (umbral: {self.DISTANCIA_QUIETO_METROS}m)")
        
        return esta_quieto
    
    async def _finalizar_viaje_en_progreso(self, usuario_id: int, puntos: List[PuntoGPSRaw]):
        """
        🏁 Finaliza y guarda un viaje detectado
        
        Pasos:
        1. Detectar punto de inicio real (primer movimiento)
        2. Detectar punto final (último punto)
        3. Calcular métricas del viaje
        4. Buscar ubicaciones cercanas conocidas
        5. Guardar viaje en BD
        6. Analizar predictibilidad
        """
        try:
            if len(puntos) < 3:
                logger.warning("⚠️ Muy pocos puntos para crear viaje válido")
                return
            
            # ═══════════════════════════════════════════════════════
            # PASO 1: Detectar punto de INICIO real del movimiento
            # ═══════════════════════════════════════════════════════
            punto_inicio_movimiento = None
            umbral_inicio = 50  # metros
            
            for i in range(len(puntos) - 1):
                dist = self._calcular_distancia_haversine(
                    puntos[i].latitud, puntos[i].longitud,
                    puntos[i+1].latitud, puntos[i+1].longitud
                )
                
                if dist > umbral_inicio and punto_inicio_movimiento is None:
                    punto_inicio_movimiento = puntos[i]
                    logger.info(f"🚀 Inicio de movimiento en punto #{i}: ({puntos[i].latitud:.6f}, {puntos[i].longitud:.6f})")
                    break
            
            if punto_inicio_movimiento is None:
                punto_inicio_movimiento = puntos[0]
                logger.warning("⚠️ No se detectó inicio claro, usando primer punto")
            
            punto_fin_movimiento = puntos[-1]
            
            logger.info(f"📍 ORIGEN: ({punto_inicio_movimiento.latitud:.6f}, {punto_inicio_movimiento.longitud:.6f})")
            logger.info(f"📍 DESTINO: ({punto_fin_movimiento.latitud:.6f}, {punto_fin_movimiento.longitud:.6f})")
            
            # ═══════════════════════════════════════════════════════
            # PASO 2: Calcular métricas del viaje
            # ═══════════════════════════════════════════════════════
            distancia_total = self._calcular_distancia_total_ruta(puntos)
            duracion = (puntos[-1].timestamp - puntos[0].timestamp).total_seconds()
            
            logger.info(f"📏 Distancia: {distancia_total:.0f}m")
            logger.info(f"⏱️  Duración: {duracion:.0f}s ({duracion/60:.1f} min)")
            logger.info(f"📊 Puntos GPS: {len(puntos)}")
            
            # ═══════════════════════════════════════════════════════
            # PASO 3: Validar viaje
            # ═══════════════════════════════════════════════════════
            if distancia_total < self.DISTANCIA_MINIMA_VIAJE:
                logger.info(f"⏭️ Viaje descartado: {distancia_total:.0f}m < {self.DISTANCIA_MINIMA_VIAJE}m")
                return
            
            if duracion < self.TIEMPO_MINIMO_VIAJE:
                logger.info(f"⏭️ Viaje descartado: {duracion:.0f}s < {self.TIEMPO_MINIMO_VIAJE}s")
                return
            
            # ═══════════════════════════════════════════════════════
            # PASO 4: Verificar duplicados
            # ═══════════════════════════════════════════════════════
            existente = self.db.query(ViajeDetectado).filter(
                ViajeDetectado.usuario_id == usuario_id,
                ViajeDetectado.fecha_inicio == puntos[0].timestamp
            ).first()
            
            if existente:
                logger.info(f"⏭️ Viaje ya existe (ID: {existente.id})")
                return
            
            # ═══════════════════════════════════════════════════════
            # PASO 5: Buscar ubicaciones conocidas cercanas
            # ═══════════════════════════════════════════════════════
            ubicacion_origen_id = self._buscar_destino_cercano(
                usuario_id, 
                punto_inicio_movimiento.latitud, 
                punto_inicio_movimiento.longitud
            )
            
            ubicacion_destino_id = self._buscar_destino_cercano(
                usuario_id, 
                punto_fin_movimiento.latitud, 
                punto_fin_movimiento.longitud
            )
            
            if ubicacion_origen_id:
                logger.info(f"✅ Origen identificado: Ubicación #{ubicacion_origen_id}")
            else:
                logger.info(f"❓ Origen desconocido")
            
            if ubicacion_destino_id:
                logger.info(f"✅ Destino identificado: Ubicación #{ubicacion_destino_id}")
            else:
                logger.info(f"❓ Destino desconocido")
            
            # ═══════════════════════════════════════════════════════
            # PASO 6: Crear y guardar viaje
            # ═══════════════════════════════════════════════════════
            geometria = self._simplificar_geometria(puntos)
            hash_trayectoria = self._calcular_hash_trayectoria(geometria)
            
            viaje = ViajeDetectado(
                usuario_id=usuario_id,
                ubicacion_origen_id=ubicacion_origen_id,
                ubicacion_destino_id=ubicacion_destino_id,
                lat_inicio=punto_inicio_movimiento.latitud,
                lon_inicio=punto_inicio_movimiento.longitud,
                lat_fin=punto_fin_movimiento.latitud,
                lon_fin=punto_fin_movimiento.longitud,
                fecha_inicio=puntos[0].timestamp,
                fecha_fin=puntos[-1].timestamp,
                geometria=geometria,
                distancia_metros=distancia_total,
                duracion_segundos=int(duracion),
                hash_trayectoria=hash_trayectoria
            )
            
            self.db.add(viaje)
            self.db.commit()
            self.db.refresh(viaje)
            
            logger.info(f"")
            logger.info(f"{'='*60}")
            logger.info(f"🚗 VIAJE DETECTADO Y GUARDADO")
            logger.info(f"{'='*60}")
            logger.info(f"   ID: {viaje.id}")
            logger.info(f"   Origen: {'Ubicación #' + str(ubicacion_origen_id) if ubicacion_origen_id else 'Desconocido'}")
            logger.info(f"   Destino: {'Ubicación #' + str(ubicacion_destino_id) if ubicacion_destino_id else 'Desconocido'}")
            logger.info(f"   Distancia: {distancia_total:.0f}m ({distancia_total/1000:.2f}km)")
            logger.info(f"   Duración: {duracion:.0f}s ({duracion/60:.1f} min)")
            logger.info(f"   Puntos GPS: {len(puntos)}")
            logger.info(f"   Velocidad promedio: {(distancia_total/duracion)*3.6:.1f} km/h")
            logger.info(f"{'='*60}")
            logger.info(f"")
            
            # ═══════════════════════════════════════════════════════
            # PASO 7: Analizar predictibilidad
            # ═══════════════════════════════════════════════════════
            if ubicacion_destino_id:
                logger.info(f"📊 Analizando predictibilidad para destino #{ubicacion_destino_id}")
                self._analizar_predictibilidad_destino(usuario_id, ubicacion_destino_id)
            
        except Exception as e:
            logger.error(f"❌ Error finalizando viaje: {e}")
            import traceback
            traceback.print_exc()
            self.db.rollback()
    
    def _analizar_predictibilidad_destino(self, usuario_id: int, ubicacion_destino_id: int):
        """
        🔥 Sistema inteligente de análisis de patrones
        """
        try:
            viajes = self.db.query(ViajeDetectado).filter(
                ViajeDetectado.usuario_id == usuario_id,
                ViajeDetectado.ubicacion_destino_id == ubicacion_destino_id
            ).order_by(desc(ViajeDetectado.fecha_inicio)).all()
            
            if len(viajes) < self.MIN_VIAJES_ANALISIS:
                logger.info(f"📊 Solo {len(viajes)} viajes, necesita {self.MIN_VIAJES_ANALISIS} para análisis")
                return
            
            # Analizar predictibilidad
            viajes_recientes = viajes[:10]
            grupos_similares = self._agrupar_trayectorias_similares(viajes_recientes)
            grupo_mas_grande = max(grupos_similares, key=lambda g: len(g['viajes']))
            
            viajes_ruta_similar = len(grupo_mas_grande['viajes'])
            total_viajes = len(viajes_recientes)
            predictibilidad = viajes_ruta_similar / total_viajes
            es_predecible = predictibilidad >= self.UMBRAL_PREDICTIBILIDAD
            
            logger.info(f"📊 Predictibilidad: {predictibilidad*100:.1f}% ({viajes_ruta_similar}/{total_viajes})")
            
            # Obtener o crear patrón
            patron = self.db.query(PatronPredictibilidad).filter(
                PatronPredictibilidad.usuario_id == usuario_id,
                PatronPredictibilidad.ubicacion_destino_id == ubicacion_destino_id
            ).first()
            
            if patron:
                patron.total_viajes = total_viajes
                patron.viajes_ruta_similar = viajes_ruta_similar
                patron.predictibilidad = predictibilidad
                patron.es_predecible = es_predecible
                patron.fecha_actualizacion = datetime.now(timezone.utc)
            else:
                patron = PatronPredictibilidad(
                    usuario_id=usuario_id,
                    ubicacion_destino_id=ubicacion_destino_id,
                    total_viajes=total_viajes,
                    viajes_ruta_similar=viajes_ruta_similar,
                    predictibilidad=predictibilidad,
                    es_predecible=es_predecible
                )
                self.db.add(patron)
            
            self.db.commit()
            
            # Sistema de notificaciones
            if es_predecible:
                debe_notificar, razon = self._debe_notificar_patron(
                    patron, 
                    viajes,
                    usuario_id,
                    ubicacion_destino_id
                )
                
                logger.info(f"📊 Decisión notificación: {razon}")
                
                if debe_notificar:
                    import asyncio
                    asyncio.create_task(
                        self._enviar_notificacion_predictibilidad(
                            usuario_id, 
                            ubicacion_destino_id, 
                            patron.predictibilidad
                        )
                    )
                    patron.notificacion_enviada = True
                    patron.fecha_ultima_notificacion = datetime.now(timezone.utc)
                    self.db.commit()
                    logger.info(f"✅ Notificación enviada")
            
        except Exception as e:
            logger.error(f"Error analizando predictibilidad: {e}")
            self.db.rollback()

    def _debe_notificar_patron(
        self,
        patron: PatronPredictibilidad,
        viajes: List[ViajeDetectado],
        usuario_id: int,
        ubicacion_destino_id: int
    ) -> Tuple[bool, str]:
        """
        🧠 Lógica inteligente para decidir si notificar
        """
        
        ahora = datetime.now(timezone.utc)
        hoy = ahora.date()
        
        # CASO 1: Primera vez detectado
        if not patron.notificacion_enviada:
            return True, "🆕 Primera vez detectado como predecible"
        
        # CASO 2: Ya notificamos HOY
        if patron.fecha_ultima_notificacion:
            ultimo_dia = patron.fecha_ultima_notificacion.date()
            
            if hoy == ultimo_dia:
                return False, f"⏭️ Ya se notificó hoy"
        
        # CASO 3: Cooldown de 7 días
        if patron.fecha_ultima_notificacion:
            dias_desde_ultima = (ahora - patron.fecha_ultima_notificacion).days
            
            if dias_desde_ultima < 7:
                return False, f"⏳ Cooldown: {dias_desde_ultima}/7 días"
        
        # CASO 4: Patrón frecuente (ventana 7 días)
        hace_7_dias = ahora - timedelta(days=7)
        
        viajes_ultimos_7_dias = [
            v for v in viajes 
            if v.fecha_inicio >= hace_7_dias
        ]
        
        cantidad_viajes_7d = len(viajes_ultimos_7_dias)
        
        if cantidad_viajes_7d >= 3:
            return True, f"🔥 Patrón frecuente: {cantidad_viajes_7d} viajes en 7 días"
        
        # CASO 5: Reset si no viaja hace 14+ días
        if viajes_ultimos_7_dias:
            ultimo_viaje = max(viajes_ultimos_7_dias, key=lambda v: v.fecha_inicio)
            dias_sin_viajar = (ahora - ultimo_viaje.fecha_inicio).days
            
            if dias_sin_viajar >= 14:
                patron.notificacion_enviada = False
                patron.fecha_ultima_notificacion = None
                self.db.commit()
                return True, f"🔄 Patrón reactivado tras {dias_sin_viajar} días"
        
        return False, f"📊 Esperando más datos: {cantidad_viajes_7d}/3 viajes"

    def _agrupar_trayectorias_similares(self, viajes: List[ViajeDetectado]) -> List[Dict]:
        """Agrupa viajes con trayectorias similares"""
        grupos = []
        
        for viaje in viajes:
            encontrado = False
            
            for grupo in grupos:
                referencia = grupo['viajes'][0]
                similitud = self._calcular_similitud_trayectorias(
                    viaje.geometria, 
                    referencia.geometria
                )
                
                if similitud >= self.UMBRAL_SIMILITUD_TRAYECTORIA:
                    grupo['viajes'].append(viaje)
                    encontrado = True
                    break
            
            if not encontrado:
                grupos.append({'viajes': [viaje]})
        
        return grupos
    
    def _calcular_similitud_trayectorias(self, geometria1: str, geometria2: str) -> float:
        """Calcula similitud entre trayectorias"""
        try:
            puntos1 = self._parsear_geometria(geometria1)
            puntos2 = self._parsear_geometria(geometria2)
            
            if not puntos1 or not puntos2:
                return 0.0
            
            # Comparar origen y destino
            dist_origen = self._calcular_distancia_haversine(
                puntos1[0][0], puntos1[0][1],
                puntos2[0][0], puntos2[0][1]
            )
            
            dist_destino = self._calcular_distancia_haversine(
                puntos1[-1][0], puntos1[-1][1],
                puntos2[-1][0], puntos2[-1][1]
            )
            
            if dist_origen < 50 and dist_destino < 50:
                similitud_base = 0.8
            else:
                similitud_base = 0.0
            
            # Comparar puntos intermedios
            distancias = []
            n_puntos = min(len(puntos1), len(puntos2), 5)
            
            if n_puntos > 2:
                indices1 = [int(i * (len(puntos1) - 1) / (n_puntos - 1)) for i in range(n_puntos)]
                indices2 = [int(i * (len(puntos2) - 1) / (n_puntos - 1)) for i in range(n_puntos)]
                
                for i1, i2 in zip(indices1, indices2):
                    dist = self._calcular_distancia_haversine(
                        puntos1[i1][0], puntos1[i1][1],
                        puntos2[i2][0], puntos2[i2][1]
                    )
                    distancias.append(dist)
                
                distancia_promedio = sum(distancias) / len(distancias)
                similitud_ruta = max(0.0, 1.0 - (distancia_promedio / 150.0))
                
                similitud_final = (similitud_base + similitud_ruta) / 2
            else:
                similitud_final = similitud_base
            
            return similitud_final
            
        except Exception as e:
            logger.error(f"Error calculando similitud: {e}")
            return 0.0
        
    async def _enviar_notificacion_predictibilidad(
        self,
        usuario_id: int,
        ubicacion_destino_id: int,
        predictibilidad: float
    ):
        """Envía notificación FCM sugiriendo rutas alternas"""
        try:
            import time
            from firebase_admin import messaging
            from app.usuarios.models import FCMToken
            from app.ubicaciones.models import UbicacionUsuario
            
            tokens_obj = self.db.query(FCMToken).filter(
                FCMToken.usuario_id == usuario_id
            ).all()
            
            if not tokens_obj:
                logger.warning(f"⚠️ No hay tokens FCM para usuario {usuario_id}")
                return None
            
            destino = self.db.query(UbicacionUsuario).filter(
                UbicacionUsuario.id == ubicacion_destino_id
            ).first()
            
            nombre_destino = destino.nombre if destino else "este destino"
            
            titulo = "🚗 Ruta frecuente detectada"
            cuerpo = f"Viajas seguido a {nombre_destino}. Toca aquí para ver rutas alternas y variar tu camino."
            
            logger.info(f"📤 Enviando notificación de rutas alternas...")
            logger.info(f"   Usuario: {usuario_id}")
            logger.info(f"   Destino: {nombre_destino}")
            logger.info(f"   Predictibilidad: {predictibilidad*100:.1f}%")
            
            exitosos = 0
            fallidos = 0
            tokens_invalidos = []
            
            for token_obj in tokens_obj:
                try:
                    logger.info(f"📱 Enviando a token: {token_obj.token[:50]}...")
                    
                    # CRÍTICO: Solo data (sin notification) para que siempre se ejecute onMessageReceived
                    message = messaging.Message(
                        data={
                            "type": "generar_rutas",
                            "titulo": titulo,
                            "cuerpo": cuerpo,
                            "ubicacion_destino_id": str(ubicacion_destino_id),
                            "ubicacion_nombre": nombre_destino,
                            "predictibilidad": str(predictibilidad),
                            "NAVIGATE_TO_ROUTES": "true",
                            "FROM_NOTIFICATION": "true",
                            "timestamp": str(int(time.time() * 1000))
                        },
                        token=token_obj.token,
                        android=messaging.AndroidConfig(
                            priority="high",
                            ttl=3600
                        )
                    )
                    
                    response = messaging.send(message)
                    exitosos += 1
                    logger.info(f"✅ Notificación enviada: {response}")
                    
                except messaging.UnregisteredError:
                    fallidos += 1
                    tokens_invalidos.append(token_obj.token)
                    logger.warning(f"⚠️ Token no registrado: {token_obj.token[:50]}...")
                    
                except Exception as e:
                    fallidos += 1
                    logger.error(f"❌ Error enviando: {str(e)}")
            
            logger.info(f"📊 Resumen: {exitosos} exitosos, {fallidos} fallidos")
            
            return {
                "exitosos": exitosos,
                "fallidos": fallidos,
                "tokens_invalidos": tokens_invalidos
            }
            
        except Exception as e:
            logger.error(f"❌ Error enviando notificación: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # ═══════════════════════════════════════════════════════════════
    # FUNCIONES AUXILIARES
    # ═══════════════════════════════════════════════════════════════
    
    def _buscar_destino_cercano(self, usuario_id: int, lat: float, lon: float) -> Optional[int]:
        """Busca ubicaciones guardadas cercanas al punto dado"""
        from app.ubicaciones.models import UbicacionUsuario
        
        destinos = self.db.query(UbicacionUsuario).filter(
            UbicacionUsuario.usuario_id == usuario_id,
            UbicacionUsuario.activo == True
        ).all()
        
        for destino in destinos:
            distancia = self._calcular_distancia_haversine(
                lat, lon, destino.latitud, destino.longitud
            )
            
            if distancia <= self.RADIO_DESTINO_METROS:
                logger.debug(f"   Ubicación cercana: {destino.nombre} ({distancia:.1f}m)")
                return destino.id
        
        return None
    
    def _simplificar_geometria(self, puntos: List[PuntoGPSRaw]) -> str:
        """
        Simplifica la geometría tomando 1 de cada 3 puntos
        Formato: "lat1,lon1|lat2,lon2|..."
        """
        puntos_simplificados = puntos[::3]
        coords = [f"{p.latitud},{p.longitud}" for p in puntos_simplificados]
        return "|".join(coords)
    
    def _parsear_geometria(self, geometria: str) -> List[Tuple[float, float]]:
        """
        Convierte string de geometría en lista de tuplas (lat, lon)
        """
        try:
            puntos = []
            for coord in geometria.split('|'):
                lat, lon = coord.split(',')
                puntos.append((float(lat), float(lon)))
            return puntos
        except:
            return []
    
    def _calcular_hash_trayectoria(self, geometria: str) -> str:
        """
        Genera hash único para identificar trayectorias similares
        """
        import hashlib
        return hashlib.md5(geometria.encode()).hexdigest()[:16]
    
    def _calcular_distancia_haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calcula distancia en metros entre dos coordenadas usando fórmula de Haversine
        
        Args:
            lat1, lon1: Coordenadas del primer punto
            lat2, lon2: Coordenadas del segundo punto
            
        Returns:
            Distancia en metros
        """
        R = 6371000  # Radio de la Tierra en metros
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _calcular_distancia_total_ruta(self, puntos: List[PuntoGPSRaw]) -> float:
        """
        Calcula la distancia total de una ruta sumando distancias entre puntos consecutivos
        
        Args:
            puntos: Lista de puntos GPS ordenados cronológicamente
            
        Returns:
            Distancia total en metros
        """
        if len(puntos) < 2:
            return 0.0
        
        distancia = 0.0
        for i in range(len(puntos) - 1):
            distancia += self._calcular_distancia_haversine(
                puntos[i].latitud, puntos[i].longitud,
                puntos[i+1].latitud, puntos[i+1].longitud
            )
        
        return distancia