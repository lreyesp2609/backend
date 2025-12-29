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
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════
# SERVICIO DE TRACKING PASIVO
# ══════════════════════════════════════════════════════════

class PassiveTrackingService:
    """
    📍 Servicio de tracking GPS pasivo
    """
    
    DISTANCIA_MINIMA_VIAJE = 200
    TIEMPO_MINIMO_VIAJE = 120
    RADIO_DESTINO_METROS = 100
    UMBRAL_SIMILITUD_TRAYECTORIA = 0.75
    MIN_VIAJES_ANALISIS = 5
    UMBRAL_PREDICTIBILIDAD = 0.70
    
    def __init__(self, db: Session):
        self.db = db
    
    def guardar_punto_gps(
        self,
        usuario_id: int,
        latitud: float,
        longitud: float,
        precision: Optional[float] = None,
        velocidad: Optional[float] = None
    ) -> bool:
        """Guarda un punto GPS"""
        try:
            punto = PuntoGPSRaw(
                usuario_id=usuario_id,
                latitud=latitud,
                longitud=longitud,
                timestamp=datetime.utcnow(),
                precision_metros=precision,
                velocidad=velocidad
            )
            
            self.db.add(punto)
            self.db.commit()
            
            self._intentar_detectar_viaje(usuario_id)
            return True
            
        except Exception as e:
            logger.error(f"Error guardando GPS: {e}")
            self.db.rollback()
            return False
    
    def _intentar_detectar_viaje(self, usuario_id: int):
        """Detecta si se completó un viaje"""
        try:
            hace_una_hora = datetime.utcnow() - timedelta(hours=1)
            
            puntos = self.db.query(PuntoGPSRaw).filter(
                PuntoGPSRaw.usuario_id == usuario_id,
                PuntoGPSRaw.timestamp >= hace_una_hora
            ).order_by(PuntoGPSRaw.timestamp).all()
            
            if len(puntos) < 3:
                return
            
            ultimos_3 = puntos[-3:]
            if self._esta_quieto(ultimos_3):
                self._finalizar_viaje_en_progreso(usuario_id, puntos)
                
        except Exception as e:
            logger.error(f"Error detectando viaje: {e}")
    
    def _esta_quieto(self, puntos: List[PuntoGPSRaw]) -> bool:
        """Verifica si está quieto"""
        if len(puntos) < 2:
            return False
        
        distancias = []
        for i in range(len(puntos) - 1):
            dist = self._calcular_distancia_haversine(
                puntos[i].latitud, puntos[i].longitud,
                puntos[i+1].latitud, puntos[i+1].longitud
            )
            distancias.append(dist)
        
        promedio = sum(distancias) / len(distancias)
        return promedio < 30
    
    def _finalizar_viaje_en_progreso(self, usuario_id: int, puntos: List[PuntoGPSRaw]):
        """Finaliza un viaje detectado"""
        try:
            if len(puntos) < 3:
                return
            
            punto_inicio = puntos[0]
            punto_fin = puntos[-1]
            
            distancia_total = self._calcular_distancia_total_ruta(puntos)
            
            if distancia_total < self.DISTANCIA_MINIMA_VIAJE:
                return
            
            duracion = (punto_fin.timestamp - punto_inicio.timestamp).total_seconds()
            
            if duracion < self.TIEMPO_MINIMO_VIAJE:
                return
            
            # Verificar si ya existe
            existente = self.db.query(ViajeDetectado).filter(
                ViajeDetectado.usuario_id == usuario_id,
                ViajeDetectado.fecha_inicio == punto_inicio.timestamp
            ).first()
            
            if existente:
                return
            
            # Buscar coincidencia con destinos
            ubicacion_origen_id = self._buscar_destino_cercano(
                usuario_id, punto_inicio.latitud, punto_inicio.longitud
            )
            
            ubicacion_destino_id = self._buscar_destino_cercano(
                usuario_id, punto_fin.latitud, punto_fin.longitud
            )
            
            geometria = self._simplificar_geometria(puntos)
            hash_trayectoria = self._calcular_hash_trayectoria(geometria)
            
            viaje = ViajeDetectado(
                usuario_id=usuario_id,
                ubicacion_origen_id=ubicacion_origen_id,
                ubicacion_destino_id=ubicacion_destino_id,
                lat_inicio=punto_inicio.latitud,
                lon_inicio=punto_inicio.longitud,
                lat_fin=punto_fin.latitud,
                lon_fin=punto_fin.longitud,
                fecha_inicio=punto_inicio.timestamp,
                fecha_fin=punto_fin.timestamp,
                geometria=geometria,
                distancia_metros=distancia_total,
                duracion_segundos=int(duracion),
                hash_trayectoria=hash_trayectoria
            )
            
            self.db.add(viaje)
            self.db.commit()
            self.db.refresh(viaje)
            
            logger.info(f"🚶 Viaje detectado: {distancia_total:.0f}m, {duracion:.0f}s")
            
            if ubicacion_destino_id:
                self._analizar_predictibilidad_destino(usuario_id, ubicacion_destino_id)
            
        except Exception as e:
            logger.error(f"Error finalizando viaje: {e}")
            self.db.rollback()
    
    def _analizar_predictibilidad_destino(self, usuario_id: int, ubicacion_destino_id: int):
        """Analiza predictibilidad"""
        try:
            viajes = self.db.query(ViajeDetectado).filter(
                ViajeDetectado.usuario_id == usuario_id,
                ViajeDetectado.ubicacion_destino_id == ubicacion_destino_id
            ).order_by(desc(ViajeDetectado.fecha_inicio)).all()
            
            if len(viajes) < self.MIN_VIAJES_ANALISIS:
                return
            
            viajes_recientes = viajes[:10]
            grupos_similares = self._agrupar_trayectorias_similares(viajes_recientes)
            grupo_mas_grande = max(grupos_similares, key=lambda g: len(g['viajes']))
            
            viajes_ruta_similar = len(grupo_mas_grande['viajes'])
            total_viajes = len(viajes_recientes)
            predictibilidad = viajes_ruta_similar / total_viajes
            es_predecible = predictibilidad >= self.UMBRAL_PREDICTIBILIDAD
            
            logger.info(f"📊 Predictibilidad: {predictibilidad*100:.1f}% ({viajes_ruta_similar}/{total_viajes})")
            
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
            
            if es_predecible and not patron.notificacion_enviada:
                self._enviar_notificacion_predictibilidad(usuario_id, ubicacion_destino_id, predictibilidad)
                patron.notificacion_enviada = True
                patron.fecha_ultima_notificacion = datetime.utcnow()
                self.db.commit()
            
        except Exception as e:
            logger.error(f"Error analizando predictibilidad: {e}")
            self.db.rollback()
    
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
        """Calcula similitud entre trayectorias"""
        try:
            puntos1 = self._parsear_geometria(geometria1)
            puntos2 = self._parsear_geometria(geometria2)
            
            if not puntos1 or not puntos2:
                return 0.0
            
            distancias = []
            n_puntos = min(len(puntos1), len(puntos2), 10)
            
            indices1 = [int(i * len(puntos1) / n_puntos) for i in range(n_puntos)]
            indices2 = [int(i * len(puntos2) / n_puntos) for i in range(n_puntos)]
            
            for i1, i2 in zip(indices1, indices2):
                dist = self._calcular_distancia_haversine(
                    puntos1[i1][0], puntos1[i1][1],
                    puntos2[i2][0], puntos2[i2][1]
                )
                distancias.append(dist)
            
            distancia_promedio = sum(distancias) / len(distancias)
            similitud = max(0.0, 1.0 - (distancia_promedio / 100.0))
            
            return similitud
            
        except Exception as e:
            logger.error(f"Error calculando similitud: {e}")
            return 0.0
    
    async def _enviar_notificacion_predictibilidad(
        self,
        usuario_id: int,
        ubicacion_destino_id: int,
        predictibilidad: float
    ):
        """Envía notificación FCM"""
        try:
            from app.usuarios.models import FCMToken
            from app.ubicaciones.models import UbicacionUsuario
            from app.services.fcm_service import fcm_service
            
            tokens_obj = self.db.query(FCMToken).filter(
                FCMToken.usuario_id == usuario_id
            ).all()
            
            if not tokens_obj:
                return
            
            tokens = [t.token for t in tokens_obj]
            
            destino = self.db.query(UbicacionUsuario).filter(
                UbicacionUsuario.id == ubicacion_destino_id
            ).first()
            
            nombre_destino = destino.nombre if destino else "ese destino"
            
            titulo = f"⚠️ Patrón detectado"
            mensaje = (f"Detectamos que siempre usas la misma ruta a {nombre_destino} "
                      f"({predictibilidad*100:.0f}% de las veces). "
                      f"Por seguridad, te sugerimos variar tus trayectos.")
            
            data = {
                "type": "patron_predictibilidad",
                "ubicacion_destino_id": str(ubicacion_destino_id),
                "predictibilidad": str(round(predictibilidad * 100, 1))
            }
            
            resultado = await fcm_service.enviar_a_multiples(
                tokens=tokens,
                titulo=titulo,
                cuerpo=mensaje,
                data=data
            )
            
            logger.warning(f"⚠️ PREDICTIBILIDAD: Usuario {usuario_id}, {predictibilidad*100:.1f}%")
            
        except Exception as e:
            logger.error(f"Error enviando notificación: {e}")
    
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