import logging
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session
import math
from .models import ComportamientoRuta

logger = logging.getLogger(__name__)

def decodificar_polyline(polyline_str: str) -> List[Tuple[float, float]]:
    """
    Decodifica Google Polyline con mejor manejo de errores y caracteres especiales
    """
    try:
        if not polyline_str or len(polyline_str) < 3:
            logger.warning(f"Polyline muy corto: {polyline_str}")
            return []
        
        # IMPORTANTE: Limpiar caracteres especiales que pueden interferir
        # Remover pipes y espacios que no son parte del formato polyline
        polyline_clean = polyline_str.replace(' ', '')
        
        # Si contiene pipes en el medio (no es formato polyline puro)
        # intentar extraer solo la parte del polyline
        if '|' in polyline_clean:
            # Buscar el segmento más largo que parezca un polyline
            segments = polyline_clean.split('|')
            for segment in segments:
                if len(segment) > 10:  # Un polyline válido suele ser largo
                    polyline_clean = segment
                    break
        
        points = []
        index = 0
        lat = 0
        lng = 0
        
        while index < len(polyline_clean):
            # Decodificar latitud
            b = 0
            shift = 0
            result = 0
            
            while True:
                if index >= len(polyline_clean):
                    break
                try:
                    b = ord(polyline_clean[index]) - 63
                except (ValueError, IndexError):
                    index += 1
                    continue
                    
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            
            if index >= len(polyline_clean):
                break
                
            dlat = ~(result >> 1) if result & 1 else result >> 1
            lat += dlat
            
            # Decodificar longitud
            shift = 0
            result = 0
            
            while True:
                if index >= len(polyline_clean):
                    break
                try:
                    b = ord(polyline_clean[index]) - 63
                except (ValueError, IndexError):
                    index += 1
                    continue
                    
                index += 1
                result |= (b & 0x1f) << shift
                shift += 5
                if b < 0x20:
                    break
            
            if index > len(polyline_clean):
                break
                
            dlng = ~(result >> 1) if result & 1 else result >> 1
            lng += dlng
            
            # Convertir a coordenadas reales
            lat_real = lat / 1e5
            lng_real = lng / 1e5
            
            # Validar coordenadas razonables para Ecuador
            if -5 <= lat_real <= 2 and -82 <= lng_real <= -75:  # Límites aproximados de Ecuador
                points.append((lat_real, lng_real))
            else:
                logger.warning(f"Coordenada fuera de rango: ({lat_real}, {lng_real})")
        
        logger.info(f"Polyline decodificado: {len(points)} puntos válidos")
        return points
        
    except Exception as e:
        logger.error(f"Error decodificando polyline '{polyline_str[:20]}...': {e}")
        return []


class DetectorDesobedienciaService:
    def __init__(self, db: Session):
        self.db = db
        # AJUSTES PARA RUTAS CORTAS (< 1km)
        self.UMBRAL_SIMILITUD = 50.0  # Más permisivo para rutas cortas
        self.ALERTAR_DESPUES_DE = 3   # Requerir más desobediencias antes de alertar
        self.TOLERANCIA_DISTANCIA = 0.050  # 50 metros de tolerancia
        self.TOLERANCIA_RUTA_CORTA = 0.100  # 100 metros para rutas < 500m
        self.DISTANCIA_RUTA_DIFERENTE = 0.5  # 500m = zona diferente
    
    def analizar_comportamiento(self, usuario_id: int, ruta_id: int, 
                            ubicacion_id: int, ruta_recomendada: str, ruta_real: str, 
                            siguio_ruta_android: Optional[bool] = None,
                            porcentaje_android: Optional[float] = None) -> dict:
        """
        Analiza comportamiento con detección inteligente de rutas diferentes
        """
        logger.info(f"Analizando comportamiento - Usuario: {usuario_id}, Ruta: {ruta_id}")
        logger.info(f"DETECTOR recibió: siguio={siguio_ruta_android}, porcentaje={porcentaje_android}")

        # 1. Decidir si usar cálculo de Android o del backend
        if siguio_ruta_android is not None:
            siguio_recomendacion = siguio_ruta_android
            similitud = porcentaje_android if porcentaje_android is not None else (100.0 if siguio_ruta_android else 0.0)
            detalles = {"calculado_desde": "android", "resultado": siguio_ruta_android, "porcentaje_real": similitud}
            logger.info(f"Usando cálculo de Android: {siguio_ruta_android} ({similitud:.1f}%)")
        else:
            # Fallback al método original del backend
            logger.info(f"Geometría recomendada (primeros 50 chars): {ruta_recomendada[:50]}")
            logger.info(f"Geometría real (primeros 50 chars): {ruta_real[:50]}")
            
            similitud, detalles = self._calcular_similitud_rutas_mejorada(ruta_recomendada, ruta_real)
            siguio_recomendacion = similitud >= self.UMBRAL_SIMILITUD
            logger.info(f"Similitud calculada en backend: {similitud:.2f}% - Siguió ruta: {siguio_recomendacion}")
        
        logger.info(f"Detalles: {detalles}")
        
        # 2. Obtener historial previo
        comportamiento_previo = self._obtener_comportamiento_reciente_mejorado(usuario_id, ubicacion_id)

        # 3. Verificar si es ruta similar a las anteriores
        es_ruta_similar = self._es_ruta_similar_a_anteriores(
            ruta_recomendada, comportamiento_previo
        )
        
        logger.info(f"¿Es ruta similar a anteriores?: {es_ruta_similar}")
        
        # 4. Calcular desobediencias
        if es_ruta_similar:
            desobediencias_consecutivas = self._contar_desobediencias_consecutivas(comportamiento_previo)
            if not siguio_recomendacion:
                desobediencias_consecutivas += 1
        else:
            desobediencias_consecutivas = 1 if not siguio_recomendacion else 0
            logger.info("🔄 RESET contador - Ruta en zona diferente")
        
        logger.info(f"Desobediencias consecutivas: {desobediencias_consecutivas}")
        
        # 5. Evaluar alerta
        debe_alertar = (es_ruta_similar and 
                    desobediencias_consecutivas >= self.ALERTAR_DESPUES_DE and
                    not siguio_recomendacion)
        
        logger.info(f"Debe alertar: {debe_alertar} (es_similar: {es_ruta_similar}, desobediencias: {desobediencias_consecutivas}, umbral: {self.ALERTAR_DESPUES_DE})")
        
        # 6. Guardar comportamiento
        nuevo_comportamiento = ComportamientoRuta(
            usuario_id=usuario_id,
            ubicacion_id=ubicacion_id,
            ruta_id=ruta_id,
            ruta_recomendada_geometria=ruta_recomendada,
            ruta_real_geometria=ruta_real,
            siguio_recomendacion=siguio_recomendacion,
            porcentaje_similitud=round(similitud, 2),
            veces_desobedecido=desobediencias_consecutivas,
            alerta_mostrada=debe_alertar
        )
        
        try:
            self.db.add(nuevo_comportamiento)
            self.db.commit()
            logger.info(f"Comportamiento guardado - Desobediencias: {desobediencias_consecutivas}")
        except Exception as e:
            logger.error(f"Error guardando comportamiento: {e}")
            self.db.rollback()
        
        return {
            "debe_alertar": debe_alertar,
            "mensaje": self._generar_mensaje_alerta() if debe_alertar else None,
            "similitud": round(similitud, 2),
            "desobediencias_consecutivas": desobediencias_consecutivas,
            "es_ruta_similar": es_ruta_similar,
            "detalles_analisis": detalles
        }
    
    def _calcular_similitud_rutas_mejorada(self, ruta_recomendada: str, ruta_real: str) -> Tuple[float, dict]:
        """
        Calcula similitud con método mejorado para rutas cortas
        """
        try:
            if not ruta_recomendada or not ruta_real:
                return 0.0, {"error": "Rutas vacías"}
            
            puntos_recomendados = self._parsear_geometria(ruta_recomendada)
            puntos_reales = self._parsear_geometria(ruta_real)
            
            logger.info(f"Puntos - Recomendados: {len(puntos_recomendados)}, Reales: {len(puntos_reales)}")
            
            if not puntos_recomendados or not puntos_reales:
                return 0.0, {"error": "No se pudieron parsear las geometrías"}
            
            # Calcular distancia total de la ruta recomendada
            distancia_total_recomendada = self._calcular_distancia_total_ruta(puntos_recomendados)
            logger.info(f"Distancia total ruta recomendada: {distancia_total_recomendada:.3f} km")
            
            # Para rutas muy cortas (< 500m), usar algoritmo especial
            if distancia_total_recomendada < 0.5:
                return self._calcular_similitud_ruta_muy_corta(
                    puntos_recomendados, puntos_reales, distancia_total_recomendada
                )
            
            # Algoritmo normal mejorado
            puntos_coincidentes = 0
            distancias_minimas = []
            
            # Usar tolerancia adaptativa según longitud de ruta
            tolerancia = self.TOLERANCIA_RUTA_CORTA if distancia_total_recomendada < 1.0 else self.TOLERANCIA_DISTANCIA
            
            for punto_real in puntos_reales:
                distancia_minima = min(
                    self._calcular_distancia_haversine(punto_real, punto_rec)
                    for punto_rec in puntos_recomendados
                )
                distancias_minimas.append(distancia_minima)
                
                if distancia_minima <= tolerancia:
                    puntos_coincidentes += 1
            
            # Calcular similitud con peso adicional para inicio y fin
            similitud_base = (puntos_coincidentes / len(puntos_reales)) * 100
            
            # Bonus si inicio y fin coinciden
            dist_inicio = self._calcular_distancia_haversine(puntos_reales[0], puntos_recomendados[0])
            dist_fin = self._calcular_distancia_haversine(puntos_reales[-1], puntos_recomendados[-1])
            
            bonus = 0
            if dist_inicio <= tolerancia:
                bonus += 10
            if dist_fin <= tolerancia:
                bonus += 10
            
            similitud_final = min(100.0, similitud_base + bonus)
            
            detalles = {
                "puntos_coincidentes": puntos_coincidentes,
                "total_puntos_reales": len(puntos_reales),
                "distancia_promedio": sum(distancias_minimas) / len(distancias_minimas) if distancias_minimas else 0,
                "distancia_inicio": dist_inicio,
                "distancia_fin": dist_fin,
                "tolerancia_usada": tolerancia,
                "distancia_ruta": distancia_total_recomendada
            }
            
            return similitud_final, detalles
            
        except Exception as e:
            logger.error(f"Error calculando similitud: {e}")
            return 0.0, {"error": str(e)}
    
    def _calcular_similitud_ruta_muy_corta(self, puntos_recomendados: List[Tuple[float, float]], 
                                           puntos_reales: List[Tuple[float, float]],
                                           distancia_total: float) -> Tuple[float, dict]:
        """
        Algoritmo especial para rutas muy cortas (< 500m)
        """
        try:
            # Para rutas muy cortas, solo importa que inicio y fin estén cerca
            inicio_rec = puntos_recomendados[0]
            fin_rec = puntos_recomendados[-1]
            
            inicio_real = puntos_reales[0]
            fin_real = puntos_reales[-1]
            
            dist_inicio = self._calcular_distancia_haversine(inicio_rec, inicio_real)
            dist_fin = self._calcular_distancia_haversine(fin_rec, fin_real)
            
            # Tolerancia muy amplia para rutas cortas (150m)
            tolerancia_muy_amplia = 0.150
            
            # Si ambos puntos están dentro de la tolerancia, considerar 80% similar
            if dist_inicio <= tolerancia_muy_amplia and dist_fin <= tolerancia_muy_amplia:
                similitud = 80.0
            elif dist_inicio <= tolerancia_muy_amplia or dist_fin <= tolerancia_muy_amplia:
                similitud = 50.0
            else:
                # Calcular similitud basada en qué tan lejos están
                distancia_promedio = (dist_inicio + dist_fin) / 2
                if distancia_promedio <= 0.3:  # 300m
                    similitud = 30.0
                else:
                    similitud = 0.0
            
            detalles = {
                "tipo_analisis": "ruta_muy_corta",
                "distancia_total_km": distancia_total,
                "dist_inicio_km": dist_inicio,
                "dist_fin_km": dist_fin,
                "tolerancia_usada": tolerancia_muy_amplia
            }
            
            logger.info(f"Ruta muy corta ({distancia_total:.3f}km) - Similitud: {similitud}%")
            
            return similitud, detalles
            
        except Exception as e:
            logger.error(f"Error en similitud ruta muy corta: {e}")
            return 0.0, {"error": str(e)}
    
    def _calcular_distancia_total_ruta(self, puntos: List[Tuple[float, float]]) -> float:
        """Calcula la distancia total de una ruta sumando segmentos"""
        if len(puntos) < 2:
            return 0.0
        
        distancia_total = 0.0
        for i in range(len(puntos) - 1):
            distancia_total += self._calcular_distancia_haversine(puntos[i], puntos[i + 1])
        
        return distancia_total
    
    def _parsear_geometria(self, geometria: str) -> List[Tuple[float, float]]:
        """
        Parsea geometría con mejor detección de formato
        """
        try:
            if not geometria:
                return []
            
            # Formato 1: Coordenadas separadas por pipe (del móvil)
            if "|" in geometria and "," in geometria:
                puntos = []
                for punto_str in geometria.split('|'):
                    if ',' in punto_str:
                        partes = punto_str.strip().split(',')
                        if len(partes) >= 2:
                            try:
                                lat = float(partes[0])
                                lng = float(partes[1])
                                # Validar que estén en Ecuador
                                if -5 <= lat <= 2 and -82 <= lng <= -75:
                                    puntos.append((lat, lng))
                            except ValueError:
                                continue
                logger.info(f"Parseado formato pipe: {len(puntos)} puntos")
                return puntos
            
            # Formato 2: Google Polyline (OpenRouteService)
            # Un polyline válido normalmente no tiene pipes, comas ni espacios
            elif not (',' in geometria):
                logger.info(f"Intentando decodificar polyline...")
                puntos = decodificar_polyline(geometria)
                if puntos:
                    logger.info(f"Polyline decodificado: {len(puntos)} puntos")
                return puntos
            
            # Formato 3: Intentar otros formatos
            else:
                logger.warning(f"Formato no reconocido claramente: {geometria[:50]}")
                # Intentar primero como polyline
                puntos = decodificar_polyline(geometria)
                if puntos:
                    return puntos
                    
            return []
                
        except Exception as e:
            logger.error(f"Error parseando geometría: {e}")
            return []
    
    def _calcular_distancia_haversine(self, punto1: Tuple[float, float], punto2: Tuple[float, float]) -> float:
        """Calcula distancia GPS real en kilómetros"""
        try:
            lat1, lon1 = punto1
            lat2, lon2 = punto2
            
            R = 6371.0  # Radio de la Tierra en km
            
            lat1_rad = math.radians(lat1)
            lon1_rad = math.radians(lon1)
            lat2_rad = math.radians(lat2)
            lon2_rad = math.radians(lon2)
            
            dlat = lat2_rad - lat1_rad
            dlon = lon2_rad - lon1_rad
            
            a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(min(1, a)))  # min(1, a) para evitar errores de dominio
            
            return R * c
        except Exception as e:
            logger.error(f"Error calculando distancia: {e}")
            return float('inf')
    
    def _es_ruta_similar_a_anteriores(self, ruta_actual: str, comportamiento_previo) -> bool:
        """
        Determina si la ruta actual es similar a rutas anteriores (misma zona)
        """
        try:
            if not comportamiento_previo:
                return False
            
            puntos_actuales = self._parsear_geometria(ruta_actual)
            if not puntos_actuales:
                return False
            
            # Centro de la ruta actual
            inicio_actual = puntos_actuales[0]
            fin_actual = puntos_actuales[-1]
            
            # Comparar con últimas 3 rutas
            for comp in comportamiento_previo[:3]:
                if not comp.ruta_recomendada_geometria:
                    continue
                    
                puntos_anterior = self._parsear_geometria(comp.ruta_recomendada_geometria)
                if not puntos_anterior:
                    continue
                
                inicio_anterior = puntos_anterior[0]
                fin_anterior = puntos_anterior[-1]
                
                # Calcular distancias entre inicios y fines
                dist_inicios = self._calcular_distancia_haversine(inicio_actual, inicio_anterior)
                dist_fines = self._calcular_distancia_haversine(fin_actual, fin_anterior)
                
                logger.info(f"Comparando rutas - Dist inicios: {dist_inicios:.3f}km, Dist fines: {dist_fines:.3f}km")
                
                # Si inicio O fin están cerca, considerar zona similar
                if dist_inicios <= self.DISTANCIA_RUTA_DIFERENTE or dist_fines <= self.DISTANCIA_RUTA_DIFERENTE:
                    logger.info("Ruta en zona similar detectada")
                    return True
            
            logger.info("Ruta en zona diferente")
            return False
            
        except Exception as e:
            logger.error(f"Error evaluando similitud de rutas: {e}")
            return False
    
    def _obtener_comportamiento_reciente_mejorado(self, usuario_id: int, ubicacion_id: int):
        """
        Obtiene comportamientos recientes de la MISMA ubicación
        """
        try:
            return self.db.query(ComportamientoRuta)\
                .filter(
                    ComportamientoRuta.usuario_id == usuario_id,
                    ComportamientoRuta.ubicacion_id == ubicacion_id  # MISMO destino
                )\
                .order_by(ComportamientoRuta.fecha_creacion.desc())\
                .limit(5).all()
        except Exception as e:
            logger.error(f"Error obteniendo comportamiento: {e}")
            return []
    
    def _contar_desobediencias_consecutivas(self, comportamiento_previo) -> int:
        """Cuenta desobediencias consecutivas"""
        desobediencias = 0
        for comp in comportamiento_previo:
            if not comp.siguio_recomendacion:
                desobediencias += 1
            else:
                break
        return desobediencias
    
    def _generar_mensaje_alerta(self):
        """Mensaje de alerta personalizado"""
        mensajes = [
            "⚠️ Hemos detectado que frecuentemente usas rutas diferentes a las recomendadas. Por tu seguridad, considera seguir las rutas sugeridas.",
            "🔒 Para tu protección, te recomendamos variar tus rutas y seguir las recomendaciones de seguridad.",
            "📍 Notamos un patrón en tus rutas. Recuerda que alternando trayectos reduces riesgos."
        ]
        import random
        return random.choice(mensajes)


def convertir_puntos_gps_a_geometria(puntos_gps: List[dict]) -> str:
    """Convierte puntos GPS del móvil a formato interno"""
    try:
        if not puntos_gps:
            return ""
        
        coordenadas = []
        for punto in puntos_gps:
            lat, lng = None, None
            
            # Soportar diferentes formatos de punto GPS
            if 'lat' in punto and 'lng' in punto:
                lat, lng = punto['lat'], punto['lng']
            elif 'latitude' in punto and 'longitude' in punto:
                lat, lng = punto['latitude'], punto['longitude']
            elif 'lat' in punto and 'lon' in punto:
                lat, lng = punto['lat'], punto['lon']
            else:
                logger.warning(f"Punto GPS sin formato reconocido: {punto}")
                continue
            
            if lat is not None and lng is not None:
                try:
                    lat_f = float(lat)
                    lng_f = float(lng)
                    # Validar coordenadas para Ecuador
                    if -5 <= lat_f <= 2 and -82 <= lng_f <= -75:
                        coordenadas.append(f"{lat_f},{lng_f}")
                    else:
                        logger.warning(f"Coordenada fuera de Ecuador: ({lat_f}, {lng_f})")
                except (ValueError, TypeError) as e:
                    logger.error(f"Error convirtiendo coordenada: {e}")
                    continue
        
        resultado = "|".join(coordenadas) if coordenadas else ""
        logger.info(f"Convertidos {len(coordenadas)} puntos GPS a geometría")
        return resultado
        
    except Exception as e:
        logger.error(f"Error convirtiendo puntos GPS: {e}")
        return ""