# ════════════════════════════════════════════════════════════
# 📍 SISTEMA DE TRACKING PASIVO REAL
# Analiza movimientos GPS sin generar rutas manualmente
# Archivo: app/services/passive_tracking_service.py
# ════════════════════════════════════════════════════════════

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
import math
from .models import *
import time
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════
# SERVICIO DE TRACKING PASIVO
# ══════════════════════════════════════════════════════════

class PassiveTrackingService:
    """
    📍 Servicio de tracking GPS pasivo
    """
    
    DISTANCIA_MINIMA_VIAJE = 50      # metros (ajustar a 200 en producción)
    TIEMPO_MINIMO_VIAJE = 30         # segundos (ajustar a 120 en producción)
    RADIO_DESTINO_METROS = 100
    PUNTOS_QUIETO_REQUERIDOS = 6
    UMBRAL_SIMILITUD_TRAYECTORIA = 0.50
    MIN_VIAJES_ANALISIS = 5
    UMBRAL_PREDICTIBILIDAD = 0.60
    
    def __init__(self, db: Session):
        self.db = db
    
    async def guardar_lote_puntos_gps(  # ✅ async aquí
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
                        timestamp = datetime.utcnow()
                    
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
            
            # ✅ Con await
            await self._intentar_detectar_viaje(usuario_id)
            
            logger.info(f"📦 {puntos_guardados} puntos GPS guardados para usuario {usuario_id}")
            
            return puntos_guardados
            
        except Exception as e:
            logger.error(f"Error en guardar_lote_puntos_gps: {e}")
            self.db.rollback()
            raise

    def _esta_quieto(self, puntos: List[PuntoGPSRaw]) -> bool:
        """Verifica si está quieto con más certeza"""
        if len(puntos) < self.PUNTOS_QUIETO_REQUERIDOS:
            return False
        
        ultimos = puntos[-self.PUNTOS_QUIETO_REQUERIDOS:]
        distancias = []
        
        for i in range(len(ultimos) - 1):
            dist = self._calcular_distancia_haversine(
                ultimos[i].latitud, ultimos[i].longitud,
                ultimos[i+1].latitud, ultimos[i+1].longitud
            )
            distancias.append(dist)
        
        promedio = sum(distancias) / len(distancias)
        logger.info(f"📏 Distancia promedio últimos {self.PUNTOS_QUIETO_REQUERIDOS} puntos: {promedio:.1f}m")
        return promedio < 30
    
    async def _intentar_detectar_viaje(self, usuario_id: int):
        try:
            ultimo_viaje = self.db.query(ViajeDetectado).filter(
                ViajeDetectado.usuario_id == usuario_id
            ).order_by(ViajeDetectado.fecha_fin.desc()).first()
            
            if ultimo_viaje:
                desde = ultimo_viaje.fecha_fin
            else:
                desde = datetime.utcnow() - timedelta(hours=2)
            
            puntos = self.db.query(PuntoGPSRaw).filter(
                PuntoGPSRaw.usuario_id == usuario_id,
                PuntoGPSRaw.timestamp >= desde
            ).order_by(PuntoGPSRaw.timestamp).all()
            
            logger.info(f"📊 Puntos GPS: {len(puntos)} desde {desde}")
            
            if len(puntos) < self.PUNTOS_QUIETO_REQUERIDOS:
                logger.info(f"⏭️ Insuficientes puntos ({len(puntos)} < {self.PUNTOS_QUIETO_REQUERIDOS})")
                return
            
            if self._esta_quieto(puntos):
                logger.info(f"✅ Usuario quieto confirmado, finalizando viaje")
                await self._finalizar_viaje_en_progreso(usuario_id, puntos)  # ✅ Con await
            else:
                logger.info(f"🏃 Usuario en movimiento, acumulando puntos...")
                
        except Exception as e:
            logger.error(f"❌ Error detectando viaje: {e}")
    
    async def _finalizar_viaje_en_progreso(self, usuario_id: int, puntos: List[PuntoGPSRaw]):
        """
        🔥 VERSIÓN CORREGIDA: Detecta origen y destino correctamente
        """
        try:
            if len(puntos) < 3:
                return
            
            # 🆕 PASO 1: Encontrar el punto donde REALMENTE empezó el movimiento
            punto_inicio_movimiento = None
            
            # Buscar el primer punto donde hay movimiento significativo
            for i in range(len(puntos) - 1):
                dist = self._calcular_distancia_haversine(
                    puntos[i].latitud, puntos[i].longitud,
                    puntos[i+1].latitud, puntos[i+1].longitud
                )
                
                # Si hay movimiento > 50 metros, ese es el punto de inicio real
                if dist > 50 and punto_inicio_movimiento is None:
                    punto_inicio_movimiento = puntos[i]
                    logger.info(f"🚀 Inicio de movimiento detectado en punto {i}: "
                            f"({puntos[i].latitud}, {puntos[i].longitud})")
                    break
            
            # Si no se detectó movimiento, usar el primer punto
            if punto_inicio_movimiento is None:
                punto_inicio_movimiento = puntos[0]
                logger.warning("⚠️ No se detectó inicio de movimiento claro, usando primer punto")
            
            # El punto final es siempre el último (donde está quieto ahora)
            punto_fin_movimiento = puntos[-1]
            
            logger.info(f"📍 Origen detectado: ({punto_inicio_movimiento.latitud}, {punto_inicio_movimiento.longitud})")
            logger.info(f"📍 Destino detectado: ({punto_fin_movimiento.latitud}, {punto_fin_movimiento.longitud})")
            
            # ✅ PASO 2: Calcular distancia y duración
            distancia_total = self._calcular_distancia_total_ruta(puntos)
            
            if distancia_total < self.DISTANCIA_MINIMA_VIAJE:
                logger.info(f"⏭️ Viaje descartado: distancia {distancia_total:.0f}m < {self.DISTANCIA_MINIMA_VIAJE}m")
                return
            
            # 🔥 CORREGIDO: Duración desde el PRIMER punto hasta el ÚLTIMO
            duracion = (puntos[-1].timestamp - puntos[0].timestamp).total_seconds()
            
            logger.info(f"⏱️ Duración calculada: {duracion:.0f}s ({duracion/60:.1f} min)")
            logger.info(f"   Desde: {puntos[0].timestamp}")
            logger.info(f"   Hasta: {puntos[-1].timestamp}")
            
            if duracion < self.TIEMPO_MINIMO_VIAJE:
                logger.info(f"⏭️ Viaje descartado: duración {duracion:.0f}s < {self.TIEMPO_MINIMO_VIAJE}s")
                return
            
            # PASO 3: Verificar si ya existe
            # ⚠️ Verificar por el PRIMER punto, no por donde empezó el movimiento
            existente = self.db.query(ViajeDetectado).filter(
                ViajeDetectado.usuario_id == usuario_id,
                ViajeDetectado.fecha_inicio == puntos[0].timestamp  # ✅ Primer punto
            ).first()
            
            if existente:
                logger.info(f"⏭️ Viaje ya existe con fecha_inicio {puntos[0].timestamp}")
                return
            
            # 🔥 PASO 4: Buscar ubicaciones cercanas
            # Origen = donde estabas al inicio (primer punto con movimiento)
            ubicacion_origen_id = self._buscar_destino_cercano(
                usuario_id, 
                punto_inicio_movimiento.latitud, 
                punto_inicio_movimiento.longitud
            )
            
            # Destino = donde terminaste (último punto)
            ubicacion_destino_id = self._buscar_destino_cercano(
                usuario_id, 
                punto_fin_movimiento.latitud, 
                punto_fin_movimiento.longitud
            )
            
            # Logging detallado
            if ubicacion_origen_id:
                logger.info(f"✅ Origen identificado: Ubicación ID {ubicacion_origen_id}")
            else:
                logger.info(f"❓ Origen desconocido (no hay ubicación cercana)")
            
            if ubicacion_destino_id:
                logger.info(f"✅ Destino identificado: Ubicación ID {ubicacion_destino_id}")
            else:
                logger.info(f"❓ Destino desconocido (no hay ubicación cercana)")
            
            # PASO 5: Crear viaje
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
                fecha_inicio=puntos[0].timestamp,           # ✅ Primer punto
                fecha_fin=puntos[-1].timestamp,             # ✅ Último punto
                geometria=geometria,
                distancia_metros=distancia_total,
                duracion_segundos=int(duracion),
                hash_trayectoria=hash_trayectoria
            )
            
            self.db.add(viaje)
            self.db.commit()
            self.db.refresh(viaje)
            
            logger.info(f"🚶 ═══════════════════════════════════════")
            logger.info(f"🚶 VIAJE DETECTADO Y GUARDADO")
            logger.info(f"🚶 ═══════════════════════════════════════")
            logger.info(f"   ID: {viaje.id}")
            logger.info(f"   Origen: {'Ubicación ' + str(ubicacion_origen_id) if ubicacion_origen_id else 'Desconocido'}")
            logger.info(f"   Destino: {'Ubicación ' + str(ubicacion_destino_id) if ubicacion_destino_id else 'Desconocido'}")
            logger.info(f"   Distancia: {distancia_total:.0f}m")
            logger.info(f"   Duración: {duracion:.0f}s ({duracion/60:.1f} min)")
            logger.info(f"   Total puntos: {len(puntos)}")
            logger.info(f"🚶 ═══════════════════════════════════════")
            
            # PASO 6: Analizar predictibilidad si llegaste a un destino conocido
            if ubicacion_destino_id:
                logger.info(f"📊 Analizando predictibilidad para destino {ubicacion_destino_id}")
                self._analizar_predictibilidad_destino(usuario_id, ubicacion_destino_id)
            
        except Exception as e:
            logger.error(f"❌ Error finalizando viaje: {e}")
            import traceback
            traceback.print_exc()
            self.db.rollback()
    
    def _analizar_predictibilidad_destino(self, usuario_id: int, ubicacion_destino_id: int):
        """
        🔥 VERSIÓN PRODUCCIÓN: Sistema inteligente de notificaciones
        Detecta patrones reales sin importar irregularidades
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
                patron.fecha_actualizacion = datetime.utcnow()
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
            
            # 🔥 SISTEMA INTELIGENTE DE NOTIFICACIONES
            if es_predecible:
                debe_notificar, razon = self._debe_notificar_patron(
                    patron, 
                    viajes,
                    usuario_id,
                    ubicacion_destino_id
                )
                
                logger.info(f"📊 Decisión de notificación: {razon}")
                
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
                    patron.fecha_ultima_notificacion = datetime.utcnow()
                    self.db.commit()
                    logger.info(f"✅ Notificación enviada: {razon}")
            
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
        
        Casos manejados:
        1. Primera vez detectado
        2. Mismo día (máximo 1 notificación)
        3. Patrón frecuente (3+ viajes en 7 días)
        4. Cooldown de 7 días después de notificar
        5. Reset si no viaja en 14 días
        """
        
        ahora = datetime.utcnow()
        hoy = ahora.date()
        
        # ═══════════════════════════════════════════════════════
        # CASO 1: Primera vez detectado como predecible
        # ═══════════════════════════════════════════════════════
        if not patron.notificacion_enviada:
            return True, "🆕 Primera vez detectado como predecible"
        
        # ═══════════════════════════════════════════════════════
        # CASO 2: Ya notificamos HOY (evitar spam)
        # ═══════════════════════════════════════════════════════
        if patron.fecha_ultima_notificacion:
            ultimo_dia = patron.fecha_ultima_notificacion.date()
            
            if hoy == ultimo_dia:
                return False, f"⏭️ Ya se notificó hoy para este destino"
        
        # ═══════════════════════════════════════════════════════
        # CASO 3: Verificar cooldown de 7 días
        # ═══════════════════════════════════════════════════════
        if patron.fecha_ultima_notificacion:
            dias_desde_ultima = (ahora - patron.fecha_ultima_notificacion).days
            
            if dias_desde_ultima < 7:
                return False, f"⏳ Cooldown activo: {dias_desde_ultima}/7 días transcurridos"
        
        # ═══════════════════════════════════════════════════════
        # CASO 4: Analizar ventana de 7 días (patrón frecuente)
        # ═══════════════════════════════════════════════════════
        hace_7_dias = ahora - timedelta(days=7)
        
        viajes_ultimos_7_dias = [
            v for v in viajes 
            if v.fecha_inicio >= hace_7_dias
        ]
        
        # Contar días únicos en los que viajó
        dias_unicos = set(v.fecha_inicio.date() for v in viajes_ultimos_7_dias)
        cantidad_viajes_7d = len(viajes_ultimos_7_dias)
        
        logger.info(f"📊 Ventana 7 días:")
        logger.info(f"   Viajes: {cantidad_viajes_7d}")
        logger.info(f"   Días únicos: {len(dias_unicos)}")
        
        # 🔥 REGLA: Si hizo 3+ viajes en los últimos 7 días → Notificar
        if cantidad_viajes_7d >= 3:
            return True, f"🔥 Patrón frecuente: {cantidad_viajes_7d} viajes en {len(dias_unicos)} días (últimos 7 días)"
        
        # ═══════════════════════════════════════════════════════
        # CASO 5: Reset automático si no viaja hace 14+ días
        # ═══════════════════════════════════════════════════════
        if viajes_ultimos_7_dias:
            ultimo_viaje = max(viajes_ultimos_7_dias, key=lambda v: v.fecha_inicio)
            dias_sin_viajar = (ahora - ultimo_viaje.fecha_inicio).days
            
            if dias_sin_viajar >= 14:
                # Reset el patrón (como si fuera nuevo)
                logger.info(f"🔄 Reset automático: {dias_sin_viajar} días sin viajar")
                patron.notificacion_enviada = False
                patron.fecha_ultima_notificacion = None
                self.db.commit()
                return True, f"🔄 Patrón reactivado después de {dias_sin_viajar} días sin viajar"
        
        # ═══════════════════════════════════════════════════════
        # CASO 6: No cumple condiciones (esperar más datos)
        # ═══════════════════════════════════════════════════════
        return False, f"📊 Esperando más datos: {cantidad_viajes_7d}/3 viajes en ventana de 7 días"

    def _agrupar_trayectorias_similares(self, viajes: List[ViajeDetectado]) -> List[Dict]:
        """Agrupa viajes similares"""
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
        """
        Calcula similitud entre trayectorias COMPLETAS (incluyendo camino intermedio)
        """
        try:
            puntos1 = self._parsear_geometria(geometria1)
            puntos2 = self._parsear_geometria(geometria2)
            
            if not puntos1 or not puntos2:
                return 0.0
            
            # 1️⃣ Comparar origen y destino (como antes)
            dist_origen = self._calcular_distancia_haversine(
                puntos1[0][0], puntos1[0][1],
                puntos2[0][0], puntos2[0][1]
            )
            
            dist_destino = self._calcular_distancia_haversine(
                puntos1[-1][0], puntos1[-1][1],
                puntos2[-1][0], puntos2[-1][1]
            )
            
            # Si origen Y destino están cerca (< 50m)
            if dist_origen < 50 and dist_destino < 50:
                logger.info(f"   ✅ Origen/destino similares: origen={dist_origen:.1f}m, destino={dist_destino:.1f}m")
                similitud_base = 0.8
            else:
                similitud_base = 0.0
            
            # 2️⃣ 🔥 NUEVO: Comparar 5 puntos intermedios de la ruta
            distancias = []
            n_puntos = min(len(puntos1), len(puntos2), 5)  # Samplear 5 puntos
            
            if n_puntos > 2:
                # Obtener índices distribuidos uniformemente
                indices1 = [int(i * (len(puntos1) - 1) / (n_puntos - 1)) for i in range(n_puntos)]
                indices2 = [int(i * (len(puntos2) - 1) / (n_puntos - 1)) for i in range(n_puntos)]
                
                # Comparar cada punto intermedio
                for i1, i2 in zip(indices1, indices2):
                    dist = self._calcular_distancia_haversine(
                        puntos1[i1][0], puntos1[i1][1],
                        puntos2[i2][0], puntos2[i2][1]
                    )
                    distancias.append(dist)
                
                # Calcular similitud de la ruta completa
                # Si los puntos están a menos de 150m en promedio → ruta similar
                distancia_promedio = sum(distancias) / len(distancias)
                similitud_ruta = max(0.0, 1.0 - (distancia_promedio / 150.0))
                
                # 3️⃣ Combinar similitud de origen/destino CON similitud de ruta
                similitud_final = (similitud_base + similitud_ruta) / 2
                
                logger.info(f"   📏 Similitud final: {similitud_final*100:.1f}%")
                logger.info(f"      Origen/destino: {similitud_base*100:.0f}%")
                logger.info(f"      Ruta intermedia: {similitud_ruta*100:.0f}%")
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
        """Envía notificación FCM sugiriendo generar rutas alternas"""
        try:
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
            
            exitosos = 0
            fallidos = 0
            tokens_invalidos = []
            
            for token_obj in tokens_obj:
                try:
                    logger.info(f"📱 Enviando a token: {token_obj.token[:50]}...")
                    
                    # 🔥 CRÍTICO: Enviar SOLO data (sin notification)
                    # Esto garantiza que onMessageReceived() SIEMPRE se ejecute
                    message = messaging.Message(
                        # ❌ NO incluir notification - esto hace que el sistema lo maneje
                        # notification=messaging.Notification(...),  # ELIMINADO
                        
                        # ✅ SOLO data - así tu código siempre se ejecuta
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
                            # 🔥 CRÍTICO: ttl para asegurar entrega
                            ttl=3600  # 1 hora
                        )
                    )
                    
                    response = messaging.send(message)
                    exitosos += 1
                    logger.info(f"✅ Notificación enviada: {response}")
                    
                except messaging.UnregisteredError as e:
                    fallidos += 1
                    tokens_invalidos.append(token_obj.token)
                    logger.warning(f"⚠️ Token no registrado: {token_obj.token[:50]}...")
                    
                except Exception as e:
                    fallidos += 1
                    logger.error(f"❌ Error enviando a token {token_obj.token[:50]}...")
                    logger.error(f"   Error: {str(e)}")
            
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
    
    # Funciones auxiliares
    def _buscar_destino_cercano(self, usuario_id: int, lat: float, lon: float) -> Optional[int]:
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
                return destino.id
        
        return None
    
    def _simplificar_geometria(self, puntos: List[PuntoGPSRaw]) -> str:
        puntos_simplificados = puntos[::3]
        coords = [f"{p.latitud},{p.longitud}" for p in puntos_simplificados]
        return "|".join(coords)
    
    def _parsear_geometria(self, geometria: str) -> List[Tuple[float, float]]:
        try:
            puntos = []
            for coord in geometria.split('|'):
                lat, lon = coord.split(',')
                puntos.append((float(lat), float(lon)))
            return puntos
        except:
            return []
    
    def _calcular_hash_trayectoria(self, geometria: str) -> str:
        import hashlib
        return hashlib.md5(geometria.encode()).hexdigest()[:16]
    
    def _calcular_distancia_haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371000
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _calcular_distancia_total_ruta(self, puntos: List[PuntoGPSRaw]) -> float:
        if len(puntos) < 2:
            return 0.0
        
        distancia = 0.0
        for i in range(len(puntos) - 1):
            distancia += self._calcular_distancia_haversine(
                puntos[i].latitud, puntos[i].longitud,
                puntos[i+1].latitud, puntos[i+1].longitud
            )
        
        return distancia